"""Attendance Phase 1 — the student attendance profile (cross-term aggregation,
derived present/late/absent, warnings) and the profile search endpoint."""
from datetime import date, timedelta

from config import Config
from models import (db, Branch, Student, ClassArmAssignment, SchoolClass, ClassArm,
                    Term, AcademicSession, StudentEnrollment, Week, Attendance, Holiday,
                    SchoolSettings)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    return c


def _setup_profile(app, tag):
    """A student with a week of derived statuses: present / late / absent."""
    with app.app_context():
        # Fully isolated session + term per test (shared session DB) so weeks and
        # class assignments never collide across test runs.
        sess = AcademicSession(name=f'PRSess{tag}', is_active=False)
        db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'PRTerm{tag}', is_active=False)
        db.session.add(term); db.session.flush()
        # A clean 5-weekday window with no holidays.
        monday = date(2025, 5, 5)   # a Monday
        wk = Week(term_id=term.id, week_number=1,
                  start_date=monday, end_date=monday + timedelta(days=6))
        db.session.add(wk); db.session.flush()
        # Unique class + arm per test so the (class, arm, term) assignment is
        # unique in the shared session DB.
        sc = SchoolClass(name=f'PRC{tag}', level=1)
        arm = ClassArm(name=f'PA{tag}', is_active=True)
        db.session.add_all([sc, arm]); db.session.flush()
        bid = Branch.get_default().id
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        st = Student(student_id=f'PR{tag}', first_name='Prof', surname=f'Zz{tag}',
                     gender='Female', is_active=True, branch_id=bid)
        db.session.add(st); db.session.flush()
        en = StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True)
        db.session.add(en); db.session.flush()
        # Mon present(2), Tue late(1: morning only), Wed absent(0), Thu present(2). Fri: no record.
        db.session.add_all([
            Attendance(enrollment_id=en.id, week_id=wk.id, date=monday, morning_present=True, afternoon_present=True),
            Attendance(enrollment_id=en.id, week_id=wk.id, date=monday + timedelta(days=1), morning_present=True, afternoon_present=False),
            Attendance(enrollment_id=en.id, week_id=wk.id, date=monday + timedelta(days=2), morning_present=False, afternoon_present=False),
            Attendance(enrollment_id=en.id, week_id=wk.id, date=monday + timedelta(days=3), morning_present=True, afternoon_present=True),
        ])
        # term boundaries must include the week
        term.start_date = monday; term.end_date = monday + timedelta(days=6)
        db.session.commit()
        return st.id, term.id


def test_profile_derives_present_late_absent(app):
    from utils.attendance_profile import build_student_profile
    sid, tid = _setup_profile(app, 'D1')
    with app.app_context():
        prof = build_student_profile(sid)
        assert prof is not None
        row = prof['terms'][0]
        # 5 school days: present(Mon,Thu)=2 full, late(Tue)=1, absent(Wed + Fri-no-record)=2
        assert row['full_days'] == 2
        assert row['late_days'] == 1
        assert row['absent_days'] == 2
        # present sessions = 2+1+0+2+0 = 5 of 10 opened = 50%
        assert row['present_sessions'] == 5 and row['total_opened'] == 10
        assert row['percentage'] == 50.0


def test_profile_warning_below_threshold(app):
    from utils.attendance_profile import build_student_profile
    sid, tid = _setup_profile(app, 'W1')
    with app.app_context():
        SchoolSettings.set('attendance_warning_threshold', '75', 'string', 'x')
        db.session.commit()
        prof = build_student_profile(sid)
        assert prof['warning'] is True          # 50% < 75%
        assert prof['overall']['percentage'] == 50.0
        # focus term carries a calendar of the school days
        assert prof['focus'] and len(prof['focus']['calendar']) == 5


def test_profile_api_and_access(app):
    sid, tid = _setup_profile(app, 'API1')
    client = _admin(app)
    r = client.get(f'/attendance/api/student/{sid}')
    assert r.status_code == 200
    body = r.get_json()
    assert body['student']['id'] == sid and 'overall' in body and 'terms' in body
    assert client.get('/attendance/api/student/99999').status_code == 404


def test_student_search_endpoint(app):
    sid, tid = _setup_profile(app, 'SR1')
    client = _admin(app)
    rows = client.get('/attendance/api/student-search?q=Zz').get_json()
    assert any(r['id'] == sid and 'student_id=' in r['url'] for r in rows)
    assert client.get('/attendance/api/student-search?q=z').get_json() == []


def test_app_shell_deeplinks_student_tab(app):
    client = _admin(app)
    html = client.get('/attendance/app?tab=student').get_data(as_text=True)
    assert 'attendance-app' in html or 'att-app' in html or 'id="react-root"' in html
