"""Deterministic, source-specific statistics over saved records."""

from collections import defaultdict
from datetime import datetime, timedelta, time, timezone as utc_timezone
from zoneinfo import ZoneInfo
from backend.app.schemas.body_metric import CATALOG, instant
from backend.app.core.values import digest


def category(r):
    return (
        CATALOG[r["metric"]]["category"]
        if r["kind"] == "measurement"
        else {"meal": "nutrition", "sleep": "sleep", "workout": "workouts"}[r["kind"]]
    )


def record_date(r, zone):
    return (
        instant(r["ends_at"] if r["kind"] == "sleep" else r["starts_at"])
        .astimezone(zone)
        .date()
        .isoformat()
    )


def select(
    records,
    after=None,
    before=None,
    category_filter=None,
    source=None,
    timezone="Asia/Shanghai",
):
    zone = ZoneInfo(timezone)
    if after:
        datetime.strptime(after, "%Y-%m-%d")
    if before:
        datetime.strptime(before, "%Y-%m-%d")
    if after and before and before < after:
        raise ValueError("结束日期不能早于开始日期。")

    def matches(r):
        first = record_date(r, zone)
        last = first
        if (
            r["kind"] == "measurement"
            and CATALOG[r["metric"]]["aggregation"] == "sum"
            and r["ends_at"]
        ):
            last = (
                (instant(r["ends_at"]) - timedelta(microseconds=1))
                .astimezone(zone)
                .date()
                .isoformat()
            )
        return (
            (not after or last >= after)
            and (not before or first <= before)
            and (not category_filter or category(r) == category_filter)
            and (not source or r["source"] == source)
        )

    return [r for r in records if matches(r)]


SERIES_FIELDS = {
    "meal": {
        "energy": "energy",
        "carbohydrate": "carbohydrate",
        "protein": "protein",
        "fat": "fat",
    },
    "sleep": {"sleep_minutes": "duration_minutes", "sleep_score": "score"},
    "workout": {"workout_minutes": "duration_minutes"},
}


def series_key(metric, source, device, data, *, measurement=False):
    unit = (
        data.get("unit", "")
        if measurement
        else (
            "kcal"
            if metric == "energy"
            else "g"
            if metric in ("carbohydrate", "protein", "fat")
            else "分"
            if metric == "sleep_score"
            else "min"
        )
    )
    return (
        metric,
        source,
        device,
        data.get("method", "") if measurement else "",
        unit,
        data.get("score_max") if metric == "sleep_score" else None,
    )


def record_values(record):
    data = record["data"]
    values = (
        {record["metric"]: data["value"]}
        if record["kind"] == "measurement"
        else {
            metric: data.get(field)
            for metric, field in SERIES_FIELDS[record["kind"]].items()
        }
    )
    if data.get("score_stale"):
        values.pop("sleep_score", None)
    return values


def original_point(record, value, zone):
    return {
        "value": value,
        "secondary_value": record["data"].get("secondary_value"),
        "date": record_date(record, zone),
        "starts_at": record["starts_at"],
        "ends_at": record["ends_at"],
        "precision": record["precision"],
        "record_id": record["record_id"],
        "allocated": False,
    }


def stats(records, timezone="Asia/Shanghai", after=None, before=None):
    zone = ZoneInfo(timezone)
    series = defaultdict(list)
    originals = defaultdict(list)
    for r in records:
        d = r["data"]
        for metric, value in record_values(r).items():
            if value is None:
                continue
            key = series_key(
                metric,
                r["source"],
                r["device"],
                d,
                measurement=r["kind"] == "measurement",
            )
            point = original_point(r, value, zone)
            originals[key].append(point)
            if (
                r["kind"] == "measurement"
                and CATALOG[metric]["aggregation"] == "sum"
                and r["ends_at"]
            ):
                start = instant(r["starts_at"]).astimezone(utc_timezone.utc)
                end = instant(r["ends_at"]).astimezone(utc_timezone.utc)
                cursor = start
                while cursor < end:
                    local = cursor.astimezone(zone)
                    boundary = datetime.combine(
                        local.date() + timedelta(days=1), time.min, zone
                    )
                    stop = min(end, boundary.astimezone(utc_timezone.utc))
                    day = local.date().isoformat()
                    if (not after or day >= after) and (not before or day <= before):
                        allocated = cursor != start or stop != end
                        series[key].append(
                            {
                                **point,
                                "date": day,
                                "starts_at": cursor.isoformat(),
                                "ends_at": stop.isoformat(),
                                "value": value
                                * (stop - cursor).total_seconds()
                                / (end - start).total_seconds(),
                                "allocated": allocated,
                            }
                        )
                    cursor = stop
            else:
                series[key].append(point)
    output = []
    for (metric, source, device, method, unit, score_max), points in series.items():
        agg = CATALOG.get(metric, {}).get(
            "aggregation", "mean" if metric == "sleep_score" else "sum"
        )
        points.sort(key=lambda p: instant(p["starts_at"]))
        days = defaultdict(list)
        for p in points:
            days[p["date"]].append(p)
        buckets = []
        omitted = set()
        for date, items in sorted(days.items()):
            # Explicit day totals are authoritative within this source/day.
            if agg == "sum":
                totals = [p for p in items if p["precision"] == "day"]
                if totals:
                    omitted.update(p["record_id"] for p in items if p is not totals[-1])
                    items = [totals[-1]]
                else:
                    clean = []
                    previous_end = None
                    for p in items:
                        a = instant(p["starts_at"])
                        b = instant(p["ends_at"]) if p["ends_at"] else a
                        if previous_end is not None and a < previous_end:
                            omitted.add(p["record_id"])
                            continue
                        clean.append(p)
                        previous_end = b
                    items = clean
            values = [p["value"] for p in items]
            value = (
                sum(values)
                if agg == "sum"
                else values[-1]
                if agg == "latest"
                else sum(values) / len(values)
            )
            buckets.append(
                {
                    "date": date,
                    "value": round(value, 4),
                    "minimum": min(values),
                    "maximum": max(values),
                    "count": len(values),
                    "record_ids": [p["record_id"] for p in items],
                    "secondary_value": round(
                        sum(p["secondary_value"] for p in items) / len(items), 4
                    )
                    if all(p["secondary_value"] is not None for p in items)
                    else None,
                }
            )
        raw_points = sorted(
            originals[(metric, source, device, method, unit, score_max)],
            key=lambda p: (instant(p["starts_at"]), p["record_id"]),
        )
        values = [p["value"] for p in raw_points]
        seconds = [
            p["secondary_value"] for p in raw_points if p["secondary_value"] is not None
        ]
        output.append(
            {
                "series_id": digest([metric, source, device, method, unit, score_max]),
                "metric": metric,
                "label": CATALOG.get(metric, {}).get(
                    "label",
                    {
                        "energy": "摄入能量",
                        "carbohydrate": "碳水化合物",
                        "protein": "蛋白质",
                        "fat": "脂肪",
                        "sleep_minutes": "睡眠时长",
                        "sleep_score": "睡眠评分",
                        "workout_minutes": "运动时长",
                    }.get(metric, metric),
                ),
                "source": source,
                "device": device,
                "method": method,
                "unit": unit,
                "score_max": score_max,
                "aggregation": agg,
                "count": len(raw_points),
                "days": len(buckets),
                "latest": values[-1],
                "minimum": min(values),
                "maximum": max(values),
                "mean": round(sum(values) / len(values), 4),
                "secondary_mean": round(sum(seconds) / len(seconds), 2)
                if seconds
                else None,
                "total": round(sum(b["value"] for b in buckets), 4)
                if agg == "sum"
                else None,
                "daily_mean": round(sum(b["value"] for b in buckets) / len(buckets), 4),
                "omitted_overlaps": len(omitted),
                "allocated_intervals": len(
                    {p["record_id"] for p in points if p["allocated"]}
                ),
                "buckets": buckets,
                "points": raw_points,
            }
        )
    return output
