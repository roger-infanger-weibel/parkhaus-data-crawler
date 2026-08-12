"""Gemeinsame Konstanten fuer alle Scanner-Module."""
from zoneinfo import ZoneInfo

SWISS_TZ = ZoneInfo("Europe/Zurich")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko)"
)

STALE_THRESHOLD_MINUTES = 30
