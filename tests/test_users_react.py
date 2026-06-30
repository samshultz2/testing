"""User management pages converted to the React shell (JSON-aware)."""
import re

from config import Config
from models import db, User
from tests.conftest import login_token


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def _ptoken(client):
    html = client.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def test_users_shells_render(app):
    client = _admin(app)
    for url, page in {
        '/users/': 'index',
        '/users/matrix': 'matrix',
        '/users/add': 'add',
    }.items():
        html = client.get(url).get_data(as_text=True)
        assert 'users-app' in html and 'users-data' in html, url
        assert f'"page": "{page}"' in html, url


def test_view_and_edit_shells_render(app):
    client = _admin(app)
    with app.app_context():
        u = User(username='ushelluser', full_name='Shell User', role='teacher')
        u.set_password('secret123')
        db.session.add(u)
        db.session.commit()
        uid = u.id
    vhtml = client.get(f'/users/{uid}').get_data(as_text=True)
    assert '"page": "view"' in vhtml and 'ushelluser' in vhtml
    ehtml = client.get(f'/users/{uid}/edit').get_data(as_text=True)
    assert '"page": "edit"' in ehtml and '"permission_map"' in ehtml


def test_add_user_json(app):
    client = _admin(app)
    r = client.post('/users/add', headers={'X-Requested-With': 'fetch'},
                    data={'username': 'ujsonteacher', 'password': 'Secret123!ab',
                          'confirm_password': 'Secret123!ab', 'role': 'teacher',
                          'scope': 'branch', '_csrf_token': _ptoken(client)}).get_json()
    assert r['ok'] and r['redirect'].endswith('/users/')
    with app.app_context():
        u = User.query.filter_by(username='ujsonteacher').first()
        assert u is not None and u.is_teacher


def test_add_user_password_mismatch_json(app):
    client = _admin(app)
    r = client.post('/users/add', headers={'X-Requested-With': 'fetch'},
                    data={'username': 'umismatch', 'password': 'Secret123!ab',
                          'confirm_password': 'nope', 'role': 'teacher',
                          '_csrf_token': _ptoken(client)})
    assert r.status_code == 400 and 'match' in r.get_json()['error'].lower()


def test_toggle_status_json(app):
    client = _admin(app)
    with app.app_context():
        u = User(username='utoggleme', full_name='Toggle', role='staff', is_active=True)
        u.set_password('secret123')
        db.session.add(u)
        db.session.commit()
        uid = u.id
    r = client.post(f'/users/{uid}/toggle-status', headers={'X-Requested-With': 'fetch'},
                    data={'_csrf_token': _ptoken(client)}).get_json()
    assert r['ok']
    with app.app_context():
        assert db.session.get(User, uid).is_active is False
