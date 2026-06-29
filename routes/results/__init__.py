"""
Results management routes - WAEC, JAMB, and Analytics Dashboard
Comprehensive academic performance tracking and analysis
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response, abort, current_app
from utils.helpers import get_active_term, get_active_session
from collections import defaultdict
from models import (db, Student, WAECResult, JAMBResult, UniversityCutoff, SchoolSettings, StudentEnrollment,
                    ClassArmAssignment, TermSummary)
import json as _json
from utils.access_control import login_required, admin_required
from utils.security import rate_limited
from utils.analytics_engine import recompute_student_safe
from utils.branch_scope import require_branch_access, scope_query, scope_by_student, viewing_branch_id
from utils.audit import log_action
from utils.helpers import (
    WAEC_SUBJECTS, WAEC_GRADES, WAEC_DEFAULT_SUBJECTS, STREAM_WAEC_SUBJECTS, get_sss3_students,
    student_subject_map,
)
from datetime import date as _date
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from utils.web_exports import xlsx_response
from utils.analytics_service import AcademicAnalytics

results_bp = Blueprint('results', __name__, url_prefix='/results')


# --- SPA helpers (no-reload React shell + JSON-aware action responses) ---
from utils.spa import section_responders
_wants_json, _render, _ok, _err = section_responders(
    'results/app.html', 'res_json', 'results.index')


def _is_admin_results():
    from utils.access_control import is_admin
    return is_admin()




# ============================================================================
# WAEC RESULTS - COMPREHENSIVE DASHBOARD
# ============================================================================













# ============================================================================
# WAEC DELETE ROUTES
# ============================================================================





# ============================================================================
# JAMB RESULTS - COMPREHENSIVE DASHBOARD
# ============================================================================









def _read_uploaded_text(file):
    """Return OCR/PDF text + a flag for whether the upload was usable."""
    from utils.waec_ocr import (tesseract_available, extract_text, pdf_available, extract_text_from_pdf)
    filename = (file.filename or '').lower()
    data = file.read()
    if (file.mimetype == 'application/pdf') or filename.endswith('.pdf'):
        if not pdf_available():
            return None
        return extract_text_from_pdf(data)
    if not tesseract_available():
        return None
    return extract_text(data)






















def _mock_waec_trend(branch_id):
    """School-level Mock WAEC progression for the active session (branch-scoped):
    one point per mock exam, showing whether the cohort is climbing toward the
    5-credit WASSCE benchmark."""
    from models.mock_waec import MockWAECAnalytics
    session = get_active_session()
    if not session:
        return []
    out = []
    for c in MockWAECAnalytics.compare_mock_exams(session.id, branch_id):
        out.append({
            'label': c['exam'].display_name,
            'avg_credits': c['avg_credits'],
            'students': c['student_count'],
            'with_5_credits_pct': c['with_5_credits_pct'],
        })
    return out


def _mock_jamb_trend(branch_id):
    """School-level Mock JAMB progression for the active session (branch-scoped):
    one point per mock exam, in order. Drives the Mock JAMB trend chart and shows
    whether the cohort is climbing toward the JAMB benchmarks."""
    from models.mock_jamb import MockJAMBExam
    session = get_active_session()
    if not session:
        return []
    q = MockJAMBExam.query.filter_by(session_id=session.id)
    if branch_id is not None:
        q = q.filter(MockJAMBExam.branch_id == branch_id)
    out = []
    for ex in q.order_by(MockJAMBExam.exam_number).all():
        scores = [r.total_score for r in ex.results.all()]
        if not scores:
            continue
        out.append({
            'label': ex.display_name,
            'average': round(sum(scores) / len(scores), 1),
            'students': len(scores),
            'above_200_pct': round(sum(1 for s in scores if s >= 200) / len(scores) * 100, 1),
        })
    return out


















# ============================================================================
# ANALYTICS API ENDPOINTS
# ============================================================================











def _at_risk_register(limit=None):
    """The persisted at-risk register: latest stored assessment per in-scope
    SSS3 student, RED/AMBER only, highest risk first. Reads engine rows (the
    analysis is for SSS3 only, so non-SSS3 assessments are excluded)."""
    from models.analytics_models import StudentRiskAssessment
    sss3_ids = {s.id for s in get_sss3_students()}
    rows = (scope_by_student(StudentRiskAssessment.query, StudentRiskAssessment)
            .order_by(StudentRiskAssessment.overall_risk_score.desc())
            .all())
    seen, out = set(), []
    for r in rows:
        if r.student_id in seen or r.student_id not in sss3_ids:
            continue
        seen.add(r.student_id)
        if r.risk_level not in ('RED', 'AMBER'):
            continue
        out.append({
            'student_id': r.student_id,
            'student_name': r.student.full_name if r.student else '',
            'risk_level': r.risk_level,
            'overall_risk_score': r.overall_risk_score,
            'risk_factors': _json.loads(r.risk_factors or '[]'),
            'recommendations': _json.loads(r.recommendations or '[]'),
            'assessment_date': r.assessment_date.isoformat() if r.assessment_date else None,
        })
        if limit and len(out) >= limit:
            break
    return out












# ============================================================================
# EXPORT FUNCTIONALITY
# ============================================================================





# ============================================================================
# ENHANCED WAEC ANALYTICS
# ============================================================================





# ============================================================================
# WAEC-JAMB CORRELATION & PREDICTIONS
# ============================================================================





def _scope_focus_to_classes(report, labels):
    """Trim a focus report to a teacher's own SSS3 classes: keep only those
    per-class rows, drop subjects with no presence in those classes, and limit
    at-risk flags to the teacher's classes."""
    if not labels:
        report['focus'] = []
        report['at_risk'] = []
        report['classes'] = []
        return report
    kept = []
    for e in report['focus']:
        pc = [c for c in e['per_class'] if c['class'] in labels]
        if not pc:
            continue
        e = dict(e); e['per_class'] = pc
        kept.append(e)
    report['focus'] = kept
    report['at_risk'] = [f for f in report['at_risk'] if f.get('class') in labels]
    report['classes'] = sorted(labels)
    return report

__all__ = [_n for _n in dir() if not _n.startswith('__')]

from . import waec, jamb, analytics, predictions, cutoffs, imports  # noqa: E402,F401  (registers routes)
