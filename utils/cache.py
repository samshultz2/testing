"""Optional Redis-backed transient state, with a safe in-process fallback.

Redis is used for **cache and transient session state** — data that is cheap to
recompute and must never be the system of record: per-exam answer keys, heartbeat
coalescing gates, small hot lookups. It is enabled automatically when ``REDIS_URL``
(or ``CACHE_REDIS_URL``) is set and the ``redis`` package is importable; otherwise
every call falls back to a bounded, thread-safe in-process dict so the app behaves
identically on a single box with no Redis installed.

Design rules:
* Never raise — a Redis hiccup degrades to the in-process store, it never 500s a
  request. A connection that errors is dropped and retried lazily.
* Values are JSON for the typed helpers, so the same code path works against Redis
  (bytes) and the local dict (objects).
* This is a cache, not a database. Callers must tolerate a miss at any time.
"""
from __future__ import annotations

import json
import os
import threading
import time

_LOCK = threading.Lock()
_LOCAL: dict[str, tuple[float | None, object]] = {}   # key -> (expires_at|None, value)
_LOCAL_MAX = 50000

_redis = None
_redis_tried = False
_redis_ok = False


def _redis_url() -> str | None:
    return os.environ.get('REDIS_URL') or os.environ.get('CACHE_REDIS_URL') or None


def _client():
    """Lazily construct a Redis client. Returns None when Redis is unavailable."""
    global _redis, _redis_tried, _redis_ok
    if _redis_tried:
        return _redis if _redis_ok else None
    _redis_tried = True
    url = _redis_url()
    if not url:
        return None
    try:
        import redis   # type: ignore
        client = redis.Redis.from_url(
            url, socket_timeout=1.5, socket_connect_timeout=1.5,
            health_check_interval=30, decode_responses=False)
        client.ping()
        _redis, _redis_ok = client, True
        return client
    except Exception:
        _redis, _redis_ok = None, False
        return None


def enabled() -> bool:
    """True when a live Redis connection is backing the cache."""
    return _client() is not None


def reset_for_tests():
    """Drop the cached client + local store (used by tests toggling REDIS_URL)."""
    global _redis, _redis_tried, _redis_ok
    _redis, _redis_tried, _redis_ok = None, False, False
    with _LOCK:
        _LOCAL.clear()


# ── local-store helpers ───────────────────────────────────────────────────────
def _local_get(key):
    with _LOCK:
        item = _LOCAL.get(key)
        if not item:
            return None
        exp, val = item
        if exp is not None and exp < time.time():
            _LOCAL.pop(key, None)
            return None
        return val


def _local_set(key, val, ttl):
    with _LOCK:
        if len(_LOCAL) > _LOCAL_MAX:                 # crude bound: drop expired first
            now = time.time()
            for k in [k for k, (e, _) in _LOCAL.items() if e is not None and e < now]:
                _LOCAL.pop(k, None)
            if len(_LOCAL) > _LOCAL_MAX:
                _LOCAL.clear()
        _LOCAL[key] = (time.time() + ttl if ttl else None, val)


# ── public API ────────────────────────────────────────────────────────────────
def get(key: str):
    """Raw string value (or None). Redis bytes are decoded to str."""
    c = _client()
    if c is not None:
        try:
            v = c.get(key)
            return v.decode('utf-8') if isinstance(v, bytes) else v
        except Exception:
            pass
    return _local_get(key)


def set(key: str, value, ttl: int | None = None):
    c = _client()
    if c is not None:
        try:
            c.set(key, value if isinstance(value, (str, bytes)) else str(value), ex=ttl)
            return
        except Exception:
            pass
    _local_set(key, value if isinstance(value, str) else str(value), ttl)


def delete(key: str):
    c = _client()
    if c is not None:
        try:
            c.delete(key)
        except Exception:
            pass
    with _LOCK:
        _LOCAL.pop(key, None)


def get_json(key: str):
    """Deserialize a JSON value stored with :func:`set_json` (or None)."""
    c = _client()
    if c is not None:
        try:
            v = c.get(key)
            if v is None:
                return None
            return json.loads(v)
        except Exception:
            pass
    return _local_get(key)


def set_json(key: str, value, ttl: int | None = None):
    c = _client()
    if c is not None:
        try:
            c.set(key, json.dumps(value), ex=ttl)
            return
        except Exception:
            pass
    # Store the live object locally (no serialization cost, same read semantics).
    _local_set(key, value, ttl)


def should_run(key: str, min_interval: int) -> bool:
    """Rate gate: return True at most once per ``min_interval`` seconds for ``key``.

    Used to coalesce writes (e.g. only persist a heartbeat every N seconds) across
    all workers when Redis is present, per-process otherwise. Backed by an atomic
    ``SET key 1 NX EX`` on Redis; a local timestamp gate as fallback.
    """
    c = _client()
    if c is not None:
        try:
            # NX: only sets when absent → the setter "wins" this window.
            return bool(c.set(key, b'1', nx=True, ex=min_interval))
        except Exception:
            pass
    now = time.time()
    with _LOCK:
        item = _LOCAL.get(key)
        if item and item[0] is not None and item[0] > now:
            return False
        _LOCAL[key] = (now + min_interval, b'1')
        return True
