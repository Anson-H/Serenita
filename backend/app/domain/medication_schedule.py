"""Deterministic execution of explicitly saved time rules, with DST handling."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from backend.app.schemas.medication import instant, end_instant

UTC = timezone.utc


def local_instant(day, clock, zone):
    naive = datetime.fromisoformat(f"{day.isoformat()}T{clock}")
    # Resolve nonexistent wall times by advancing to the first valid minute.
    for _ in range(181):
        aware = naive.replace(tzinfo=zone, fold=0)
        if aware.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == naive:
            return aware.astimezone(UTC)
        naive += timedelta(minutes=1)
    raise ValueError("无法解析该时区的用药时间。")


def schedulable(plan):
    schedule = plan.get("schedule")
    return bool(
        plan.get("starts_at")
        and schedule
        and plan["usage_status"] not in ("paused", "stopped", "completed")
        and schedule.get("times")
    )


def first_occurrence(plan, after, until):
    """Find a missed occurrence without walking an unbounded historical range."""
    if not schedulable(plan):
        return None
    schedule, zone = plan["schedule"], ZoneInfo(plan["timezone"])
    start, end = instant(plan["starts_at"]), end_instant(plan["ends_at"])
    after = max(after, start - timedelta(microseconds=1))
    if end is not None:
        until = min(until, end - timedelta(microseconds=1))
    if until <= after:
        return None
    day, last = after.astimezone(zone).date(), until.astimezone(zone).date()
    # The first eligible day may have only times earlier than the lower bound.
    for _ in range(2):
        gap = 0
        if schedule["kind"] == "weekly":
            gap = min(
                (weekday - day.isoweekday()) % 7 for weekday in schedule["weekdays"]
            )
        elif schedule["kind"] == "every_n_days":
            anchor = datetime.fromisoformat(schedule["anchor_date"]).date()
            gap = (
                (anchor - day).days
                if day < anchor
                else (-(day - anchor).days) % schedule["interval_days"]
            )
        if gap > (last - day).days:
            return None
        candidate = day + timedelta(days=gap)
        for item in sorted(schedule["times"], key=lambda item: item["time"]):
            value = local_instant(candidate, item["time"], zone)
            if after < value <= until and value >= start:
                return value
        if candidate >= last:
            return None
        day = candidate + timedelta(days=1)
    return None


def occurrences(plan, after, until):
    if not schedulable(plan):
        return []
    schedule, zone = plan["schedule"], ZoneInfo(plan["timezone"])
    start = instant(plan["starts_at"])
    end = end_instant(plan["ends_at"])
    after = max(after, start - timedelta(microseconds=1))
    if until <= after:
        return []
    results = {}
    day = after.astimezone(zone).date()
    last = until.astimezone(zone).date()
    while day <= last:
        allowed = schedule["kind"] == "daily" or (
            schedule["kind"] == "weekly" and day.isoweekday() in schedule["weekdays"]
        )
        if schedule["kind"] == "every_n_days":
            offset = (day - datetime.fromisoformat(schedule["anchor_date"]).date()).days
            allowed = offset >= 0 and offset % schedule["interval_days"] == 0
        if allowed:
            for item in schedule["times"]:
                value = local_instant(day, item["time"], zone)
                if (
                    after < value <= until
                    and value >= start
                    and (end is None or value < end)
                ):
                    results[value] = plan.get("dose_text")
        day += timedelta(days=1)
    return sorted(results.items())
