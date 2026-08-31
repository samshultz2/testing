"""Characterization + correctness tests for attendance summary calculations.

Pins the public behaviour of get_daily/weekly/termly_attendance_summary so the
N+1 query optimization stays behaviour-preserving.
"""
from datetime import date
import pytest
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment, Week, Attendance)


@pytest.fixture
def att_data(app):
    with app.app_context():
        existing = AcademicSession.query.filter_by(name='ATT-S').first()
        if existing:
            term = Term.query.filter_by(session_id=existing.id).first()
            wk = Week.query.filter_by(term_id=term.id).first()
            caa = ClassArmAssignment.query.filter_by(term_id=term.id).first()
            a = Student.query.filter_by(student_id='ATA1').first()
            b = Student.query.filter_by(student_id='ATB1').first()
            return dict(caa=caa.id, term=term.id, week=wk.id, d1=date(2025, 1, 6),
                        sa=a.id, sb=b.id)
        bid = Branch.get_default().id
        sess = AcademicSession(name='ATT-S'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='ATT-T'); db.session.add(term); db.session.flush()
        sc = SchoolClass.query.first(); arm = ClassArm.query.first()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        wk = Week(term_id=term.id, week_number=1,
                  start_date=date(2025, 1, 6), end_date=date(2025, 1, 10))  # Mon–Fri
        db.session.add(wk); db.session.flush()
        a = Student(student_id='ATA1', first_name='A', surname='Aa', gender='Male', is_active=True, branch_id=bid)
        b = Student(student_id='ATB1', first_name='B', surname='Bb', gender='Female', is_active=True, branch_id=bid)
        db.session.add_all([a, b]); db.session.flush()
        ea = StudentEnrollment(student_id=a.id, class_arm_assignment_id=caa.id, is_active=True)
        eb = StudentEnrollment(student_id=b.id, class_arm_assignment_id=caa.id, is_active=True)
        db.session.add_all([ea, eb]); db.session.flush()
        d1, d2 = date(2025, 1, 6), date(2025, 1, 7)
        db.session.add_all([
            Attendance(enrollment_id=ea.id, date=d1, week_id=wk.id, morning_present=True, afternoon_present=True),
            Attendance(enrollment_id=ea.id, date=d2, week_id=wk.id, morning_present=True, afternoon_present=False),
            Attendance(enrollment_id=eb.id, date=d1, week_id=wk.id, morning_present=True, afternoon_present=False),
        ])
        db.session.commit()
        return dict(caa=caa.id, term=term.id, week=wk.id, d1=d1, sa=a.id, sb=b.id)


def test_daily_summary(app, att_data):
    from utils.calculations import get_daily_attendance_summary
    with app.app_context():
        s = get_daily_attendance_summary(att_data['caa'], att_data['d1'])
        assert s['total_students'] == 2
        assert s['morning_present'] == 2 and s['morning_absent'] == 0
        assert s['afternoon_present'] == 1 and s['afternoon_absent'] == 1
        by_id = {r['student_id']: r for r in s['students']}
        assert by_id[att_data['sa']]['afternoon_present'] is True
        assert by_id[att_data['sb']]['afternoon_present'] is False


def test_weekly_summary(app, att_data):
    from utils.calculations import get_weekly_attendance_summary
    with app.app_context():
        s = get_weekly_attendance_summary(att_data['caa'], att_data['week'])
        assert s['school_days_count'] == 5 and s['times_opened'] == 10
        ct = s['class_totals']
        assert ct['total_morning'] == 3 and ct['total_afternoon'] == 1
        assert ct['total_attendance'] == 4 and ct['weekly_percentage'] == 20.0
        by_id = {r['student_id']: r for r in s['students']}
        assert by_id[att_data['sa']]['weekly_total'] == 3
        assert by_id[att_data['sb']]['weekly_total'] == 1


def test_termly_summary(app, att_data):
    from utils.calculations import get_termly_attendance_summary
    with app.app_context():
        s = get_termly_attendance_summary(att_data['caa'], att_data['term'])
        assert s['total_students'] == 2
        ct = s['class_totals']
        assert ct['total_morning'] == 3 and ct['total_afternoon'] == 1
        assert ct['total_attendance'] == 4
        by_id = {r['student_id']: r for r in s['students']}
        assert by_id[att_data['sa']]['termly_total'] == 3
        assert by_id[att_data['sb']]['termly_total'] == 1
