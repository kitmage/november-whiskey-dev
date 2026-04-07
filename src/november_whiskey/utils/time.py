from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def ceil_to_interval(dt: datetime, interval_minutes: int) -> datetime:
    dt = dt.replace(second=0, microsecond=0)
    remainder = dt.minute % interval_minutes
    if remainder == 0:
        return dt
    return dt + timedelta(minutes=interval_minutes - remainder)


def format_pacific_human(iso_datetime: str, fallback_timezone: str = "America/Los_Angeles") -> str:
    dt = datetime.fromisoformat(iso_datetime)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(fallback_timezone))
    dt = dt.astimezone(ZoneInfo("America/Los_Angeles"))
    hour = dt.strftime("%I").lstrip("0") or "0"
    return f"{dt:%A}, {dt.month}/{dt.day} at {hour}:{dt:%M} {dt:%p}".replace("AM", "am").replace("PM", "pm") + " Pacific"
