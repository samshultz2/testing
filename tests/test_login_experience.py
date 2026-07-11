"""Login-experience refinements: email-or-username sign-in, Remember-me session
persistence, the conditional legacy hint, and the UX/a11y markup on the page."""
import uuid

from config import Config
from models import db, Branch, User
from tests.conftest import login_token

_PW = 'StrongPass123!'


def _staff(app, username, email=None):
    with app.app_context():
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(username=username, role='teacher', is_active=True,
                     email=email, branch_id=Branch.get_default().id)
            u.set_password(_PW)
            db.session.add(u); db.session.commit()
        return u.id


def test_login_with_email_works(app):
    uniq = uuid.uuid4().hex[:6]
    email = f'jane.{uniq}@school.edu'
    _staff(app, f'jane_{uniq}', email=email)
    c = app.test_client()
    c.post('/login', data={'username': email, 'password': _PW,
                           'remember': '1', '_csrf_token': login_token(c)})
    with c.session_transaction() as sess:
        assert sess.get('logged_in') is True


def test_login_with_username_still_works(app):
    uniq = uuid.uuid4().hex[:6]
    _staff(app, f'joe_{uniq}', email=f'joe.{uniq}@school.edu')
    c = app.test_client()
    c.post('/login', data={'username': f'joe_{uniq}', 'password': _PW,
                           '_csrf_token': login_token(c)})
    with c.session_transaction() as sess:
        assert sess.get('logged_in') is True


def test_remember_me_controls_session_permanence(app):
    uniq = uuid.uuid4().hex[:6]
    _staff(app, f'rin_{uniq}')
    # unchecked (field absent) → browser-session cookie (not permanent)
    c1 = app.test_client()
    c1.post('/login', data={'username': f'rin_{uniq}', 'password': _PW,
                            '_csrf_token': login_token(c1)})
    with c1.session_transaction() as s:
        assert s.get('logged_in') is True and s.permanent is False
    # checked → persistent session
    c2 = app.test_client()
    c2.post('/login', data={'username': f'rin_{uniq}', 'password': _PW,
                            'remember': '1', '_csrf_token': login_token(c2)})
    with c2.session_transaction() as s:
        assert s.get('logged_in') is True and s.permanent is True


def test_wrong_email_password_is_generic_failure(app):
    uniq = uuid.uuid4().hex[:6]
    _staff(app, f'kim_{uniq}', email=f'kim.{uniq}@school.edu')
    c = app.test_client()
    r = c.post('/login', data={'username': f'kim.{uniq}@school.edu', 'password': 'wrong',
                               '_csrf_token': login_token(c)}, follow_redirects=True)
    assert 'Invalid credentials' in r.get_data(as_text=True)
    with c.session_transaction() as sess:
        assert not sess.get('logged_in')


def test_login_page_has_ux_and_a11y_markup(app):
    html = app.test_client().get('/login').get_data(as_text=True)
    # password show/hide toggle + caps-lock hint + submit loading affordance
    assert 'id="pwToggle"' in html and 'Show password' in html
    assert 'id="capsHint"' in html
    # accessible labels + live error region + remember-me + trust footer
    assert 'for="username"' in html and 'for="password"' in html
    assert 'aria-live="assertive"' in html
    assert 'name="remember"' in html
    assert 'Secure' in html and 'slug=\'privacy\'' not in html  # privacy rendered as a URL
    assert '/legal/privacy' in html and '/legal/terms' in html
    # email-or-username affordance + password-manager autocomplete
    assert 'Email or username' in html
    assert 'autocomplete="current-password"' in html


def test_legacy_hint_only_shown_when_enabled(app):
    """conftest enables legacy login, so the admin hint is present; the field is
    not autofocused (the hint replaces autofocus)."""
    html = app.test_client().get('/login').get_data(as_text=True)
    if Config.ENABLE_LEGACY_LOGIN and Config.ADMIN_PASSWORD:
        assert 'password-only sign-in' in html
    else:
        assert 'password-only sign-in' not in html
