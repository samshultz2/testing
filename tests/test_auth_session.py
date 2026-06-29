"""Auth session-security gaps not covered elsewhere: brute-force lockout, CSRF/session
rotation on login (fixation defence), and logout clearing the session."""
from config import Config
from tests.conftest import login_token, auth_csrf


def _clear_lockout(app):
    """Reset the IP-keyed staff-login throttle so these tests don't lock out (or get
    locked out by) other suites sharing the 127.0.0.1 client key."""
    from utils.security import login_limiter
    with app.app_context():
        login_limiter.clear_attempts('staff_login:127.0.0.1')
        login_limiter.clear_attempts('staff_login:unknown')


def test_login_lockout_after_max_attempts(app):
    _clear_lockout(app)
    try:
        c = app.test_client()
        for _ in range(Config.LOGIN_MAX_ATTEMPTS):
            c.post('/login', data={'password': 'definitely-wrong', '_csrf_token': login_token(c)})
        # Even the CORRECT password is now refused while locked out.
        r = c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)},
                   follow_redirects=True)
        body = r.get_data(as_text=True).lower()
        with c.session_transaction() as s:
            assert not s.get('logged_in')
        assert 'too many' in body or 'try again' in body
    finally:
        _clear_lockout(app)


def test_csrf_token_rotates_on_login(app):
    """Session fixation defence: the CSRF token (and session) must change on login."""
    _clear_lockout(app)
    try:
        c = app.test_client()
        login_token(c)                       # ensure a pre-login token exists
        with c.session_transaction() as s:
            before = s.get('_csrf_token')
        c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': before})
        after = auth_csrf(c)
        assert after and after != before
        with c.session_transaction() as s:
            assert s.get('logged_in') is True
    finally:
        _clear_lockout(app)


def test_logout_clears_session(app):
    _clear_lockout(app)
    try:
        c = app.test_client()
        c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
        with c.session_transaction() as s:
            assert s.get('logged_in') is True
        c.get('/logout', follow_redirects=True)
        with c.session_transaction() as s:
            assert not s.get('logged_in')
            assert not s.get('role')
        # a protected page now redirects to login
        r = c.get('/students')
        assert r.status_code in (301, 302, 303)
    finally:
        _clear_lockout(app)
