"""Mock -> real calibration: predicted vs actual error stats."""
import uuid
from datetime import date

from models import db, AcademicSession, Student, JAMBResult, WAECResult
from models.mock_jamb import MockJAMBExam, MockJAMBResult
from models.mock_waec import MockWAECExam, MockWAECResult, waec_grade_from_score
from utils import exam_insights as EI


def _session(app):
    with app.app_context():
        s = AcademicSession(name='CAL ' + uuid.uuid4().hex[:5])
        db.session.add(s); db.session.commit()
        return s.id


def _student(app):
    with app.app_context():
        s = Student(student_id='CL' + uuid.uuid4().hex[:7].upper(), first_name='Cal',
                    surname='Ibrate', gender='Female')
        db.session.add(s); db.session.commit()
        return s.id


def test_jamb_calibration_measures_error(app):
    ssid = _session(app); sid = _student(app)
    with app.app_context():
        for n, total in ((1, 200), (2, 210)):          # mocks -> prediction ~205
            ex = MockJAMBExam(name=f'MJ{n}', exam_number=n, session_id=ssid,
                              exam_date=date(2025, 1, n))
            db.session.add(ex); db.session.flush()
            db.session.add(MockJAMBResult(student_id=sid, mock_exam_id=ex.id, total_score=total))
        db.session.add(JAMBResult(student_id=sid, exam_year=2025, total_score=230))  # actual
        db.session.commit()
        s = db.session.get(Student, sid)
        cal = EI.jamb_calibration([s])
        assert cal['n'] == 1
        assert cal['bias'] < 0            # mocks under-predicted the real score
        assert cal['mae'] >= 1


def test_waec_calibration_measures_credit_error(app):
    ssid = _session(app); sid = _student(app)
    with app.app_context():
        ex = MockWAECExam(name='MW1', exam_number=1, session_id=ssid, exam_date=date(2025, 1, 1))
        db.session.add(ex); db.session.flush()
        # mock: 5 credits
        for subj, sc in [('Mathematics', 70), ('English Language', 62), ('Biology', 60),
                         ('Chemistry', 58), ('Physics', 55)]:
            db.session.add(MockWAECResult(student_id=sid, mock_exam_id=ex.id, subject=subj,
                                          score=sc, grade=waec_grade_from_score(sc)))
        # actual: also 5 credits -> zero error
        for subj in ['Mathematics', 'English Language', 'Biology', 'Chemistry', 'Physics']:
            db.session.add(WAECResult(student_id=sid, exam_year=2025, subject=subj, grade='C4'))
        db.session.commit()
        s = db.session.get(Student, sid)
        cal = EI.waec_calibration([s])
        assert cal['n'] == 1
        assert cal['within_tol_pct'] == 100.0   # within +/-1 credit


def test_calibration_empty_when_no_pairs(app):
    sid = _student(app)
    with app.app_context():
        s = db.session.get(Student, sid)
        summary = EI.calibration_summary([s])
        assert summary['jamb']['n'] == 0 and summary['waec']['n'] == 0
