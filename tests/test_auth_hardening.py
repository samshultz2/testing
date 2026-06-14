"""Force-password-change, admin reset, and idle-timeout behaviours."""
import time
from config import Config
from models import db, User
from tests.conftest import login_token


def _mk(app, username, must_change=False):
    with app.app_context():
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(username=username, role='staff', scope='central', full_name=username)
            u.set_password('secret123'); u.must_change_password = must_change
            db.session.add(u); db.session.commit()
        return u.id


def _login(app, username, password='secret123'):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': password,
                           '_csrf_token': login_token(c)})
    return c


def _pt(c):
    import re
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get('/change-password').get_data(as_text=True)).group(1)


def test_force_password_change_redirects(app):
    _mk(app, 'mustchg', must_change=True)
    c = _login(app, 'mustchg')
    # any normal page bounces to change-password
    r = c.get('/students', follow_redirects=False)
    assert r.status_code in (302, 303) and '/change-password' in r.headers['Location']
    # after changing, access is restored
    c.post('/change-password', data={'current_password': 'secret123',
                                     'new_password': 'Newpass123',
                                     'confirm_password': 'Newpass123',
                                     '_csrf_token': _pt(c)}, follow_redirects=True)
    # dashboard is reachable now (no more forced bounce to change-password)
    assert c.get('/', follow_redirects=False).status_code == 200
    with app.app_context():
        assert User.query.filter_by(username='mustchg').first().must_change_password is False


def test_admin_reset_password(app):
    uid = _mk(app, 'resetme')
    c = app.test_client()
    import re
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    pt = re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                   c.get('/').get_data(as_text=True)).group(1)
    c.post(f'/users/{uid}/reset-password', data={'_csrf_token': pt}, follow_redirects=True)
    with app.app_context():
        u = User.query.get(uid)
        assert u.must_change_password is True
        assert not u.check_password('secret123')   # old password no longer valid


def test_idle_timeout_logs_out(app):
    uid = _mk(app, 'idler')
    c = app.test_client()
    with c.session_transaction() as s:
        s['logged_in'] = True
        s['user_id'] = uid
        s['role'] = 'staff'
        s['scope'] = 'central'
        s['last_seen'] = int(time.time()) - (Config.SESSION_IDLE_MINUTES * 60 + 120)
    r = c.get('/', follow_redirects=False)
    assert r.status_code in (302, 303) and '/login' in r.headers['Location']
