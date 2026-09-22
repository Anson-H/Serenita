"""File adapters. Parsing and validation never invoke an action model."""

import csv
import hashlib
import io
import json
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import PurePosixPath
from backend.app.schemas.body_metric import BodyRecord, instant

MAX_UPLOAD = 64 * 1024 * 1024
MAX_EXPANDED = 256 * 1024 * 1024
MAX_RECORDS = 250000
APPLE = {
    "Height": ("height", "cm"),
    "BodyMass": ("weight", "kg"),
    "BodyMassIndex": ("bmi", "kg/m²"),
    "WaistCircumference": ("waist", "cm"),
    "BodyFatPercentage": ("body_fat", "%"),
    "HeartRate": ("heart_rate", "次/分"),
    "RestingHeartRate": ("resting_heart_rate", "次/分"),
    "HeartRateVariabilitySDNN": ("hrv", "ms"),
    "OxygenSaturation": ("blood_oxygen", "%"),
    "BloodGlucose": ("blood_glucose", "mmol/L"),
    "BodyTemperature": ("temperature", "°C"),
    "StepCount": ("steps", "步"),
    "ActiveEnergyBurned": ("active_energy", "kcal"),
    "AppleExerciseTime": ("exercise_minutes", "min"),
}
NUTRIENTS = {
    "DietaryEnergyConsumed": "energy",
    "DietaryCarbohydrates": "carbohydrate",
    "DietaryProtein": "protein",
    "DietaryFatTotal": "fat",
}
STAGE_MAP = {
    "0": "in_bed",
    "1": "unknown",
    "2": "awake",
    "3": "light",
    "4": "deep",
    "5": "rem",
    "HKCategoryValueSleepAnalysisInBed": "in_bed",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "unknown",
    "HKCategoryValueSleepAnalysisAwake": "awake",
    "HKCategoryValueSleepAnalysisAsleepCore": "light",
    "HKCategoryValueSleepAnalysisAsleepDeep": "deep",
    "HKCategoryValueSleepAnalysisAsleepREM": "rem",
}


def apple(stream):
    sleeps = defaultdict(list)
    nutrients = defaultdict(dict)
    pressure = defaultdict(dict)
    originals = defaultdict(list)

    # Apple includes a DTD. Reject entities but allow its internal element declarations.
    class CheckedReader:
        def __init__(self, f):
            self.f = f
            self.tail = b""

        def read(self, n=-1):
            chunk = self.f.read(n)
            scanned = (self.tail + chunk).upper()
            if b"<!ENTITY" in scanned or b"SYSTEM " in scanned or b"PUBLIC " in scanned:
                raise ValueError("XML 不接受外部实体或外部文档声明。")
            self.tail = scanned[-100:]
            return chunk

    raw_count = 0
    for event, element in ET.iterparse(CheckedReader(stream), events=("end",)):
        if element.tag not in ("Record", "Workout"):
            continue
        raw_count += 1
        if raw_count > MAX_RECORDS:
            raise ValueError("单次苹果导入超过 250000 条，请缩小范围。")
        a = dict(element.attrib)
        source = a.get("sourceName", "Apple Health")
        device = a.get("device", "")[:200]
        try:
            start = instant(a["startDate"]).isoformat()
            end = instant(a["endDate"]).isoformat()
            base = {
                "source": source,
                "device": device,
                "origin": "apple_health",
                "starts_at": start,
                "ends_at": end if end != start else None,
                "precision": "interval" if end != start else "instant",
                "_source_payload": a,
            }
            typ = (
                a.get("type", "")
                .removeprefix("HKQuantityTypeIdentifier")
                .removeprefix("HKCategoryTypeIdentifier")
            )
            base["external_id"] = hashlib.sha256(
                json.dumps(
                    [element.tag, typ, source, device, start, end], ensure_ascii=False
                ).encode()
            ).hexdigest()
            if element.tag == "Workout":
                duration = float(a.get("duration", 0))
                duration_unit = a.get("durationUnit", "min")
                if duration_unit == "s":
                    duration /= 60
                base.update(
                    kind="workout",
                    data={
                        "activity": a.get("workoutActivityType", "运动").removeprefix(
                            "HKWorkoutActivityType"
                        ),
                        "duration_minutes": duration,
                        "distance_km": float(a["totalDistance"])
                        if a.get("totalDistanceUnit") == "km"
                        else None,
                        "energy": float(a["totalEnergyBurned"])
                        if a.get("totalEnergyBurnedUnit") == "kcal"
                        else None,
                    },
                )
                yield base
            elif typ == "SleepAnalysis":
                stage = STAGE_MAP.get(a.get("value"), "unknown")
                sleeps[(source, device)].append(
                    {**base, "stage": stage, "original_stage": a.get("value", "")}
                )
            elif typ in NUTRIENTS:
                group = nutrients[(source, device, start, end)]
                key = NUTRIENTS[typ]
                originals[("meal", source, device, start, end)].append(a)
                value = float(a["value"])
                unit = a.get("unit", "")
                if key == "energy" and unit == "kJ":
                    value /= 4.184
                elif unit not in ("kcal", "g"):
                    raise ValueError("无法换算饮食单位。")
                group[key] = group.get(key, 0) + value
            elif typ in ("BloodPressureSystolic", "BloodPressureDiastolic"):
                if a.get("unit") != "mmHg":
                    raise ValueError("无法换算血压单位。")
                pressure[(source, device, start, end)][typ] = float(a["value"])
                originals[("blood_pressure", source, device, start, end)].append(a)
            elif typ == "AppleStandHour":
                yield {
                    **base,
                    "kind": "measurement",
                    "metric": "stand_hours",
                    "data": {
                        "value": 1
                        if a.get("value") in ("HKCategoryValueAppleStandHourStood", "0")
                        else 0,
                        "unit": "小时",
                    },
                }
            elif typ in APPLE:
                metric, unit = APPLE[typ]
                value = float(a["value"])
                original_unit = a.get("unit", "")
                unit_alias = {
                    "count/min": "次/分",
                    "count": "步",
                    "degC": "°C",
                    "kg/m^2": "kg/m²",
                }
                if original_unit == "%" and metric in ("body_fat", "blood_oxygen"):
                    value *= 100
                elif metric == "bmi" and original_unit == "count":
                    pass
                elif metric in ("height", "waist") and original_unit == "m":
                    value *= 100
                elif metric == "hrv" and original_unit == "s":
                    value *= 1000
                elif original_unit not in (unit,):
                    unit = unit_alias.get(original_unit, original_unit)
                yield {
                    **base,
                    "kind": "measurement",
                    "metric": metric,
                    "data": {
                        "value": value,
                        "unit": unit,
                        "method": "SDNN" if metric == "hrv" else "",
                        "basis": f"Apple Health 原值 {a['value']} {original_unit}",
                    },
                }
            else:
                yield {"_unsupported": a.get("type", element.tag)}
        except (ValueError, KeyError) as exc:
            yield {"_error": str(exc)}
        element.clear()
    for (source, device, start, end), data in nutrients.items():
        yield {
            "_source_payload": originals[("meal", source, device, start, end)],
            "kind": "meal",
            "starts_at": start,
            "ends_at": end if end != start else None,
            "source": source,
            "device": device,
            "origin": "apple_health",
            "external_id": hashlib.sha256(
                json.dumps(["meal", source, device, start, end]).encode()
            ).hexdigest(),
            "data": {**data, "basis": "Apple Health 营养记录；餐次待补充"},
        }
    for (source, device, start, end), data in pressure.items():
        if len(data) != 2:
            yield {"_error": "血压记录缺少成对收缩压或舒张压。"}
            continue
        yield {
            "_source_payload": originals[
                ("blood_pressure", source, device, start, end)
            ],
            "kind": "measurement",
            "metric": "blood_pressure",
            "starts_at": start,
            "source": source,
            "device": device,
            "origin": "apple_health",
            "external_id": hashlib.sha256(
                json.dumps(["blood_pressure", source, device, start, end]).encode()
            ).hexdigest(),
            "data": {
                "value": data["BloodPressureSystolic"],
                "secondary_value": data["BloodPressureDiastolic"],
                "unit": "mmHg",
            },
        }
    for (source, device), segments in sleeps.items():
        # Detailed stages replace a containing in-bed/unspecified summary, never double count it.
        detailed = [s for s in segments if s["stage"] not in ("in_bed", "unknown")]
        segments = [
            s
            for s in segments
            if s["stage"] not in ("in_bed", "unknown")
            or not any(
                instant(d["starts_at"]) >= instant(s["starts_at"])
                and instant(d["ends_at"]) <= instant(s["ends_at"])
                for d in detailed
            )
        ]
        unique = {json.dumps(s, sort_keys=True): s for s in segments}
        sessions = []
        for s in sorted(unique.values(), key=lambda s: instant(s["starts_at"])):
            if not sessions or instant(s["starts_at"]) > max(
                instant(x["ends_at"]) for x in sessions[-1]
            ) + timedelta(hours=3):
                sessions.append([])
            sessions[-1].append(s)
        for parts in sessions:
            yield {
                "_source_payload": [part["_source_payload"] for part in parts],
                "kind": "sleep",
                "source": source,
                "device": device,
                "origin": "apple_health",
                "external_id": hashlib.sha256(
                    json.dumps(
                        ["sleep", source, device, parts[0]["starts_at"]]
                    ).encode()
                ).hexdigest(),
                "starts_at": parts[0]["starts_at"],
                "ends_at": max(parts, key=lambda s: instant(s["ends_at"]))["ends_at"],
                "precision": "interval",
                "data": {
                    "stages": [
                        {
                            "stage_id": hashlib.sha256(
                                json.dumps(s, sort_keys=True).encode()
                            ).hexdigest()[:24],
                            "stage": s["stage"],
                            "starts_at": s["starts_at"],
                            "ends_at": s["ends_at"],
                            "original_stage": s["original_stage"],
                        }
                        for s in parts
                    ]
                },
            }


CSV_FIELDS = [
    "row_type",
    "external_id",
    "parent_id",
    "kind",
    "metric",
    "starts_at",
    "ends_at",
    "timezone",
    "precision",
    "source",
    "device",
    "origin",
    "notes",
    "data",
]


def csv_records(content):
    rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    parents = {}
    children = []
    for row in rows:
        typ = row.pop("row_type", "record") or "record"
        parent = row.pop("parent_id", "")
        value = {k: v for k, v in row.items() if v != ""}
        if None in value:
            raise ValueError("CSV 行列数量不一致。")
        value["data"] = json.loads(value.get("data", "{}"))
        if typ in ("food", "stage"):
            children.append((typ, parent, value))
            continue
        if typ != "record":
            raise ValueError("CSV row_type 必须为 record、food 或 stage。")
        key = value.get("external_id")
        if not key or key in parents:
            raise ValueError("CSV 主记录须有唯一 external_id。")
        parents[key] = value
    for typ, parent, value in children:
        if parent not in parents:
            raise ValueError("CSV 明细缺少对应主记录。")
        key = "foods" if typ == "food" else "stages"
        child = value["data"]
        child[typ + "_id"] = value["external_id"]
        parents[parent]["data"].setdefault(key, []).append(child)
    return parents.values()


def parse_file(filename, content):
    if len(content) > MAX_UPLOAD:
        raise ValueError("文件超过 64 MiB。")
    suffix = PurePosixPath(filename.lower()).suffix
    if suffix == ".zip":
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            entries = z.infolist()
            if len(entries) > 10000 or sum(e.file_size for e in entries) > MAX_EXPANDED:
                raise ValueError("解压内容超过 256 MiB 或文件数过多。")
            for e in entries:
                path = PurePosixPath(e.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("压缩包路径不合法。")
            matches = [
                e for e in entries if PurePosixPath(e.filename).name == "export.xml"
            ]
            if len(matches) != 1:
                raise ValueError(
                    "仅支持包含唯一 export.xml 的苹果健康压缩包。安卓请使用标准 CSV/JSON。"
                )
            with z.open(matches[0]) as stream:
                return validate(apple(stream))
    if suffix == ".xml":
        return validate(apple(io.BytesIO(content)))
    if suffix == ".json":
        obj = json.loads(content)
        if (
            not isinstance(obj, dict)
            or obj.get("format") != "serenita-body-metrics"
            or not isinstance(obj.get("records"), list)
        ):
            raise ValueError(
                "JSON 必须包含 format=serenita-body-metrics 和 records 数组。"
            )
        return validate(obj["records"])
    if suffix == ".csv":
        return validate(csv_records(content))
    raise ValueError("请选择 XML、ZIP、CSV 或 JSON 文件。")


def validate(values):
    records = []
    issues = []
    counts = Counter()
    total = 0
    for i, value in enumerate(values, 1):
        total = i
        if i > MAX_RECORDS:
            raise ValueError("单次导入超过 250000 条，请缩小日期范围。")
        try:
            if not isinstance(value, dict):
                raise ValueError("记录必须是 JSON 对象。")
            if "_unsupported" in value:
                counts[value["_unsupported"]] += 1
                continue
            if "_error" in value:
                raise ValueError(value["_error"])
            source_payload = value.get("_source_payload", value)
            normalized = BodyRecord.model_validate(
                {key: item for key, item in value.items() if key != "_source_payload"}
            ).model_dump()
            records.append({**normalized, "_source_payload": source_payload})
        except (ValueError, TypeError, KeyError) as exc:
            if len(issues) < 100:
                issues.append({"row": i, "message": str(exc)[:500]})
            counts["invalid"] += 1
    return {
        "records": records,
        "issues": issues,
        "unsupported": dict(counts),
        "input_count": total,
        "valid_count": len(records),
    }
