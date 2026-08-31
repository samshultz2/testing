"""Communication pages converted to the React shell (JSON-aware, no-reload)."""
import re

from config import Config
from models import db, MessageTemplate, Announcement
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


def test_comms_shells_render(app):
    client = _admin(app)
    for url, page in {
        '/communication/': 'dashboard',
        '/communication/compose': 'compose',
        '/communication/announcements': 'announcements',
        '/communication/templates': 'templates',
        '/communication/contacts': 'contacts',
        '/communication/messages': 'messages',
        '/communication/settings': 'settings',
    }.items():
        html = client.get(url).get_data(as_text=True)
        assert 'comm-app' in html and 'comm-data' in html, url
        assert f'"page": "{page}"' in html, url


def test_template_json_create_and_delete(app):
    client = _admin(app)
    token = _ptoken(client)
    r = client.post('/communication/templates/add', headers={'X-Requested-With': 'fetch'},
                    data={'name': 'JSON Tpl', 'body': 'Hi {first_name}', 'category': 'Fees',
                          '_csrf_token': token}).get_json()
    assert r['ok']
    with app.app_context():
        t = MessageTemplate.query.filter_by(name='JSON Tpl').first()
        assert t is not None and t.body == 'Hi {first_name}'
        tid = t.id
    d = client.post(f'/communication/templates/{tid}/delete', headers={'X-Requested-With': 'fetch'},
                    data={'_csrf_token': token}).get_json()
    assert d['ok']
    with app.app_context():
        assert MessageTemplate.query.get(tid) is None


def test_announcement_json_create(app):
    client = _admin(app)
    r = client.post('/communication/announcements/add', headers={'X-Requested-With': 'fetch'},
                    data={'title': 'Sports Day', 'category': 'Event', 'audience': 'All',
                          '_csrf_token': _ptoken(client)}).get_json()
    assert r['ok']
    with app.app_context():
        assert Announcement.query.filter_by(title='Sports Day').first() is not None


def test_announcement_requires_title(app):
    client = _admin(app)
    r = client.post('/communication/announcements/add', headers={'X-Requested-With': 'fetch'},
                    data={'title': '  ', '_csrf_token': _ptoken(client)})
    assert r.status_code == 400 and 'Title is required' in r.get_json()['error']
