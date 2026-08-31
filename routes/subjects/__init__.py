"""
Subjects and Score Management routes
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from utils.helpers import get_active_term, session_terms
from utils.web_exports import xlsx_response
from utils.db_tx import safe_transaction
from utils.branch_scope import require_branch_access
from models import (
    db, Subject, ClassSubject, AssessmentType, SubjectAssessmentOverride,
    StudentScore, StudentEnrollment, ClassArmAssignment, Term, SchoolClass,
    ClassArm, Student, GradeScale, SchoolSettings, TermSummary
)
from utils.access_control import (
    login_required, can_access_class, can_enter_results,
    filter_classes_for_user, is_admin, result_card_required
)

subjects_bp = Blueprint('subjects', __name__, url_prefix='/subjects')

SUBJECT_CATEGORIES = ['Science', 'Arts', 'Commercial', 'General', 'Languages', 'Vocational']


# --- SPA helpers (no-reload React shell + JSON-aware action responses) ---
from utils.spa import section_responders
_wants_json, _render, _ok, _err = section_responders(
    'subjects/app.html', 'subj_json', 'subjects.subjects_list')


def _nav_urls():
    return {'subjects': url_for('subjects.subjects_list'),
            'class_subjects': url_for('subjects.class_subjects_list')}


# ---------------------------------------------------------------------------
# Shared score-write safety rules (publication lock, edit-permission, range
# clamp, audit). Every score-persist path routes through persist_scores() so the
# rules can't drift between the grid / bulk / import / scan-save entry points.
# ---------------------------------------------------------------------------
def results_locked(term_id):
    """True when a term's results are published and the current user is NOT an
    admin. Grades must not be silently rewritten after release to the parent /
    student portal; an admin can unpublish (Result Portal) to make corrections."""
    if is_admin():
        return False
    t = db.session.get(Term, term_id) if term_id else None
    return bool(t and t.results_published)


def can_edit_existing_results(assignment_id=None, subject_id=None):
    """Whether the user may CHANGE or DELETE an already-entered score (vs. only
    entering a new one). Admins and teachers holding the can_edit_results flag
    may; an enter-only teacher can add fresh scores but not alter existing ones."""
    if is_admin():
        return True
    from utils.access_control import get_teacher_profile
    t = get_teacher_profile()
    if not (t and t.can_edit_results):
        return False
    return can_enter_results(assignment_id, subject_id)


def log_score_changes(term_id, class_subject_id, changes):
    """Audit grade edits. ``changes`` is a list of (student_id, old, new); None
    means the score was absent. No-ops are dropped. One compact log line per save
    so grade tampering is attributable after the fact."""
    real = [(sid, old, new) for sid, old, new in changes if old != new]
    if not real:
        return
    from utils.audit import log_action

    def _f(v):
        return '∅' if v is None else f'{v:g}'
    sample = '; '.join(f'stu{sid}:{_f(old)}→{_f(new)}' for sid, old, new in real[:15])
    more = '' if len(real) <= 15 else f' (+{len(real) - 15} more)'
    log_action('results.score_edit',
               detail=f'term={term_id} class_subject={class_subject_id}: '
                      f'{len(real)} change(s) — {sample}{more}')


def persist_scores(term_id, assignment_id, class_subject_id, subject_id, items,
                   *, allow_delete=True):
    """Apply score cells with the shared safety rules and audit the result.

    ``items`` is an iterable of (student_id, assessment_type_id, raw_value,
    max_score). Adds/updates/deletes on the session (caller commits). Returns a
    counts dict, or None if writes are blocked because the term is published.
    """
    if results_locked(term_id):
        return None
    may_edit = can_edit_existing_results(assignment_id, subject_id)
    counts = {'saved': 0, 'rejected': 0, 'blocked': 0}
    changes = []
    for student_id, at_id, raw, max_score in items:
        raw = '' if raw is None else str(raw).strip()
        existing = StudentScore.query.filter_by(
            student_id=student_id, class_subject_id=class_subject_id,
            assessment_type_id=at_id).first()
        old = existing.score if existing else None
        if raw == '':
            if existing and allow_delete:
                if not may_edit:
                    counts['blocked'] += 1
                    continue
                changes.append((student_id, old, None))
                db.session.delete(existing)
                counts['saved'] += 1
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        # Reject out-of-range values (negative, or above the assessment maximum)
        # rather than silently clamping — a stored clamp would misrepresent the mark.
        if val < 0 or (max_score and val > max_score):
            counts['rejected'] += 1
            continue
        if existing:
            if existing.score == val:
                continue                      # genuine no-op, don't audit
            if not may_edit:
                counts['blocked'] += 1
                continue
            changes.append((student_id, old, val))
            existing.score = val
            counts['saved'] += 1
        else:
            db.session.add(StudentScore(
                student_id=student_id, class_subject_id=class_subject_id,
                assessment_type_id=at_id, score=val))
            changes.append((student_id, None, val))
            counts['saved'] += 1
    log_score_changes(term_id, class_subject_id, changes)
    return counts


# ============================================================================
# SUBJECTS CRUD
# ============================================================================











# ============================================================================
# CLASS-SUBJECT ASSIGNMENT
# ============================================================================











# ============================================================================
# SCORE ENTRY
# ============================================================================





# ============================================================================
# VIEW SCORES / BROADSHEET
# ============================================================================













# ============================================================================
# STUDENT REPORT CARD
# ============================================================================





# ============================================================================
# API ENDPOINTS
# ============================================================================





# ============================================================================
# EXPORT BROADSHEET TO EXCEL
# ============================================================================



# ============================================================================
# BULK SCORE IMPORT FROM EXCEL
# ============================================================================





# ============================================================================
# SCORE-SHEET (BROADSHEET) IMAGE IMPORT — Tesseract OCR
# ============================================================================

def _sheet_columns(class_subject, term=None):
    """Assessment columns for a subject in a term, ordered as they appear on a
    printed broadsheet. Returns [(assessment_type, max_score), ...]. When ``term``
    is given, per-term assessment settings apply."""
    from utils.assessments import subject_columns
    from utils.waec_ocr import SHEET_COLUMN_ORDER
    cols = subject_columns(class_subject.subject, term=term)  # [(at, max)] in storage order
    # Collapse assessment types that share a short name. A mis-seeded tenant DB can
    # hold two active "EXAM"/"CBT" types; without this the sheet showed each column
    # twice and split a single pasted value across the duplicate ids (scores then
    # looked lost on the report card). Keep the first (lowest order) per short name.
    present = {}
    for at, mx in cols:
        sn = (at.short_name or at.name or '').upper()
        present.setdefault(sn, (at, mx))
    ordered = [present[sn] for sn in SHEET_COLUMN_ORDER if sn in present]
    # Append any remaining columns not covered by the canonical order (defensive).
    seen_sn = {sn for sn in SHEET_COLUMN_ORDER if sn in present}
    ordered += [(at, mx) for sn, (at, mx) in present.items() if sn not in seen_sn]
    return ordered


def _scan_selector_context():
    """Shared term/class/subject selector context for the scan pages."""
    term_id = request.values.get('term_id', type=int)
    assignment_id = request.values.get('assignment_id', type=int)
    class_subject_id = request.values.get('class_subject_id', type=int)

    if not term_id:
        active_term = get_active_term()
        if active_term:
            term_id = active_term.id

    terms = session_terms()
    assignments = []
    if term_id:
        all_assignments = ClassArmAssignment.query.filter_by(term_id=term_id).all()
        assignments = filter_classes_for_user(all_assignments)

    class_subjects = []
    assignment = db.session.get(ClassArmAssignment, assignment_id) if assignment_id else None
    if assignment:
        class_subjects = ClassSubject.query.filter_by(
            term_id=term_id, class_id=assignment.class_id, is_active=True
        ).filter(
            (ClassSubject.arm_id == None) | (ClassSubject.arm_id == assignment.arm_id)
        ).join(Subject).order_by(Subject.name).all()

    return {
        'terms': terms, 'term_id': term_id,
        'assignments': assignments, 'assignment_id': assignment_id,
        'class_subjects': class_subjects, 'class_subject_id': class_subject_id,
    }




# Tokens that mean "no score" in a pasted cell.
_PASTE_BLANKS = {'', '-', '--', '–', 'nil', 'absent', 'a', 'x', 'na', 'n/a'}


def _parse_pasted_scores(text, num_columns):
    """Parse pasted comma/tab-separated rows into ``[{'identifier', 'cells'}]``.

    One student per line: the first field is the identifier (admission number or
    name), the remaining fields are scores in the sheet's column order. Blank /
    dash / 'absent' cells become empty. A leading header row is skipped."""
    import re as _re
    rows = []
    for raw in text.splitlines():
        line = raw.strip().strip(',').strip()
        if not line:
            continue
        parts = [p.strip() for p in _re.split(r'[,\t]', line)]
        ident = parts[0].strip() if parts else ''
        if not ident:
            continue
        # Skip an obvious header line — the first field is a header label, not a
        # real student (column headers like CA1/CA2 legitimately contain digits,
        # so we key off the identifier word, not the trailing cells).
        key = _re.sub(r'[^a-z]', '', ident.lower())
        if key in {'name', 'names', 'fullname', 'student', 'students', 'studentname',
                   'adm', 'admno', 'admission', 'admissionnumber', 'admissionno',
                   'sn', 'sno', 'no', 'reg', 'regno', 'serial'}:
            continue
        cells = []
        for c in parts[1:1 + num_columns]:
            c = c.strip()
            if c.lower() in _PASTE_BLANKS:
                cells.append('')
            else:
                m = _re.search(r'\d+(?:\.\d+)?', c)
                cells.append(m.group(0) if m else '')
        rows.append({'identifier': ident, 'cells': cells})
    return rows






# ============================================================================
# PRINT ALL REPORT CARDS
# ============================================================================

__all__ = [_n for _n in dir() if not _n.startswith('__')]

from . import crud, scores, reports  # noqa: E402,F401  (registers routes)
