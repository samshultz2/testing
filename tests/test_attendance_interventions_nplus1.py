"""The Interventions tab (/attendance/api/interventions) had the same class of
N+1 bugs already fixed elsewhere this pass: dashboard() called _row() in a
loop, where each row's student_term_percentage() re-queries Week/Holiday/
enrollment/Attendance per student, _class_for() re-queries ClassArmAssignment
(plus a lazy load each for .school_class/.arm) per student, iv.student
lazy-loads per row (the intervention query had no eager loading), and
iv.notes.order_by(...).all() (a lazy='dynamic' relationship) re-queries per
row. recommendations() repeated the same per-student percentage/class-name
pattern for every low-attendance candidate with no open intervention."""
import re
import uuid
from datetime import date, timedelta
from sqlalchemy import event
from config import Config
from models import (db, Branch, Student, ClassArmAssignment, SchoolClass, ClassArm,
                    Term, AcademicSession, StudentEnrollment, Week, Attendance)
from tests.conftest import login_token

_COHORT_SIZE = 12


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
    """A term with _COHORT_SIZE students: half get an open intervention (with
    two follow-up notes each), half are just low-attendance so they surface
    as recommendations — exercising both of dashboard()'s per-student loops."""
    with app.app_context():
        sess = AcademicSession(name=f'{tag}-Sess', is_active=False)
        db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'{tag}-Term', is_active=False,
                    start_date=date(2025, 6, 2), end_date=date(2025, 6, 6))
        db.session.add(term); db.session.flush()
        wk = Week(term_id=term.id, week_number=1, start_date=date(2025, 6, 2), end_date=date(2025, 6, 8))
        db.session.add(wk); db.session.flush()
        sc = SchoolClass(name=f'{tag}C', level=1); arm = ClassArm(name=f'{tag}A', is_active=True)
        db.session.add_all([sc, arm]); db.session.flush()
        bid = Branch.get_default().id
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()

        student_ids = []
        for i in range(_COHORT_SIZE):
            st = Student(student_id=f'{tag}{i:03d}', first_name=f'S{i}', surname=tag,
                        gender='Male', is_active=True, branch_id=bid)
            db.session.add(st); db.session.flush()
            en = StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True)
            db.session.add(en); db.session.flush()
            present = (i % 2 == 0)   # even i: full attendance; odd i: absent all week (low)
            for off in range(5):
                db.session.add(Attendance(enrollment_id=en.id, week_id=wk.id,
                                          date=date(2025, 6, 2) + timedelta(days=off),
                                          morning_present=present, afternoon_present=present))
            student_ids.append(st.id)
        db.session.commit()

        from utils import attendance_interventions as IV
        term_obj = db.session.get(Term, term.id)
        for sid in student_ids[:_COHORT_SIZE // 2]:
            iv, _ = IV.open_intervention(sid, term_obj, reason='Low attendance', opened_by='Head')
            IV.add_note(iv, kind='Call', body='Called parent', author='Head')
            IV.add_note(iv, kind='Follow-up', next_action='Check next week', author='Head')
        db.session.commit()
        return term.id


def test_interventions_dashboard_notes_do_not_scale_with_cohort_size(app):
    tid = _seed(app, f'IVN{uuid.uuid4().hex[:5]}')
    c = _admin(app)
    n = _count_selects(app, 'attendance_intervention_notes',
                       lambda: c.get(f'/attendance/api/interventions?term_id={tid}'))
    assert n < _COHORT_SIZE // 2, (
        f'{n} attendance_intervention_notes SELECTs for {_COHORT_SIZE // 2} open '
        f'interventions — looks like an N+1 (one query per row via the dynamic '
        f'.notes relationship instead of one batched IN query)')


def test_interventions_dashboard_student_lookups_do_not_scale_with_cohort_size(app):
    tid = _seed(app, f'IVS{uuid.uuid4().hex[:5]}')
    c = _admin(app)
    n = _count_selects(app, 'students',
                       lambda: c.get(f'/attendance/api/interventions?term_id={tid}'))
    assert n < _COHORT_SIZE // 2, (
        f'{n} students SELECTs for a {_COHORT_SIZE}-student cohort — looks like an '
        f'N+1 (iv.student lazy-loaded per row instead of eager-loaded on the query)')


def test_interventions_dashboard_class_lookups_do_not_scale_with_cohort_size(app):
    tid = _seed(app, f'IVC{uuid.uuid4().hex[:5]}')
    c = _admin(app)
    n = _count_selects(app, 'class_arm_assignments',
                       lambda: c.get(f'/attendance/api/interventions?term_id={tid}'))
    assert n < _COHORT_SIZE, (
        f'{n} class_arm_assignments SELECTs for a {_COHORT_SIZE}-student cohort — '
        f'looks like an N+1 (_class_for() queried per student instead of batched)')


def test_interventions_dashboard_response_shape_unchanged(app):
    """The bulk rewrite must keep producing the same fields/values as before.

    Of the 12 seeded students: i=0..5 get an open intervention regardless of
    attendance; odd i is low-attendance (absent all week). So recommendations
    (low-attendance, no open intervention) = odd i in 6..11 = {7, 9, 11} = 3.
    """
    tid = _seed(app, f'IVR{uuid.uuid4().hex[:5]}')
    c = _admin(app)
    data = c.get(f'/attendance/api/interventions?term_id={tid}').get_json()
    assert data['counts']['active'] == _COHORT_SIZE // 2
    assert len(data['recommendations']) == 3
    row = data['active'][0]
    assert row['name'] and row['class'] and len(row['notes']) == 2
    for rec in data['recommendations']:
        assert rec['name'] and rec['class'] and rec['percentage'] is not None
