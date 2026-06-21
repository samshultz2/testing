"""Lightweight error tracking — persistent, with optional email alerts.

Every unhandled server exception and every reported client-side JS error is:
  * logged with context (what failed, where, which user),
  * appended to a JSONL file (``Config.ERROR_LOG_FILE``) so the in-app Error Log
    survives restarts and is shared across workers, and
  * kept in a small in-memory ring buffer as a fallback when the file can't be
    written (e.g. a read-only filesystem).

When ``Config.ALERT_EMAIL`` is set, *server* errors also trigger a throttled
email alert so ops hears about 500s without external infrastructure. No external
service is required; Sentry is a separate, opt-in layer.
"""
import json
import logging
import os
import time
from collections import deque
from threading import Lock

_log = logging.getLogger('posyhub.errors')
_recent = deque(maxlen=300)
_lock = Lock()

_writes_since_trim = 0
_last_alert_ts = 0.0


def _cfg(name, default=None):
    try:
        from config import Config
        return getattr(Config, name, default)
    except Exception:
        return default


def _log_path():
    return _cfg('ERROR_LOG_FILE', '')


def record_error(kind, message, *, where='', user='', detail=''):
    """Record one error: log it, persist it, keep it in the recent buffer, and
    (for server errors) fire a throttled email alert."""
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
    _persist(entry)
    if kind == 'server':
        _maybe_alert(entry)
    return entry


def _persist(entry):
    """Append one entry as a JSON line, trimming the file periodically so it
    never grows without bound. Best-effort — failures fall back to memory."""
    global _writes_since_trim
    path = _log_path()
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _lock:
            with open(path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            _writes_since_trim += 1
            if _writes_since_trim >= 200:
                _writes_since_trim = 0
                _trim_locked(path)
    except Exception:
        pass  # read-only fs etc. — the in-memory buffer still has it


def _trim_locked(path):
    """Keep only the most recent ERROR_LOG_MAX lines. Caller holds the lock."""
    cap = int(_cfg('ERROR_LOG_MAX', 2000) or 2000)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        if len(lines) > cap:
            with open(path, 'w', encoding='utf-8') as f:
                f.writelines(lines[-cap:])
    except Exception:
        pass


def _maybe_alert(entry):
    """Email ALERT_EMAIL about a server error, no more than once per
    ERROR_ALERT_MIN_INTERVAL seconds. Best-effort and non-blocking."""
    global _last_alert_ts
    to = _cfg('ALERT_EMAIL', '')
    if not to:
        return
    interval = float(_cfg('ERROR_ALERT_MIN_INTERVAL', 900) or 0)
    now = time.time()
    with _lock:
        if now - _last_alert_ts < interval:
            return
        _last_alert_ts = now
    try:
        from utils import mailer
        if not mailer.is_configured():
            return
        recipients = [a.strip() for a in str(to).split(',') if a.strip()]
        app_name = _cfg('APP_NAME', 'App') or 'App'
        subject = f'[{app_name}] Server error: {entry["message"][:80]}'
        paragraphs = [
            f'A server error occurred at {entry["ts"]}.',
            f'Where: {entry["where"]}',
            f'User: {entry["user"]}',
            f'Error: {entry["message"]}',
            f'Trace (truncated):\n{entry["detail"][:1500]}',
        ]
        text = '\n\n'.join(paragraphs)
        html = mailer.branded_html('Server error', paragraphs,
                                   footer='Automated alert. Further alerts are '
                                          'throttled to avoid flooding.')
        mailer.send_email_async(recipients, subject, text, html=html)
    except Exception:
        pass


def _read_persisted(limit):
    """Return the most recent persisted entries (newest first), or [] if the
    file is missing/unreadable."""
    path = _log_path()
    if not path or not os.path.exists(path):
        return []
    try:
        with _lock:
            with open(path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        out = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []


def recent_errors(limit=200):
    """Most recent errors, newest first. Prefers the persisted file (survives
    restarts, spans workers); falls back to the in-memory buffer."""
    rows = _read_persisted(limit)
    if rows:
        return rows
    with _lock:
        return list(_recent)[:limit]


def clear_errors():
    with _lock:
        _recent.clear()
        path = _log_path()
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
