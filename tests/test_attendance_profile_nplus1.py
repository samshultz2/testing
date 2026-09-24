"""build_student_profile() (the attendance 'Full profile' page,
/attendance/api/student/<id>) already joined ClassArmAssignment onto its
enrollments query for filtering — but built the term-order sort key and
every term row with plain attribute access (e.enrollment.class_arm_assignment,
.term, .term.session, .display_name -> .school_class/.arm), none of it
eager-loaded. For a student tracked across many terms, each one re-lazy-loads
its own ClassArmAssignment/Term/AcademicSession/SchoolClass/ClassArm — a
handful of extra queries per term, scaling with how long the student has
been enrolled."""
import re
import uuid
from datetime import date, timedelta
from sqlalchemy import event
from config import Config
from models import (db, Branch, Student, ClassArmAssignment, SchoolClass, ClassArm,
                    Term, AcademicSession, StudentEnrollment, Week, Attendance)
from tests.conftest import login_token

_N_TERMS = 8


def _count_selects(app, table, fn):
    pattern = re.compile(r'^select\b.*\bfrom\s+' + re.escape(table) + r'\b',
                         re.IGNORECASE | re.DOTALL)
    counts = {'n': 0}

    def before(conn, cursor, statement, params, context, executemany):
        if pattern.match(statement):
            counts['n'] += 1
    with app.app_context():
        engine = db.engine
    event.listen(engine, 'before_cursor_execute', before)
    try:
        fn()
    finally:
        event.remove(engine, 'before_cursor_execute', before)
    return counts['n']


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _seed(app, tag):
    """One student enrolled across _N_TERMS separate, fully-completed
    (long-past) terms — each with its own session, term, class, arm and a
    week of attendance, so every term contributes a distinct row the
    profile must resolve."""
    with app.app_context():
        bid = Branch.get_default().id
        st = Student(student_id=f'{tag}S', first_name='Long', surname='Tenure',
                     gender='Male', is_active=True, branch_id=bid)
        db.session.add(st); db.session.flush()

        base = date(2018, 9, 3)   # long in the past, well before "today"
        for i in range(_N_TERMS):
            sess = AcademicSession(name=f'{tag}-Sess{i}', is_active=False)
            db.session.add(sess); db.session.flush()
            monday = base + timedelta(weeks=20 * i)
            term = Term(session_id=sess.id, term_number=1, name=f'{tag}-Term{i}',
                       is_active=False, start_date=monday, end_date=monday + timedelta(days=4))
            db.session.add(term); db.session.flush()
            wk = Week(term_id=term.id, week_number=1, start_date=monday, end_date=monday + timedelta(days=4))
            db.session.add(wk); db.session.flush()
            sc = SchoolClass(name=f'{tag}C{i}', level=1)
            arm = ClassArm(name=f'{tag}A{i}', is_active=True)
            db.session.add_all([sc, arm]); db.session.flush()
            caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
            db.session.add(caa); db.session.flush()
            en = StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True)
            db.session.add(en); db.session.flush()
            for off in range(5):
                db.session.add(Attendance(enrollment_id=en.id, week_id=wk.id,
                                          date=monday + timedelta(days=off),
                                          morning_present=True, afternoon_present=True))
        db.session.commit()
        return st.id


def test_profile_class_arm_assignment_lookups_do_not_scale_with_term_count(app):
    sid = _seed(app, f'BPN{uuid.uuid4().hex[:5]}')
    c = _admin(app)
    n = _count_selects(app, 'class_arm_assignments',
                       lambda: c.get(f'/attendance/api/student/{sid}'))
    assert n <= 2, (
        f'{n} class_arm_assignments SELECTs for a {_N_TERMS}-term profile — '
        f'looks like an N+1 (the enrollments query already joins this table '
        f'but does not eager-load it)')


def test_profile_term_and_session_lookups_do_not_scale_with_term_count(app):
    sid = _seed(app, f'BPT{uuid.uuid4().hex[:5]}')
    c = _admin(app)
    n_terms = _count_selects(app, 'terms', lambda: c.get(f'/attendance/api/student/{sid}'))
    n_sess = _count_selects(app, 'academic_sessions', lambda: c.get(f'/attendance/api/student/{sid}'))
    assert n_terms <= 2, f'{n_terms} terms SELECTs for a {_N_TERMS}-term profile — looks like an N+1'
    assert n_sess <= 2, f'{n_sess} academic_sessions SELECTs for a {_N_TERMS}-term profile — looks like an N+1'


def test_profile_class_name_lookups_do_not_scale_with_term_count(app):
    sid = _seed(app, f'BPC{uuid.uuid4().hex[:5]}')
    c = _admin(app)
    n_classes = _count_selects(app, 'school_classes', lambda: c.get(f'/attendance/api/student/{sid}'))
    n_arms = _count_selects(app, 'class_arms', lambda: c.get(f'/attendance/api/student/{sid}'))
    assert n_classes <= 2, f'{n_classes} school_classes SELECTs for a {_N_TERMS}-term profile — looks like an N+1'
    assert n_arms <= 2, f'{n_arms} class_arms SELECTs for a {_N_TERMS}-term profile — looks like an N+1'


def test_profile_response_shape_unchanged(app):
    sid = _seed(app, f'BPR{uuid.uuid4().hex[:5]}')
    c = _admin(app)
    data = c.get(f'/attendance/api/student/{sid}').get_json()
    assert data['overall']['terms'] == _N_TERMS
    assert len(data['terms']) == _N_TERMS
    for t in data['terms']:
        assert t['term'] and t['session'] and t['class'] and t['percentage'] == 100.0
