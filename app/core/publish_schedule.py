from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from config.settings import settings


def get_schedule_timezone() -> ZoneInfo:
    return ZoneInfo(settings.facebook_schedule_timezone)


def _parse_schedule_hours() -> list[int]:
    hours: list[int] = []
    for part in settings.facebook_schedule_hours.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            hour = int(part)
        except ValueError:
            continue
        if 0 <= hour <= 23:
            hours.append(hour)
    return hours or [8, 11, 14, 17, 20]


def compute_schedule_times(count: int, *, start: datetime | None = None) -> list[datetime]:
    """Return `count` upcoming publish slots in the configured US timezone."""
    if count <= 0:
        return []

    tz = get_schedule_timezone()
    hours = _parse_schedule_hours()
    now_local = (start or datetime.now(timezone.utc)).astimezone(tz)
    slots: list[datetime] = []

    day_offset = 0
    while len(slots) < count:
        base_date = (now_local + timedelta(days=day_offset)).date()
        for hour in hours:
            candidate = datetime.combine(base_date, time(hour, 0), tzinfo=tz)
            if candidate > now_local:
                slots.append(candidate)
                if len(slots) >= count:
                    break
        day_offset += 1
        if day_offset > 14:
            break

    return slots[:count]


def format_schedule_slot(slot: datetime) -> str:
    local = slot.astimezone(get_schedule_timezone())
    hour = local.strftime("%I").lstrip("0") or "12"
    return f"{hour}:{local.strftime('%M %p %Z')}"
