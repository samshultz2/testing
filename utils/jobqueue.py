"""A tiny optional job queue: Redis-backed when available, inline otherwise.

Used to move spiky or non-critical work off the request that triggers it — most
importantly, keeping exam **analytics fully asynchronous** and offering an
optional **queued (async) grading** path so a whole cohort submitting at the
deadline doesn't grade synchronously on the web workers.

Two enqueue modes make the graceful fallback explicit:

* ``inline_fallback=True`` (default) — when no Redis queue is configured, the job
  runs immediately, in-process. Correct for work that must happen (grading).
* ``inline_fallback=False`` — when no queue is configured, the job is simply
  dropped. Correct for best-effort work with an on-demand fallback elsewhere
  (analytics, which the admin page computes on the fly if the cache is cold), so
  it never lands back on the student's request.

The dedicated jobs worker (``scripts/run_jobs.py``) — or the in-process worker on
a single box — calls :func:`drain` to run queued jobs. Handlers are registered by
name with :func:`register`. Everything is best-effort and never raises into the
caller.
"""
from __future__ import annotations

import json
import os

_QUEUE_KEY = 'edusyncra:jobq'
_HANDLERS: dict = {}


def register(kind: str, fn):
    """Register a handler ``fn(app, payload_dict)`` for jobs of type ``kind``."""
    _HANDLERS[kind] = fn


def backend_enabled() -> bool:
    """True when a Redis queue backs enqueue/drain (vs. inline-only)."""
    from utils import cache
    return cache.enabled()


def _redis():
    from utils import cache
    return cache._client()          # shares the cache's connection/config


def enqueue(kind: str, payload: dict | None = None, *, inline_fallback: bool = True):
    """Queue a job. Falls back per ``inline_fallback`` when no backend exists.

    Returns 'queued' | 'inline' | 'dropped' so callers/tests can assert behaviour.
    """
    payload = payload or {}
    client = _redis()
    if client is not None:
        try:
            client.rpush(_QUEUE_KEY, json.dumps({'kind': kind, 'payload': payload}))
            return 'queued'
        except Exception:
            pass
    # No backend (or push failed): run now, or drop for best-effort jobs.
    if inline_fallback:
        _run(None, kind, payload)
        return 'inline'
    return 'dropped'


def _run(app, kind: str, payload: dict):
    fn = _HANDLERS.get(kind)
    if fn is None:
        return
    try:
        fn(app, payload)
    except Exception:
        try:
            from flask import current_app
            (app or current_app).logger.warning('jobqueue handler %s failed', kind, exc_info=True)
        except Exception:
            pass


def drain(app, max_items: int = 1000) -> int:
    """Pop and run up to ``max_items`` queued jobs. Returns how many ran.

    Runs inside an app context so handlers can touch the DB. No-op (returns 0)
    when there's no Redis backend — inline jobs already ran at enqueue time.
    """
    client = _redis()
    if client is None:
        return 0
    ran = 0
    for _ in range(max_items):
        try:
            raw = client.lpop(_QUEUE_KEY)
        except Exception:
            break
        if not raw:
            break
        try:
            job = json.loads(raw)
        except Exception:
            continue
        kind, payload = job.get('kind'), job.get('payload') or {}
        if app is not None:
            with app.app_context():
                _run(app, kind, payload)
        else:
            _run(app, kind, payload)
        ran += 1
    return ran


def queue_length() -> int:
    client = _redis()
    if client is None:
        return 0
    try:
        return int(client.llen(_QUEUE_KEY))
    except Exception:
        return 0
