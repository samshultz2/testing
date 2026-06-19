"""Settings pages converted to the React shell (JSON-aware)."""
import re

from config import Config
from models import db, User, GradeScale
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


def test_settings_shells_render(app):
    client = _admin(app)
    for url, page in {
        '/settings/': 'index',
        '/settings/school': 'school',
        '/settings/academic': 'academic',
        '/settings/grades': 'grades',
        '/settings/traits': 'traits',
        '/settings/assessments': 'assessments',
        '/settings/timetable-slots': 'timetable_slots',
        '/settings/backup': 'backup',
        '/settings/branches': 'branches',
        '/settings/users': 'users',
        '/settings/users/add': 'add_user',
    }.items():
        html = client.get(url).get_data(as_text=True)
        assert 'settings-app' in html and 'settings-data' in html, url
        assert f'"page": "{page}"' in html, url


def test_edit_user_shell_renders(app):
    client = _admin(app)
    with app.app_context():
        u = User(username='shelluser', role='teacher', full_name='Shell User')
        u.set_password('secret123')
        db.session.add(u)
        db.session.commit()
        uid = u.id
    html = client.get(f'/settings/users/{uid}/edit').get_data(as_text=True)
    assert '"page": "edit_user"' in html and 'shelluser' in html


def test_add_user_json(app):
    client = _admin(app)
    r = client.post('/settings/users/add', headers={'X-Requested-With': 'fetch'},
                    data={'username': 'JsonUser', 'password': 'secret123',
                          'role': 'teacher', '_csrf_token': _ptoken(client)}).get_json()
    assert r['ok'] and r['redirect'].endswith('/settings/users')
    with app.app_context():
        assert User.query.filter_by(username='jsonuser').first() is not None


def test_save_grades_json(app):
    client = _admin(app)
    r = client.post('/settings/grades/save', headers={'X-Requested-With': 'fetch'},
                    data={'grade[]': ['A', 'F'], 'min_score[]': ['70', '0'],
                          'max_score[]': ['100', '39'], 'remark[]': ['Excellent', 'Fail'],
                          '_csrf_token': _ptoken(client)}).get_json()
    assert r['ok']
    with app.app_context():
        assert GradeScale.query.filter_by(grade='A').count() == 1
        assert GradeScale.query.filter_by(grade='F').count() == 1
