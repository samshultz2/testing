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


def test_add_event_notifies_admins(app):
    from models import Notification
    client = _admin(app)
    r = client.post('/events/add', headers={'X-Requested-With': 'fetch'},
                    data={'title': 'ZzNotify Founders Day', 'start_date': date.today().isoformat(),
                          'category': 'Activity', 'location': 'Main Hall',
                          '_csrf_token': _ptoken(client)})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        notes = Notification.query.filter_by(title='Event added', role='admin').all()
        assert any('ZzNotify Founders Day' in (n.body or '') and 'Main Hall' in (n.body or '')
                  for n in notes)


def test_disabling_event_added_automation_skips_notification(app):
    from models import Notification
    from utils import automations
    with app.app_context():
        automations.set_enabled('event_added', False)
    try:
        client = _admin(app)
        r = client.post('/events/add', headers={'X-Requested-With': 'fetch'},
                        data={'title': 'ZzQuiet Event', 'start_date': date.today().isoformat(),
                              '_csrf_token': _ptoken(client)})
        assert r.status_code == 200 and r.get_json()['ok']
        with app.app_context():
            notes = Notification.query.filter_by(title='Event added', role='admin').filter(
                Notification.body.like('%ZzQuiet Event%')).all()
            assert not notes
    finally:
        with app.app_context():
            automations.set_enabled('event_added', True)


def test_duplicate_event_to_new_date_and_ics_export(app):
    client = _admin(app)
    client.post('/events/add', headers={'X-Requested-With': 'fetch'},
                data={'title': 'PTA, Term 1', 'start_date': '2026-01-10', 'end_date': '2026-01-11',
                      'category': 'Meeting', '_csrf_token': _ptoken(client)})
    with app.app_context():
        src = SchoolEvent.query.filter_by(title='PTA, Term 1').first()
        sid = src.id
    r = client.post(f'/events/{sid}/duplicate', headers={'X-Requested-With': 'fetch'},
                    data={'start_date': '2026-05-02', '_csrf_token': _ptoken(client)})
    assert r.status_code == 200
    with app.app_context():
        copies = SchoolEvent.query.filter_by(title='PTA, Term 1').order_by(SchoolEvent.id).all()
        assert len(copies) == 2
        assert copies[1].start_date == date(2026, 5, 2) and copies[1].end_date == date(2026, 5, 3)
    ics = client.get('/events/calendar.ics')
    body = ics.get_data(as_text=True)
    assert ics.status_code == 200 and 'text/calendar' in ics.content_type
    assert 'BEGIN:VCALENDAR' in body and 'SUMMARY:PTA\\, Term 1' in body
