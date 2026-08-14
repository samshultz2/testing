"""Dashboard Phase 4 — expensive metrics are memoized via AnalyticsCache so the
dashboard stays responsive for large schools (no recompute every load)."""
from flask import session
from models import db, AnalyticsCache


def test_dash_cached_memoizes(app):
    from routes.main import _dash_cached
    calls = {'n': 0}

    def compute():
        calls['n'] += 1
        return {'v': 42}

    with app.test_request_context('/'):
        session['logged_in'] = True
        session['role'] = 'admin'
        first = _dash_cached('unittest:memo', 300, compute)
        second = _dash_cached('unittest:memo', 300, compute)
        assert first == {'v': 42} and second == {'v': 42}
        assert calls['n'] == 1   # second call served from cache, not recomputed


def test_dash_cached_is_branch_namespaced(app):
    from routes.main import _dash_cached
    seen = []

    def compute():
        seen.append(1)
        return {'ok': True}

    with app.test_request_context('/'):
        session['logged_in'] = True
        session['role'] = 'super_admin'
        session['view_branch_id'] = 1
        _dash_cached('unittest:ns', 300, compute)
    with app.test_request_context('/'):
        session['logged_in'] = True
        session['role'] = 'super_admin'
        session['view_branch_id'] = 2
        _dash_cached('unittest:ns', 300, compute)
    # Different branch context ⇒ different cache key ⇒ recomputed once each.
    assert len(seen) == 2
    with app.app_context():
        keys = {c.cache_key for c in AnalyticsCache.query.filter(
            AnalyticsCache.cache_key.like('dash:unittest:ns%')).all()}
        # Keys are branch-namespaced (b1 vs b2) and version-stamped (:v<token>).
        assert any(k.startswith('dash:unittest:ns:b1:v') for k in keys)
        assert any(k.startswith('dash:unittest:ns:b2:v') for k in keys)


def test_dash_cached_invalidates_on_bump(app):
    """query_cache.bump('dash') advances the version token, so the next read
    misses the old entry and recomputes — write-time invalidation, not just TTL."""
    from routes.main import _dash_cached
    from utils import query_cache
    calls = {'n': 0}

    def compute():
        calls['n'] += 1
        return {'n': calls['n']}

    with app.test_request_context('/'):
        session['logged_in'] = True
        session['role'] = 'admin'
        first = _dash_cached('unittest:inv', 300, compute)
        assert _dash_cached('unittest:inv', 300, compute) == first   # cached
        assert calls['n'] == 1
        query_cache.bump('dash')                                     # data changed
        second = _dash_cached('unittest:inv', 300, compute)
        assert calls['n'] == 2 and second != first                  # recomputed
