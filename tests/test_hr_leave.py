"""HR Phase 3 — leave allowances, balances, calendar data and approve/reject
notifications."""
import re
from datetime import date, timedelta

from config import Config
from models import db, StaffMember, LeaveRecord, User, SchoolSettings, Notification
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


def test_default_allowances_and_override(app):
    from utils import hr as hr_utils
    with app.app_context():
        a = hr_utils.leave_allowances()
        assert a['Annual'] == 20 and a['Sick'] == 12
        SchoolSettings.set('hr_leave_allow_Annual', '25', 'int', 'x')
        db.session.commit()
        assert hr_utils.leave_allowances()['Annual'] == 25


def test_leave_balances_counts_only_approved(app):
    from utils import hr as hr_utils
    with app.app_context():
        s = StaffMember(staff_id='LVB1', first_name='Bal', surname='Zzance', is_active=True)
        db.session.add(s); db.session.flush()
        yr = date.today().year
        db.session.add(LeaveRecord(staff_id=s.id, leave_type='Annual',
                                   start_date=date(yr, 2, 1), end_date=date(yr, 2, 6),
                                   days=6, status='Approved'))
        db.session.add(LeaveRecord(staff_id=s.id, leave_type='Annual',
                                   start_date=date(yr, 3, 1), end_date=date(yr, 3, 3),
                                   days=3, status='Pending'))   # not counted
        db.session.commit()
        bals = {b['type']: b for b in hr_utils.leave_balances(s.id, yr)}
        assert bals['Annual']['taken'] == 6
        assert bals['Annual']['remaining'] == bals['Annual']['allowance'] - 6


def test_save_leave_allowances_via_settings(app):
    client = _admin(app)
    tok = _ptoken(client)
    r = client.post('/hr/settings/save', headers={'X-Requested-With': 'fetch'},
                    data={'late_time': '07:30', 'late_rate': '10', 'absence_deduction': '0',
                          'leave_allow_Annual': '30', 'leave_allow_Sick': '15',
                          '_csrf_token': tok}).get_json()
    assert r['ok']
    with app.app_context():
        from utils import hr as hr_utils
        a = hr_utils.leave_allowances()
        assert a['Annual'] == 30 and a['Sick'] == 15


def test_leave_list_exposes_calendar_dates(app):
    with app.app_context():
        s = StaffMember(staff_id='LVCAL1', first_name='Cal', surname='Zzendar', is_active=True)
        db.session.add(s); db.session.flush()
        db.session.add(LeaveRecord(staff_id=s.id, leave_type='Casual',
                                   start_date=date.today(), end_date=date.today() + timedelta(days=2),
                                   days=3, status='Approved'))
        db.session.commit()
    client = _admin(app)
    html = client.get('/hr/leave').get_data(as_text=True)
    assert '"page": "leave"' in html
    assert '"start":' in html and '"end":' in html   # ISO dates for the calendar


def test_approve_notifies_linked_staff_user(app):
    with app.app_context():
        u = User(username='leaveuser', full_name='Leave User', role='teacher',
                 password_hash='x', is_active=True)
        db.session.add(u); db.session.flush()
        s = StaffMember(staff_id='LVNOT1', first_name='Note', surname='Zzuser',
                        user_id=u.id, is_active=True)
        db.session.add(s); db.session.flush()
        lv = LeaveRecord(staff_id=s.id, leave_type='Annual',
                         start_date=date.today() + timedelta(days=5),
                         end_date=date.today() + timedelta(days=7), days=3, status='Pending')
        db.session.add(lv); db.session.commit()
        lid, uid = lv.id, u.id
        before = Notification.query.filter_by(user_id=uid).count()
    client = _admin(app)
    tok = _ptoken(client)
    r = client.post(f'/hr/leave/{lid}/status', headers={'X-Requested-With': 'fetch'},
                    data={'status': 'Approved', '_csrf_token': tok}).get_json()
    assert r['ok']
    with app.app_context():
        after = Notification.query.filter_by(user_id=uid).filter(
            Notification.title == 'Leave approved').count()
        assert after >= 1


def test_add_leave_notifies_branch_admins(app):
    """Submitting a leave request should alert admins (branch-scoped, same
    pattern as notify_staff_change) so it doesn't sit unseen as Pending.
    notify_branch_admins() addresses real admin User rows individually (not
    a role broadcast) when a branch_id is given, so one must exist for this
    branch for a notification to land at all -- see notify_staff_change's
    own tests for the same requirement."""
    with app.app_context():
        from models import Branch
        b = Branch(name='ZzLeaveNotifyBranch', code=None)
        db.session.add(b); db.session.flush()
        bid = b.id
        admin_u = User(username='zzleaveadmin', full_name='Branch Admin', role='admin',
                      branch_id=bid, password_hash='x', is_active=True)
        db.session.add(admin_u); db.session.flush()
        admin_uid = admin_u.id
        s = StaffMember(staff_id='LVNOTADM1', first_name='Needs', surname='Zzapproval',
                        branch_id=bid, is_active=True)
        db.session.add(s); db.session.commit()
        sid = s.id
    client = _admin(app)
    tok = _ptoken(client)
    start = date.today() + timedelta(days=10)
    end = start + timedelta(days=2)
    r = client.post('/hr/leave/add', headers={'X-Requested-With': 'fetch'},
                    data={'staff_id': str(sid), 'leave_type': 'Annual',
                          'start_date': start.isoformat(), 'end_date': end.isoformat(),
                          '_csrf_token': tok}).get_json()
    assert r['ok']
    with app.app_context():
        lv = LeaveRecord.query.filter_by(staff_id=sid).first()
        assert lv is not None and lv.status == 'Pending'
        notes = Notification.query.filter(
            Notification.title == 'Leave request submitted', Notification.user_id == admin_uid).all()
        # StaffMember.full_name is "surname first_name" (see the model property).
        assert any('Zzapproval Needs' in (n.body or '') and 'LVNOTADM1' in (n.body or '')
                  for n in notes)


def test_disabling_leave_requested_automation_skips_notification(app):
    with app.app_context():
        from models import Branch
        from utils import automations
        automations.set_enabled('leave_requested', False)
        b = Branch(name='ZzLeaveNotifyOffBranch', code=None)
        db.session.add(b); db.session.flush()
        bid = b.id
        # An admin who WOULD be notified if the toggle were on -- proves the
        # absence of a notification is the toggle, not just no recipient.
        db.session.add(User(username='zzleaveadminoff', full_name='Branch Admin Off',
                            role='admin', branch_id=bid, password_hash='x', is_active=True))
        s = StaffMember(staff_id='LVNOTOFF1', first_name='Quiet', surname='Zzrequest',
                        branch_id=bid, is_active=True)
        db.session.add(s); db.session.commit()
        sid = s.id
    try:
        client = _admin(app)
        tok = _ptoken(client)
        start = date.today() + timedelta(days=12)
        r = client.post('/hr/leave/add', headers={'X-Requested-With': 'fetch'},
                        data={'staff_id': str(sid), 'leave_type': 'Casual',
                              'start_date': start.isoformat(), 'end_date': start.isoformat(),
                              '_csrf_token': tok}).get_json()
        assert r['ok']
        with app.app_context():
            notes = Notification.query.filter(
                Notification.title == 'Leave request submitted',
                Notification.body.like('%Zzrequest Quiet%')).all()
            assert not notes
    finally:
        with app.app_context():
            from utils import automations
            automations.set_enabled('leave_requested', True)


def test_profile_exposes_leave_balances(app):
    with app.app_context():
        s = StaffMember(staff_id='LVPRO1', first_name='Pro', surname='Zzbal', is_active=True)
        db.session.add(s); db.session.commit()
        sid = s.id
    client = _admin(app)
    html = client.get(f'/hr/staff/{sid}').get_data(as_text=True)
    assert '"leave_balances"' in html
