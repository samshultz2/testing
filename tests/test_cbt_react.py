"""CBT admin pages converted to the React shell (JSON-aware, no-reload)."""
import re

from config import Config
from models import db, CBTExam
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


def test_cbt_shells_render(app):
    client = _admin(app)
    for url, page in {
        '/cbt/': 'dashboard',
        '/cbt/settings': 'settings',
        '/cbt/lab-setup': 'lab_setup',
        '/cbt/exams/add': 'exam_form',
    }.items():
        html = client.get(url).get_data(as_text=True)
        assert 'cbt-app' in html and 'cbt-data' in html, url
        assert f'"page": "{page}"' in html, url


def test_add_exam_json_then_results_shell(app):
    client = _admin(app)
    r = client.post('/cbt/exams/add', headers={'X-Requested-With': 'fetch'},
                    data={'title': 'React CBT', 'access_password': 'go123',
                          'exam_date': '2026-06-20', 'duration_minutes': 20,
                          '_csrf_token': _ptoken(client)}).get_json()
    assert r['ok'] and '/cbt/exams/' in r['redirect']
    with app.app_context():
        e = CBTExam.query.filter_by(title='React CBT').first()
        assert e is not None and e.access_password == 'go123'
        eid = e.id
    html = client.get(f'/cbt/exams/{eid}/results').get_data(as_text=True)
    assert '"page": "results"' in html


def test_add_exam_requires_title_and_password(app):
    client = _admin(app)
    r = client.post('/cbt/exams/add', headers={'X-Requested-With': 'fetch'},
                    data={'title': '', 'access_password': '', '_csrf_token': _ptoken(client)})
    assert r.status_code == 400 and 'required' in r.get_json()['error']


def test_settings_save_json(app):
    client = _admin(app)
    r = client.post('/cbt/settings', headers={'X-Requested-With': 'fetch'},
                    data={'supervisor_pin': '4827', '_csrf_token': _ptoken(client)}).get_json()
    assert r['ok']
    with app.app_context():
        from models import SchoolSettings
        assert SchoolSettings.get('cbt_supervisor_pin', '') == '4827'
