"""Mock WAEC credit logic must respect the English+Maths requirement: 5 credits
alone is not an admission pass."""
import uuid
from datetime import date

from models import db, AcademicSession, Student
from models.mock_waec import (MockWAECExam, MockWAECResult, MockWAECAnalytics,
                              waec_grade_from_score)


def _session(app):
    with app.app_context():
        s = AcademicSession.query.filter_by(is_active=True).first() or \
            AcademicSession(name='CORE 25/26', is_active=True)
        db.session.add(s); db.session.commit()
        return s.id


def _exam(app, ssid, n):
    with app.app_context():
        ex = MockWAECExam(name=f'Core Mock {n}', exam_number=n, session_id=ssid,
                          exam_date=date(2025, 2, n))
        db.session.add(ex); db.session.commit()
        return ex.id


def _student(app):
    with app.app_context():
        s = Student(student_id='C' + uuid.uuid4().hex[:7].upper(),
                    first_name='Core', surname='Tester', gender='Male')
        db.session.add(s); db.session.commit()
        return s.id


def _add(app, sid, exam_id, scores):
    with app.app_context():
        for subj, sc in scores.items():
            db.session.add(MockWAECResult(student_id=sid, mock_exam_id=exam_id,
                                          subject=subj, score=sc,
                                          grade=waec_grade_from_score(sc)))
        db.session.commit()


# 5 credits but English failed -> NOT an admission pass.
FIVE_NO_ENGLISH = {'Mathematics': 70, 'Biology': 60, 'Chemistry': 60,
                   'Physics': 60, 'Economics': 60, 'English Language': 30}
# 5 credits including English & Maths -> admission-grade.
FIVE_WITH_CORE = {'Mathematics': 70, 'English Language': 60, 'Biology': 60,
                  'Chemistry': 60, 'Physics': 60, 'Economics': 30}


def test_five_credits_without_english_is_not_admission_pass(app):
    ssid = _session(app); exam_id = _exam(app, ssid, 1); sid = _student(app)
    _add(app, sid, exam_id, FIVE_NO_ENGLISH)
    with app.app_context():
        s = MockWAECAnalytics.get_student_exam_summary(sid, exam_id)
        assert s['credits'] == 5
        assert s['has_5_credits'] is True          # the naive count
        assert s['has_5_incl_core'] is False       # but not admissible
        assert s['missing_core'] == ['English Language']


def test_five_credits_with_core_is_admission_pass(app):
    ssid = _session(app); exam_id = _exam(app, ssid, 2); sid = _student(app)
    _add(app, sid, exam_id, FIVE_WITH_CORE)
    with app.app_context():
        s = MockWAECAnalytics.get_student_exam_summary(sid, exam_id)
        assert s['credits'] == 5
        assert s['has_5_incl_core'] is True
        assert s['missing_core'] == []


def test_exam_statistics_reports_core_inclusive_rate(app):
    ssid = _session(app); exam_id = _exam(app, ssid, 3)
    s1 = _student(app); s2 = _student(app)
    _add(app, s1, exam_id, FIVE_NO_ENGLISH)    # 5 credits, no English
    _add(app, s2, exam_id, FIVE_WITH_CORE)     # 5 credits incl core
    with app.app_context():
        stats = MockWAECAnalytics.get_exam_statistics(exam_id)['statistics']
        assert stats['with_5_credits'] == 2            # both have 5 raw credits
        assert stats['with_5_incl_core'] == 1          # only one is admissible
        assert stats['with_5_incl_core_pct'] == 50.0


def test_prediction_flags_missing_core(app):
    ssid = _session(app); exam_id = _exam(app, ssid, 4); sid = _student(app)
    _add(app, sid, exam_id, FIVE_NO_ENGLISH)
    with app.app_context():
        pred = MockWAECAnalytics.predict_waec(sid, ssid)
        assert pred['meets_minimum'] is True               # 5 credits projected
        assert pred['meets_minimum_incl_core'] is False    # but English missing
        assert 'English Language' in pred['missing_core']
