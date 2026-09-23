"""Regression: the attendance mark page loads existing marks in ONE batched query,
not one-per-enrollment (the former N+1). Counts SELECTs against the attendance table."""
import re
from datetime import date, timedelta

from sqlalchemy import event

from models import (db, Branch, Student, AcademicSession, Term, SchoolClass,
                    ClassArm, ClassArmAssignment, StudentEnrollment, Week, Attendance)
from config import Config
from tests.conftest import login_token


def _make_select_counter(table):
    """A before_cursor_execute counter for `SELECT ... FROM <table>` statements.
    Matches on a regex, not a plain ' from <table>' substring: SQLAlchemy's
    compiled SQL puts a newline before FROM (`...columns \nFROM students \n...`),
    so a literal-space substring check silently never matches anything and the
    guard always reports zero — which is exactly what happened here before
    this fix (both this helper and its predecessor always passed, N+1 or not)."""
    pattern = re.compile(r'^select\b.*\bfrom\s+' + re.escape(table) + r'\b', re.IGNORECASE | re.DOTALL)
    counts = {'n': 0}

    def before(conn, cursor, statement, params, context, executemany):
        if pattern.match(statement):
            counts['n'] += 1
    return counts, before


def _count_selects(app, table, fn):
    counts, before = _make_select_counter(table)
    with app.app_context():
        engine = db.engine
    event.listen(engine, 'before_cursor_execute', before)
    try:
        fn()
    finally:
        event.remove(engine, 'before_cursor_execute', before)
    return counts['n']


def _count_attendance_selects(app, fn):
    return _count_selects(app, 'attendance', fn)


def test_attendance_mark_existing_is_single_query(app):
    with app.app_context():
        br = Branch.query.filter_by(code='NP1').first() or Branch(name='NP1', code='NP1', is_active=True)
        db.session.add(br); db.session.flush()
        ssn = AcademicSession.query.filter_by(is_active=True).first() or AcademicSession(name='NP1 25/26', is_active=True)
        db.session.add(ssn); db.session.flush()
        term = Term.query.filter_by(is_active=True).first() or Term(session_id=ssn.id, term_number=1, name='First Term', is_active=True)
        db.session.add(term); db.session.flush()
        sss = SchoolClass.query.filter_by(name='SSS1').first() or SchoolClass(name='SSS1', level=4)
        db.session.add(sss); db.session.flush()
        arm = ClassArm.query.filter_by(name='NP1A').first() or ClassArm(name='NP1A', is_active=True)
        db.session.add(arm); db.session.flush()
        caa = ClassArmAssignment.query.filter_by(class_id=sss.id, arm_id=arm.id, term_id=term.id).first() \
            or ClassArmAssignment(class_id=sss.id, arm_id=arm.id, term_id=term.id, branch_id=br.id)
        db.session.add(caa); db.session.flush()
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        wk = Week.query.filter(Week.term_id == term.id, Week.start_date <= today, Week.end_date >= today).first() \
            or Week(term_id=term.id, week_number=88, start_date=monday, end_date=monday + timedelta(days=6))
        db.session.add(wk); db.session.flush()
        school_date = wk.start_date
        while school_date.weekday() >= 5:
            school_date += timedelta(days=1)
        eids = []
        for i in range(12):
            st = Student(student_id=Student.generate_student_id(), first_name=f'N{i}', surname='NPlus',
                         gender='Male', is_active=True, branch_id=br.id)
            db.session.add(st); db.session.flush()
            en = StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True)
            db.session.add(en); db.session.flush()
            eids.append(en.id)
            db.session.add(Attendance(enrollment_id=en.id, date=school_date, week_id=wk.id,
                                      morning_present=True, afternoon_present=True))
        db.session.commit()
        caa_id, ds = caa.id, school_date.isoformat()

    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})

    n = _count_attendance_selects(
        app, lambda: c.get(f'/attendance/mark?assignment_id={caa_id}&date={ds}'))
    # one batched SELECT for 12 students' existing marks — not 12 (the old N+1).
    assert n <= 2, f'expected a single batched attendance query, got {n}'


def _count_student_selects(app, fn):
    return _count_selects(app, 'students', fn)


def _roster_fixture(app, tag, n_students=20):
    """A class arm with n_students enrolled — shared setup for the React
    attendance SPA's /api/roster and /api/week N+1 regression checks below.
    `tag` must be unique per caller: the `app` fixture is session-scoped (one
    shared DB for the whole test run), so reusing a branch/arm code across
    two tests would enrol the second test's students into the first test's
    class arm on top of its own, inflating the roster instead of isolating it."""
    with app.app_context():
        br = Branch.query.filter_by(code=tag).first() or Branch(name=tag, code=tag, is_active=True)
        db.session.add(br); db.session.flush()
        ssn = AcademicSession.query.filter_by(is_active=True).first() or AcademicSession(name=tag + ' 25/26', is_active=True)
        db.session.add(ssn); db.session.flush()
        term = Term.query.filter_by(is_active=True).first() or Term(session_id=ssn.id, term_number=1, name='First Term', is_active=True)
        db.session.add(term); db.session.flush()
        sss = SchoolClass.query.filter_by(name='SSS1').first() or SchoolClass(name='SSS1', level=4)
        db.session.add(sss); db.session.flush()
        arm = ClassArm.query.filter_by(name=tag + 'A').first() or ClassArm(name=tag + 'A', is_active=True)
        db.session.add(arm); db.session.flush()
        caa = ClassArmAssignment.query.filter_by(class_id=sss.id, arm_id=arm.id, term_id=term.id).first() \
            or ClassArmAssignment(class_id=sss.id, arm_id=arm.id, term_id=term.id, branch_id=br.id)
        db.session.add(caa); db.session.flush()
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        wk = Week.query.filter(Week.term_id == term.id, Week.start_date <= today, Week.end_date >= today).first() \
            or Week(term_id=term.id, week_number=89, start_date=monday, end_date=monday + timedelta(days=6))
        db.session.add(wk); db.session.flush()
        school_date = wk.start_date
        while school_date.weekday() >= 5:
            school_date += timedelta(days=1)
        for i in range(n_students):
            st = Student(student_id=Student.generate_student_id(), first_name=f'R{i}', surname='Roster',
                         gender='Male', is_active=True, branch_id=br.id)
            db.session.add(st); db.session.flush()
            db.session.add(StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True))
        db.session.commit()
        return caa.id, wk.id, school_date.isoformat()


def test_roster_api_students_is_single_query(app):
    """/attendance/api/roster (the React SPA's default "Mark daily" tab) must
    populate each enrollment's .student from the JOIN it already does for
    filtering, not one lazy-load SELECT per student (the old N+1: a class of
    35 meant 35 extra round-trips just to open the register)."""
    caa_id, _wk_id, ds = _roster_fixture(app, 'NP2', n_students=20)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    resp = {}
    n = _count_student_selects(
        app, lambda: resp.setdefault('r', c.get(f'/attendance/api/roster?assignment_id={caa_id}&date={ds}')))
    assert resp['r'].status_code == 200, resp['r'].get_data(as_text=True)
    assert len(resp['r'].get_json()['students']) == 20
    assert n <= 1, f'expected the students JOIN to be reused (contains_eager), got {n} SELECTs'


def test_week_api_students_is_single_query(app):
    """/attendance/api/week (the SPA's Weekly grid tab) has the same
    join-then-lazy-load pattern as the roster endpoint — same fix, same guard."""
    caa_id, wk_id, _ds = _roster_fixture(app, 'NP3', n_students=20)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    resp = {}
    n = _count_student_selects(
        app, lambda: resp.setdefault('r', c.get(f'/attendance/api/week?assignment_id={caa_id}&week_id={wk_id}')))
    assert resp['r'].status_code == 200, resp['r'].get_data(as_text=True)
    assert len(resp['r'].get_json()['students']) == 20
    assert n <= 1, f'expected the students JOIN to be reused (contains_eager), got {n} SELECTs'


def test_absentees_api_students_is_single_query(app):
    """/attendance/api/absentees (Daily summary's WhatsApp absentee list) has
    the same join-then-lazy-load pattern — same fix, same guard."""
    caa_id, wk_id, ds = _roster_fixture(app, 'NP4', n_students=20)
    with app.app_context():
        eids = [e.id for e in StudentEnrollment.query.filter_by(
            class_arm_assignment_id=caa_id, is_active=True).all()]
        for eid in eids:
            db.session.add(Attendance(enrollment_id=eid, week_id=wk_id,
                                      date=date.fromisoformat(ds),
                                      morning_present=False, afternoon_present=False))
        db.session.commit()
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    resp = {}
    n = _count_student_selects(
        app, lambda: resp.setdefault('r', c.get(f'/attendance/api/absentees?assignment_id={caa_id}&date={ds}')))
    assert resp['r'].status_code == 200, resp['r'].get_data(as_text=True)
    assert len(resp['r'].get_json()['absentees']) == 20
    assert n <= 1, f'expected the students JOIN to be reused (contains_eager), got {n} SELECTs'


def test_alerts_api_students_is_single_query(app):
    """/attendance/api/report/alerts (Alerts tab) has the same
    join-then-lazy-load pattern — worse here since it spans every class the
    user can see for the whole term, not just one. Same fix, same guard."""
    caa_id, _wk_id, _ds = _roster_fixture(app, 'NP5', n_students=20)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    resp = {}
    n = _count_student_selects(
        app, lambda: resp.setdefault('r', c.get('/attendance/api/report/alerts?threshold=100')))
    assert resp['r'].status_code == 200, resp['r'].get_data(as_text=True)
    assert n <= 1, f'expected the students JOIN to be reused (contains_eager), got {n} SELECTs'
