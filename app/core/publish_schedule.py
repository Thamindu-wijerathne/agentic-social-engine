"""Assign Facebook publish times to fixed US daily slots."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from config.settings import settings

DEFAULT_SCHEDULE_HOURS = (8, 11, 14, 17, 20)
FACEBOOK_MIN_LEAD_MINUTES = 15


def get_schedule_hours() -> tuple[int, ...]:
    raw = settings.facebook_schedule_hours.strip()
    if not raw:
        return DEFAULT_SCHEDULE_HOURS
    hours = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    return hours or DEFAULT_SCHEDULE_HOURS


def get_schedule_timezone() -> ZoneInfo:
    return ZoneInfo(settings.facebook_schedule_timezone)


def compute_schedule_times(count: int) -> list[datetime]:
    """Return the next `count` slot datetimes in the configured US timezone."""
    if count <= 0:
        return []

    tz = get_schedule_timezone()
    hours = get_schedule_hours()
    now = datetime.now(tz)
    earliest = now + timedelta(minutes=FACEBOOK_MIN_LEAD_MINUTES)

    slots: list[datetime] = []
    day = now.date()

    while len(slots) < count:
        for hour in hours:
            candidate = datetime.combine(day, time(hour, 0), tzinfo=tz)
            if candidate >= earliest:
                slots.append(candidate)
                if len(slots) >= count:
                    return slots
        day += timedelta(days=1)

    return slots


def format_schedule_slot(dt: datetime) -> str:
    localized = dt.astimezone(get_schedule_timezone())
    return localized.strftime("%I:%M %p %Z").lstrip("0")
