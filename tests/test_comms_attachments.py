"""Communication attachments — upload/download, validation, and wiring into
announcements and email campaigns."""
import io
import os
import re

from config import Config
from models import db, Announcement, Message, MessageRecipient, CommAttachment
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


def _make_attachment(app, name='note.txt', data=b'hello world'):
    from werkzeug.datastructures import FileStorage
    from utils import comm_attachments as CA
    with app.app_context():
        fs = FileStorage(stream=io.BytesIO(data), filename=name, content_type='text/plain')
        att = CA.save(fs, created_by='tester')
        return att.id


def _cleanup(app, att_id):
    from utils import comm_attachments as CA
    with app.app_context():
        att = db.session.get(CommAttachment, att_id)
        if att:
            CA.delete(att)


# --- upload / download / validation -----------------------------------------
def test_upload_and_download_roundtrip(app):
    client = _admin(app)
    tok = _ptoken(client)
    r = client.post('/communication/attachments',
                    data={'file': (io.BytesIO(b'%PDF-1.4 hi'), 'circular.pdf')},
                    content_type='multipart/form-data',
                    headers={'X-Requested-With': 'fetch', 'X-CSRFToken': tok}).get_json()
    assert r['ok'] and r['attachment']['name'] == 'circular.pdf'
    aid = r['attachment']['id']
    with app.app_context():
        from utils import comm_attachments as CA
        att = db.session.get(CommAttachment, aid)
        assert att is not None and CA.fs_path(att) is not None
    # download streams it back as an attachment
    dl = client.get(r['attachment']['url'])
    assert dl.status_code == 200
    assert 'circular.pdf' in dl.headers.get('Content-Disposition', '')
    _cleanup(app, aid)


def test_upload_rejects_bad_extension(app):
    client = _admin(app)
    tok = _ptoken(client)
    r = client.post('/communication/attachments',
                    data={'file': (io.BytesIO(b'MZ...'), 'evil.exe')},
                    content_type='multipart/form-data',
                    headers={'X-Requested-With': 'fetch', 'X-CSRFToken': tok})
    assert r.status_code == 400
    assert 'not allowed' in r.get_json()['error']


# --- announcement attachment ------------------------------------------------
def test_announcement_carries_attachment(app):
    aid = _make_attachment(app, 'newsletter.pdf', b'%PDF-1.4')
    client = _admin(app)
    tok = _ptoken(client)
    r = client.post('/communication/announcements/add',
                    headers={'X-Requested-With': 'fetch'},
                    data={'title': 'ATTACHANN', 'attachment_id': aid,
                          '_csrf_token': tok}).get_json()
    assert r['ok']
    with app.app_context():
        a = Announcement.query.filter_by(title='ATTACHANN').first()
        assert a is not None and a.attachment_id == aid
    body = client.get('/communication/announcements').get_data(as_text=True)
    assert 'newsletter.pdf' in body and '"attachment"' in body
    _cleanup(app, aid)


# --- email campaign attachment ----------------------------------------------
def test_build_campaign_stores_attachment_for_email(app):
    from models import Student, ParentContact
    from utils import comms
    aid = _make_attachment(app, 'invoice.pdf', b'%PDF-1.4')
    with app.app_context():
        s = Student(student_id='ATTMAIL1', first_name='At', surname='Tach',
                    gender='Male', is_active=True)
        db.session.add(s); db.session.flush()
        db.session.add(ParentContact(student_id=s.id, phone_number='08123400001',
                                     email='att@ex.com', is_primary=True))
        db.session.commit()
    with app.test_request_context('/'):
        from flask import session
        session['role'] = 'admin'; session['scope'] = 'central'
        msg = comms.build_campaign('Hi', channel='Email', audience='all',
                                   title='Billing', attachment_id=aid, created_by='t')
        assert msg is not None and msg.attachment_id == aid
    # a non-email channel must NOT carry the attachment
    with app.test_request_context('/'):
        from flask import session
        session['role'] = 'admin'; session['scope'] = 'central'
        sms = comms.build_campaign('Hi', channel='SMS', audience='all',
                                   title='SmsNoAtt', attachment_id=aid, created_by='t')
        assert sms is not None and sms.attachment_id is None
    _cleanup(app, aid)


def test_email_dispatch_sends_attachment(app, monkeypatch):
    from utils import comms, mailer
    aid = _make_attachment(app, 'report.txt', b'the report')
    captured = {}
    monkeypatch.setattr(mailer, 'send_email',
                        lambda to, subject, body, html=None, attachments=None:
                        (captured.update(attachments=attachments) or True))
    with app.app_context():
        m = Message(title='Report out', body='hi', channel='Email', status='Sending',
                    recipient_count=1, attachment_id=aid)
        db.session.add(m); db.session.flush()
        db.session.add(MessageRecipient(message_id=m.id, parent_name='P',
                                        email='p@ex.com', body='hi', status='Pending'))
        db.session.commit()
        s, f = comms.dispatch_campaign_email(m)
        assert (s, f) == (1, 0)
        assert captured['attachments'] and captured['attachments'][0][1] == 'report.txt'
    _cleanup(app, aid)
