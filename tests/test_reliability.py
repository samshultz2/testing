"""Custom error pages, client-side error tracking + Error Log, and reset
rate-limiting."""
import re

from config import Config
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_custom_404_html_and_json(app):
    c = app.test_client()
    r = c.get('/this-route-does-not-exist')
    assert r.status_code == 404
    body = r.get_data(as_text=True)
    assert 'Page Not Found' in body and 'Go to Dashboard' in body
    # SPA fetches get JSON, not the HTML page.
    j = c.get('/nope', headers={'X-Requested-With': 'fetch'})
    assert j.status_code == 404 and j.get_json()['error'] == 'Not found'


def test_client_error_endpoint_is_csrf_exempt_and_logged(app):
    from utils.error_tracking import recent_errors, clear_errors
    with app.app_context():
        clear_errors()
    c = app.test_client()
    # No CSRF token (device-side reporter) — still accepted.
    r = c.post('/client-error', json={'message': 'BoomError: kaboom',
                                      'url': 'https://x/users/', 'stack': 'at foo'})
    assert r.status_code == 204
    with app.app_context():
        errs = recent_errors()
        assert any('kaboom' in e['message'] for e in errs)
        assert any(e['kind'] == 'client' for e in errs)


def test_error_log_view_central_admin_only(app):
    from utils.error_tracking import record_error
    with app.app_context():
        record_error('server', 'ValueError: sample', where='GET /x', user='tester',
                     detail='traceback…')
    # Anonymous is redirected to login.
    anon = app.test_client()
    assert anon.get('/error-log', follow_redirects=False).status_code in (302, 303)
    # Central admin sees the log with the recorded error.
    html = _admin(app).get('/error-log').get_data(as_text=True)
    assert 'Error Log' in html and 'ValueError: sample' in html


def test_forgot_password_rate_limited(app):
    c = app.test_client()
    last = None
    for _ in range(12):
        tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                        c.get('/forgot-password').get_data(as_text=True))
        token = tok.group(1) if tok else login_token(c)
        last = c.post('/forgot-password', data={'identifier': 'nobody@example.com',
                                                '_csrf_token': token}, follow_redirects=True)
    assert 'Too many reset requests' in last.get_data(as_text=True)


def test_soft_nav_css_marker_present(app):
    """Soft navigation relies on the spa-css marker to carry each page's CSS;
    without it, swapped pages render unstyled until a reload."""
    html = _admin(app).get('/users/').get_data(as_text=True)
    head = html.split('</head>')[0]
    assert 'spa-css-marker' in head
    # the page's extra_css must come AFTER the marker (so soft-nav swaps it)
    assert head.index('spa-css-marker') < head.rindex('<style')
