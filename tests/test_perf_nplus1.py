"""Regression: the attendance mark page loads existing marks in ONE batched query,
not one-per-enrollment (the former N+1). Counts SELECTs against the attendance table."""
from datetime import date, timedelta

from sqlalchemy import event

from models import (db, Branch, Student, AcademicSession, Term, SchoolClass,
                    ClassArm, ClassArmAssignment, StudentEnrollment, Week, Attendance)
from config import Config
from tests.conftest import login_token


def _count_attendance_selects(app, fn):
    counts = {'n': 0}

    def before(conn, cursor, statement, params, context, executemany):
        s = statement.lower()
        if s.startswith('select') and ' from attendance' in s:
            counts['n'] += 1
    with app.app_context():
        engine = db.engine
    event.listen(engine, 'before_cursor_execute', before)
    try:
        fn()
    finally:
        event.remove(engine, 'before_cursor_execute', before)
    return counts['n']


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
