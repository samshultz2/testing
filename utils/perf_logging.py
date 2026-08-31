"""Lightweight performance logging.

Emits a WARNING log line only when a request or a SQL query crosses a threshold,
so the cost is one timer per request/query and nothing else. Thresholds are
configurable via app config or the SLOW_REQUEST_MS / SLOW_QUERY_MS env vars.
Purely observational — it never changes a response or raises.

Recent slow events are also kept in small in-process ring buffers so an admin can
see them on the Settings → Performance page without shell access to the logs.
Because the buffers live in the worker process, they show this worker's recent
activity (not a cluster-wide view) and reset on restart — enough to spot a slow
endpoint or query at a glance.
"""
import os
import time
from collections import deque
from datetime import datetime

from flask import g, request, session

_ENGINE_HOOKED = False

# Ring buffers of the most recent slow events (newest appended last). Module-level
# so the once-registered Engine listener and every per-tenant app share them.
_SLOW_REQUESTS = deque(maxlen=100)
_SLOW_QUERIES = deque(maxlen=100)


def _threshold(app, key, env, default):
    val = app.config.get(key)
    if val is None:
        val = os.environ.get(env)
    if val is None or val == '':
        return default
    try:
        return int(val)          # respects an explicit 0
    except (TypeError, ValueError):
        return default


def recent_slow_requests(limit=50):
    """Most-recent slow requests, newest first (list of dicts)."""
    return list(reversed(list(_SLOW_REQUESTS)))[:limit]


def recent_slow_queries(limit=50):
    """Most-recent slow queries, newest first (list of dicts)."""
    return list(reversed(list(_SLOW_QUERIES)))[:limit]


def clear_perf_buffers():
    """Drop everything captured so far (used by the Clear button / tests)."""
    _SLOW_REQUESTS.clear()
    _SLOW_QUERIES.clear()


def init_perf_logging(app):
    slow_req_ms = _threshold(app, 'SLOW_REQUEST_MS', 'SLOW_REQUEST_MS', 1500)
    slow_q_ms = _threshold(app, 'SLOW_QUERY_MS', 'SLOW_QUERY_MS', 500)
    # Expose the resolved thresholds so the Performance page can show them.
    app.config['SLOW_REQUEST_MS'] = slow_req_ms
    app.config['SLOW_QUERY_MS'] = slow_q_ms

    @app.before_request
    def _perf_start():
        g._perf_t0 = time.perf_counter()

    @app.after_request
    def _perf_end(response):
        t0 = getattr(g, '_perf_t0', None)
        if t0 is None:
            return response
        dur = (time.perf_counter() - t0) * 1000.0
        try:
            path = request.path or ''
            if dur >= slow_req_ms and not path.startswith('/static'):
                who = session.get('user') or session.get('username') or '-'
                app.logger.warning('SLOW REQUEST %.0fms %s %s -> %s [host=%s user=%s]',
                                   dur, request.method, path, response.status_code,
                                   request.host, who)
                _SLOW_REQUESTS.append({
                    'at': datetime.now().strftime('%d %b %H:%M:%S'),
                    'ms': round(dur), 'method': request.method, 'path': path,
                    'status': response.status_code, 'host': request.host, 'user': who,
                })
        except Exception:
            pass
        return response

    # SQL slow-query logging — registered once on the Engine class so it covers
    # every (per-tenant) engine. Guarded so repeated app creation (tests) doesn't
    # stack listeners.
    global _ENGINE_HOOKED
    if _ENGINE_HOOKED:
        return
    _ENGINE_HOOKED = True
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, 'before_cursor_execute')
    def _q_start(conn, cursor, statement, parameters, context, executemany):
        context._perf_q0 = time.perf_counter()

    @event.listens_for(Engine, 'after_cursor_execute')
    def _q_end(conn, cursor, statement, parameters, context, executemany):
        t0 = getattr(context, '_perf_q0', None)
        if t0 is None:
            return
        dur = (time.perf_counter() - t0) * 1000.0
        if dur >= slow_q_ms:
            sql = ' '.join(statement.split())[:300]
            try:
                app.logger.warning('SLOW QUERY %.0fms: %s', dur, sql)
            except Exception:
                pass
            _SLOW_QUERIES.append({
                'at': datetime.now().strftime('%d %b %H:%M:%S'),
                'ms': round(dur), 'sql': sql,
            })
