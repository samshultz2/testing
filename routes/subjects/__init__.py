"""
Subjects and Score Management routes
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from utils.helpers import get_active_term
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

def _sheet_columns(class_subject):
    """Assessment columns for a subject, ordered as they appear on a printed
    broadsheet. Returns [(assessment_type, max_score), ...]."""
    from utils.assessments import subject_columns
    from utils.waec_ocr import SHEET_COLUMN_ORDER
    cols = subject_columns(class_subject.subject)  # [(at, max)] in storage order
    present = {at.short_name: (at, mx) for at, mx in cols}
    ordered = [present[sn] for sn in SHEET_COLUMN_ORDER if sn in present]
    # Append any columns not covered by the canonical order (defensive).
    seen = {at.id for at, _ in ordered}
    ordered += [(at, mx) for at, mx in cols if at.id not in seen]
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

    terms = Term.query.order_by(Term.id.desc()).all()
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
