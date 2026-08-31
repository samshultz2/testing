"""Live at-risk watchlist (roadmap #6): projects SSS3 candidates' readiness now
and flags those off track, grouped by class arm — page renders and the service
returns a sane shape."""
from config import Config


def _admin(app):
    from tests.conftest import login_token
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_live_at_risk_shape_empty_is_safe(app):
    from utils.at_risk_live import live_at_risk
    # Branch scoping in get_sss3_students() needs a request context.
    with app.test_request_context():
        from flask import session
        session['role'] = 'super_admin'
        session['scope'] = 'central'
        data = live_at_risk()
    assert set(data.keys()) == {'total_flagged', 'counts', 'by_class'}
    assert isinstance(data['by_class'], list)
    assert data['total_flagged'] == sum(g['count'] for g in data['by_class'])


def test_watchlist_page_renders(app):
    c = _admin(app)
    r = c.get('/results/analytics/watchlist')
    assert r.status_code == 200
    assert 'At-Risk Watchlist' in r.get_data(as_text=True)
