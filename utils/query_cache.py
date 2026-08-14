"""Cache-through for expensive READ queries, with write-time invalidation.

Thin layer over :mod:`utils.cache` (Redis when present, in-process dict
otherwise) that adds the two things a query cache needs:

* **Tenant namespacing** — a single Redis is shared by every school, so keys are
  prefixed with the active subdomain (mirrors ``routes.cbt._tns``). School A's
  cached dashboard can never be served to school B.
* **Version-based invalidation** — each cache *domain* (e.g. ``'dash'``) has a
  version counter. Cached entries embed the current version in their key, and a
  write bumps the version, so every entry in that domain for that tenant becomes
  unreachable at once (and expires on its own TTL). This is far less brittle than
  deleting individual keys: a mutation site just calls :func:`bump('dash')`
  without needing to know which of the many per-user dashboard keys exist.

Safety: this is a cache, never a source of truth. Every entry also carries a
short TTL, so a *missed* invalidation self-heals within that TTL rather than
serving stale data indefinitely. Without Redis the counters live per-process, so
cross-worker invalidation needs Redis — the TTL bounds staleness in the meantime.
Never raises: a compute error propagates (so the caller sees real failures), but
any cache hiccup falls through to recomputing.
"""
from __future__ import annotations

import time

from utils import cache


def _tns() -> str:
    """Active school namespace ('single' in single-school mode). Mirrors
    routes.cbt._tns so both share one convention."""
    try:
        from utils.tenant_runtime import current_tenant
        t = current_tenant()
        return t.subdomain if t is not None else 'single'
    except Exception:
        return 'single'


def _ver_key(domain: str) -> str:
    return f'qc:{_tns()}:ver:{domain}'


def _version(domain: str) -> str:
    """Current version token for a domain. Defaults to '0' before the first
    write. Stored WITHOUT a TTL so it never silently resets under a live entry."""
    try:
        v = cache.get(_ver_key(domain))
        return v if v else '0'
    except Exception:
        return '0'


def version(domain: str) -> str:
    """Public accessor for a domain's current version token (see :func:`bump`).
    Callers that manage their own value store (e.g. a DB-backed cache) embed this
    in their key so a bump invalidates their entries too. Defaults to '0'."""
    return _version(domain)


def bump(domain: str) -> None:
    """Invalidate every cached entry in ``domain`` for the CURRENT tenant.

    Call this at a write site after a mutation that could change what the
    domain's cached reads return. Uses a monotonic nanosecond token, so
    concurrent bumps can't collide on a shared value the way read-modify-write
    increments could — any new token abandons all older keys."""
    try:
        cache.set(_ver_key(domain), str(time.time_ns()), ttl=None)
    except Exception:
        pass


def cached(domain: str, name: str, ttl: int, compute):
    """Return ``compute()``'s result, memoised under (tenant, domain, version,
    name) for ``ttl`` seconds. On a hit the cached JSON is returned; on a miss
    ``compute`` runs and its result is cached. ``name`` must capture everything
    that changes the result but ISN'T already in the domain/version — most
    importantly the viewer's scope (user, branch, term) for per-user data, so
    one user's cached view is never served to another.

    ``compute`` must return a JSON-serialisable value. A compute exception is
    NOT swallowed (real errors must surface); only cache errors fall through to
    a plain ``compute()``."""
    try:
        key = f'qc:{_tns()}:{domain}:{_version(domain)}:{name}'
    except Exception:
        return compute()
    try:
        hit = cache.get_json(key)
        if hit is not None:
            return hit
    except Exception:
        pass
    val = compute()
    try:
        if val is not None:
            cache.set_json(key, val, ttl)
    except Exception:
        pass
    return val
