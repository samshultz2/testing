"""Root-cause fix: _term_school_days() returned every weekday of a term's
FULL calendar (generate_weeks bulk-creates the whole term up front,
including weeks far in the future), and every percentage/day-count
consumer used that as their denominator — treating days that haven't
happened yet (no register can exist for them) as 'absent'. For any term
still in progress, this understated attendance for every student, flagged
perfectly-present students as low-attendance, and hid an in-progress
term's real percentage behind a huge false-absence count.

Covers every consumer that touches this: student_term_percentage /
build_student_profile (student profile page), bulk_term_percentages
(intervention dashboard), _low_attendance_student_ids (low-attendance
notify/recommendations), and attendance_analytics.build()'s overall % and
weekly trend."""
from datetime import date, timedelta
from models import (db, Branch, Student, ClassArmAssignment, SchoolClass, ClassArm,
                    Term, AcademicSession, StudentEnrollment, Week, Attendance)


def _seed(app, tag, weeks_started=2, weeks_total=10):
    """A term whose full calendar spans ``weeks_total`` weeks, but only the
    first ``weeks_started`` have actually begun (start_date <= today). One
    student, fully present on every school day of every started week —
    perfect attendance so far, with a large stretch of the term still ahead."""
    with app.app_context():
        today = date.today()
        monday_this_week = today - timedelta(days=today.weekday())
        # Week ``weeks_started`` = this week, so weeks 1..weeks_started have
        # started and weeks_started+1..weeks_total are still in the future.
        week1_start = monday_this_week - timedelta(weeks=weeks_started - 1)

        sess = AcademicSession(name=f'{tag}-Sess', is_active=False)
        db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'{tag}-Term', is_active=False,
                    start_date=week1_start, end_date=week1_start + timedelta(weeks=weeks_total))
        db.session.add(term); db.session.flush()

        weeks = []
        for wn in range(1, weeks_total + 1):
            ws = week1_start + timedelta(weeks=wn - 1)
            w = Week(term_id=term.id, week_number=wn, start_date=ws, end_date=ws + timedelta(days=4))
            db.session.add(w)
            weeks.append(w)
        db.session.flush()

        bid = Branch.get_default().id
        sc = SchoolClass(name=f'{tag}C', level=1); arm = ClassArm(name=f'{tag}A', is_active=True)
        db.session.add_all([sc, arm]); db.session.flush()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        st = Student(student_id=f'{tag}S', first_name='Perfect', surname='Attendee',
                     gender='Male', is_active=True, branch_id=bid)
        db.session.add(st); db.session.flush()
        en = StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True)
        db.session.add(en); db.session.flush()

        for w in weeks[:weeks_started]:
            for off in range(5):
                d = w.start_date + timedelta(days=off)
                if d <= today:
                    db.session.add(Attendance(enrollment_id=en.id, week_id=w.id, date=d,
                                              morning_present=True, afternoon_present=True))
        db.session.commit()
        return term.id, caa.id, st.id


def test_student_term_percentage_ignores_future_weeks(app):
    from utils.attendance_profile import student_term_percentage
    tid, caa_id, sid = _seed(app, 'ADNW1')
    with app.app_context():
        pct = student_term_percentage(sid, tid)
    assert pct == 100.0, (
        f'expected 100% (perfect attendance on every day that has happened so '
        f'far), got {pct} — future term weeks are being counted as absences')


def test_build_student_profile_focus_term_ignores_future_weeks(app):
    from utils.attendance_profile import build_student_profile
    tid, caa_id, sid = _seed(app, 'ADNW2')
    with app.app_context():
        prof = build_student_profile(sid, focus_term_id=tid)
    assert prof['overall']['percentage'] == 100.0
    focus = prof['focus']
    assert focus['term_id'] == tid
    assert focus['percentage'] == 100.0
    # The calendar still shows the whole term (future days included, as
    # 'unmarked') for display — that part is unaffected by this fix.
    assert len(focus['calendar']) > focus['school_days']


def test_bulk_term_percentages_ignores_future_weeks(app):
    from utils.attendance_profile import bulk_term_percentages
    tid, caa_id, sid = _seed(app, 'ADNW3')
    with app.app_context():
        pcts = bulk_term_percentages([sid], tid)
    assert pcts.get(sid) == 100.0


def test_low_attendance_recommendations_do_not_flag_perfect_students(app):
    from utils.attendance_notify import _low_attendance_student_ids
    tid, caa_id, sid = _seed(app, 'ADNW4')
    with app.app_context():
        term = db.session.get(Term, tid)
        low_ids = _low_attendance_student_ids(term, [caa_id], threshold=75.0)
    assert sid not in low_ids, (
        'a student with perfect attendance on every day so far was flagged '
        'as low-attendance — future weeks are dragging the percentage down')


def test_analytics_overall_and_trend_ignore_future_weeks(app):
    from utils import attendance_analytics
    tid, caa_id, sid = _seed(app, 'ADNW5')
    with app.app_context():
        term = db.session.get(Term, tid)
        caa = db.session.get(ClassArmAssignment, caa_id)
        data = attendance_analytics.build(term, [caa], is_central=True, use_cache=False)
    assert data['kpis']['overall'] == 100.0, data['kpis']['overall']
    today = date.today()
    with app.app_context():
        weeks_by_label = {f'W{w.week_number}': w for w in Week.query.filter_by(term_id=tid).all()}
    for point in data['trend']:
        w = weeks_by_label.get(point['label'])
        assert w is not None and w.start_date <= today, (
            f"trend includes a future week: {point}")
