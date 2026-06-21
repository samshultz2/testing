"""School-level trends: JAMB subject breakdown, Mock WAEC subject value-added,
attendance<->results correlation."""
import uuid
from datetime import date

from models import (db, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, StudentEnrollment, Student, Week,
                    Attendance, JAMBResult)
from models.mock_waec import MockWAECExam, MockWAECResult, waec_grade_from_score
from utils import exam_trends as T


def _student(app, **kw):
    with app.app_context():
        s = Student(student_id='TR' + uuid.uuid4().hex[:7].upper(), first_name='T',
                    surname='Rend', gender='Male', **kw)
        db.session.add(s); db.session.commit()
        return s.id


def test_jamb_subject_breakdown(app):
    a, b = _student(app), _student(app)
    with app.app_context():
        db.session.add(JAMBResult(student_id=a, exam_year=2025, total_score=260,
                                  subject1='Use of English', subject1_score=70,
                                  subject2='Government', subject2_score=60))
        db.session.add(JAMBResult(student_id=b, exam_year=2025, total_score=240,
                                  subject1='Use of English', subject1_score=50,
                                  subject2='Government', subject2_score=80))
        db.session.commit()
        rows = {r['subject']: r for r in T.jamb_subject_breakdown(exam_year=2025)}
        assert rows['Use of English']['average'] == 60.0 and rows['Use of English']['count'] == 2
        assert rows['Government']['average'] == 70.0


def test_mock_waec_subject_gains(app):
    with app.app_context():
        ss = AcademicSession(name='GN ' + uuid.uuid4().hex[:5]); db.session.add(ss); db.session.flush()
        ssid = ss.id
        e1 = MockWAECExam(name='M1', exam_number=1, session_id=ssid, exam_date=date(2025, 1, 1))
        e2 = MockWAECExam(name='M2', exam_number=2, session_id=ssid, exam_date=date(2025, 2, 1))
        db.session.add_all([e1, e2]); db.session.flush()
        sid = Student(student_id='TR' + uuid.uuid4().hex[:7].upper(), first_name='G',
                      surname='Ain', gender='Male')
        db.session.add(sid); db.session.flush()
        db.session.add(MockWAECResult(student_id=sid.id, mock_exam_id=e1.id, subject='Mathematics',
                                      score=50, grade=waec_grade_from_score(50)))
        db.session.add(MockWAECResult(student_id=sid.id, mock_exam_id=e2.id, subject='Mathematics',
                                      score=65, grade=waec_grade_from_score(65)))
        db.session.commit()
        res = T.mock_waec_subject_gains(ssid)
        maths = [s for s in res['subjects'] if s['subject'] == 'Mathematics'][0]
        assert maths['first'] == 50.0 and maths['latest'] == 65.0 and maths['gain'] == 15.0


def _enroll_with_attendance(app, present_days, absent_days, jamb):
    """Create a student with attendance (present/absent day counts) and a JAMB score."""
    with app.app_context():
        ss = AcademicSession.query.filter_by(name='ATT 25/26').first() or AcademicSession(name='ATT 25/26')
        db.session.add(ss); db.session.flush()
        t = Term.query.filter_by(session_id=ss.id, term_number=1).first() or \
            Term(session_id=ss.id, term_number=1, name='First Term')
        db.session.add(t); db.session.flush()
        wk = Week.query.filter_by(term_id=t.id, week_number=1).first() or Week(
            term_id=t.id, week_number=1, start_date=date(2026, 5, 18), end_date=date(2026, 5, 22))
        db.session.add(wk); db.session.flush()
        sc = SchoolClass.query.filter_by(name='ATTC').first() or SchoolClass(name='ATTC', level=1)
        db.session.add(sc); db.session.flush()
        arm = ClassArm.query.filter_by(name='ATTA').first() or ClassArm(name='ATTA', is_active=True)
        db.session.add(arm); db.session.flush()
        caa = ClassArmAssignment.query.filter_by(class_id=sc.id, arm_id=arm.id, term_id=t.id).first() or \
            ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=t.id)
        db.session.add(caa); db.session.flush()
        st = Student(student_id='AT' + uuid.uuid4().hex[:7].upper(), first_name='A', surname='Tt', gender='Male')
        db.session.add(st); db.session.flush()
        en = StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True)
        db.session.add(en); db.session.flush()
        day = 1
        for _ in range(present_days):
            db.session.add(Attendance(enrollment_id=en.id, week_id=wk.id, date=date(2026, 5, day),
                                      morning_present=True, afternoon_present=True)); day += 1
        for _ in range(absent_days):
            db.session.add(Attendance(enrollment_id=en.id, week_id=wk.id, date=date(2026, 5, day),
                                      morning_present=False, afternoon_present=False)); day += 1
        db.session.add(JAMBResult(student_id=st.id, exam_year=2026, total_score=jamb))
        db.session.commit()
        return st.id


def test_attendance_correlates_with_results(app):
    # High attendance -> high JAMB; low -> low. Expect a positive correlation.
    ids = [
        _enroll_with_attendance(app, present_days=4, absent_days=0, jamb=300),
        _enroll_with_attendance(app, present_days=2, absent_days=2, jamb=200),
        _enroll_with_attendance(app, present_days=0, absent_days=4, jamb=120),
    ]
    with app.app_context():
        students = [db.session.get(Student, i) for i in ids]
        res = T.attendance_performance_correlation(students, metric='jamb')
        assert res['n'] == 3
        assert res['coefficient'] is not None and res['coefficient'] > 0.5
        assert 'positive' in res['strength']
