"""
Site-wide timezone handling.

A single configurable timezone (SchoolSettings 'timezone', default Africa/Lagos
= UTC+1) drives every "now"/"today" used for comparisons, and every stored
``created_at`` (via models.local_now). Datetimes are stored naive but represent
wall-clock time in the configured zone, so display is correct everywhere without
per-template conversion.
"""
import time
from datetime import datetime

try:
    from zoneinfo import ZoneInfo, available_timezones
except ImportError:  # pragma: no cover
    ZoneInfo = None
    available_timezones = lambda: set()

DEFAULT_TZ = 'Africa/Lagos'   # West Africa Time, UTC+1

# A short, friendly menu (plus whatever else the OS offers via available_timezones).
COMMON_TIMEZONES = [
    'Africa/Lagos', 'Africa/Accra', 'Africa/Nairobi', 'Africa/Johannesburg',
    'Africa/Cairo', 'UTC', 'Europe/London', 'Europe/Paris', 'America/New_York',
    'America/Chicago', 'America/Los_Angeles', 'Asia/Dubai', 'Asia/Kolkata',
    'Asia/Shanghai',
]

_cache = {'name': None, 'ts': 0.0}


def get_timezone():
    """Configured timezone name (cached ~30s to avoid a DB hit per call)."""
    nowt = time.time()
    if _cache['name'] is None or nowt - _cache['ts'] > 30:
        name = DEFAULT_TZ
        try:
            from models import SchoolSettings
            name = SchoolSettings.get('timezone', DEFAULT_TZ) or DEFAULT_TZ
        except Exception:
            name = DEFAULT_TZ
        _cache['name'] = name
        _cache['ts'] = nowt
    return _cache['name']


def clear_cache():
    _cache['name'] = None


def now():
    """Naive current datetime in the configured timezone."""
    name = get_timezone()
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(name)).replace(tzinfo=None)
        except Exception:
            pass
    return datetime.now()


def today():
    return now().date()


def all_timezones():
    extra = sorted(t for t in available_timezones() if t not in COMMON_TIMEZONES)
    return COMMON_TIMEZONES + extra
