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

DEFAULT_TIME_FORMAT = '24h'   # or '12h'

_fmt_cache = {'value': None, 'ts': 0.0}


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


def get_time_format():
    """Configured clock display format, ``'12h'`` or ``'24h'`` (cached ~30s).

    Governs how period/school-day clock times are *displayed* everywhere
    (timetable pages, generator previews, PDF/image/XLSX exports) -- it never
    touches how times are stored (always naive 24h) or the value of a native
    ``<input type="time">``, which browsers already render per the user's own
    OS locale regardless of this setting."""
    nowt = time.time()
    if _fmt_cache['value'] is None or nowt - _fmt_cache['ts'] > 30:
        value = DEFAULT_TIME_FORMAT
        try:
            from models import SchoolSettings
            value = SchoolSettings.get('time_format', DEFAULT_TIME_FORMAT) or DEFAULT_TIME_FORMAT
        except Exception:
            value = DEFAULT_TIME_FORMAT
        if value not in ('12h', '24h'):
            value = DEFAULT_TIME_FORMAT
        _fmt_cache['value'] = value
        _fmt_cache['ts'] = nowt
    return _fmt_cache['value']


def format_clock(hour, minute, fmt=None):
    """Format an ``(hour, minute)`` 24h clock pair per the configured (or
    given) time format. ``'12h'`` renders like ``8:20 AM`` / ``1:00 PM``
    (no leading zero on the hour); ``'24h'`` renders like ``08:20`` /
    ``13:00``."""
    fmt = fmt or get_time_format()
    hour = int(hour) % 24
    minute = int(minute) % 60
    if fmt == '12h':
        period = 'AM' if hour < 12 else 'PM'
        h12 = hour % 12 or 12
        return f'{h12}:{minute:02d} {period}'
    return f'{hour:02d}:{minute:02d}'


def clear_time_format_cache():
    _fmt_cache['value'] = None


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
