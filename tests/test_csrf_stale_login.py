"""A stale sign-in page (old tab, expired session, cached copy) must never dead-end
on an error page: the CSRF failure sends the person back to the same form with a
fresh token, and the sign-in pages are kept out of every cache."""
import re

from config import Config
from tests.conftest import login_token


def _token(html):
    return re.search(r'name="_csrf_token" value="([^"]+)"', html).group(1)


def test_stale_login_token_redirects_back_to_the_form(app):
    old = app.test_client()
    stale = _token(old.get('/login').get_data(as_text=True))
    c = app.test_client()                              # new session — the old token is stale
    r = c.post('/login?next=/finance/', data={'password': 'x', '_csrf_token': stale})
    assert r.status_code == 303
    assert r.headers['Location'].endswith('/login?next=/finance/')
    page = c.get('/login?next=/finance/').get_data(as_text=True)
    assert 'Your session expired' in page
    # ...and signing in from the refreshed form works
    r = c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': _token(page)})
    assert r.status_code == 302 and '/login' not in r.headers['Location']


def test_portal_logins_recover_too(app):
    for path in ('/parent/login', '/exam/login', '/forgot-password'):
        r = app.test_client().post(path, data={'_csrf_token': 'stale'})
        assert r.status_code == 303 and r.headers['Location'].endswith(path), path


def test_other_forms_and_fetches_still_reject(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    r = c.post('/finance/items/add', data={'name': 'x', '_csrf_token': 'stale'})
    assert r.status_code == 400 and b'Reload the page' in r.data
    r = app.test_client().post('/login', data={'_csrf_token': 'stale'}, headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 400


def test_login_pages_are_not_cached(app):
    for path in ('/login', '/parent/login', '/exam/login'):
        assert 'no-store' in app.test_client().get(path).headers.get('Cache-Control', ''), path
