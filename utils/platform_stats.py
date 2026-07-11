"""Best-effort live usage stats for one tenant, read from its own database.

Used by the platform Tenant Profile page. Each count is guarded independently so
a missing table or an unreachable database degrades gracefully to ``None`` (shown
as “—”) rather than failing the page. Computed on demand for a single tenant and
cached briefly per-process, so opening a profile never runs an expensive
cross-tenant sweep.
"""
from __future__ import annotations

import time as _time

# subdomain-agnostic: keyed by database_url. Small TTL cache so a refresh or a
# double-open doesn't re-hit the tenant DB.
_CACHE = {}
_TTL = 60

# (label_key, SQL). Counts stay simple + index-friendly.
_QUERIES = [
    ('students', "SELECT COUNT(*) FROM students WHERE is_active = 1"),
    ('staff', "SELECT COUNT(*) FROM staff_members"),
    ('branches', "SELECT COUNT(*) FROM branches"),
    ('users', "SELECT COUNT(*) FROM users WHERE is_active = 1"),
    ('parents', "SELECT COUNT(*) FROM parent_contacts"),
]


def _count(conn, sql):
    from sqlalchemy import text
    try:
        return int(conn.execute(text(sql)).scalar() or 0)
    except Exception:
        return None


def tenant_usage(database_url, *, use_cache=True):
    """{'students':N,'staff':N,'branches':N,'users':N,'parents':N, ...} for a
    tenant DB, each value an int or None. Never raises."""
    if not database_url:
        return {k: None for k, _ in _QUERIES}
    now = _time.time()
    if use_cache:
        hit = _CACHE.get(database_url)
        if hit and hit[0] > now:
            return dict(hit[1])
    out = {k: None for k, _ in _QUERIES}
    try:
        from utils.tenant_runtime import _engine_for
        engine = _engine_for(database_url)
        with engine.connect() as conn:
            for key, sql in _QUERIES:
                out[key] = _count(conn, sql)
    except Exception:
        pass
    _CACHE[database_url] = (now + _TTL, dict(out))
    return out
