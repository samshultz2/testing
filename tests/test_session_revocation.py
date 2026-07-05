"""Server-side session revocation (users.token_version) and the common-password
blocklist. A password change / admin reset / deactivation must invalidate every
existing signed-cookie session for that user."""
from tests.conftest import login_token, auth_csrf

_FETCH = {'X-Requested-With': 'fetch'}
_PW = 'Str0ng!Passw0rd1'


def _mk_user(username, password=_PW):
    from models import db, User
    u = User(username=username, full_name=username, role='teacher', scope='branch',
             is_active=True, must_change_password=False)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return u.id


def _login(app, username, password=_PW):
    c = app.test_client()
    t = login_token(c)
    c.post('/login', data={'username': username, 'password': password, '_csrf_token': t})
    return c


def _alive(client):
    # A protected page renders (200) while the session is valid; once revoked the
    # gate bounces the request to the login page (302).
    return client.get('/students').status_code == 200


def _revoked(client):
    return client.get('/students').status_code == 302


def _cleanup(uid):
    from models import db, User
    with_ctx = db.session.get(User, uid)
    if with_ctx:
        db.session.delete(with_ctx)
        db.session.commit()


def test_bumping_token_version_revokes_existing_session(app):
    from models import db, User
    with app.app_context():
        uid = _mk_user('rev_user')
    try:
        c = _login(app, 'rev_user')
        assert _alive(c)                       # logged in
        with app.app_context():
            u = db.session.get(User, uid)
            u.revoke_sessions()                # e.g. admin "sign out everywhere"
            db.session.commit()
        # The old session cookie is now stale -> rejected.
        assert _revoked(c)
    finally:
        with app.app_context():
            _cleanup(uid)


def test_change_password_keeps_this_device_revokes_others(app):
    with app.app_context():
        uid = _mk_user('cp_user')
    try:
        c1 = _login(app, 'cp_user')            # device 1
        c2 = _login(app, 'cp_user')            # device 2
        assert _alive(c1) and _alive(c2)
        new_pw = 'Zebra!Mango42Q'
        tok = auth_csrf(c1)
        c1.post('/change-password',
                data={'current_password': _PW, 'new_password': new_pw,
                      'confirm_password': new_pw, '_csrf_token': tok})
        # Device 1 (who changed it) stays in; device 2 is signed out.
        assert _alive(c1)
        assert _revoked(c2)
    finally:
        with app.app_context():
            _cleanup(uid)


def test_deactivating_user_ends_session_immediately(app):
    from models import db, User
    with app.app_context():
        uid = _mk_user('deact_user')
    try:
        c = _login(app, 'deact_user')
        assert _alive(c)
        with app.app_context():
            u = db.session.get(User, uid)
            u.is_active = False
            db.session.commit()
        assert _revoked(c)
    finally:
        with app.app_context():
            from models import db as _db, User as _U
            u = _db.session.get(_U, uid)
            if u:
                _db.session.delete(u); _db.session.commit()


def test_common_passwords_are_rejected():
    from utils.security import is_password_strong
    for weak in ('Password123!', 'Qwerty@12345', 'Welcome@2024', 'Admin@123456', 'Letmein@2026'):
        ok, msg = is_password_strong(weak)
        assert not ok and 'common' in msg.lower(), weak
    # A genuinely unique passphrase still passes.
    ok, _ = is_password_strong('Zebra!Mango42Q')
    assert ok
