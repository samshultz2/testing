"""Reports section (React shells + JSON import)."""
import io
import re

from config import Config
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


def test_reports_pages_are_react_shells(app):
    client = _admin(app)
    pages = {'/reports/': 'index', '/reports/summary': 'summary',
             '/reports/export/class-students': 'export_class', '/reports/import/students': 'import'}
    for url, page in pages.items():
        html = client.get(url).get_data(as_text=True)
        assert 'reports-app' in html and 'reports-data' in html
        assert f'"page": "{page}"' in html


def test_import_students_json_rejects_bad_file(app):
    client = _admin(app)
    data = {'file': (io.BytesIO(b'not a spreadsheet'), 'notes.txt'), '_csrf_token': _ptoken(client)}
    r = client.post('/reports/import/students', headers={'X-Requested-With': 'fetch'},
                    data=data, content_type='multipart/form-data')
    assert r.status_code == 400 and r.get_json()['ok'] is False
