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
from utils.helpers import get_active_session

logger = logging.getLogger(__name__)

# Bump when the scoring/prediction logic changes, so stored rows are traceable.
MODEL_VERSION = 'rule-v1'


class AnalyticsEngine:
    """Computes and upserts persisted analytics. One current row per student
    (per type); historical trends live in per-term snapshots (added separately).

    Inference draws on every external-exam signal we actually collect for SSS3
    students — WAEC, real JAMB and the Mock JAMB trajectory — not WAEC alone."""

    @staticmethod
    def _exam_signals(student_id):
        """Risk signals from real JAMB + the Mock JAMB trajectory, returned as
        ``(component_deltas, factor_strings)`` to augment the WAEC/attendance base.

        This is the JAMB/mock inference that was previously missing: a declining
        mock trend feeds trend-risk; sub-benchmark mock/JAMB scores feed academic
        risk. Everything degrades gracefully when a student lacks that data."""
        from models.mock_jamb import MockJAMBAnalytics
        from models.mock_waec import MockWAECAnalytics
        from models import JAMBResult

        extra = {'academic': 0, 'trend': 0}
        factors = []

        # Mock WAEC trajectory: credit count is the WASSCE success metric.
        waec_prog = MockWAECAnalytics.get_student_progress(student_id)
        if waec_prog and waec_prog['exam_count'] >= 1:
            credits = waec_prog['latest_credits']
            if credits < 5:
                extra['academic'] += 25
                factors.append(f"Latest mock WAEC below 5 credits ({credits})")
            if waec_prog['exam_count'] >= 2 and waec_prog['credit_change'] < 0:
                extra['trend'] += 20
                factors.append(f"Mock WAEC credits declining ({waec_prog['credit_change']:+d})")

        # Mock JAMB trajectory across all of the student's mocks (time-ordered).
        progress = MockJAMBAnalytics.get_student_progress(student_id)
        if progress and progress['exam_count'] >= 1:
            latest = progress['latest_score']
            if latest < 180:
                extra['academic'] += 25
                factors.append(f"Latest mock JAMB below 180 ({latest})")
            elif latest < 200:
                extra['academic'] += 10
                factors.append(f"Latest mock JAMB below the 200 benchmark ({latest})")
            if progress['exam_count'] >= 2:
                change = progress['total_change']
                if change <= -20:
                    extra['trend'] += 30
                    factors.append(f"Mock JAMB scores declining ({change:+d})")
                elif change < 0:
                    extra['trend'] += 15
                    factors.append(f"Mock JAMB scores slipping ({change:+d})")

        # Most recent actual JAMB sitting.
        jamb = (JAMBResult.query.filter_by(student_id=student_id)
                .order_by(JAMBResult.exam_year.desc()).first())
        if jamb and jamb.total_score is not None:
            if jamb.total_score < 180:
                extra['academic'] += 30
                factors.append(f"JAMB score below 180 ({jamb.total_score})")
            elif jamb.total_score < 200:
                extra['academic'] += 15
                factors.append(f"JAMB score below the 200 cut-off ({jamb.total_score})")

        return extra, factors

    @staticmethod
    def recompute_student_risk(student_id):
        """Upsert the student's :class:`StudentRiskAssessment`, combining the
        WAEC/attendance base with JAMB + Mock JAMB signals. Returns the row, or
        None if the student does not exist."""
        data = AcademicAnalytics.calculate_student_risk_score(student_id)
        if not data:
            return None

        extra, extra_factors = AnalyticsEngine._exam_signals(student_id)
        comp = dict(data.get('component_scores') or {})
        academic = min(100, (comp.get('academic') or 0) + extra['academic'])
        attendance = comp.get('attendance') or 0
        trend = min(100, (comp.get('trend') or 0) + extra['trend'])
        overall = round(academic * 0.5 + attendance * 0.3 + trend * 0.2, 1)
        level = 'RED' if overall >= 60 else 'AMBER' if overall >= 30 else 'GREEN'

        factors = list(data.get('risk_factors') or []) + extra_factors
        recommendations = AcademicAnalytics._generate_recommendations(factors)
        joined = ' '.join(extra_factors).lower()
        if 'declining' in joined or 'slipping' in joined:
            recommendations.append('Investigate the recent drop in mock scores and intensify revision')
        if 'mock jamb below' in joined or 'jamb score below' in joined:
            recommendations.append('Targeted JAMB CBT drilling on the weakest subjects')
        recommendations = list(dict.fromkeys(recommendations))  # dedupe, keep order

        row = (StudentRiskAssessment.query.filter_by(student_id=student_id)
               .order_by(StudentRiskAssessment.id.desc()).first())
        if row is None:
            row = StudentRiskAssessment(student_id=student_id)
            db.session.add(row)
        row.assessment_date = date.today()
        row.overall_risk_score = overall
        row.academic_risk_score = academic
        row.attendance_risk_score = attendance
        row.trend_risk_score = trend
        row.risk_level = level
        row.risk_factors = json.dumps(factors)
        row.recommendations = json.dumps(recommendations)
        return row

    @staticmethod
    def recompute_student_prediction(student_id):
        """Upsert the student's JAMB :class:`AcademicPrediction`.

        Prefers the Mock JAMB trajectory (the richest, most direct predictor) when
        the student has >=2 mocks in the active session; otherwise falls back to
        the WAEC->JAMB rule model. Returns the row, or None when neither basis
        exists."""
        from models.mock_jamb import MockJAMBAnalytics

        session = get_active_session()
        mock = MockJAMBAnalytics.predict_real_jamb(student_id, session.id) if session else None
        if mock:
            source = 'mock-trend-v1'
            predicted = mock.get('predicted_score')
            confidence = round((mock.get('confidence_level') or 0) / 100.0, 2)
            explanation = mock.get('recommendation')
            features = {'mock_count': mock.get('mock_count'), 'trend': mock.get('trend'),
                        'range': mock.get('predicted_range')}
        else:
            data = AcademicAnalytics.predict_jamb_score(student_id)
            if not data or 'error' in data:
                return None
            source = 'waec-rule-v1'
            predicted = data.get('predicted_score')
            confidence = data.get('confidence')
            explanation = data.get('explanation')
            features = data.get('factors', {})

        row = (AcademicPrediction.query
               .filter_by(student_id=student_id, prediction_type='JAMB_SCORE')
               .order_by(AcademicPrediction.id.desc()).first())
        if row is None:
            row = AcademicPrediction(student_id=student_id, prediction_type='JAMB_SCORE')
            db.session.add(row)
        row.prediction_date = date.today()
        row.predicted_value = str(predicted)
        row.confidence_score = confidence
        row.model_version = source
        row.features_used = json.dumps(features)
        row.explanation = explanation
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
