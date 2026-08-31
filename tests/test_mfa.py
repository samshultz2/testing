"""Opt-in TOTP 2FA: RFC-6238 core, enrollment, login verify step, backup codes,
disable, and admin reset."""
import base64
import re

from config import Config
from models import db, Branch, User
from tests.conftest import login_token, auth_csrf
from utils import totp

_PW = 'StrongPass123!'
_CODE_RE = re.compile(r'<code[^>]*>([A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4})</code>')


def _staff(app, username='mfauser', mfa=False):
    with app.app_context():
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(username=username, role='teacher', is_active=True,
                     branch_id=Branch.get_default().id)
            u.set_password(_PW)
            db.session.add(u); db.session.commit()
        if mfa:
            u.mfa_secret = totp.generate_secret()
            u.mfa_enabled = True
            db.session.commit()
        return u.id


def _login_pw(app, username='mfauser'):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': _PW,
                           '_csrf_token': login_token(c)})
    return c


# --- core -------------------------------------------------------------------
def test_totp_rfc6238_vector():
    secret = base64.b32encode(b'12345678901234567890').decode()
    assert totp.totp_at(secret, for_time=59) == '287082'          # RFC-6238 SHA1
    assert totp.verify(secret, totp.totp_at(secret))
    assert not totp.verify(secret, '000000')


def test_mfa_columns_exist(app):
    with app.app_context():
        cols = {c['name'] for c in db.inspect(db.engine).get_columns('users')}
        assert {'mfa_enabled', 'mfa_secret', 'mfa_backup_codes'} <= cols


# --- login gate -------------------------------------------------------------
def test_login_without_mfa_unchanged(app):
    _staff(app, 'plainuser')
    c = _login_pw(app, 'plainuser')
    with c.session_transaction() as s:
        assert s.get('logged_in') is True          # straight in, no verify step


def test_login_with_mfa_requires_code_then_completes(app):
    uid = _staff(app, 'mfauser', mfa=True)
    c = _login_pw(app, 'mfauser')
    # password alone must NOT log in — a pending state is held instead
    with c.session_transaction() as s:
        assert not s.get('logged_in')
        assert s.get('_pending_mfa_uid') == uid
    # a valid current TOTP completes the login
    with app.app_context():
        secret = db.session.get(User, uid).mfa_secret
    c.post('/login/verify', data={'code': totp.totp_at(secret), '_csrf_token': auth_csrf(c)})
    with c.session_transaction() as s:
        assert s.get('logged_in') is True
        assert s.get('user_id') == uid
        assert not s.get('_pending_mfa_uid')


def test_wrong_code_does_not_log_in(app):
    _staff(app, 'mfauser2', mfa=True)
    c = _login_pw(app, 'mfauser2')
    c.post('/login/verify', data={'code': '000000', '_csrf_token': auth_csrf(c)})
    with c.session_transaction() as s:
        assert not s.get('logged_in')


# --- enrollment + backup codes ---------------------------------------------
def test_enroll_and_backup_code_single_use(app):
    _staff(app, 'enroller')
    c = _login_pw(app, 'enroller')
    # setup saves a not-yet-active secret
    c.get('/security/2fa/setup')
    with app.app_context():
        u = User.query.filter_by(username='enroller').first()
        assert u.mfa_secret and not u.mfa_enabled
        secret = u.mfa_secret
    # confirm with a valid code -> enabled + backup codes shown once
    r = c.post('/security/2fa/confirm', data={'code': totp.totp_at(secret), '_csrf_token': auth_csrf(c)})
    codes = _CODE_RE.findall(r.get_data(as_text=True))
    assert len(codes) == 10
    with app.app_context():
        assert User.query.filter_by(username='enroller').first().mfa_enabled

    # a backup code logs in once, then is consumed
    c2 = _login_pw(app, 'enroller')
    c2.post('/login/verify', data={'code': codes[0], '_csrf_token': auth_csrf(c2)})
    with c2.session_transaction() as s:
        assert s.get('logged_in') is True
    with app.app_context():
        u = User.query.filter_by(username='enroller').first()
        assert not u.consume_backup_code(codes[0])      # already used
        assert u.consume_backup_code(codes[1])          # a different one still works


# --- disable + admin reset --------------------------------------------------
def test_self_disable_requires_password(app):
    _staff(app, 'disabler', mfa=True)
    c = _login_pw_mfa(app, 'disabler')
    c.post('/security/2fa/disable', data={'password': 'nope', '_csrf_token': auth_csrf(c)})
    with app.app_context():
        assert User.query.filter_by(username='disabler').first().mfa_enabled  # wrong pw -> unchanged
    c.post('/security/2fa/disable', data={'password': _PW, '_csrf_token': auth_csrf(c)})
    with app.app_context():
        assert not User.query.filter_by(username='disabler').first().mfa_enabled


def test_admin_reset_mfa(app):
    uid = _staff(app, 'lockedout', mfa=True)
    admin = app.test_client()
    admin.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(admin)})
    admin.post(f'/users/{uid}/reset-mfa', data={'_csrf_token': auth_csrf(admin)})
    with app.app_context():
        assert not db.session.get(User, uid).mfa_enabled


def _login_pw_mfa(app, username):
    """Log a MFA user fully in (password + a current TOTP)."""
    c = _login_pw(app, username)
    with app.app_context():
        secret = User.query.filter_by(username=username).first().mfa_secret
    c.post('/login/verify', data={'code': totp.totp_at(secret), '_csrf_token': auth_csrf(c)})
    return c
