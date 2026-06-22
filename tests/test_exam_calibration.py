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


def test_calibration_query_count_bounded_for_empty_pool(app):
    """Students with no results add no per-student queries — only the bulk loads."""
    from sqlalchemy import event
    from models import db

    def count(n_students):
        ids = [_student(app) for _ in range(n_students)]
        with app.app_context():
            students = [db.session.get(Student, i) for i in ids]
            c = {'q': 0}
            eng = db.engine

            def before(*a, **k):
                c['q'] += 1
            event.listen(eng, 'before_cursor_execute', before)
            try:
                EI.calibration_summary(students)
            finally:
                event.remove(eng, 'before_cursor_execute', before)
            return c['q']

    # No valid pairs in either cohort -> query count must not grow with N.
    assert count(2) == count(8)


def test_calibrate_jamb_pure():
    # No calibration, or too few samples -> unchanged.
    assert EI.calibrate_jamb(200, None) == (200, None)
    assert EI.calibrate_jamb(200, {'bias': 12, 'n': 3}) == (200, None)
    assert EI.calibrate_jamb(200, {'bias': 0.4, 'n': 50}) == (200, None)   # bias too small
    # Over-prediction is subtracted; under-prediction added; both clamped 0..400.
    assert EI.calibrate_jamb(200, {'bias': 12, 'n': 10}) == (188, 12.0)
    assert EI.calibrate_jamb(200, {'bias': -15, 'n': 10}) == (215, -15.0)
    assert EI.calibrate_jamb(390, {'bias': -20, 'n': 10}) == (400, -20.0)


def test_projected_jamb_applies_calibration(app):
    ssid = _session(app); sid = _student(app)
    with app.app_context():
        for n, total in ((1, 200), (2, 210)):
            ex = MockJAMBExam(name=f'PJ{n}', exam_number=n, session_id=ssid,
                              exam_date=date(2025, 1, n))
            db.session.add(ex); db.session.flush()
            db.session.add(MockJAMBResult(student_id=sid, mock_exam_id=ex.id, total_score=total))
        db.session.commit()
        st = db.session.get(Student, sid)
        raw = EI.projected_jamb(st, ssid)                       # uncalibrated
        cal = EI.projected_jamb(st, ssid, {'bias': 15, 'n': 12})
        assert cal['score'] == max(0, raw['score'] - 15)
        assert cal['calibrated_by'] == 15.0 and cal['raw_score'] == raw['score']


def test_get_jamb_bias_is_cached(app):
    from models.analytics_models import AnalyticsCache
    with app.app_context():
        b1 = EI.get_jamb_bias()
        assert 'bias' in b1 and 'n' in b1
        assert AnalyticsCache.get(EI.JAMB_BIAS_CACHE_KEY) is not None   # persisted
        assert EI.get_jamb_bias() == b1                                 # served from cache
