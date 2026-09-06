from datetime import datetime


def local_now() -> datetime:
    """Return the current local wall-clock time with its UTC offset."""

    return datetime.now().astimezone()


def local_now_iso() -> str:
    """Return the current local time as an offset-aware ISO 8601 string."""

    return local_now().isoformat()


def as_local_datetime(value: datetime) -> datetime:
    """Interpret naive values as local time and convert aware values to local time."""

    return value.astimezone()


def parse_local_datetime(value: str) -> datetime:
    """Parse an ISO value and return it in the process' local timezone."""

    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return as_local_datetime(parsed)


def local_iso(value: str | datetime) -> str:
    """Normalize an ISO/datetime value to an offset-aware local ISO string."""

    parsed = parse_local_datetime(value) if isinstance(value, str) else value
    return as_local_datetime(parsed).isoformat()


def local_datetime_from_epoch_ms(timestamp: int) -> datetime:
    """Render an absolute event timestamp in the process' local timezone."""

    return datetime.fromtimestamp(timestamp / 1000).astimezone()


def elapsed_ms(start: float, end: float) -> int:
    return max(1, round((end - start) * 1000))
