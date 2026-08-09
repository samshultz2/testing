"""Settings → Performance page: surfaces the in-process slow-request / slow-query
ring buffers (roadmap #10) so admins can spot slow endpoints without shell access."""
from config import Config


def _admin(app):
    from tests.conftest import login_token, auth_csrf
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_buffers_capture_and_clear(app):
    from utils import perf_logging as pl
    pl.clear_perf_buffers()
    assert pl.recent_slow_requests() == [] and pl.recent_slow_queries() == []
    pl._SLOW_REQUESTS.append({'at': 'now', 'ms': 2000, 'method': 'GET',
                              'path': '/slow', 'status': 200, 'host': 'h', 'user': '-'})
    pl._SLOW_QUERIES.append({'at': 'now', 'ms': 900, 'sql': 'SELECT 1'})
    assert pl.recent_slow_requests()[0]['path'] == '/slow'
    assert pl.recent_slow_queries()[0]['ms'] == 900
    pl.clear_perf_buffers()
    assert pl.recent_slow_requests() == []


def test_performance_page_renders_thresholds(app):
    from utils import perf_logging as pl
    pl.clear_perf_buffers()
    pl._SLOW_REQUESTS.append({'at': 'now', 'ms': 2500, 'method': 'GET',
                              'path': '/results/analytics', 'status': 200,
                              'host': 'h', 'user': 'admin'})
    c = _admin(app)
    r = c.get('/settings/performance')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Performance' in body
    assert '/results/analytics' in body      # the captured slow request shows up


def test_performance_page_clear_button(app):
    from utils import perf_logging as pl
    pl._SLOW_QUERIES.append({'at': 'now', 'ms': 800, 'sql': 'SELECT 42'})
    c = _admin(app)
    from tests.conftest import auth_csrf
    r = c.post('/settings/performance', data={'_csrf_token': auth_csrf(c)})
    assert r.status_code in (302, 303)
    assert pl.recent_slow_queries() == []
