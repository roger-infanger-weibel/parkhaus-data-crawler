"""Zeit-Helfer. Alle Zeitstempel in der DB sind naive Europe/Zurich-Lokalzeit."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

SWISS_TZ = ZoneInfo("Europe/Zurich")
GRID_MINUTES = 15


def now_local() -> datetime:
    """Aktuelle Schweizer Lokalzeit als naive datetime (wie in der DB)."""
    return datetime.now(SWISS_TZ).replace(tzinfo=None)


def floor_to_grid(dt: datetime, minutes: int = GRID_MINUTES) -> datetime:
    """Auf das 15-Minuten-Raster abrunden."""
    return dt.replace(minute=dt.minute - dt.minute % minutes, second=0, microsecond=0)


def floor_to_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def target_time(created_at: datetime, horizon_h: int) -> datetime:
    return created_at + timedelta(hours=horizon_h)
