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


# Platform-wide roll-up (a sweep across active tenants) — cached longer since it
# touches every school DB. Safe for the current scale; if the platform grows to
# thousands of tenants this should move to a periodic background job that writes
# the totals to the control plane.
_TOTALS = {'exp': 0.0, 'val': None}


def platform_totals(tenants, *, ttl=900, use_cache=True):
    """Summed students / staff / branches across all active tenants, cached for
    ``ttl`` seconds. ``tenants`` is an iterable of control-plane Tenant rows."""
    now = _time.time()
    if use_cache and _TOTALS['val'] is not None and _TOTALS['exp'] > now:
        return dict(_TOTALS['val'])
    agg = {'students': 0, 'staff': 0, 'branches': 0, 'schools_counted': 0}
    for t in tenants:
        if getattr(t, 'status', None) != 'active' or not getattr(t, 'database_url', None):
            continue
        u = tenant_usage(t.database_url)
        if u.get('students') is None and u.get('branches') is None:
            continue                                  # unreachable — skip
        agg['schools_counted'] += 1
        for k in ('students', 'staff', 'branches'):
            agg[k] += (u.get(k) or 0)
    _TOTALS['val'] = dict(agg)
    _TOTALS['exp'] = now + ttl
    return dict(agg)
