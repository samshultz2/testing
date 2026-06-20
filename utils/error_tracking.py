"""Lightweight error tracking.

Every unhandled server exception and every reported client-side JS error is
logged with context (what failed, where, and which user) AND kept in a small
in-memory ring buffer so an admin can see recent problems at a glance via the
"Error Log" page — without needing external infrastructure.
"""
import logging
import time
from collections import deque
from threading import Lock

_log = logging.getLogger('posyhub.errors')
_recent = deque(maxlen=300)
_lock = Lock()


def record_error(kind, message, *, where='', user='', detail=''):
    """Record one error: log it (so ops/log files capture it) and keep it in the
    recent-errors buffer (so it shows in the in-app Error Log)."""
    entry = {
        'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
        'kind': kind,
        'message': str(message)[:1000],
        'where': str(where)[:300],
        'user': str(user)[:80],
        'detail': str(detail)[:6000],
    }
    with _lock:
        _recent.appendleft(entry)
    try:
        _log.error('[%s] %s | where=%s user=%s\n%s', kind, entry['message'],
                   entry['where'], entry['user'], entry['detail'][:1500])
    except Exception:
        pass
    return entry


def recent_errors(limit=200):
    with _lock:
        return list(_recent)[:limit]


def clear_errors():
    with _lock:
        _recent.clear()
