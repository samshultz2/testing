"""
Attendance management routes
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response, abort
from sqlalchemy import case, func
from utils.helpers import get_active_term
from utils.web_exports import xlsx_response
from datetime import datetime, date, timedelta
from models import (
    db, Student, StudentEnrollment, ClassArmAssignment, 
    Week, Holiday, Attendance, Term, AcademicSession
)
from utils.access_control import (
    login_required, can_access_class, can_mark_attendance, can_view_attendance,
    filter_classes_for_user, can_access_module, auto_select_assignment
)
from utils.branch_scope import require_branch_access
from utils.security import rate_limited
from utils.helpers import is_school_day, pick_current_week
from utils.calculations import (
    get_daily_attendance_summary, get_weekly_attendance_summary,
    get_termly_attendance_summary, mark_attendance_bulk, mark_all_present
)
from utils.excel_utils import export_attendance_to_excel

attendance_bp = Blueprint('attendance', __name__, url_prefix='/attendance')


def _actor_name(default='Admin'):
    """Display name of whoever is marking attendance, for the audit trail and
    the 'register marked' notification."""
    try:
        from utils.access_control import get_current_user
        u = get_current_user()
        if u:
            return (getattr(u, 'full_name', None) or getattr(u, 'username', None) or default)
    except Exception:
        pass
    return default








def roster_order():
    """ORDER BY clauses for an attendance roster.

    Many schools don't list the register as one flat alphabetical run — they
    split it by gender, boys first then girls, each group alphabetical by
    surname (then first name). This returns the SQL expressions for exactly
    that, so every attendance roster orders the same way. Requires the query to
    ``.join(Student)``.

    Gender is matched case-insensitively on its first letter, so ``Male``/``M``
    and ``Female``/``F`` all rank together; anything unrecognised (or blank)
    sorts last, so no student is ever dropped from the register.
    """
    g = func.lower(func.substr(func.coalesce(Student.gender, ''), 1, 1))
    gender_rank = case((g == 'm', 0), (g == 'f', 1), else_=2)
    return (gender_rank, Student.surname, Student.first_name)


def _week_school_days(week, holidays):
    """The school weekdays (Mon–Fri, minus holidays) within a week."""
    holiday_dates = {h.date for h in holidays}
    days, d = [], week.start_date
    while d <= week.end_date:
        if d.weekday() < 5 and d not in holiday_dates:
            days.append(d)
        d += timedelta(days=1)
    return days




















# ============================================================================
# API ENDPOINTS
# ============================================================================







# ============================================================================
# JSON API for the React offline pilot (roster read + idempotent mark write)
# ============================================================================

def _week_for_date(term_id, target_date):
    """The Week (within term_id) that contains target_date, or None."""
    return Week.query.filter(
        Week.term_id == term_id,
        Week.start_date <= target_date,
        Week.end_date >= target_date,
    ).first()


def _validate_attendance_date(target_date, term_id):
    """Reject dates a register can't legitimately be taken for: in the future,
    outside the term window, or on a non-school day (weekend / holiday). Returns
    an error string, or None when the date is acceptable. Stops silent back- or
    future-dating of attendance — the save endpoint previously trusted any date.
    """
    if target_date > date.today():
        return 'You cannot mark attendance for a future date.'
    term = db.session.get(Term, term_id) if term_id else None
    if term and term.start_date and target_date < term.start_date:
        return 'That date is before the start of the selected term.'
    if term and term.end_date and target_date > term.end_date:
        return 'That date is after the end of the selected term.'
    holidays = Holiday.query.filter_by(term_id=term_id).all() if term_id else []
    if not is_school_day(target_date, holidays):
        return 'That date is a weekend or holiday — not a school day.'
    return None


















# ============================================================================
# JSON API: read-only attendance reports for the React SPA (installment 2)
# ----------------------------------------------------------------------------
# All endpoints are branch-scoped and permission-checked, mirroring the
# server-rendered report pages. They require the network (no offline write).
# ============================================================================

def _jsonable(value):
    """Recursively convert date/datetime values to ISO strings so a summary
    dict (which mixes in date objects) can be returned by jsonify untouched."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _scoped_caa(assignment_id):
    """Resolve an assignment the current user may VIEW, or return a JSON error
    tuple. Reports are read-only, so view access (branch + class) is required —
    marking permission is not (that gates the write endpoints only)."""
    if not assignment_id:
        return None, (jsonify({'error': 'assignment_id required'}), 400)
    caa = db.session.get(ClassArmAssignment, assignment_id)
    if not caa:
        return None, (jsonify({'error': 'invalid assignment'}), 400)
    require_branch_access(caa.branch_id)
    if not can_view_attendance(caa.id):   # teachers: their form class only
        return None, (jsonify({'error': 'forbidden'}), 403)
    return caa, None












# ============================================================================
# ATTENDANCE ALERTS
# ============================================================================





# ============================================================================
# PRINT-READY ATTENDANCE REGISTER
# ============================================================================

__all__ = [_n for _n in dir() if not _n.startswith('__')]

from . import marking, reports, api  # noqa: E402,F401  (registers routes)
