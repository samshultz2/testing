"""Communication Phase 3 — unified history timeline (filters + pagination) and
usage/delivery reports with export."""
import re

from config import Config
from models import db, Message, MessageRecipient, Announcement
from tests.conftest import login_token


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def _campaign(app, *, title, channel='SMS', status='Sent', sent=2, recip=3, by='Admin'):
    with app.app_context():
        m = Message(title=title, body='hi', channel=channel, audience='all',
                    audience_label='All parents', status=status, created_by=by,
                    recipient_count=recip, sent_count=sent)
        db.session.add(m)
        db.session.flush()
        for i in range(recip):
            db.session.add(MessageRecipient(message_id=m.id, parent_name=f'P{i}',
                                            phone=f'0800000{i:04d}',
                                            status='Sent' if i < sent else 'Failed'))
        db.session.commit()
        return m.id


# --- unified timeline -------------------------------------------------------
def test_history_page_renders_with_filters(app):
    client = _admin(app)
    html = client.get('/communication/messages').get_data(as_text=True)
    assert '"page": "messages"' in html
    for key in ('"items"', '"types"', '"statuses"', '"senders"', '"pages"'):
        assert key in html


def test_history_includes_campaigns_and_announcements(app):
    _campaign(app, title='HISTCAMP1', channel='SMS')
    with app.app_context():
        db.session.add(Announcement(title='HISTANN1', body='notice', created_by='Admin'))
        db.session.commit()
    client = _admin(app)
    body = client.get('/communication/messages').get_data(as_text=True)
    assert 'HISTCAMP1' in body and 'HISTANN1' in body


def test_history_type_filter_excludes_announcements(app):
    _campaign(app, title='HISTCAMP2', channel='Email')
    with app.app_context():
        db.session.add(Announcement(title='HISTANN2', body='x', created_by='Admin'))
        db.session.commit()
    client = _admin(app)
    body = client.get('/communication/messages?type=Email').get_data(as_text=True)
    assert 'HISTCAMP2' in body and 'HISTANN2' not in body


def test_history_search_filter(app):
    _campaign(app, title='ZZQ_UNIQUE_TITLE', channel='SMS')
    _campaign(app, title='OTHER_ONE', channel='SMS')
    client = _admin(app)
    body = client.get('/communication/messages?q=ZZQ_UNIQUE').get_data(as_text=True)
    assert 'ZZQ_UNIQUE_TITLE' in body and 'OTHER_ONE' not in body


def test_history_status_filter_hides_announcements(app):
    # A campaign-only status must exclude announcements from the timeline.
    with app.app_context():
        db.session.add(Announcement(title='HISTANN3', body='x', created_by='Admin'))
        db.session.commit()
    client = _admin(app)
    body = client.get('/communication/messages?status=Sent').get_data(as_text=True)
    assert 'HISTANN3' not in body


# --- reports ----------------------------------------------------------------
def test_reports_page_renders(app):
    _campaign(app, title='RPTCAMP1', channel='SMS', sent=2, recip=3)
    client = _admin(app)
    html = client.get('/communication/reports').get_data(as_text=True)
    assert '"page": "reports"' in html and '"data"' in html
    for key in ('total_campaigns', 'delivery_rate', 'by_channel', 'failed'):
        assert key in html


def test_reports_export_csv(app):
    _campaign(app, title='RPTCAMP2', channel='SMS')
    client = _admin(app)
    r = client.get('/communication/reports/export?format=csv')
    assert r.status_code == 200 and 'text/csv' in r.content_type
    text = r.get_data(as_text=True)
    assert 'Report period' in text and 'Delivery rate' in text and 'Channel' in text


def test_reports_export_xlsx(app):
    _campaign(app, title='RPTCAMP3', channel='SMS')
    client = _admin(app)
    r = client.get('/communication/reports/export?format=xlsx')
    assert r.status_code == 200
    assert 'spreadsheet' in r.content_type or 'excel' in r.content_type
