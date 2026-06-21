"""Analytics inference engine: computes insights and PERSISTS them, refreshed
event-driven when results change."""
import json

from config import Config
from models import db, Student, WAECResult
from models.analytics_models import StudentRiskAssessment, AcademicPrediction
from utils.analytics_engine import AnalyticsEngine, recompute_student_safe
from tests.conftest import login_token, auth_csrf


def _make_student(app, name='Engine Test One'):
    import uuid
    with app.app_context():
        s = Student(student_id='ENG' + uuid.uuid4().hex[:10],
                    first_name=name.split()[-1], surname=name.split()[0], gender='Male')
        db.session.add(s)
        db.session.commit()
        return s.id


def _give_waec(app, sid, grades):
    with app.app_context():
        for subj, g in grades.items():
            db.session.add(WAECResult(student_id=sid, exam_year=2025, subject=subj, grade=g))
        db.session.commit()


def test_recompute_persists_risk_and_prediction(app):
    sid = _make_student(app, 'Engine Risky')
    # Multiple failures + missing credits => elevated academic risk.
    _give_waec(app, sid, {
        'ENGLISH LANGUAGE': 'F9', 'MATHEMATICS': 'E8', 'BIOLOGY': 'F9',
        'CHEMISTRY': 'E8', 'PHYSICS': 'D7',
    })
    with app.app_context():
        AnalyticsEngine.recompute_student(sid)
        risk = StudentRiskAssessment.query.filter_by(student_id=sid).first()
        assert risk is not None
        assert risk.risk_level in ('RED', 'AMBER')
        assert risk.overall_risk_score and risk.overall_risk_score > 0
        assert json.loads(risk.risk_factors)            # non-empty factors
        pred = AcademicPrediction.query.filter_by(student_id=sid, prediction_type='JAMB_SCORE').first()
        assert pred is not None and pred.predicted_value
        assert pred.model_version == 'waec-rule-v1'   # no mocks -> WAEC fallback


def test_recompute_is_idempotent_upsert(app):
    sid = _make_student(app, 'Engine Idempotent')
    _give_waec(app, sid, {'ENGLISH LANGUAGE': 'A1', 'MATHEMATICS': 'A1', 'BIOLOGY': 'B2'})
    with app.app_context():
        AnalyticsEngine.recompute_student(sid)
        AnalyticsEngine.recompute_student(sid)   # second run must not duplicate
        assert StudentRiskAssessment.query.filter_by(student_id=sid).count() == 1
        assert AcademicPrediction.query.filter_by(student_id=sid).count() == 1


def test_safe_recompute_swallows_errors(app):
    # A non-existent student yields no data and must not raise.
    with app.app_context():
        recompute_student_safe(99999999)   # no exception = pass


def test_results_save_triggers_recompute(app):
    """Saving WAEC results through the route refreshes the persisted analytics."""
    sid = _make_student(app, 'Engine Hooked')
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    tok = auth_csrf(c)
    c.post('/results/waec/add', data={
        '_csrf_token': tok, 'student_id': str(sid), 'exam_year': '2025',
        'subject[]': ['ENGLISH LANGUAGE', 'MATHEMATICS', 'BIOLOGY'],
        'grade[]': ['F9', 'E8', 'F9'],
    }, follow_redirects=True)
    with app.app_context():
        # The hook ran on save — an assessment now exists without a manual call.
        assert StudentRiskAssessment.query.filter_by(student_id=sid).first() is not None


def _active_session(app):
    from models import AcademicSession
    with app.app_context():
        s = AcademicSession.query.filter_by(is_active=True).first()
        if not s:
            s = AcademicSession(name='2025/2026', is_active=True)
            db.session.add(s)
            db.session.commit()
        return s.id


def _give_mocks(app, sid, session_id, scores):
    from datetime import date
    from models.mock_jamb import MockJAMBExam, MockJAMBResult
    with app.app_context():
        for i, sc in enumerate(scores, 1):
            ex = MockJAMBExam.query.filter_by(session_id=session_id, exam_number=i,
                                              branch_id=None).first()
            if not ex:
                ex = MockJAMBExam(name=f'Mock {i}', exam_number=i, session_id=session_id,
                                  exam_date=date(2025, 1, i + 1))
                db.session.add(ex)
                db.session.commit()
            db.session.add(MockJAMBResult(student_id=sid, mock_exam_id=ex.id, total_score=sc))
        db.session.commit()


def test_prediction_prefers_mock_trajectory(app):
    """With >=2 mocks, the JAMB prediction is driven by the mock trend, not WAEC."""
    sid = _make_student(app, 'Engine Mocked')
    ssid = _active_session(app)
    _give_mocks(app, sid, ssid, [190, 230])
    with app.app_context():
        AnalyticsEngine.recompute_student_prediction(sid)
        pred = AcademicPrediction.query.filter_by(student_id=sid).first()
        assert pred is not None and pred.model_version == 'mock-trend-v1'
        assert pred.predicted_value


def test_declining_mocks_raise_trend_risk(app):
    """A falling mock trajectory feeds the trend-risk component (previously always 0)."""
    sid = _make_student(app, 'Engine Declining')
    ssid = _active_session(app)
    _give_mocks(app, sid, ssid, [250, 200])
    with app.app_context():
        AnalyticsEngine.recompute_student_risk(sid)
        risk = StudentRiskAssessment.query.filter_by(student_id=sid).first()
        assert risk.trend_risk_score and risk.trend_risk_score > 0
        assert any('declin' in f.lower() for f in json.loads(risk.risk_factors))


def test_at_risk_register_lists_only_elevated(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    sid = _make_student(app, 'Engine AtRisk')
    _give_waec(app, sid, {'ENGLISH LANGUAGE': 'F9', 'MATHEMATICS': 'F9', 'BIOLOGY': 'F9'})
    with app.app_context():
        AnalyticsEngine.recompute_student(sid)
    data = c.get('/results/api/at-risk').get_json()
    assert any(s['student_id'] == sid for s in data['students'])
    assert all(s['risk_level'] in ('RED', 'AMBER') for s in data['students'])
