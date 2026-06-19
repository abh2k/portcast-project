from datetime import datetime, timezone
from typing import Optional


def current_utc_now() -> datetime:
    return datetime.now(timezone.utc)


def current_period(now: Optional[datetime] = None) -> str:
    value = now or current_utc_now()
    return value.strftime("%Y-%m")


def next_period_start(now: Optional[datetime] = None) -> datetime:
    value = now or current_utc_now()
    if value.month == 12:
        return value.replace(year=value.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return value.replace(month=value.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)


def reset_at_iso(now: Optional[datetime] = None) -> str:
    return next_period_start(now).isoformat().replace("+00:00", "Z")


def ttl_seconds_until_reset_with_buffer(
    buffer_seconds: int,
    now: Optional[datetime] = None,
) -> int:
    value = now or current_utc_now()
    reset_at = next_period_start(value)
    delta_seconds = int((reset_at - value).total_seconds())
    return max(delta_seconds + buffer_seconds, buffer_seconds)
