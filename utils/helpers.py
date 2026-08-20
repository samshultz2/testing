"""
Helper utility functions for the Student Management System
"""
from datetime import datetime, date, timedelta
from utils import timeutil
from functools import wraps
from flask import session, redirect, url_for, flash


def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'warning')
            from utils.nav import login_url
            return redirect(login_url())
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
    
    today = timeutil.today()
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

# Academic streams / tracks.
STREAMS = ['Science', 'Arts', 'Commercial']

# Compulsory WAEC subjects per stream (pre-selected on the WAEC entry page).
STREAM_WAEC_SUBJECTS = {
    'Science': [
        'Mathematics', 'English Language', 'Civic Education', 'Livestock Farming',
        'Physics', 'Chemistry', 'Biology',
    ],
    'Arts': [
        'Mathematics', 'English Language', 'Civic Education', 'Livestock Farming',
        'Literature in English', 'Christian Religious Studies', 'Government', 'Economics',
    ],
    'Commercial': [
        'Mathematics', 'English Language', 'Civic Education', 'Livestock Farming',
        'Commerce', 'Christian Religious Studies', 'Digital Technologies',
        'Government', 'Economics',
    ],
}


def infer_stream_from_jamb(student):
    """
    Infer a student's stream from the subjects they sat for JAMB:
    Physics -> Science, Literature in English -> Arts, Commerce -> Commercial.
    Returns None when none of the marker subjects are present.
    """
    from models import JAMBResult
    subjects = set()
    for r in JAMBResult.query.filter_by(student_id=student.id).all():
        for v in (r.subject1, r.subject2, r.subject3, r.subject4):
            if v:
                subjects.add(v)
    if 'Physics' in subjects:
        return 'Science'
    if 'Literature in English' in subjects:
        return 'Arts'
    if 'Commerce' in subjects:
        return 'Commercial'
    return None


def get_sss3_class():
    """The graduating class (SSS3) — the only class that sits WAEC, JAMB, Mock
    JAMB and Mock WAEC. Matched by the canonical name first, then tolerant of
    common spellings (SS3, 'SSS 3', 'Senior Secondary 3'), so a slightly
    different class name never silently widens these exams to the whole school.
    """
    import re
    from models import SchoolClass
    cls = SchoolClass.query.filter_by(name='SSS3').first()
    if cls:
        return cls
    for c in SchoolClass.query.all():
        norm = re.sub(r'[^a-z0-9]', '', (c.name or '').lower())
        if norm in ('sss3', 'ss3', 'seniorsecondary3', 'seniorsecondaryschool3'):
            return c
    return None


def _sss3_enrolled_map():
    """Return {id: Student} for active SSS3 students enrolled in the active term."""
    from models import (
        Student, ClassArmAssignment, StudentEnrollment
    )

    active_term = get_active_term()
    sss3 = get_sss3_class()

    students = {}
    if sss3 and active_term:
        from utils.branch_scope import scope_query
        assignments = scope_query(ClassArmAssignment.query.filter_by(
            class_id=sss3.id, term_id=active_term.id), ClassArmAssignment).all()
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
    from models import Student
    from utils.branch_scope import scope_query

    students = _sss3_enrolled_map()

    # Include this session's graduates (former SSS3) so results can still be added.
    active_session = get_active_session()
    if active_session:
        graduates = scope_query(Student.query.filter_by(
            is_active=True, is_graduated=True,
            graduation_session_id=active_session.id), Student).all()
        for g in graduates:
            students.setdefault(g.id, g)

    # An SSS3 arm teacher with only derived External-Exams access sees just their
    # own arm's students, never the whole SSS3 cohort.
    try:
        from utils.access_control import exam_student_scope
        scope = exam_student_scope()
    except Exception:
        scope = None
    if scope is not None:
        students = {sid: s for sid, s in students.items() if sid in scope}

    if students:
        return sorted(students.values(), key=lambda s: (s.surname or '', s.first_name or ''))

    # Nobody resolved. Only WAEC/JAMB/Mock students are SSS3, so once the school
    # is configured (an SSS3 class exists *and* a term is active) we must NOT
    # widen to the whole school — an empty list correctly says "no SSS3 enrolled
    # for this term yet". The all-students fallback is reserved for a brand-new
    # setup where SSS3 or the active term hasn't been created at all.
    if get_sss3_class() is not None and get_active_term() is not None:
        return []
    return scope_query(Student.query.filter_by(is_active=True), Student).order_by(Student.surname).all()


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
            'stream': s.stream,
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


def view_session_override():
    """The AcademicSession an *admin* has chosen to view instead of the live one
    (a personal, cookie-stored 'time-travel'), or None. Only honoured for admins,
    so it never changes anything for other users or the database itself."""
    from flask import session as flask_session, g, has_request_context
    if not has_request_context():
        return None
    if '_view_override' in g.__dict__:
        return g._view_override
    val = None
    sid = flask_session.get('view_session_id')
    if sid:
        try:
            from utils.access_control import is_admin
            if is_admin():
                from models import AcademicSession
                val = db_get_session(int(sid))
        except Exception:
            val = None
    g._view_override = val
    return val


def db_get_session(sid):
    from models import db, AcademicSession
    return db.session.get(AcademicSession, sid)


def get_active_term():
    """The currently active Term (or None). Single source of truth for the
    common active-term lookup. When an admin is viewing a past session, returns
    that session's latest term instead.

    Memoised for the lifetime of a request (the context processor and templates
    call this repeatedly per render): within one request the active term is
    constant. Outside a request context (scripts/tests) it always re-queries.
    """
    from flask import g, has_request_context
    if has_request_context():
        if '_active_term' in g.__dict__:
            return g._active_term
    from models import Term, AcademicSession
    ov = view_session_override()
    if ov is not None:
        val = (Term.query.filter_by(session_id=ov.id)
               .order_by(Term.term_number.desc()).first())
    else:
        sess = AcademicSession.query.filter_by(is_active=True).first()
        val = Term.query.filter_by(is_active=True).first()
        # Keep the active TERM consistent with the active SESSION. After a new
        # session is activated, the flagged-active term can still belong to the
        # OLD session (or none is flagged) — in that case fall back to the active
        # session's current term. This is what makes every term-scoped page
        # follow a session switch, not just the session-level ones.
        if sess is not None and (val is None or val.session_id != sess.id):
            # The flagged-active term belongs to a different (or no) session than
            # the active one — an inconsistent state that can arise after a botched
            # session switch. We follow the active session (below), but surface the
            # mismatch so it can be spotted rather than silently masked.
            if val is not None and val.session_id != sess.id:
                try:
                    from flask import current_app
                    current_app.logger.debug(
                        'active-term/session mismatch: term %s (session %s) but active '
                        'session is %s — using the active session\'s current term',
                        val.id, val.session_id, sess.id)
                except Exception:
                    pass
            val = _session_current_term(sess.id)
    if has_request_context():
        g._active_term = val
    return val


def _session_current_term(session_id):
    """The 'current' term of a session: the one whose date range covers today,
    else the latest by term number. None if the session has no terms."""
    from datetime import date
    from models import Term
    terms = Term.query.filter_by(session_id=session_id).all()
    if not terms:
        return None
    today = timeutil.today()
    for t in terms:
        if t.start_date and t.end_date and t.start_date <= today <= t.end_date:
            return t
    return max(terms, key=lambda t: (t.term_number or 0))


def get_active_session():
    """The currently active AcademicSession (or None) — or the past session an
    admin is viewing. Request-memoised; see :func:`get_active_term`."""
    from flask import g, has_request_context
    if has_request_context():
        if '_active_session' in g.__dict__:
            return g._active_session
    from models import AcademicSession
    ov = view_session_override()
    val = ov if ov is not None else AcademicSession.query.filter_by(is_active=True).first()
    if has_request_context():
        g._active_session = val
    return val


def session_terms(session=None):
    """Terms of the active (or admin-time-travelled) academic session, newest
    term first — the correct population for any term-picker dropdown.

    Switching the active session changes what every term dropdown offers, so a
    user can only pick terms that belong to the session they're viewing. Falls
    back to *all* terms only when there is genuinely no active session (a fresh
    or misconfigured install), so dropdowns never come up empty there."""
    from models import Term
    s = session if session is not None else get_active_session()
    if s is None:
        return Term.query.order_by(Term.id.desc()).all()
    return (Term.query.filter_by(session_id=s.id)
            .order_by(Term.term_number.desc()).all())


def session_exam_year(session=None):
    """The external-exam (calendar) year for an academic session — e.g. the
    session ``2025/2026`` sits its WAEC/JAMB in **2026** (the second year). Falls
    back to the session's end/start-date year. Returns None if it can't be told.

    Used to scope external-exam pages to the active (or time-travelled) session."""
    import re
    s = session if session is not None else get_active_session()
    if s is None:
        return None
    nums = re.findall(r'\d{4}', (s.name or ''))
    if len(nums) >= 2:
        return int(nums[1])
    if len(nums) == 1:
        return int(nums[0])
    if getattr(s, 'end_date', None):
        return s.end_date.year
    if getattr(s, 'start_date', None):
        return s.start_date.year
    return None


def resolve_exam_year(requested, years):
    """Pick the external-exam year to show, honouring the active/viewed session.

    * Time-travelling (admin viewing a past session): locked to that session's
      exam year, so external-exam pages show only that session.
    * Live session: an explicit ?year wins (deliberate exploration); otherwise
      lock to the live session's own exam year — *even when that year has no data
      yet*. Switching to a fresh session must show that session (empty), not
      silently fall back to the previous session's results.

    Only when the session's exam year can't be determined at all (an unnamed
    session, or none active) do we fall back to the most recent year with data.
    ``years`` is the list of years present in the data (newest first)."""
    ov = view_session_override()
    sy = session_exam_year(get_active_session())
    if ov is not None:
        return sy if sy is not None else (requested or (years[0] if years else None))
    if requested:
        return requested
    if sy is not None:
        return sy
    return years[0] if years else None


def exam_year_choices():
    """Session picker for external-exam entry: a list of ``(exam_year, label)``
    newest first, where the label is the academic-session name (e.g.
    ``(2026, "2025/2026")``). External exams are session-based — the stored
    ``exam_year`` is the session's second year — so the UI shows sessions while
    the value written stays the exam year, needing no data migration."""
    from models import AcademicSession
    seen, out = set(), []
    for s in AcademicSession.query.order_by(AcademicSession.name.desc()).all():
        ey = session_exam_year(s)
        if ey and ey not in seen:
            seen.add(ey)
            out.append((ey, s.name))
    # Make sure the active session's year is always offered, even with no data yet.
    ay = session_exam_year(get_active_session())
    if ay and ay not in seen:
        out.insert(0, (ay, (get_active_session().name if get_active_session() else str(ay))))
    return out


def safe_redirect(fallback):
    """Redirect to the page the user came from, but only if it is same-origin.

    ``redirect(request.referrer or fallback)`` is an open-redirect surface — the
    Referer is attacker-influenceable. This restricts it to our own host and
    falls back otherwise. Behaviour is unchanged for normal same-site use.
    """
    from flask import request, redirect
    ref = request.referrer
    if ref and ref.startswith(request.host_url):
        return redirect(ref)
    return redirect(fallback)


def pick_current_week(weeks, on=None):
    """The Week to pre-select: the one containing `on` (default today), else the
    most recently started week, else the first. `weeks` is an ordered list of
    Week objects. Returns None for an empty list."""
    if not weeks:
        return None
    on = on or timeutil.today()
    for w in weeks:
        if w.start_date and w.end_date and w.start_date <= on <= w.end_date:
            return w
    started = [w for w in weeks if w.start_date and w.start_date <= on]
    return started[-1] if started else weeks[0]
