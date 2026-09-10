"""Record identity, edits and date predicates without storage dependencies."""

from backend.app.core.values import digest
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from backend.app.schemas.body_metric import BodyRecord, CATALOG


def identity(record):
    if record.get("external_id"):
        return digest(
            [
                record[key]
                for key in (
                    "origin",
                    "source",
                    "device",
                    "kind",
                    "metric",
                    "external_id",
                )
            ]
        )
    return digest(
        {key: value for key, value in record.items() if key in BodyRecord.model_fields}
    )


def updated_record(old, changes):
    allowed = {
        "metric",
        "starts_at",
        "ends_at",
        "timezone",
        "precision",
        "notes",
        "data",
    }
    if not changes or set(changes) - allowed:
        raise ValueError("更新仅接受业务内容与时间，来源身份不可更新。")
    base = {key: value for key, value in old.items() if key in BodyRecord.model_fields}
    if "data" in changes:
        if not isinstance(changes["data"], dict):
            raise ValueError("data 必须为对象。")
        changes = {**changes, "data": {**base["data"], **changes["data"]}}
    value = BodyRecord.model_validate({**base, **changes}).model_dump()
    if base["kind"] == "sleep":
        sleep_changed = any(
            base[key] != value[key] for key in ("starts_at", "ends_at")
        ) or any(
            base["data"].get(key) != value["data"].get(key)
            for key in ("stages", "duration_minutes")
        )
        score_changed = any(
            base["data"].get(key) != value["data"].get(key)
            for key in ("score", "score_max", "score_basis")
        )
        value["data"]["score_stale"] = bool(
            value["data"]["score"] is not None
            and (
                sleep_changed
                or (
                    base["data"]["score_stale"]
                    and not (score_changed and value["data"]["score_basis"])
                )
            )
        )
    return value, value != base


@dataclass(frozen=True)
class RecordFilter:
    after: str | None = None
    before: str | None = None
    category: str | None = None
    source: str | None = None
    timezone: str = "Asia/Shanghai"

    def __post_init__(self):
        ZoneInfo(self.timezone)
        for value in (self.after, self.before):
            if value and date.fromisoformat(value).isoformat() != value:
                raise ValueError("日期必须为 YYYY-MM-DD。")
        if self.after and self.before and self.after > self.before:
            raise ValueError("结束日期不能早于开始日期。")
        if self.category and self.category not in {
            m["category"] for m in CATALOG.values()
        } | {"nutrition", "sleep", "workouts"}:
            raise ValueError("未知身体指标分类。")

    def sql(self, member):
        clauses, values = ["member_id=?"], [member]
        if self.source:
            clauses.append("source=?")
            values.append(self.source)
        if self.category:
            kinds = {"nutrition": "meal", "sleep": "sleep", "workouts": "workout"}
            if self.category in kinds:
                clauses.append("kind=?")
                values.append(kinds[self.category])
            else:
                metrics = [
                    m["metric"]
                    for m in CATALOG.values()
                    if m["category"] == self.category
                ]
                clauses.append("metric IN (" + ",".join("?" for _ in metrics) + ")")
                values.extend(metrics)
        sums = ",".join(
            "'" + m["metric"] + "'"
            for m in CATALOG.values()
            if m["aggregation"] == "sum"
        )
        zone = ZoneInfo(self.timezone)
        if self.after:
            lower = (
                datetime.combine(date.fromisoformat(self.after), time.min, zone)
                .astimezone(timezone.utc)
                .isoformat(timespec="microseconds")
            )
            clauses.append(
                f"((kind='sleep' AND ends_at>=?) OR (kind='measurement' AND metric IN ({sums}) AND ends_at IS NOT NULL AND ends_at>?) OR (kind!='sleep' AND starts_at>=?))"
            )
            values.extend([lower] * 3)
        if self.before:
            upper = (
                datetime.combine(
                    date.fromisoformat(self.before) + timedelta(days=1), time.min, zone
                )
                .astimezone(timezone.utc)
                .isoformat(timespec="microseconds")
            )
            clauses.append("CASE WHEN kind='sleep' THEN ends_at ELSE starts_at END < ?")
            values.append(upper)
        return " AND ".join(clauses), values
