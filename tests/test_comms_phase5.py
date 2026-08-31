"""Communication Phase 5 — in-app notification channel + announcement
read-acknowledgement."""
import re

from config import Config
from models import (db, StaffMember, Notification, Message, MessageRecipient,
                    Announcement, AnnouncementAck, User)
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


# --- in-app channel ---------------------------------------------------------
def _staff_user(app, sid):
    with app.app_context():
        u = User.query.filter_by(username=f'u_{sid}').first()
        if not u:
            u = User(username=f'u_{sid}', role='teacher', is_active=True,
                     password_hash='x')
            db.session.add(u)
            db.session.flush()
        s = StaffMember.query.filter_by(staff_id=sid).first()
        if not s:
            s = StaffMember(staff_id=sid, first_name='In', surname='App',
                            staff_type='Teaching', is_active=True, user_id=u.id)
            db.session.add(s)
            db.session.commit()
        return u.id


def test_inapp_reachability_needs_user_account(app):
    from utils import comms
    assert comms.channel_is_inapp('In-app') is True
    targets = [{'user_id': 5, 'phone': '', 'email': ''},
               {'user_id': None, 'phone': '080', 'email': ''}]
    assert len(comms.reachable_targets(targets, 'In-app')) == 1


def test_inapp_campaign_delivers_bell_notification(app):
    from utils import comms
    uid = _staff_user(app, 'INAPP01')
    with app.test_request_context('/'):
        from flask import session
        session['role'] = 'admin'; session['scope'] = 'central'
        before = Notification.query.filter_by(user_id=uid).count()
        msg = comms.build_campaign('Staff meeting at 3pm', channel='In-app',
                                   spec={'to': 'staff', 'staff_scope': 'all'},
                                   title='Meeting', created_by='admin')
        assert msg is not None and msg.channel == 'In-app'
        assert msg.status == 'Sent' and msg.sent_count >= 1
        # a bell notification landed for the linked user, recipient marked Sent
        assert Notification.query.filter_by(user_id=uid).count() == before + 1
        assert msg.recipients.filter_by(status='Sent').count() == msg.recipient_count


def test_compose_offers_inapp_for_admin(app):
    client = _admin(app)
    html = client.get('/communication/compose').get_data(as_text=True)
    assert 'In-app' in html and '"channels"' in html


def test_inapp_campaign_send_is_rejected(app):
    # An already-delivered in-app campaign can't be "sent" via the gateway route.
    uid = _staff_user(app, 'INAPP02')
    with app.app_context():
        m = Message(title='X', body='hi', channel='In-app', status='Sent',
                    recipient_count=1, sent_count=1)
        db.session.add(m); db.session.commit(); mid = m.id
    client = _admin(app)
    with client.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    r = client.post(f'/communication/messages/{mid}/send-gateway',
                    data={'_csrf_token': 'a' * 64}, follow_redirects=False)
    assert r.status_code in (302, 303)   # redirected with an error, not dispatched


# --- announcement acknowledgement -------------------------------------------
def test_announcement_needs_ack_persisted(app):
    client = _admin(app)
    tok = _ptoken(client)
    r = client.post('/communication/announcements/add',
                    headers={'X-Requested-With': 'fetch'},
                    data={'title': 'ACKANN1', 'needs_ack': 'on', '_csrf_token': tok}).get_json()
    assert r['ok']
    with app.app_context():
        a = Announcement.query.filter_by(title='ACKANN1').first()
        assert a is not None and a.needs_ack is True


def test_acknowledge_announcement_is_idempotent(app):
    # Acknowledgement is per real user, so create one and log in through the real
    # login flow (which establishes the full authenticated session).
    with app.app_context():
        u = User.query.filter_by(username='acker1').first()
        if not u:
            u = User(username='acker1', role='admin', is_active=True)
            u.set_password('ackerpass1')
            db.session.add(u); db.session.commit()
        a = Announcement(title='ACKANN2', needs_ack=True, created_by='Admin')
        db.session.add(a); db.session.commit(); aid = a.id
    client = app.test_client()
    tok = login_token(client)
    client.post('/login', data={'username': 'acker1', 'password': 'ackerpass1',
                                '_csrf_token': tok})
    ptok = _ptoken(client)
    for _ in range(2):     # acking twice creates exactly one row
        rr = client.post(f'/communication/announcements/{aid}/ack',
                         headers={'X-Requested-With': 'fetch'},
                         data={'_csrf_token': ptok}).get_json()
        assert rr and rr['ok']
    with app.app_context():
        assert AnnouncementAck.query.filter_by(announcement_id=aid).count() == 1


def test_announcements_list_shows_ack_count(app):
    with app.app_context():
        a = Announcement(title='ACKANN3', needs_ack=True, created_by='Admin')
        db.session.add(a); db.session.commit()
    client = _admin(app)
    body = client.get('/communication/announcements').get_data(as_text=True)
    assert '"needs_ack"' in body and '"ack_count"' in body
