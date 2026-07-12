"""Active-device tracking: a login creates a session row; a user can list and
revoke devices; a revoked device is signed out on its next request."""
import uuid

from models import db, Branch, User, UserSession
from tests.conftest import login_token, auth_csrf
from utils import sessions as S
from utils import totp

_PW = 'Zebra!Mango42Q'


def _user(app):
    with app.app_context():
        u = User(username='sess_' + uuid.uuid4().hex[:6], full_name='Sess User',
                 role='teacher', is_active=True, branch_id=Branch.get_default().id)
        u.set_password(_PW); u.must_change_password = False
        db.session.add(u); db.session.commit()
        return u.id


def _login(app, uid):
    with app.app_context():
        uname = db.session.get(User, uid).username
    c = app.test_client()
    c.post('/login', data={'username': uname, 'password': _PW, '_csrf_token': login_token(c)})
    return c


def test_device_label():
    assert S.device_label('Mozilla/5.0 (Windows NT 10) ... Chrome/120') == 'Chrome on Windows'
    assert 'iPhone' in S.device_label('Mozilla/5.0 (iPhone) ... Safari')


def test_login_creates_session_row(app):
    uid = _user(app)
    _login(app, uid)
    with app.app_context():
        rows = UserSession.query.filter_by(user_id=uid, revoked=False).all()
        assert len(rows) >= 1 and rows[0].sid


def test_revoke_other_devices(app):
    uid = _user(app)
    c1 = _login(app, uid)          # device 1 (kept)
    _login(app, uid)               # device 2
    with app.app_context():
        assert UserSession.query.filter_by(user_id=uid, revoked=False).count() == 2
    with c1.session_transaction() as s:
        s['_csrf_token'] = 'z' * 64
    c1.post('/account/sessions/revoke-others', data={'_csrf_token': 'z' * 64})
    with app.app_context():
        live = UserSession.query.filter_by(user_id=uid, revoked=False).all()
        assert len(live) == 1        # only the current device remains


def test_revoked_device_is_logged_out_next_request(app):
    uid = _user(app)
    c = _login(app, uid)
    # revoke this very session out-of-band
    with app.app_context():
        with c.session_transaction() as s:
            sid = s.get('sid')
        UserSession.query.filter_by(sid=sid).update({'revoked': True})
        db.session.commit()
    # next request should bounce to login
    r = c.get('/account', follow_redirects=False)
    assert r.status_code == 302 and '/login' in r.headers['Location']


def test_sessions_page_lists_current_device(app):
    uid = _user(app)
    html = _login(app, uid).get('/account/sessions').get_data(as_text=True)
    assert 'Active devices' in html and 'This device' in html


# --- trusted device skips MFA on the next login ----------------------------
def _mfa_user(app):
    with app.app_context():
        u = User(username='mfa_' + uuid.uuid4().hex[:6], full_name='MFA User',
                 role='teacher', is_active=True, branch_id=Branch.get_default().id)
        u.set_password(_PW); u.must_change_password = False
        u.mfa_secret = totp.generate_secret(); u.mfa_enabled = True
        db.session.add(u); db.session.commit()
        return u.id, u.username, u.mfa_secret


def test_trusted_device_skips_mfa_next_login(app):
    uid, uname, secret = _mfa_user(app)
    c = app.test_client()          # one client keeps the device cookie across logins
    # first login: password holds a pending MFA state
    c.post('/login', data={'username': uname, 'password': _PW, '_csrf_token': login_token(c)})
    with c.session_transaction() as s:
        assert not s.get('logged_in') and s.get('_pending_mfa_uid') == uid
    # verify with "trust this device" ticked -> completes and marks the session trusted
    c.post('/login/verify', data={'code': totp.totp_at(secret), 'trust_device': '1',
                                  '_csrf_token': auth_csrf(c)})
    with c.session_transaction() as s:
        assert s.get('logged_in') is True
    with app.app_context():
        assert UserSession.query.filter_by(user_id=uid, trusted=True, revoked=False).count() == 1
    # log out, then log in again from the SAME browser: MFA is skipped
    c.get('/logout')
    c.post('/login', data={'username': uname, 'password': _PW, '_csrf_token': login_token(c)})
    with c.session_transaction() as s:
        assert s.get('logged_in') is True          # straight in, no verify step
        assert not s.get('_pending_mfa_uid')


def test_untrusted_device_still_requires_mfa(app):
    uid, uname, secret = _mfa_user(app)
    c = app.test_client()
    c.post('/login', data={'username': uname, 'password': _PW, '_csrf_token': login_token(c)})
    # verify WITHOUT ticking trust -> session not trusted
    c.post('/login/verify', data={'code': totp.totp_at(secret), '_csrf_token': auth_csrf(c)})
    with app.app_context():
        assert UserSession.query.filter_by(user_id=uid, trusted=True).count() == 0
    c.get('/logout')
    c.post('/login', data={'username': uname, 'password': _PW, '_csrf_token': login_token(c)})
    with c.session_transaction() as s:
        assert not s.get('logged_in') and s.get('_pending_mfa_uid') == uid   # MFA again


# --- new-device alert -------------------------------------------------------
def test_new_device_login_alerts_owner(app):
    from models import Notification
    uid = _user(app)
    _login(app, uid)               # first login on device A — not "new", establishes history
    with app.app_context():
        before = Notification.query.filter_by(user_id=uid).count()
    _login(app, uid)               # fresh client => fresh device cookie => new device
    with app.app_context():
        after = Notification.query.filter_by(user_id=uid).count()
        assert after == before + 1
        n = Notification.query.filter_by(user_id=uid).order_by(Notification.id.desc()).first()
        assert 'new device' in (n.body or '').lower()
