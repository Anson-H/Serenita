"""Time and status calculations independent of storage."""

from datetime import datetime, timezone
from backend.app.schemas.medication import instant, end_instant


def medication_name(identity):
    return " ".join(dict.fromkeys(
        value for value in (identity.get("brand_name"), identity.get("generic_name")) if value
    ))


def plan_status(plan, at=None):
    at = at or datetime.now(timezone.utc)
    start, end = instant(plan["starts_at"]), end_instant(plan["ends_at"])
    if start > at:
        return "upcoming", plan["usage_status"]
    if (end is not None and end <= at) or plan["usage_status"] in ("stopped", "completed"):
        return "ended", plan["usage_status"]
    return "ongoing", plan["usage_status"]


def matches_date(plan, filters):
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    if filters.get("undated"):
        return False
    lower, upper = filters.get("after_date"), filters.get("before_date")
    zone = ZoneInfo(plan["timezone"])
    lo = datetime.fromisoformat(lower).replace(tzinfo=zone) if lower else None
    hi = datetime.fromisoformat(upper).replace(tzinfo=zone) + timedelta(days=1) if upper else None
    end = end_instant(plan["ends_at"])
    return (hi is None or instant(plan["starts_at"]) < hi) and (lo is None or end is None or end > lo)
