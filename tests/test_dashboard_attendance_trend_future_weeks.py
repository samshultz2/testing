"""The dashboard's 'Attendance trend' widget (main._dash_attendance_trend)
took Week.query.filter_by(term_id=...).order_by(start_date).all()[-8:] — the
chronologically LAST 8 weeks of the term's calendar. But generate_weeks()
(routes/academics.py) bulk-creates every week of a term up front, including
ones far in the future relative to today. For a term with more than 8 weeks
where fewer than 8 have actually started, that slice is entirely future
weeks with no attendance marked yet — the chart renders 8 zero points even
though real attendance data exists for the weeks that have already happened."""
from datetime import date, timedelta
from models import (db, Branch, Student, ClassArmAssignment, SchoolClass, ClassArm,
                    Term, AcademicSession, StudentEnrollment, Week, Attendance)


def _seed(app, tag):
    """A 14-week term where only the first 6 weeks have started (start_date
    <= today) and are fully marked present; weeks 7-14 are future and
    unmarked — exactly the generate_weeks() shape that trips the bug."""
    with app.app_context():
        today = date.today()
        monday_this_week = today - timedelta(days=today.weekday())
        week1_start = monday_this_week - timedelta(weeks=5)   # week 6 = this week

        sess = AcademicSession(name=f'{tag}-Sess', is_active=False)
        db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'{tag}-Term', is_active=False,
                    start_date=week1_start, end_date=week1_start + timedelta(weeks=14))
        db.session.add(term); db.session.flush()

        weeks = []
        for wn in range(1, 15):
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
        st = Student(student_id=f'{tag}S', first_name='A', surname='Trend',
                     gender='Male', is_active=True, branch_id=bid)
        db.session.add(st); db.session.flush()
        en = StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True)
        db.session.add(en); db.session.flush()

        # Weeks 1-6 (the ones that have actually happened) marked fully present.
        for w in weeks[:6]:
            for off in range(5):
                db.session.add(Attendance(enrollment_id=en.id, week_id=w.id,
                                          date=w.start_date + timedelta(days=off),
                                          morning_present=True, afternoon_present=True))
        db.session.commit()
        return term.id


def test_trend_excludes_weeks_that_have_not_started_yet(app):
    from flask import session
    from routes.main import _dash_attendance_trend
    tid = _seed(app, 'TRF')
    with app.test_request_context():
        session['role'] = 'super_admin'   # central scope: no branch filter narrows out the fixture
        term = db.session.get(Term, tid)
        trend = _dash_attendance_trend(term)

    # None of the returned points should be for a week starting in the future.
    today = date.today()
    with app.app_context():
        weeks_by_number = {w.week_number: w for w in Week.query.filter_by(term_id=tid).all()}
    for point in trend:
        w = weeks_by_number.get(point['label'])
        if w is not None:
            assert w.start_date <= today, (
                f"trend includes week {point['label']} starting {w.start_date}, "
                f"which hasn't happened yet (today is {today})")

    # The 6 weeks that actually happened, and were fully marked present,
    # must show up with real data (100%) — not be crowded out by 8 future
    # zero-weeks appended after them.
    assert len(trend) == 6, f'expected exactly the 6 started weeks, got {len(trend)}: {trend}'
    assert all(p['pct'] == 100.0 for p in trend), trend
