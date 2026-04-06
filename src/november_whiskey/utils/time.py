from __future__ import annotations

from datetime import datetime, timedelta


def ceil_to_interval(dt: datetime, interval_minutes: int) -> datetime:
    dt = dt.replace(second=0, microsecond=0)
    remainder = dt.minute % interval_minutes
    if remainder == 0:
        return dt
    return dt + timedelta(minutes=interval_minutes - remainder)
