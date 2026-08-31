"""Return-to-page after login: a logged-out hit on a protected page bounces to
login with ?next=, and a successful login lands back on that page."""
import re
from urllib.parse import urlparse, parse_qs

from config import Config


def test_safe_next_rejects_offsite_and_allows_local():
    from utils.nav import safe_next
    assert safe_next('/timetable') == '/timetable'
    assert safe_next('/results/scores?term=2') == '/results/scores?term=2'
    assert safe_next('https://evil.test/x', '/fallback') == '/fallback'   # absolute
    assert safe_next('//evil.test/x', '/fallback') == '/fallback'         # scheme-relative
    assert safe_next('/\\evil.test', '/fallback') == '/fallback'          # backslash trick
    assert safe_next('', '/fallback') == '/fallback'
    assert safe_next(None, '/fallback') == '/fallback'


def test_logged_out_page_bounces_with_next_then_returns_after_login(app):
    c = app.test_client()

    # 1. hit a protected page while logged out -> bounced to login carrying next
    r = c.get('/students', follow_redirects=False)
    assert r.status_code in (301, 302)
    loc = r.headers['Location']
    assert '/login' in loc
    q = parse_qs(urlparse(loc).query)
    assert q.get('next') == ['/students']

    # 2. log in (legacy admin) with that next -> land back on /students
    page = c.get('/login?next=/students').get_data(as_text=True)
    assert 'name="next" value="/students"' in page                # carried in the form
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', page).group(1)
    r = c.post('/login', data={'password': Config.ADMIN_PASSWORD, 'next': '/students',
                               '_csrf_token': tok}, follow_redirects=False)
    assert r.status_code in (301, 302)
    assert urlparse(r.headers['Location']).path == '/students'    # returned to the page


def test_login_ignores_offsite_next(app):
    c = app.test_client()
    page = c.get('/login').get_data(as_text=True)
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', page).group(1)
    r = c.post('/login', data={'password': Config.ADMIN_PASSWORD,
                               'next': 'https://evil.test/steal', '_csrf_token': tok},
               follow_redirects=False)
    # falls back to the dashboard, never off-site
    assert 'evil.test' not in (r.headers.get('Location') or '')
