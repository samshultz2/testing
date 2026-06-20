"""In-app notifications: helper creates them, the API lists/marks-read, scoped
to the current user (their own + role broadcasts)."""
from config import Config
from models import db, User, Notification
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _ptoken(c):
    import re
    html = c.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def test_notify_admins_appears_for_admin(app):
    with app.app_context():
        from utils.notify import notify_admins
        notify_admins('Test broadcast', 'Body here', url='/students', category='success')
    c = _admin(app)
    j = c.get('/api/notifications').get_json()
    assert j['count'] >= 1
    assert any(it['title'] == 'Test broadcast' for it in j['items'])


def test_mark_read_and_read_all(app):
    with app.app_context():
        from utils.notify import notify_admins
        notify_admins('Mark me', 'x')
    c = _admin(app)
    before = c.get('/api/notifications').get_json()
    nid = next(it['id'] for it in before['items'] if it['title'] == 'Mark me')
    assert c.post(f'/api/notifications/{nid}/read', headers={'X-CSRFToken': _ptoken(c)}).status_code == 204
    # read-all clears the rest
    r = c.post('/api/notifications/read-all', headers={'X-CSRFToken': _ptoken(c)}).get_json()
    assert r['cleared'] >= 0
    assert c.get('/api/notifications').get_json()['count'] == 0


def test_notifications_require_login(app):
    assert app.test_client().get('/api/notifications', follow_redirects=False).status_code in (302, 303)
