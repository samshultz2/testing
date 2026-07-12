"""Active-device tracking: a login creates a session row; a user can list and
revoke devices; a revoked device is signed out on its next request."""
import uuid

from models import db, Branch, User, UserSession
from tests.conftest import login_token
from utils import sessions as S

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
