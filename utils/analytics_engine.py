"""Analytics inference engine.

The :class:`~utils.analytics_service.AcademicAnalytics` service computes student
insights live; this engine runs those computations and **persists** them
(risk assessments, JAMB predictions, WAEC↔JAMB correlation) so dashboards read
stored rows and we can track results over time.

Recompute is event-driven: routes that save results/scores call
:func:`recompute_student_safe` (best-effort — it never raises into the caller,
so a stats hiccup can't fail a results save). A manual bulk recompute is exposed
for backfilling existing data.
"""
import json
import logging
from datetime import date

from models import db, Student
from models.analytics_models import (StudentRiskAssessment, AcademicPrediction,
                                      WAECJAMBCorrelation)
from utils.analytics_service import AcademicAnalytics

logger = logging.getLogger(__name__)

# Bump when the scoring/prediction logic changes, so stored rows are traceable.
MODEL_VERSION = 'rule-v1'


class AnalyticsEngine:
    """Computes and upserts persisted analytics. One current row per student
    (per type); historical trends live in per-term snapshots (added separately)."""

    @staticmethod
    def recompute_student_risk(student_id):
        """Upsert the student's :class:`StudentRiskAssessment`. Returns the row,
        or None if the student has no data to assess."""
        data = AcademicAnalytics.calculate_student_risk_score(student_id)
        if not data:
            return None
        row = (StudentRiskAssessment.query.filter_by(student_id=student_id)
               .order_by(StudentRiskAssessment.id.desc()).first())
        if row is None:
            row = StudentRiskAssessment(student_id=student_id)
            db.session.add(row)
        comp = data.get('component_scores', {})
        row.assessment_date = date.today()
        row.overall_risk_score = data.get('overall_risk_score')
        row.academic_risk_score = comp.get('academic')
        row.attendance_risk_score = comp.get('attendance')
        row.trend_risk_score = comp.get('trend')
        row.risk_level = data.get('risk_level')
        row.risk_factors = json.dumps(data.get('risk_factors', []))
        row.recommendations = json.dumps(data.get('recommendations', []))
        return row

    @staticmethod
    def recompute_student_prediction(student_id):
        """Upsert the student's JAMB :class:`AcademicPrediction`. Returns the row,
        or None when there's no WAEC basis to predict from."""
        data = AcademicAnalytics.predict_jamb_score(student_id)
        if not data or 'error' in data:
            return None
        row = (AcademicPrediction.query
               .filter_by(student_id=student_id, prediction_type='JAMB_SCORE')
               .order_by(AcademicPrediction.id.desc()).first())
        if row is None:
            row = AcademicPrediction(student_id=student_id, prediction_type='JAMB_SCORE')
            db.session.add(row)
        row.prediction_date = date.today()
        row.predicted_value = str(data.get('predicted_score'))
        row.confidence_score = data.get('confidence')
        row.model_version = MODEL_VERSION
        row.features_used = json.dumps(data.get('factors', {}))
        row.explanation = data.get('explanation')
        return row

    @staticmethod
    def recompute_student(student_id, commit=True):
        """Recompute every per-student insight. Commits unless ``commit=False``
        (so a caller can batch many students into one transaction)."""
        risk = AnalyticsEngine.recompute_student_risk(student_id)
        pred = AnalyticsEngine.recompute_student_prediction(student_id)
        if commit:
            db.session.commit()
        return {'risk': risk, 'prediction': pred}

    @staticmethod
    def recompute_correlation(exam_year, branch_id=None, commit=True):
        """Upsert the overall WAEC↔JAMB :class:`WAECJAMBCorrelation` for a year."""
        data = AcademicAnalytics.calculate_waec_jamb_correlation(exam_year, branch_id)
        if not data or data.get('error') or not data.get('sample_size'):
            return None
        row = WAECJAMBCorrelation.query.filter_by(exam_year=exam_year, subject=None).first()
        if row is None:
            row = WAECJAMBCorrelation(exam_year=exam_year, subject=None)
            db.session.add(row)
        row.correlation_coefficient = data.get('correlation_coefficient')
        row.sample_size = data.get('sample_size')
        row.mean_waec_points = data.get('mean_waec_points')
        row.mean_jamb_score = data.get('mean_jamb_score')
        # Store predictive strength (HIGH/MODERATE/LOW) as a coarse accuracy proxy.
        strength = {'HIGH': 0.8, 'MODERATE': 0.5, 'LOW': 0.2}.get(data.get('predictive_power'))
        row.prediction_accuracy = strength
        if commit:
            db.session.commit()
        return row

    @staticmethod
    def recompute_all_students(student_ids=None, branch_id=None):
        """Backfill/refresh: recompute every (in-scope) student in one commit.
        Returns the count of students whose insights were written."""
        q = Student.query
        if branch_id is not None:
            q = q.filter(Student.branch_id == branch_id)
        if student_ids is not None:
            q = q.filter(Student.id.in_(student_ids or [-1]))
        written = 0
        for sid in [s.id for s in q.all()]:
            res = AnalyticsEngine.recompute_student(sid, commit=False)
            if res['risk'] is not None or res['prediction'] is not None:
                written += 1
        db.session.commit()
        return written


def recompute_student_safe(student_id):
    """Best-effort per-student recompute for use in result-saving routes.

    Swallows and logs any error (rolling back only the analytics work) so a
    failure here can never break the results save that triggered it."""
    try:
        AnalyticsEngine.recompute_student(student_id, commit=True)
    except Exception:
        logger.exception('analytics recompute failed for student %s', student_id)
        try:
            db.session.rollback()
        except Exception:
            pass
