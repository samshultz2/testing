"""Audit-trail coverage: device/user-agent capture, user deletion logging,
salary old->new, and attendance-modification logging — the gaps closed after the
audit-of-audit review.
"""
from datetime import date, timedelta
from config import Config
from models import (db, Branch, User, StaffMember, AuditLog, AcademicSession, Term,
                    SchoolClass, ClassArm, ClassArmAssignment, Student,
                    StudentEnrollment, Week, Attendance)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _pt(c):
    import re
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get('/').get_data(as_text=True)).group(1)


# --- device / user-agent ----------------------------------------------------
def test_audit_captures_user_agent(app):
    c = _admin(app)
    ua = 'Mozilla/5.0 (AuditTestPhone) Chrome/9.9'
    # A throwaway user whose creation is audited, sent with a device UA header.
    c.post('/users/add', data={
        'username': 'ua_probe', 'password': 'Str0ng!Pass99',
        'confirm_password': 'Str0ng!Pass99', 'full_name': 'UA', 'role': 'teacher',
        '_csrf_token': _pt(c)}, headers={'User-Agent': ua}, follow_redirects=True)
    with app.app_context():
        row = (AuditLog.query.filter_by(action='user.create')
               .order_by(AuditLog.id.desc()).first())
        assert row is not None
        assert row.user_agent and 'AuditTestPhone' in row.user_agent
        assert row.ip_address is not None and row.created_at is not None


# --- user deletion ----------------------------------------------------------
def test_user_deletion_is_audited(app):
    with app.app_context():
        u = User.query.filter_by(username='del_target').first()
        if not u:
            u = User(username='del_target', full_name='Del Target', role='teacher',
                     scope='branch', branch_id=Branch.get_default().id, rank=5)
            u.set_password('secret123'); db.session.add(u); db.session.commit()
        uid = u.id
    c = _admin(app)
    c.post(f'/users/{uid}/delete', data={'_csrf_token': _pt(c)}, follow_redirects=True)
    with app.app_context():
        assert User.query.get(uid) is None                 # actually deleted
        row = (AuditLog.query.filter_by(action='user.delete')
               .order_by(AuditLog.id.desc()).first())
        assert row is not None and 'del_target' in (row.detail or '')
        assert row.target_id == uid


# --- salary old -> new ------------------------------------------------------
def test_salary_change_audits_old_and_new(app):
    with app.app_context():
        s = StaffMember.query.filter_by(staff_id='AUD-STF1').first()
        if not s:
            s = StaffMember(staff_id='AUD-STF1', first_name='Sal', surname='Ary',
                            branch_id=Branch.get_default().id, salary=100000)
            db.session.add(s); db.session.commit()
        sid = s.id
    c = _admin(app)
    c.post(f'/hr/staff/{sid}/salary', data={
        'new_salary': '150000', '_csrf_token': _pt(c)}, follow_redirects=True)
    with app.app_context():
        row = (AuditLog.query.filter_by(action='hr.salary_adjust')
               .order_by(AuditLog.id.desc()).first())
        assert row is not None
        # old and new both present
        assert '100,000' in row.detail and '150,000' in row.detail and '→' in row.detail


# --- attendance modification ------------------------------------------------
def _att_setup(app):
    with app.app_context():
        if Student.query.filter_by(student_id='AUD-AT1').first():
            t = Term.query.filter_by(name='AUD-Term').first()
            caa = ClassArmAssignment.query.filter_by(term_id=t.id).first()
            en = StudentEnrollment.query.filter_by(class_arm_assignment_id=caa.id).first()
            wk = Week.query.filter_by(term_id=t.id).first()
            return dict(asg=caa.id, en=en.id, week=wk.id)
        bid = Branch.get_default().id
        ses = AcademicSession(name='AUD-Sess'); db.session.add(ses); db.session.flush()
        start = date.today() - timedelta(days=20); end = date.today() + timedelta(days=20)
        t = Term(session_id=ses.id, term_number=1, name='AUD-Term',
                 start_date=start, end_date=end, is_active=True)
        db.session.add(t); db.session.flush()
        wk = Week(term_id=t.id, week_number=1, start_date=start, end_date=end)
        db.session.add(wk); db.session.flush()
        sc = SchoolClass.query.first(); arm = ClassArm.query.first()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=t.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        st = Student(student_id='AUD-AT1', first_name='A', surname='T', gender='Male',
                     is_active=True, branch_id=bid)
        db.session.add(st); db.session.flush()
        en = StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True)
        db.session.add(en); db.session.commit()
        return dict(asg=caa.id, en=en.id, week=wk.id)


def _mark(c, ids, d):
    return c.post('/attendance/mark/save', data={
        'assignment_id': ids['asg'], 'date': d.isoformat(), 'session_type': 'morning',
        'week_id': ids['week'], 'present[]': [ids['en']], '_csrf_token': _pt(c)},
        follow_redirects=True)


def _att_log_count(app):
    with app.app_context():
        return AuditLog.query.filter(
            AuditLog.action.in_(['attendance.modified', 'attendance.backdated'])).count()


def test_attendance_overwrite_is_audited(app):
    ids = _att_setup(app)
    c = _admin(app)
    # A markable in-term weekday (today if it's a weekday, else the nearest past one).
    d = date.today()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    _mark(c, ids, d)                       # establish a register for this date
    before = _att_log_count(app)
    _mark(c, ids, d)                       # re-save over the existing register
    after = _att_log_count(app)
    # The overwrite is audited — as attendance.modified for a current date, or
    # attendance.backdated if the run day forced a past date. Either way, logged.
    assert after > before
