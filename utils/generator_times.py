"""School-day clock for the timetable generator.

The day's start time, period length and break length are configurable per
school level (JSS vs SSS can start/end at different times) and stored as
GenTimetableRule rows, so they arrive here inside the same ``rules`` dict the
generator already builds (``{rule_type: value}``). Everything degrades to the
historical defaults (08:20 start, 40-min periods, 30-min break) when a value is
missing or malformed, so old tenants keep their previous timetable exactly.
"""
from __future__ import annotations

DEFAULT_START = (8, 20)   # (hour, minute)
DEFAULT_PERIOD = 40       # minutes per period
DEFAULT_BREAK = 30        # minutes of break/recess


def _int(value, default):
    try:
        v = int(str(value).strip())
        return v if v > 0 else default
    except (TypeError, ValueError):
        return default


def clock_params(rules):
    """Day-clock inputs for a level's rules map.

    Returns ``(start_hour, start_min, period_minutes, break_minutes)``, each
    falling back to the historical default when unset/invalid.
    """
    sh, sm = DEFAULT_START
    raw = str(rules.get('day_start', '') or '').strip()
    if ':' in raw:
        h, _, m = raw.partition(':')
        try:
            sh, sm = int(h), int(m)
            if not (0 <= sh < 24 and 0 <= sm < 60):
                sh, sm = DEFAULT_START
        except ValueError:
            sh, sm = DEFAULT_START
    return sh, sm, _int(rules.get('period_minutes'), DEFAULT_PERIOD), \
        _int(rules.get('break_minutes'), DEFAULT_BREAK)


def day_end_time(rules, periods_per_day, break_after=5):
    """The computed dismissal time as ``H:MM`` for the given level.

    end = start + periods*period_len + one break (only if the break falls
    within the day, i.e. break_after < periods_per_day).
    """
    sh, sm, plen, blen = clock_params(rules)
    total = sh * 60 + sm + periods_per_day * plen
    if 0 < break_after < periods_per_day:
        total += blen
    return f"{total // 60}:{total % 60:02d}"
