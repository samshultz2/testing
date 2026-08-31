"""
Utilities package initialization
"""
from .helpers import (
    login_required, format_date, parse_date, get_weekday_name,
    get_school_days_in_week, is_school_day, calculate_times_opened,
    calculate_percentage, get_weeks_in_range, validate_phone_number,
    format_phone_number, get_age_from_dob, get_term_name,
    FlashMessages, WAEC_SUBJECTS, WAEC_GRADES, RELIGIONS
)

from .calculations import (
    get_daily_attendance_summary, get_weekly_attendance_summary,
    get_termly_attendance_summary, mark_attendance_bulk,
    mark_all_present, get_attendance_statistics
)

from .excel_utils import (
    export_students_to_excel, create_student_import_template,
    import_students_from_excel, export_attendance_to_excel,
    export_waec_results_to_excel
)

__all__ = [
    'login_required', 'format_date', 'parse_date', 'get_weekday_name',
    'get_school_days_in_week', 'is_school_day', 'calculate_times_opened',
    'calculate_percentage', 'get_weeks_in_range', 'validate_phone_number',
    'format_phone_number', 'get_age_from_dob', 'get_term_name',
    'FlashMessages', 'WAEC_SUBJECTS', 'WAEC_GRADES', 'RELIGIONS',
    'get_daily_attendance_summary', 'get_weekly_attendance_summary',
    'get_termly_attendance_summary', 'mark_attendance_bulk',
    'mark_all_present', 'get_attendance_statistics',
    'export_students_to_excel', 'create_student_import_template',
    'import_students_from_excel', 'export_attendance_to_excel',
    'export_waec_results_to_excel'
]
from utils.security import login_required, csrf_protect, sanitize_string, strip_tags
