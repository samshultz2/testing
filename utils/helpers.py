"""
Helper utility functions for the Student Management System
"""
from datetime import datetime, date, timedelta
from functools import wraps
from flask import session, redirect, url_for, flash


def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def format_date(date_obj, format_str='%d %b %Y'):
    """Format a date object to string"""
    if date_obj:
        return date_obj.strftime(format_str)
    return ''


def parse_date(date_str, format_str='%Y-%m-%d'):
    """Parse a date string to date object"""
    if date_str:
        try:
            return datetime.strptime(date_str, format_str).date()
        except ValueError:
            return None
    return None


def get_weekday_name(date_obj):
    """Get weekday name from date"""
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    return days[date_obj.weekday()]


def get_school_days_in_week(week_start, week_end, holidays):
    """
    Get list of school days in a week (excluding weekends and holidays)
    
    Args:
        week_start: Monday of the week
        week_end: Friday of the week
        holidays: List of holiday dates
        
    Returns:
        List of date objects that are school days
    """
    school_days = []
    current = week_start
    holiday_dates = set(h.date if hasattr(h, 'date') else h for h in holidays)
    
    while current <= week_end:
        # Only include weekdays (0-4 = Mon-Fri)
        if current.weekday() < 5 and current not in holiday_dates:
            school_days.append(current)
        current += timedelta(days=1)
    
    return school_days


def is_school_day(date_obj, holidays):
    """Check if a date is a school day"""
    # Check if weekend
    if date_obj.weekday() >= 5:
        return False
    
    # Check if holiday
    holiday_dates = set(h.date if hasattr(h, 'date') else h for h in holidays)
    if date_obj in holiday_dates:
        return False
    
    return True


def calculate_times_opened(school_days_count):
    """Calculate number of times school opened (days * 2 sessions)"""
    return school_days_count * 2


def calculate_percentage(value, total, decimal_places=2):
    """Calculate percentage with specified decimal places"""
    if total == 0:
        return 0.0
    return round((value / total) * 100, decimal_places)


def get_weeks_in_range(start_date, end_date):
    """
    Generate week ranges between two dates
    
    Returns:
        List of tuples (week_number, monday_date, friday_date)
    """
    weeks = []
    
    # Find first Monday
    current = start_date
    while current.weekday() != 0:  # 0 = Monday
        current += timedelta(days=1)
    
    week_num = 1
    while current <= end_date:
        friday = current + timedelta(days=4)
        if friday > end_date:
            friday = end_date
        weeks.append((week_num, current, friday))
        current += timedelta(days=7)
        week_num += 1
    
    return weeks


def validate_phone_number(phone):
    """Validate Nigerian phone number format"""
    if not phone:
        return False
    
    # Remove spaces and dashes
    phone = phone.replace(' ', '').replace('-', '')
    
    # Nigerian numbers: 11 digits starting with 0
    if len(phone) == 11 and phone.startswith('0') and phone.isdigit():
        return True
    
    # International format: +234 followed by 10 digits
    if phone.startswith('+234') and len(phone) == 14 and phone[1:].isdigit():
        return True
    
    return False


def format_phone_number(phone):
    """Format phone number for display"""
    if not phone:
        return ''
    
    phone = phone.replace(' ', '').replace('-', '')
    
    if len(phone) == 11 and phone.startswith('0'):
        return f"{phone[:4]} {phone[4:7]} {phone[7:]}"
    
    return phone


def get_age_from_dob(dob):
    """Calculate age from date of birth"""
    if not dob:
        return None
    
    today = date.today()
    age = today.year - dob.year
    
    if (today.month, today.day) < (dob.month, dob.day):
        age -= 1
    
    return age


def generate_student_id_from_sequence(sequence_number, prefix='STU'):
    """Generate student ID from sequence number"""
    return f"{prefix}{sequence_number:05d}"


def get_term_name(term_number):
    """Get term name from term number"""
    names = {1: 'First Term', 2: 'Second Term', 3: 'Third Term'}
    return names.get(term_number, f'Term {term_number}')


def get_academic_session_from_year(year):
    """Generate academic session name from year"""
    return f"{year}/{year + 1}"


class FlashMessages:
    """Standard flash message constants"""
    STUDENT_CREATED = "Student created successfully!"
    STUDENT_UPDATED = "Student updated successfully!"
    STUDENT_DELETED = "Student deleted successfully!"
    ATTENDANCE_SAVED = "Attendance saved successfully!"
    RESULT_SAVED = "Results saved successfully!"
    IMPORT_SUCCESS = "Data imported successfully!"
    EXPORT_SUCCESS = "Data exported successfully!"
    ERROR_OCCURRED = "An error occurred. Please try again."
    INVALID_DATA = "Invalid data provided."
    NOT_FOUND = "Record not found."


# WAEC Subject list
WAEC_SUBJECTS = [
    'English Language',
    'Mathematics',
    'Physics',
    'Chemistry',
    'Biology',
    'Economics',
    'Government',
    'Literature in English',
    'Agricultural Science',
    'Geography',
    'Commerce',
    'Accounting',
    'Further Mathematics',
    'Computer Studies',
    'Civic Education',
    'Christian Religious Studies',
    'Islamic Religious Studies',
    'French',
    'Yoruba',
    'Igbo',
    'Hausa',
    'History',
    'Visual Arts',
    'Music',
    'Technical Drawing',
    'Food and Nutrition',
    'Home Economics',
    'Physical Education',
    'Data Processing',
    'Digital Technologies',
    'Livestock Farming'
]

# WAEC Grades
WAEC_GRADES = ['A1', 'B2', 'B3', 'C4', 'C5', 'C6', 'D7', 'E8', 'F9']

# Subjects pre-selected by default on the WAEC entry page (most students take them).
WAEC_DEFAULT_SUBJECTS = [
    'Mathematics',
    'English Language',
    'Livestock Farming',
    'Civic Education',
]


def _sss3_enrolled_map():
    """Return {id: Student} for active SSS3 students enrolled in the active term."""
    from models import (
        Student, SchoolClass, ClassArmAssignment, StudentEnrollment, Term
    )

    active_term = Term.query.filter_by(is_active=True).first()
    sss3 = SchoolClass.query.filter_by(name='SSS3').first()

    students = {}
    if sss3 and active_term:
        assignments = ClassArmAssignment.query.filter_by(
            class_id=sss3.id, term_id=active_term.id
        ).all()
        for assignment in assignments:
            enrollments = StudentEnrollment.query.filter_by(
                class_arm_assignment_id=assignment.id,
                is_active=True
            ).join(Student).all()
            for enrollment in enrollments:
                if enrollment.student.is_active:
                    students[enrollment.student.id] = enrollment.student
    return students


def get_sss3_enrolled_students():
    """Active SSS3 students enrolled in the current active term, ordered by name."""
    students = _sss3_enrolled_map()
    return sorted(students.values(), key=lambda s: (s.surname or '', s.first_name or ''))


def get_sss3_students():
    """
    Students eligible for external-exam (WAEC/JAMB/Mock JAMB) result entry.

    This is the current SSS3 class (enrolled in the active term) PLUS students
    who graduated in the active session, so their WAEC/JAMB results can still be
    entered after they have graduated. Falls back to all active students only if
    the SSS3 class / active term has not been set up yet, so result entry never
    becomes impossible.
    """
    from models import Student, AcademicSession

    students = _sss3_enrolled_map()

    # Include this session's graduates (former SSS3) so results can still be added.
    active_session = AcademicSession.query.filter_by(is_active=True).first()
    if active_session:
        graduates = Student.query.filter_by(
            is_active=True, is_graduated=True,
            graduation_session_id=active_session.id
        ).all()
        for g in graduates:
            students.setdefault(g.id, g)

    if students:
        return sorted(students.values(), key=lambda s: (s.surname or '', s.first_name or ''))

    # Fallback: SSS3/active term not configured yet.
    return Student.query.filter_by(is_active=True).order_by(Student.surname).all()


def student_subject_map(students):
    """
    Build {student_id: {'waec': [...], 'jamb': [...]}} for the given students so
    result-entry pages can auto-populate the subject fields from each student's
    saved exam enrolment.
    """
    return {
        s.id: {
            'waec': s.waec_subject_list,
            'jamb': s.jamb_subject_list,
        }
        for s in students
    }

# Religions
RELIGIONS = [
    'Christianity',
    'Islam',
    'Traditional',
    'Others'
]
