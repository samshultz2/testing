"""Internal staff messaging (inbox) + campaign read-receipts."""
import re

from config import Config
from models import (db, User, StaffMember, Conversation, ChatMessage,
                    MessageRecipient, Notification)
from tests.conftest import login_token


def _user(app, username, **kw):
    with app.app_context():
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(username=username, role=kw.get('role', 'admin'), is_active=True,
                     full_name=kw.get('full_name', username.title()))
            u.set_password('pw-' + username)
            db.session.add(u); db.session.commit()
        return u.id


def _login(app, username):
    client = app.test_client()
    tok = login_token(client)
    client.post('/login', data={'username': username, 'password': 'pw-' + username,
                                '_csrf_token': tok})
    return client


def _ptoken(client):
    html = client.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


# --- chat service -----------------------------------------------------------
def test_direct_conversation_is_deduped(app):
    from utils import chat
    a = _user(app, 'chatA'); b = _user(app, 'chatB')
    with app.app_context():
        c1 = chat.get_or_create_direct(a, b)
        c2 = chat.get_or_create_direct(b, a)   # same pair, reversed
        assert c1.id == c2.id
        assert chat.get_or_create_direct(a, a) is None   # not with yourself


def test_post_and_unread_and_read(app):
    from utils import chat
    a = _user(app, 'chatC'); b = _user(app, 'chatD')
    with app.app_context():
        c = chat.get_or_create_direct(a, b)
        chat.post_message(c.id, a, 'hello')
        assert chat.total_unread(b) == 1
        assert chat.total_unread(a) == 0          # sender's own message isn't unread
        chat.mark_read(c.id, b)
        assert chat.total_unread(b) == 0
        # the other side sees the sender's name as the conversation title
        assert chat.conversations_for(b)[0]['title'] == 'Chatc'


def test_group_conversation(app):
    from utils import chat
    a = _user(app, 'grpA'); b = _user(app, 'grpB'); c = _user(app, 'grpC')
    with app.app_context():
        g = chat.create_group(a, [b, c], 'Committee')
        assert g.kind == 'group' and g.members.count() == 3
        chat.post_message(g.id, a, 'welcome all')
        assert chat.total_unread(b) == 1 and chat.total_unread(c) == 1


# --- inbox routes -----------------------------------------------------------
def test_inbox_start_and_send_flow(app):
    a = _user(app, 'inboxA'); b = _user(app, 'inboxB')
    client = _login(app, 'inboxA')
    tok = _ptoken(client)
    r = client.post('/communication/inbox/start', headers={'X-Requested-With': 'fetch'},
                    data={'user_ids': b, '_csrf_token': tok}).get_json()
    assert r['ok'] and '/communication/inbox/' in r['redirect']
    conv_id = int(r['redirect'].rstrip('/').split('/')[-1])
    s = client.post(f'/communication/inbox/{conv_id}/send', headers={'X-Requested-With': 'fetch'},
                    data={'body': 'hi there', '_csrf_token': tok}).get_json()
    assert s['ok']
    with app.app_context():
        assert ChatMessage.query.filter_by(conversation_id=conv_id).count() == 1


def test_inbox_non_member_blocked(app):
    a = _user(app, 'insiderA'); b = _user(app, 'insiderB'); intruder = _user(app, 'intruderX')
    from utils import chat
    with app.app_context():
        conv = chat.get_or_create_direct(a, b)
        cid = conv.id
    client = _login(app, 'intruderX')
    r = client.post(f'/communication/inbox/{cid}/send', headers={'X-Requested-With': 'fetch'},
                    data={'body': 'sneak', '_csrf_token': _ptoken(client)})
    assert r.status_code == 400   # not a member


def test_inbox_user_search_excludes_self(app):
    a = _user(app, 'searchselfA')
    client = _login(app, 'searchselfA')
    rows = client.get('/communication/inbox/users?q=searchself').get_json()
    assert all(u['id'] != a for u in rows)


# --- read receipts ----------------------------------------------------------
def test_inapp_read_receipt_marks_recipient(app):
    from utils import comms, notify
    from flask import session
    uid = _user(app, 'rcptStaff', role='teacher')
    with app.app_context():
        if not StaffMember.query.filter_by(staff_id='RCPT1').first():
            db.session.add(StaffMember(staff_id='RCPT1', first_name='R', surname='Cpt',
                                       staff_type='Teaching', is_active=True, user_id=uid))
            db.session.commit()
    with app.test_request_context('/'):
        session['role'] = 'admin'; session['scope'] = 'central'
        m = comms.build_campaign('read me', channel='In-app',
                                 spec={'to': 'staff', 'staff_scope': 'all'},
                                 title='RR', created_by='admin')
        mid = m.id
    with app.app_context():
        rec = MessageRecipient.query.filter_by(message_id=mid,
                                               parent_name=None).first() \
            or MessageRecipient.query.filter_by(message_id=mid).filter(
                MessageRecipient.email.is_(None)).first()
        # find the recipient tied to our staff user via its notification
        n = Notification.query.filter(Notification.origin_recipient_id.isnot(None),
                                      Notification.user_id == uid).first()
        assert n is not None
        rec = db.session.get(MessageRecipient, n.origin_recipient_id)
        assert rec.read_at is None
        notify.mark_read(uid, 'teacher', n.id)
        db.session.refresh(rec)
        assert rec.read_at is not None


def test_reports_include_read_metrics(app):
    client = app.test_client()
    tok = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    html = client.get('/communication/reports').get_data(as_text=True)
    assert '"read"' in html and 'read_rate' in html


# --- email open-tracking ----------------------------------------------------
def test_open_token_roundtrip(app):
    from utils import comms
    with app.test_request_context('/'):
        tok = comms.open_token(4242)
        assert comms.read_open_token(tok) == 4242
        assert comms.read_open_token('tampered') is None


def test_open_pixel_marks_read_unauthenticated(app):
    from models import Message, MessageRecipient
    from utils import comms
    with app.app_context():
        m = Message(title='E', body='hi', channel='Email', status='Sent', recipient_count=1)
        db.session.add(m); db.session.flush()
        r = MessageRecipient(message_id=m.id, email='p@ex.com', body='hi', status='Sent')
        db.session.add(r); db.session.commit()
        rid = r.id
    with app.test_request_context('/'):
        token = comms.open_token(rid)
    client = app.test_client()   # no login — an email client isn't authenticated
    resp = client.get('/communication/track/open?t=' + token)
    assert resp.status_code == 200 and resp.mimetype == 'image/gif'
    with app.app_context():
        assert db.session.get(MessageRecipient, rid).read_at is not None
    # a bad token still returns the pixel, never errors
    assert client.get('/communication/track/open?t=nope').status_code == 200


def test_email_dispatch_embeds_tracking_pixel(app, monkeypatch):
    from utils import comms, mailer
    from models import Message, MessageRecipient
    captured = {}
    monkeypatch.setattr(mailer, 'send_email',
                        lambda to, subject, body, html=None, attachments=None:
                        (captured.update(html=html) or True))
    with app.app_context():
        m = Message(title='Open me', body='hello', channel='Email', status='Sending',
                    recipient_count=1)
        db.session.add(m); db.session.flush()
        db.session.add(MessageRecipient(message_id=m.id, email='p@ex.com', body='hello',
                                        status='Pending'))
        db.session.commit()
        comms.dispatch_campaign_email(m, base_url='https://school.example/')
        assert captured['html'] and '/communication/track/open?t=' in captured['html']


def test_bundle_url_is_versioned(app):
    # The React bundle must be served with a cache-busting version query so a
    # rebuilt bundle reaches clients instead of a stale cached copy.
    client = app.test_client()
    tok = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    html = client.get('/communication/').get_data(as_text=True)
    import re
    assert re.search(r'js/react/comms-app\.js\?v=\d+', html)
