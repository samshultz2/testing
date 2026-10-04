"""Finalizing/paying a payroll run, and recording a job application or
scheduling an interview, should alert the branch's admins -- same
notify_branch_admins pattern as the rest of HR, gated by the
'payroll_run'/'recruitment_activity' automation toggles."""
from datetime import date

from config import Config
from models import db, Branch, StaffMember, PayrollRun, Notification, User
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return c


def _post(c, url, **data):
    data.setdefault('_csrf_token', 'a' * 64)
    return c.post(url, data=data)


def _add_default_branch_admin(username):
    bid = Branch.get_default().id
    u = User(username=username, full_name='Payroll Branch Admin', role='admin',
            branch_id=bid, password_hash='x', is_active=True)
    db.session.add(u); db.session.commit()
    return u.id, bid


def test_finalize_payroll_notifies_branch_admins(app):
    with app.app_context():
        admin_uid, bid = _add_default_branch_admin('zzpayrollfinalize')
        s = StaffMember(staff_id='PRN001', first_name='Pay', surname='Zznotify',
                        branch_id=bid, salary=100000, is_active=True, status='Active')
        db.session.add(s)
        run = PayrollRun(year=2099, month=7, status='Draft', branch_id=bid)
        db.session.add(run); db.session.commit()
        run_id = run.id

    c = _admin(app)
    r = _post(c, f'/hr/payroll/{run_id}/finalize')
    assert r.status_code in (200, 302)
    with app.app_context():
        run = db.session.get(PayrollRun, run_id)
        assert run.status == 'Finalized'
        notes = Notification.query.filter_by(title='Payroll finalized', user_id=admin_uid).all()
        assert notes, 'expected a bell notification when payroll was finalized'


def test_mark_paid_notifies_branch_admins(app):
    with app.app_context():
        admin_uid, bid = _add_default_branch_admin('zzpayrollpaid')
        run = PayrollRun(year=2099, month=8, status='Finalized', branch_id=bid)
        db.session.add(run); db.session.commit()
        run_id = run.id

    c = _admin(app)
    r = _post(c, f'/hr/payroll/{run_id}/mark-paid')
    assert r.status_code in (200, 302)
    with app.app_context():
        run = db.session.get(PayrollRun, run_id)
        assert run.status == 'Paid'
        notes = Notification.query.filter_by(title='Payroll marked paid', user_id=admin_uid).all()
        assert notes, 'expected a bell notification when payroll was marked paid'


def test_disabling_payroll_run_automation_skips_notification(app):
    with app.app_context():
        from utils import automations
        automations.set_enabled('payroll_run', False)
        admin_uid, bid = _add_default_branch_admin('zzpayrolloff')
        run = PayrollRun(year=2099, month=9, status='Draft', branch_id=bid)
        db.session.add(run); db.session.commit()
        run_id = run.id
    try:
        c = _admin(app)
        r = _post(c, f'/hr/payroll/{run_id}/finalize')
        assert r.status_code in (200, 302)
        with app.app_context():
            notes = Notification.query.filter_by(user_id=admin_uid).all()
            assert not notes
    finally:
        with app.app_context():
            from utils import automations
            automations.set_enabled('payroll_run', True)


def test_recording_application_notifies_branch_admins(app):
    with app.app_context():
        from models import JobVacancy, Department
        admin_uid, bid = _add_default_branch_admin('zzrecruitapp')
        v = JobVacancy(branch_id=bid, title='ZzMaths Teacher', status='Open')
        db.session.add(v); db.session.commit()
        vac_id = v.id

    c = _admin(app)
    r = _post(c, f'/hr/recruitment/{vac_id}/applications/add',
             first_name='Jane', surname='Zzcandidate')
    assert r.status_code in (200, 302)
    with app.app_context():
        notes = Notification.query.filter_by(title='Job application recorded', user_id=admin_uid).all()
        assert notes
        assert any('Zzcandidate' in (n.body or '') and 'ZzMaths Teacher' in (n.body or '')
                  for n in notes)


def test_scheduling_interview_notifies_branch_admins(app):
    with app.app_context():
        from models import JobVacancy, JobApplication
        admin_uid, bid = _add_default_branch_admin('zzrecruitintv')
        v = JobVacancy(branch_id=bid, title='ZzBiology Teacher', status='Open')
        db.session.add(v); db.session.flush()
        a = JobApplication(vacancy_id=v.id, first_name='Tom', surname='Zzinterviewee', status='Applied')
        db.session.add(a); db.session.commit()
        app_id = a.id

    c = _admin(app)
    r = _post(c, f'/hr/applications/{app_id}/interview', scheduled_at='2099-07-01T10:00',
             mode='In-person', location='Room 2')
    assert r.status_code in (200, 302)
    with app.app_context():
        notes = Notification.query.filter_by(title='Interview scheduled', user_id=admin_uid).all()
        assert notes
        assert any('Zzinterviewee' in (n.body or '') for n in notes)


def test_disabling_recruitment_automation_skips_notification(app):
    with app.app_context():
        from utils import automations
        from models import JobVacancy
        automations.set_enabled('recruitment_activity', False)
        admin_uid, bid = _add_default_branch_admin('zzrecruitoff')
        v = JobVacancy(branch_id=bid, title='ZzQuiet Role', status='Open')
        db.session.add(v); db.session.commit()
        vac_id = v.id
    try:
        c = _admin(app)
        r = _post(c, f'/hr/recruitment/{vac_id}/applications/add',
                 first_name='Silent', surname='Zzapplicant')
        assert r.status_code in (200, 302)
        with app.app_context():
            notes = Notification.query.filter_by(user_id=admin_uid).all()
            assert not notes
    finally:
        with app.app_context():
            from utils import automations
            automations.set_enabled('recruitment_activity', True)
