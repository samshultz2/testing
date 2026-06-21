"""Analytics inference engine: computes insights and PERSISTS them, refreshed
event-driven when results change."""
import json

from config import Config
from models import db, Student, WAECResult
from models.analytics_models import StudentRiskAssessment, AcademicPrediction
from utils.analytics_engine import AnalyticsEngine, recompute_student_safe
from tests.conftest import login_token, auth_csrf


def _make_student(app, name='Engine Test One'):
    with app.app_context():
        s = Student(student_id='ENG' + str(abs(hash(name)) % 100000),
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
        assert pred.model_version == 'rule-v1'


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
