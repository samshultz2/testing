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
    student_subject_map, resolve_exam_year, session_exam_year, exam_year_choices,
)
from datetime import date as _date
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from utils.web_exports import xlsx_response
from utils.analytics_service import AcademicAnalytics

results_bp = Blueprint('results', __name__, url_prefix='/results')


def students_needing_result(students, result_model, exam_year):
    """Filter the eligible cohort down to students who do NOT yet have a
    ``result_model`` (WAECResult/JAMBResult) entered for ``exam_year`` — so the
    add-result dropdowns only offer students still awaiting entry. ``students``
    is the already-branch-scoped list from get_sss3_students()."""
    if not students or not exam_year:
        return students
    ids = [s.id for s in students]
    entered = {sid for (sid,) in db.session.query(result_model.student_id)
               .filter(result_model.student_id.in_(ids),
                       result_model.exam_year == exam_year).distinct().all()}
    return [s for s in students if s.id not in entered]


# --- SPA helpers (no-reload React shell + JSON-aware action responses) ---
from utils.spa import section_responders
_wants_json, _render, _ok, _err = section_responders(
    'results/app.html', 'res_json', 'results.index')


def _is_admin_results():
    from utils.access_control import is_admin
    return is_admin()


def _student_in_scope(student_id):
    """Load a student by id and confirm the current user's branch may touch it —
    used to guard the result-entry write paths where the student_id comes from
    the form (not a scoped roster). Returns the Student, or None when it doesn't
    exist, belongs to another branch, or falls outside an SSS3-arm teacher's
    own-arm exam scope."""
    from utils.branch_scope import can_access_branch
    from utils.access_control import exam_student_scope
    s = db.session.get(Student, student_id) if student_id else None
    if not s or not can_access_branch(s.branch_id):
        return None
    scope = exam_student_scope()
    if scope is not None and s.id not in scope:
        return None
    return s


def _assert_exam_student(student_id):
    """Abort 403 if a derived SSS3-arm teacher tries to open/edit a student
    outside their own arm(s). No-op for admins and full-module holders."""
    from utils.access_control import exam_student_scope
    scope = exam_student_scope()
    if scope is not None and int(student_id) not in scope:
        abort(403)




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


# --------------------------------------------------------------------------- #
# Cached school statistics
# --------------------------------------------------------------------------- #
# The WAEC/JAMB school statistics and their correlation walk every result row for
# the year, so the analytics hub recomputes a lot on each load. They only change
# when results are added/edited (or on an explicit recompute), so cache them per
# (year, branch) with a short TTL and bust on recompute.
_STATS_TTL = 900          # 15 min — refreshed sooner by recompute/results edits


def _stats_cache_key(kind, year, branch_id):
    return f'exam_hub:{kind}:{year}:{branch_id if branch_id is not None else "all"}'


def _cached_school_stats(kind, year, branch_id, compute):
    """Return ``compute()`` for (kind, year, branch), memoised in AnalyticsCache.

    Best-effort: any cache error falls through to a live computation so the hub
    never breaks because of the cache layer."""
    from models.analytics_models import AnalyticsCache
    key = _stats_cache_key(kind, year, branch_id)
    try:
        hit = AnalyticsCache.get(key)
        if hit is not None:
            return hit if hit != '__none__' else None
    except Exception:
        db.session.rollback()
    val = compute()
    try:
        AnalyticsCache.set(key, val if val is not None else '__none__', _STATS_TTL)
    except Exception:
        db.session.rollback()
    return val


def waec_school_stats(year, branch_id):
    return _cached_school_stats(
        'waec', year, branch_id,
        lambda: AcademicAnalytics.get_waec_school_statistics(year, branch_id))


def jamb_school_stats(year, branch_id):
    return _cached_school_stats(
        'jamb', year, branch_id,
        lambda: AcademicAnalytics.get_jamb_school_statistics(year, branch_id))


def waec_jamb_correlation(year, branch_id):
    return _cached_school_stats(
        'corr', year, branch_id,
        lambda: AcademicAnalytics.calculate_waec_jamb_correlation(year, branch_id))


def bust_school_stats(year=None, branch_id=None):
    """Drop cached school-stats rows so the next hub load recomputes. Called after
    a recompute; broad by design (a bulk import can touch any year/branch)."""
    from models.analytics_models import AnalyticsCache
    try:
        AnalyticsCache.query.filter(
            AnalyticsCache.cache_key.like('exam_hub:%')).delete(synchronize_session=False)
        db.session.commit()
    except Exception:
        db.session.rollback()


# --------------------------------------------------------------------------- #
# Comparative analytics (branch-vs-branch, cohort-vs-cohort)
# --------------------------------------------------------------------------- #
def branch_comparison(year):
    """Per-branch headline metrics for ``year``, ranked by JAMB mean. Only built
    when viewing all branches and at least two branches have data — otherwise
    there is nothing to compare. Uses the cached per-branch stat wrappers."""
    from models.models_branch import Branch
    from utils import exam_compare
    if viewing_branch_id() is not None:          # a single branch is in scope
        return []
    rows = []
    for b in Branch.query.filter_by(is_active=True).order_by(Branch.name).all():
        m = exam_compare.headline_metrics(jamb_school_stats(year, b.id),
                                          waec_school_stats(year, b.id))
        if m['has_data']:
            rows.append({'id': b.id, 'label': b.name, 'metrics': m})
    return exam_compare.rank_branches(rows) if len(rows) >= 2 else []


def sss3_subject_teachers():
    """``{subject_name: [teacher_name, ...]}`` for the SSS3 class in the active
    term — the teachers who own each WAEC/JAMB exam subject. Empty when the class
    or term isn't set up. One query."""
    from models import ClassSubject, Subject
    from utils.helpers import get_sss3_class
    cls = get_sss3_class()
    term = get_active_term()
    if not cls or not term:
        return {}
    out = {}
    rows = (db.session.query(Subject.name, ClassSubject.teacher_name)
            .join(ClassSubject, ClassSubject.subject_id == Subject.id)
            .filter(ClassSubject.class_id == cls.id,
                    ClassSubject.term_id == term.id,
                    ClassSubject.is_active == True).all())
    for subject_name, teacher in rows:
        name = (teacher or '').strip()
        if name:
            out.setdefault(subject_name, set()).add(name)
    return {k: sorted(v) for k, v in out.items()}


def year_comparison(year, compare_year, branch_id):
    """A/B headline comparison of ``year`` vs ``compare_year`` for the branch in
    scope, with per-metric deltas. Returns None when the pair is invalid."""
    from utils import exam_compare
    if not compare_year or compare_year == year:
        return None
    a = exam_compare.headline_metrics(jamb_school_stats(year, branch_id),
                                      waec_school_stats(year, branch_id))
    b = exam_compare.headline_metrics(jamb_school_stats(compare_year, branch_id),
                                      waec_school_stats(compare_year, branch_id))
    if not (a['has_data'] and b['has_data']):
        return None
    return {'year': year, 'compare_year': compare_year,
            'metrics': exam_compare.compare_years(a, b)}


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

from . import waec, jamb, analytics, predictions, cutoffs, imports, waec_cert  # noqa: E402,F401  (registers routes)
