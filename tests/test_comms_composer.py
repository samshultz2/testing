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


# --- Phase 2: unified recipient engine --------------------------------------
def _staff(app, sid, *, phone='08120000000', email=None, staff_type='Teaching', dept=None):
    from models import StaffMember
    with app.app_context():
        s = StaffMember.query.filter_by(staff_id=sid).first()
        if not s:
            s = StaffMember(staff_id=sid, first_name='St', surname=sid, phone=phone,
                            email=email, staff_type=staff_type, department_id=dept,
                            is_active=True)
            db.session.add(s)
            db.session.commit()
        return s.id


def test_resolve_recipients_staff(app):
    from utils import comms
    _staff(app, 'RCSTAFF1', phone='08120000101', email='t@ex.com', staff_type='Teaching')
    _staff(app, 'RCSTAFF2', phone='08120000102', staff_type='Non-teaching')
    with app.test_request_context('/'):
        from flask import session
        session['role'] = 'admin'; session['scope'] = 'central'
        allt = comms.resolve_recipients({'to': 'staff', 'staff_scope': 'all'})
        names = {t['name'] for t in allt}
        assert any('RCSTAFF1' in n for n in names) and any('RCSTAFF2' in n for n in names)
        teach = comms.resolve_recipients({'to': 'staff', 'staff_scope': 'teaching'})
        assert all(t['staff'].staff_type == 'Teaching' for t in teach)
        # Every staff target exposes phone/email for channel-aware reach.
        assert all('phone' in t and 'email' in t for t in allt)


def test_resolve_recipients_parent_filters_and_exclude(app):
    from utils import comms
    from models import Student
    _student_with(app, 'RCP_M', phone='08120000201', email=None)
    _student_with(app, 'RCP_F', phone='08120000202', email=None)
    with app.app_context():
        m = Student.query.filter_by(student_id='RCP_M').first(); m.gender = 'Male'
        f = Student.query.filter_by(student_id='RCP_F').first(); f.gender = 'Female'
        db.session.commit()
        mid, fid = m.id, f.id
    with app.test_request_context('/'):
        from flask import session
        session['role'] = 'admin'; session['scope'] = 'central'
        males = comms.resolve_recipients({'to': 'parents', 'audience': 'all', 'gender': 'Male'})
        ids = {t['student'].id for t in males}
        assert mid in ids and fid not in ids
        # excluding the male student removes him
        excl = comms.resolve_recipients({'to': 'parents', 'audience': 'all', 'gender': 'Male',
                                         'exclude_ids': [mid]})
        assert mid not in {t['student'].id for t in excl}


def test_compose_staff_campaign_as_admin(app):
    _staff(app, 'RCSTAFF3', phone='08120000103', email='s3@ex.com')
    client = _admin(app)
    tok = _ptoken(client)
    r = client.post('/communication/compose', headers={'X-Requested-With': 'fetch'},
                    data={'to': 'staff', 'staff_scope': 'all', 'channel': 'SMS',
                          'title': 'Staff notice', 'body': 'Dear {name}, meeting at 4pm.',
                          '_csrf_token': tok}).get_json()
    assert r['ok']
    with app.app_context():
        m = Message.query.filter_by(title='Staff notice').first()
        assert m is not None and m.recipients.count() >= 1
        # staff recipients carry no student_id
        assert m.recipients.first().student_id is None


# --- Phase 2: saved recipient groups ----------------------------------------
def test_save_and_reload_recipient_group(app):
    from models import RecipientGroup
    client = _admin(app)
    tok = _ptoken(client)
    r = client.post('/communication/groups/save', headers={'X-Requested-With': 'fetch'},
                    data={'name': 'Owing SS3', 'to': 'parents', 'audience': 'defaulters',
                          'gender': 'Male', '_csrf_token': tok}).get_json()
    assert r['ok']
    with app.app_context():
        g = RecipientGroup.query.filter_by(name='Owing SS3').first()
        assert g is not None
        spec = g.spec_dict()
        assert spec['audience'] == 'defaulters' and spec['gender'] == 'Male'
        gid = g.id
    # the compose page exposes saved groups
    html = client.get('/communication/compose').get_data(as_text=True)
    assert 'Owing SS3' in html and '"groups"' in html
    d = client.post(f'/communication/groups/{gid}/delete', headers={'X-Requested-With': 'fetch'},
                    data={'_csrf_token': tok}).get_json()
    assert d['ok']
    with app.app_context():
        assert RecipientGroup.query.get(gid) is None


def test_compose_prefills_specific_students_and_body(app):
    """Deep-link from results ('Message parents') pre-selects the students and a
    drafted body, with the audience switched to the specific-students mode."""
    client = _admin(app)
    sid = _student_with(app, 'PREFILL-1')
    html = client.get(f'/communication/compose?students={sid}&body=Please+see+the+teacher').get_data(as_text=True)
    assert '"pre_students"' in html
    assert 'Oser' in html and 'Comp' in html        # the student label is embedded
    assert '"pre_audience": "students"' in html
    assert 'Please see the teacher' in html         # drafted body carried over


def test_compose_prefills_specific_staff(app):
    """'Message this teacher' deep-link pre-selects a specific staff member and
    switches the composer to staff mode (admin only)."""
    from models import db, StaffMember, Branch
    client = _admin(app)
    with app.app_context():
        bid = Branch.get_default().id
        st = StaffMember(first_name='Grace', surname='Ade', staff_type='Teaching',
                         is_active=True, branch_id=bid)
        db.session.add(st); db.session.commit()
        sid = st.id
    html = client.get(f'/communication/compose?to=staff&staff_ids={sid}&body=Please+see+me').get_data(as_text=True)
    assert '"pre_staff"' in html
    assert 'Grace' in html and 'Ade' in html
    assert '"pre_to": "staff"' in html
