"""Events & Calendar (React shells + JSON actions)."""
import re
from datetime import date

from config import Config
from models import db, SchoolEvent
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


def test_events_pages_are_react_shells(app):
    client = _admin(app)
    pages = {'/events/': 'calendar', '/events/list': 'agenda',
             '/events/add': 'event_form', '/events/import': 'import'}
    for url, page in pages.items():
        html = client.get(url).get_data(as_text=True)
        assert 'events-app' in html and 'events-data' in html
        assert f'"page": "{page}"' in html


def test_add_event_json(app):
    client = _admin(app)
    r = client.post('/events/add', headers={'X-Requested-With': 'fetch'},
                    data={'title': 'JSON Founders Day', 'start_date': date.today().isoformat(),
                          'category': 'Activity', '_csrf_token': _ptoken(client)})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        assert SchoolEvent.query.filter_by(title='JSON Founders Day').first() is not None
