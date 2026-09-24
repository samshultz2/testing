"""The student profile page's 'Attendance Summary' card used to lead with the
OVERALL (cross-term) percentage and day counts, with only a bare percentage
for the current term — so a viewer wanting "how many days present/absent
THIS term" for the student had no way to see it without doing the maths
manually. _student_attendance_summary() now leads with the current/latest
term's figures (donut, badge, present/late/absent counts) and demotes the
cross-term aggregate to a secondary 'overall' line."""
from datetime import date, timedelta
from models import (db, Branch, Student, ClassArmAssignment, SchoolClass, ClassArm,
                    Term, AcademicSession, StudentEnrollment, Week, Attendance)


def _seed_single_term(app, tag):
    """One student, one term, in progress, perfect attendance so far."""
    with app.app_context():
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        sess = AcademicSession(name=f'{tag}-Sess', is_active=False)
        db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'{tag}-Term', is_active=False,
                    start_date=monday, end_date=monday + timedelta(weeks=8))
        db.session.add(term); db.session.flush()
        wk = Week(term_id=term.id, week_number=1, start_date=monday, end_date=monday + timedelta(days=4))
        db.session.add(wk); db.session.flush()
        bid = Branch.get_default().id
        sc = SchoolClass(name=f'{tag}C', level=1); arm = ClassArm(name=f'{tag}A', is_active=True)
        db.session.add_all([sc, arm]); db.session.flush()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        st = Student(student_id=f'{tag}S', first_name='Solo', surname='Term',
                     gender='Male', is_active=True, branch_id=bid)
        db.session.add(st); db.session.flush()
        en = StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True)
        db.session.add(en); db.session.flush()
        for off in range((today - monday).days + 1):
            d = monday + timedelta(days=off)
            if d.weekday() < 5 and d <= today:
                db.session.add(Attendance(enrollment_id=en.id, week_id=wk.id, date=d,
                                          morning_present=True, afternoon_present=True))
        db.session.commit()
        return st.id


def _seed_two_terms(app, tag):
    """A student with a rough, fully-completed PAST term (2 present, 3 absent
    -> 40%) and a perfect, currently in-progress term (this week so far, all
    present) — the exact shape from the reported screenshot: current term
    100%, overall dragged down by real history."""
    with app.app_context():
        bid = Branch.get_default().id
        st = Student(student_id=f'{tag}S', first_name='Two', surname='Terms',
                     gender='Female', is_active=True, branch_id=bid)
        db.session.add(st); db.session.flush()

        # Past, fully-completed term.
        past_sess = AcademicSession(name=f'{tag}-PastSess', is_active=False)
        db.session.add(past_sess); db.session.flush()
        past_monday = date(2024, 5, 6)   # long in the past
        past_term = Term(session_id=past_sess.id, term_number=2, name=f'{tag}-PastTerm',
                         is_active=False, start_date=past_monday, end_date=past_monday + timedelta(days=4))
        db.session.add(past_term); db.session.flush()
        past_wk = Week(term_id=past_term.id, week_number=1, start_date=past_monday,
                       end_date=past_monday + timedelta(days=4))
        db.session.add(past_wk); db.session.flush()
        past_sc = SchoolClass(name=f'{tag}PC', level=1); past_arm = ClassArm(name=f'{tag}PA', is_active=True)
        db.session.add_all([past_sc, past_arm]); db.session.flush()
        past_caa = ClassArmAssignment(class_id=past_sc.id, arm_id=past_arm.id,
                                      term_id=past_term.id, branch_id=bid)
        db.session.add(past_caa); db.session.flush()
        past_en = StudentEnrollment(student_id=st.id, class_arm_assignment_id=past_caa.id, is_active=True)
        db.session.add(past_en); db.session.flush()
        for off, present in zip(range(5), [True, True, False, False, False]):
            db.session.add(Attendance(enrollment_id=past_en.id, week_id=past_wk.id,
                                      date=past_monday + timedelta(days=off),
                                      morning_present=present, afternoon_present=present))

        # Current, in-progress term (later session -> sorts as "latest").
        # is_active=False on both: build_student_profile() orders by
        # (session_id, term_number) — a higher session_id already sorts this
        # newest, no active flag needed — and leaving one set would pollute
        # get_active_term() (it cross-checks AcademicSession.is_active against
        # Term.is_active) for every test that runs after this one in the same
        # session-scoped test DB.
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        sess = AcademicSession(name=f'{tag}-CurSess', is_active=False)
        db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'{tag}-CurTerm', is_active=False,
                    start_date=monday, end_date=monday + timedelta(weeks=8))
        db.session.add(term); db.session.flush()
        wk = Week(term_id=term.id, week_number=1, start_date=monday, end_date=monday + timedelta(days=4))
        db.session.add(wk); db.session.flush()
        sc = SchoolClass(name=f'{tag}CC', level=1); arm = ClassArm(name=f'{tag}CA', is_active=True)
        db.session.add_all([sc, arm]); db.session.flush()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        en = StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True)
        db.session.add(en); db.session.flush()
        for off in range((today - monday).days + 1):
            d = monday + timedelta(days=off)
            if d.weekday() < 5 and d <= today:
                db.session.add(Attendance(enrollment_id=en.id, week_id=wk.id, date=d,
                                          morning_present=True, afternoon_present=True))
        db.session.commit()
        return st.id, term.name


def test_single_term_headline_matches_the_only_term(app):
    from routes.main import _student_attendance_summary
    sid = _seed_single_term(app, 'ASC1')
    with app.test_request_context():
        summary = _student_attendance_summary(sid)
    assert summary['percentage'] == 100.0
    assert summary['absent_days'] == 0
    assert summary['terms'] == 1
    # A single tracked term: no separate 'overall' line needed by the caller,
    # but the field is still present and matches the headline.
    assert summary['overall_percentage'] == summary['percentage']


def test_two_terms_headline_is_current_term_not_overall(app):
    from routes.main import _student_attendance_summary
    sid, cur_term_name = _seed_two_terms(app, 'ASC2')
    with app.test_request_context():
        summary = _student_attendance_summary(sid)

    # Headline = current term: perfect so far.
    assert summary['percentage'] == 100.0, summary
    assert summary['absent_days'] == 0
    assert summary['term_name'] == cur_term_name
    assert summary['warning'] is False   # current term is fine — no false alarm

    # Overall = real cross-term aggregate, dragged down by the past term's
    # 2-present/3-absent record.
    assert summary['terms'] == 2
    assert summary['overall_percentage'] < 100.0
    assert summary['overall_absent_days'] >= 3   # at least the past term's 3 absences
