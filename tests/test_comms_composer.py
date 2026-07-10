"""Communication Phase 1 — unified composer (email as a first-class channel),
the shared build_campaign refactor, channel-aware preview, and the actionable
dashboard stats."""
import re

from config import Config
from models import db, Student, ParentContact, Message, MessageRecipient
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


def _student_with(app, sid, *, phone='08099990000', email=None, active=True):
    with app.app_context():
        s = Student.query.filter_by(student_id=sid).first()
        if not s:
            s = Student(student_id=sid, first_name='Comp', surname='Oser',
                        gender='Male', is_active=active)
            db.session.add(s)
            db.session.flush()
            db.session.add(ParentContact(student_id=s.id, phone_number=phone,
                                         email=email, name='Parent', is_primary=True))
            db.session.commit()
        return s.id


# --- shared builder ---------------------------------------------------------
def test_build_campaign_sms_and_email_reachability(app):
    from utils import comms
    _student_with(app, 'COMPSMS1', phone='08111100001', email=None)
    _student_with(app, 'COMPEML1', phone='08111100002', email='p@ex.com')
    with app.test_request_context('/'):
        from flask import session
        session['role'] = 'admin'; session['scope'] = 'central'
        # Email channel only reaches the parent that has an address.
        m = comms.build_campaign('Hi {first_name}', channel='Email', audience='all',
                                 title='Blast', created_by='t')
        assert m is not None and m.channel == 'Email'
        emails = [r.email for r in m.recipients.all()]
        assert 'p@ex.com' in emails
        assert all(e for e in emails)   # every email-channel recipient has an address


def test_reachable_targets_helper(app):
    from utils import comms
    targets = [{'phone': '080', 'email': ''}, {'phone': '', 'email': 'a@b.com'},
               {'phone': '081', 'email': 'c@d.com'}]
    assert len(comms.reachable_targets(targets, 'SMS')) == 2
    assert len(comms.reachable_targets(targets, 'Email')) == 2
    assert comms.channel_is_email('Email') and not comms.channel_is_email('SMS')


# --- composer route: email is a first-class channel -------------------------
def test_compose_offers_email_channel(app):
    client = _admin(app)
    html = client.get('/communication/compose').get_data(as_text=True)
    assert '"channels"' in html and 'Email' in html
    assert '"email_ready"' in html


def test_compose_preselects_channel_from_query(app):
    client = _admin(app)
    html = client.get('/communication/compose?channel=Email').get_data(as_text=True)
    assert '"pre_channel": "Email"' in html


def test_compose_creates_email_campaign(app):
    _student_with(app, 'COMPEML2', phone='08111100003', email='mail2@ex.com')
    client = _admin(app)
    tok = _ptoken(client)
    r = client.post('/communication/compose', headers={'X-Requested-With': 'fetch'},
                    data={'audience': 'all', 'channel': 'Email', 'title': 'Term news',
                          'body': 'Dear {parent}, hello.', '_csrf_token': tok}).get_json()
    assert r['ok']
    with app.app_context():
        m = Message.query.filter_by(title='Term news', channel='Email').first()
        assert m is not None
        assert m.recipients.filter(MessageRecipient.email.isnot(None)).count() >= 1


def test_compose_email_with_no_addresses_errors(app):
    # A specific student with a phone but no email can't be reached by Email.
    sid = _student_with(app, 'COMPNOEML', phone='08111100004', email=None)
    client = _admin(app)
    tok = _ptoken(client)
    r = client.post('/communication/compose', headers={'X-Requested-With': 'fetch'},
                    data={'audience': 'students', 'student_ids': sid, 'channel': 'Email',
                          'body': 'hi', '_csrf_token': tok})
    assert r.status_code == 400
    assert 'email address' in r.get_json()['error']


def test_compose_preview_is_channel_aware(app):
    _student_with(app, 'COMPPRE1', phone='08111100005', email='prev@ex.com')
    client = _admin(app)
    tok = _ptoken(client)
    j = client.post('/communication/compose/preview', headers={'X-Requested-With': 'fetch'},
                    data={'audience': 'all', 'channel': 'Email', 'body': 'Hi {first_name}',
                          '_csrf_token': tok}).get_json()
    assert 'reachable' in j and j.get('by_email') is True


# --- actionable dashboard ---------------------------------------------------
def test_dashboard_exposes_pipeline_stats(app):
    client = _admin(app)
    html = client.get('/communication/').get_data(as_text=True)
    assert '"stats"' in html
    for key in ('sent_today', 'scheduled', 'drafts', 'failed', 'success_rate'):
        assert key in html
    assert '"compose_email"' in html and '"compose_sms"' in html
