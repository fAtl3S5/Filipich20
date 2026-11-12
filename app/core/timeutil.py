from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta


DISPLAY_TZ_NAME = "Asia/Novosibirsk"


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def same_instant(a: datetime, b: datetime) -> bool:
    return ensure_utc(a) == ensure_utc(b)


def add_calendar_months(start: datetime, months: int) -> datetime:
    """Add calendar months in UTC, preserving time-of-day and handling month-ends/leap years."""
    start = ensure_utc(start)
    return start + relativedelta(months=months)


def format_novosibirsk(dt: datetime, tz_name: str = DISPLAY_TZ_NAME) -> str:
    local = ensure_utc(dt).astimezone(ZoneInfo(tz_name))
    return local.strftime("%d.%m.%Y %H:%M") + f" ({tz_name})"


def remaining_human(ends_at: datetime, now: datetime | None = None) -> str:
    now = ensure_utc(now or utcnow())
    ends_at = ensure_utc(ends_at)
    if ends_at <= now:
        return "истекла"
    delta = ends_at - now
    days = delta.days
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    parts: list[str] = []
    if days:
        parts.append(f"{days} дн.")
    if hours:
        parts.append(f"{hours} ч.")
    if minutes and not days:
        parts.append(f"{minutes} мин.")
    return " ".join(parts) if parts else "меньше минуты"
