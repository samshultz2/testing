"""Persistent-absence alerts: admins are belled when a student is absent several
consecutive school days in a row (deduped while unread)."""
from datetime import date

from models import (db, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, StudentEnrollment, Student, Week,
                    Attendance, Notification)
from utils.attendance_alerts import check_absence_alerts, _consecutive_absences


def _enrolled_student(app):
    with app.app_context():
        s = AcademicSession.query.filter_by(name='ABS 25/26').first() or AcademicSession(name='ABS 25/26')
        db.session.add(s); db.session.flush()
        t = Term.query.filter_by(session_id=s.id, term_number=1).first() or \
            Term(session_id=s.id, term_number=1, name='First Term')
        db.session.add(t); db.session.flush()
        wk = Week.query.filter_by(term_id=t.id, week_number=1).first() or Week(
            term_id=t.id, week_number=1, start_date=date(2026, 5, 18), end_date=date(2026, 5, 22))
        db.session.add(wk); db.session.flush()
        sc = SchoolClass.query.filter_by(name='ABSCLASS').first() or SchoolClass(name='ABSCLASS', level=1)
        db.session.add(sc); db.session.flush()
        arm = ClassArm.query.filter_by(name='ABSA').first() or ClassArm(name='ABSA', is_active=True)
        db.session.add(arm); db.session.flush()
        caa = ClassArmAssignment.query.filter_by(class_id=sc.id, arm_id=arm.id, term_id=t.id).first() or \
            ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=t.id)
        db.session.add(caa); db.session.flush()
        st = Student.query.filter_by(student_id='ABS1').first() or Student(
            student_id='ABS1', first_name='Sade', surname='Absent', gender='Female', is_active=True)
        db.session.add(st); db.session.flush()
        en = StudentEnrollment.query.filter_by(student_id=st.id, class_arm_assignment_id=caa.id).first() or \
            StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True)
        db.session.add(en); db.session.flush()
        db.session.commit()
        return en.id, wk.id


def _mark(app, eid, wid, days, present):
    with app.app_context():
        for d in days:
            rec = Attendance.query.filter_by(enrollment_id=eid, date=d).first() or \
                Attendance(enrollment_id=eid, week_id=wid, date=d)
            rec.week_id = wid
            rec.morning_present = present
            rec.afternoon_present = present
            db.session.add(rec)
        db.session.commit()


def test_streak_counts_recent_consecutive_absences(app):
    eid, wid = _enrolled_student(app)
    _mark(app, eid, wid, [date(2026, 5, 18), date(2026, 5, 19), date(2026, 5, 20)], present=False)
    with app.app_context():
        assert _consecutive_absences(eid) == 3


def test_alert_fires_at_threshold_and_dedupes(app):
    eid, wid = _enrolled_student(app)
    _mark(app, eid, wid, [date(2026, 5, 18), date(2026, 5, 19), date(2026, 5, 20)], present=False)
    with app.app_context():
        created = check_absence_alerts([eid], threshold=3)
        assert created == 1
        assert Notification.query.filter(
            Notification.title.ilike('Attendance alert: Absent Sade')).count() == 1
        # Calling again while the alert is unread does not duplicate it.
        assert check_absence_alerts([eid], threshold=3) == 0
        assert Notification.query.filter(
            Notification.title.ilike('Attendance alert: Absent Sade')).count() == 1


def test_below_threshold_no_alert(app):
    eid, wid = _enrolled_student(app)
    _mark(app, eid, wid, [date(2026, 5, 18), date(2026, 5, 19)], present=False)
    with app.app_context():
        assert check_absence_alerts([eid], threshold=3) == 0


def test_present_day_breaks_the_streak(app):
    eid, wid = _enrolled_student(app)
    # Absent, absent, then present on the most recent day -> streak resets to 0.
    _mark(app, eid, wid, [date(2026, 5, 18), date(2026, 5, 19)], present=False)
    _mark(app, eid, wid, [date(2026, 5, 20)], present=True)
    with app.app_context():
        assert _consecutive_absences(eid) == 0
        assert check_absence_alerts([eid], threshold=3) == 0


def test_threshold_zero_disables(app):
    eid, wid = _enrolled_student(app)
    _mark(app, eid, wid, [date(2026, 5, 18), date(2026, 5, 19), date(2026, 5, 20)], present=False)
    with app.app_context():
        assert check_absence_alerts([eid], threshold=0) == 0
