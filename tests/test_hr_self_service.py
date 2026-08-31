"""Self-scope HR permissions — the finest permission tier.

A user can be granted access to ONLY their own record: view own attendance and
clock themselves in, view own payslips, view own deductions (read-only) — without
any HR-module access to other staff. Enforced in the backend, not just hidden.
"""
from datetime import date
from flask import session
from config import Config
from models import (db, User, StaffMember, Branch, StaffAttendance,
                    PayrollRun, Payslip, PayslipDeduction)
from tests.conftest import login_token, auth_csrf


def _linked_staff_user(app, username, perms):
    """A 'staff' user linked to a StaffMember, granted `perms`, with a finalized
    payslip (+deduction) and one attendance row of their own."""
    with app.app_context():
        bid = Branch.get_default().id
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(username=username, full_name=username.title(), role='staff',
                     scope='branch', branch_id=bid)
            u.set_password('CorrectHorse9')
            db.session.add(u); db.session.flush()
        u.set_password('CorrectHorse9')
        u.is_active = True
        u.set_permissions(perms)
        s = StaffMember.query.filter_by(user_id=u.id).first()
        if not s:
            s = StaffMember(first_name='Self', surname=username.title(), is_active=True,
                            status='Active', staff_type='Teaching', branch_id=bid,
                            user_id=u.id, salary=100000)
            db.session.add(s); db.session.flush()
        if not StaffAttendance.query.filter_by(staff_id=s.id, date=date.today()).first():
            db.session.add(StaffAttendance(staff_id=s.id, date=date.today(),
                                           status='Present', clock_in='07:55'))
        run = PayrollRun.query.filter_by(year=2025, month=3, branch_id=bid).first()
        if not run:
            run = PayrollRun(year=2025, month=3, branch_id=bid, status='Finalized')
            db.session.add(run); db.session.flush()
        slip = Payslip.query.filter_by(run_id=run.id, staff_id=s.id).first()
        if not slip:
            slip = Payslip(run_id=run.id, staff_id=s.id, staff_name=s.full_name,
                           basic=100000, allowances=20000, deductions=5000, net=110000)
            db.session.add(slip); db.session.flush()
            db.session.add(PayslipDeduction(payslip_id=slip.id, name='Pension', amount=8000))
        db.session.commit()
        return u.id, s.id


def test_self_caps_registered_and_are_capabilities(app):
    from utils.access_control import (CAPABILITY_SUBSECTIONS, SELF_SCOPE_SUBSECTIONS,
                                      MODULE_SUBSECTIONS)
    assert SELF_SCOPE_SUBSECTIONS <= CAPABILITY_SUBSECTIONS       # never unlock the module
    for k in ('self_attendance', 'self_payroll', 'self_deductions'):
        assert k in MODULE_SUBSECTIONS['hr']                     # surfaced in the editor


def test_self_payroll_only_sees_own_payslips_not_module(app):
    uid, sid = _linked_staff_user(app, 'ss_pay', {'hr.self_payroll': 'view'})
    with app.test_request_context('/'):
        session['logged_in'] = True
        session['user_id'] = uid
        session['role'] = 'staff'
        from utils.access_control import can_access_module, self_scope_level
        from utils.hr import hr_self_service
        # The capability does NOT grant HR-module access (can't browse other staff).
        assert can_access_module('hr') is False
        assert self_scope_level('hr.self_payroll') == 'view'
        data = hr_self_service(db.session.get(User, uid))
        assert data is not None
        assert data['payslips'] and data['payslips'][0]['net'] == 110000
        # Only the granted section is populated.
        assert data['attendance'] is None and data['deductions'] is None
        assert data['can_clock'] is False


def test_self_attendance_edit_can_clock_view_cannot(app):
    # View-only self-attendance: sees own record, cannot clock in.
    uid_v, _ = _linked_staff_user(app, 'ss_att_v', {'hr.self_attendance': 'view'})
    with app.test_request_context('/'):
        session.update(logged_in=True, user_id=uid_v, role='staff')
        from utils.access_control import self_scope_level
        from utils.hr import hr_self_service
        assert self_scope_level('hr.self_attendance') == 'view'
        d = hr_self_service(db.session.get(User, uid_v))
        assert d['attendance'] is not None and d['can_clock'] is False


def test_clock_endpoint_enforces_edit_and_marks_own(app):
    uid, sid = _linked_staff_user(app, 'ss_clock', {'hr.self_attendance': 'edit'})
    # Wipe today's row so the clock creates it fresh.
    with app.app_context():
        StaffAttendance.query.filter_by(staff_id=sid, date=date.today()).delete()
        db.session.commit()
    c = app.test_client()
    c.post('/login', data={'username': 'ss_clock', 'password': 'CorrectHorse9',
                           '_csrf_token': login_token(c)})
    r = c.post('/hr/clock', data={'_csrf_token': auth_csrf(c)}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        rec = StaffAttendance.query.filter_by(staff_id=sid, date=date.today()).first()
        assert rec is not None and rec.clock_in       # own attendance was recorded


def test_self_leave_shows_own_balances_and_records(app):
    from models import LeaveRecord
    from datetime import date, timedelta
    uid, sid = _linked_staff_user(app, 'ss_leave', {'hr.self_leave': 'view'})
    with app.app_context():
        if not LeaveRecord.query.filter_by(staff_id=sid).first():
            db.session.add(LeaveRecord(staff_id=sid, leave_type='Annual',
                                       start_date=date.today(), end_date=date.today() + timedelta(days=2),
                                       days=3, status='Approved'))
            db.session.commit()
    with app.test_request_context('/'):
        session.update(logged_in=True, user_id=uid, role='staff')
        from utils.access_control import can_access_module
        from utils.hr import hr_self_service
        assert can_access_module('hr') is False
        d = hr_self_service(db.session.get(User, uid))
        assert d['leave'] is not None and d['leave_balances'] is not None
        assert d['payslips'] is None and d['attendance'] is None   # only leave granted


def test_self_loans_shows_own_balance_not_module(app):
    from models import StaffLoan
    from datetime import date
    uid, sid = _linked_staff_user(app, 'ss_loans', {'hr.self_loans': 'view'})
    with app.app_context():
        if not StaffLoan.query.filter_by(staff_id=sid).first():
            db.session.add(StaffLoan(staff_id=sid, principal=50000, total_repayable=55000,
                                     monthly_amount=5000, amount_repaid=15000, months=11,
                                     status='active', date_taken=date.today()))
            db.session.commit()
    with app.test_request_context('/'):
        session.update(logged_in=True, user_id=uid, role='staff')
        from utils.access_control import can_access_module
        from utils.hr import hr_self_service
        assert can_access_module('hr') is False
        d = hr_self_service(db.session.get(User, uid))
        assert d['loans'] and d['loans'][0]['outstanding'] == 40000   # 55000 - 15000
        assert d['payslips'] is None and d['leave'] is None           # only loans granted


def test_self_documents_own_only_and_download_boundary(app):
    """A holder lists + downloads only their OWN documents; another staff's
    document id 404s, and no capability is a hard 403."""
    from models import StaffDocument
    uid, sid = _linked_staff_user(app, 'ss_docs', {'hr.self_documents': 'view'})
    other_uid, other_sid = _linked_staff_user(app, 'ss_docs_other', {'hr.self_documents': 'view'})
    with app.app_context():
        mine = StaffDocument(staff_id=sid, title='My Contract', doc_type='Employment contract',
                             is_current=True)
        theirs = StaffDocument(staff_id=other_sid, title='Their Contract', is_current=True)
        db.session.add_all([mine, theirs]); db.session.commit()
        my_doc_id, their_doc_id = mine.id, theirs.id
    # Assembler lists only the caller's own document.
    with app.test_request_context('/'):
        session.update(logged_in=True, user_id=uid, role='staff')
        from utils.hr import hr_self_service
        d = hr_self_service(db.session.get(User, uid))
        titles = {x['title'] for x in d['documents']}
        assert 'My Contract' in titles and 'Their Contract' not in titles
    # HTTP download authorization.
    c = app.test_client()
    c.post('/login', data={'username': 'ss_docs', 'password': 'CorrectHorse9',
                           '_csrf_token': login_token(c)})
    own = c.get(f'/hr/me/documents/{my_doc_id}')
    other = c.get(f'/hr/me/documents/{their_doc_id}')
    assert own.status_code == 404 and b'File not found' in own.data     # passed cap+ownership
    assert other.status_code == 404 and b'File not found' not in other.data  # blocked at ownership

    # A user without the capability is refused outright.
    nocap_uid, _ = _linked_staff_user(app, 'ss_docs_nocap', {'students': 'view'})
    c2 = app.test_client()
    c2.post('/login', data={'username': 'ss_docs_nocap', 'password': 'CorrectHorse9',
                            '_csrf_token': login_token(c2)})
    assert c2.get(f'/hr/me/documents/{my_doc_id}').status_code == 403


def test_clock_toggles_in_then_out(app):
    uid, sid = _linked_staff_user(app, 'ss_toggle', {'hr.self_attendance': 'edit'})
    with app.app_context():
        StaffAttendance.query.filter_by(staff_id=sid, date=date.today()).delete()
        db.session.commit()
    c = app.test_client()
    c.post('/login', data={'username': 'ss_toggle', 'password': 'CorrectHorse9',
                           '_csrf_token': login_token(c)})
    c.post('/hr/clock', data={'_csrf_token': auth_csrf(c)}, follow_redirects=True)   # in
    c.post('/hr/clock', data={'_csrf_token': auth_csrf(c)}, follow_redirects=True)   # out
    with app.app_context():
        rec = StaffAttendance.query.filter_by(staff_id=sid, date=date.today()).first()
        assert rec is not None and rec.clock_in and rec.clock_out   # both stamped


def test_clock_refused_without_edit_capability(app):
    uid, sid = _linked_staff_user(app, 'ss_noclock', {'hr.self_attendance': 'view'})
    c = app.test_client()
    c.post('/login', data={'username': 'ss_noclock', 'password': 'CorrectHorse9',
                           '_csrf_token': login_token(c)})
    before = None
    with app.app_context():
        StaffAttendance.query.filter_by(staff_id=sid, date=date.today()).delete()
        db.session.commit()
    r = c.post('/hr/clock', data={'_csrf_token': auth_csrf(c)}, follow_redirects=True)
    # View-only self-attendance may not clock in; no row is created.
    with app.app_context():
        assert StaffAttendance.query.filter_by(staff_id=sid, date=date.today()).first() is None
