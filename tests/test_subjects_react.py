"""Subject-management pages converted to the React shell (JSON-aware)."""
import re

from config import Config
from models import db, Subject
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


def test_subject_shells_render(app):
    client = _admin(app)
    for url, page in {
        '/subjects/': 'list',
        '/subjects/add': 'add',
        '/subjects/bulk-add': 'bulk_add',
        '/subjects/class-subjects': 'class_subjects',
        '/subjects/class-subjects/assign': 'assign',
        '/subjects/scores': 'scores',
        '/subjects/workflow': 'workflow',
        '/subjects/bulk-entry': 'bulk_entry',
        '/subjects/broadsheet': 'broadsheet',
        '/subjects/affective': 'affective',
        '/subjects/comments': 'comments',
    }.items():
        html = client.get(url).get_data(as_text=True)
        assert 'subj-app' in html and 'subj-data' in html, url
        assert f'"page": "{page}"' in html, url


def test_add_subject_json(app):
    client = _admin(app)
    r = client.post('/subjects/add', headers={'X-Requested-With': 'fetch'},
                    data={'name': 'Robotics 101', 'category': 'Vocational',
                          '_csrf_token': _ptoken(client)}).get_json()
    assert r['ok'] and r['redirect'].endswith('/subjects/')
    with app.app_context():
        s = Subject.query.filter_by(name='Robotics 101').first()
        assert s is not None and s.category == 'Vocational'


def test_add_subject_requires_name_and_rejects_dupe(app):
    client = _admin(app)
    token = _ptoken(client)
    assert client.post('/subjects/add', headers={'X-Requested-With': 'fetch'},
                       data={'name': '  ', '_csrf_token': token}).status_code == 400
    client.post('/subjects/add', headers={'X-Requested-With': 'fetch'},
                data={'name': 'Dupe Subject', '_csrf_token': token})
    r = client.post('/subjects/add', headers={'X-Requested-With': 'fetch'},
                    data={'name': 'Dupe Subject', '_csrf_token': token})
    assert r.status_code == 400 and 'already exists' in r.get_json()['error']


def test_edit_subject_shell_then_delete(app):
    client = _admin(app)
    token = _ptoken(client)
    client.post('/subjects/add', headers={'X-Requested-With': 'fetch'},
                data={'name': 'Temp Subject', '_csrf_token': token})
    with app.app_context():
        sid = Subject.query.filter_by(name='Temp Subject').first().id
    html = client.get(f'/subjects/{sid}/edit').get_data(as_text=True)
    assert '"page": "edit"' in html
    r = client.post(f'/subjects/{sid}/delete', headers={'X-Requested-With': 'fetch'},
                    data={'_csrf_token': token}).get_json()
    assert r['ok']
    with app.app_context():
        assert Subject.query.get(sid).is_active is False
