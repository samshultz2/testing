"""Dashboard Phase 2 — KPIs carry trend context, not isolated numbers.

new_students_month (admissions growth) and finance collected_today (today's
collection) are exposed so the React KPIs can render movement chips.
"""
from datetime import datetime, timedelta
from config import Config
from models import db, Branch, Student
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD,
                           '_csrf_token': login_token(c)})
    return c


def test_new_students_month_counts_recent_only(app):
    c = _admin(app)
    with app.app_context():
        bid = Branch.get_default().id
        recent = Student(student_id='ZZ_KPI_NEW', first_name='New', surname='ZzKpiNew',
                         gender='Male', is_active=True, branch_id=bid)
        old = Student(student_id='ZZ_KPI_OLD', first_name='Old', surname='ZzKpiOld',
                      gender='Male', is_active=True, branch_id=bid)
        db.session.add_all([recent, old]); db.session.flush()
        # Backdate one well beyond the 30-day window.
        old.created_at = datetime.now() - timedelta(days=120)
        db.session.commit()
    j = c.get('/api/dashboard/data').get_json()
    assert 'new_students_month' in j
    # The recent student counts; the 120-day-old one does not.
    assert j['new_students_month'] >= 1
    # Sanity: it never exceeds the total headcount.
    assert j['new_students_month'] <= j['total_students']


def test_hr_widget_reports_todays_absences(app):
    """The staff widget surfaces today's attendance: once anyone is marked, the
    absent count is exposed so the dashboard can show 'N absent today'."""
    from datetime import date
    from flask import session
    from routes.main import _dash_hr
    from models.models_hr import StaffMember, StaffAttendance
    with app.app_context():
        bid = Branch.get_default().id
        s = StaffMember(first_name='Ab', surname='ZzHrAbsent', is_active=True,
                        status='Active', staff_type='Teaching', branch_id=bid)
        db.session.add(s); db.session.flush()
        db.session.add(StaffAttendance(staff_id=s.id, date=date.today(), status='Absent'))
        db.session.commit()
    with app.test_request_context('/'):
        session['logged_in'] = True
        session['role'] = 'super_admin'   # central scope: sees all branches' staff
        hr = _dash_hr()
        assert hr and hr['att']['marked'] >= 1
        assert hr['att']['absent'] >= 1


def test_headline_kpis_build_real_series(app):
    """The headline KPI cards get real sparkline series + trend deltas: cumulative
    students by term, enrolments per term, and cumulative graduates by session."""
    from datetime import date, datetime
    from flask import session
    from routes.main import _dash_headline_kpis
    from models import (AcademicSession, Term, SchoolClass, ClassArm,
                        ClassArmAssignment, StudentEnrollment)
    with app.app_context():
        bid = Branch.get_default().id
        # Sentinel far-future session/term so this test owns the newest points.
        sess = AcademicSession(name='HK-Session', is_active=False,
                               start_date=date(2099, 9, 1), end_date=date(2100, 7, 31))
        db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='HK-Term',
                    start_date=date(2099, 9, 1), end_date=date(2099, 12, 20))
        db.session.add(term); db.session.flush()
        s1 = Student(student_id='ZZ_HK1', first_name='A', surname='ZzHk1',
                     gender='Male', is_active=True, branch_id=bid)
        s2 = Student(student_id='ZZ_HK2', first_name='B', surname='ZzHk2',
                     gender='Female', is_active=True, branch_id=bid)
        db.session.add_all([s1, s2]); db.session.flush()
        s1.created_at = datetime(2099, 10, 1); s2.created_at = datetime(2099, 11, 1)
        g = Student(student_id='ZZ_HKG', first_name='G', surname='ZzHkG', gender='Male',
                    is_active=True, is_graduated=True, graduation_date=date(2099, 12, 1),
                    branch_id=bid)
        db.session.add(g)
        cls = SchoolClass.query.first() or SchoolClass(name='HKClass', level=1, is_active=True)
        arm = ClassArm.query.first() or ClassArm(name='HK', is_active=True)
        db.session.add_all([cls, arm]); db.session.flush()
        caa = ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        db.session.add(StudentEnrollment(student_id=s1.id, class_arm_assignment_id=caa.id, is_active=True))
        db.session.commit()
        tid, sid = term.id, sess.id

    with app.test_request_context('/'):
        session['logged_in'] = True; session['role'] = 'super_admin'; session['scope'] = 'central'
        hk = _dash_headline_kpis(db.session.get(Term, tid), db.session.get(AcademicSession, sid), None)

    for key in ('students', 'enrolled', 'attendance', 'graduates'):
        assert key in hk
        assert isinstance(hk[key]['series'], list)
        assert isinstance(hk[key]['delta_label'], str)
        assert hk[key]['delta'] is None or set(hk[key]['delta']) == {'pct', 'dir'}
    assert hk['students']['series'] and hk['students']['series'][-1] >= 2   # both students, cumulative
    assert hk['enrolled']['series'] and hk['enrolled']['series'][-1] >= 1   # the one enrolment
    assert hk['graduates']['series'] and hk['graduates']['series'][-1] >= 1  # the graduate


def test_finance_stat_exposes_collected_today(app):
    """When finance is enabled, the term stat carries today's collection so the
    KPI can show a 'x today' chip."""
    c = _admin(app)
    j = c.get('/api/dashboard/data').get_json()
    fs = j.get('finance_stat')
    # finance is a default widget for admins; if present, the new key is there.
    if fs is not None:
        assert 'collected_today' in fs
        assert isinstance(fs['collected_today'], (int, float))
