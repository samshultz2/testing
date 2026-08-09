"""Lightweight performance logging.

Emits a WARNING log line only when a request or a SQL query crosses a threshold,
so the cost is one timer per request/query and nothing else. Thresholds are
configurable via app config or the SLOW_REQUEST_MS / SLOW_QUERY_MS env vars.
Purely observational — it never changes a response or raises.
"""
import os
import time

from flask import g, request, session

_ENGINE_HOOKED = False


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


def init_perf_logging(app):
    slow_req_ms = _threshold(app, 'SLOW_REQUEST_MS', 'SLOW_REQUEST_MS', 1500)
    slow_q_ms = _threshold(app, 'SLOW_QUERY_MS', 'SLOW_QUERY_MS', 500)

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
            try:
                app.logger.warning('SLOW QUERY %.0fms: %s', dur, ' '.join(statement.split())[:300])
            except Exception:
                pass
