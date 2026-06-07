"""
Access Control Utilities for PosyHub
Provides decorators and helper functions for role-based access control
"""
from functools import wraps
from flask import session, redirect, url_for, flash, request, abort
from models import db, User, Teacher, TeacherClassAssignment, TeacherSubjectAssignment, ClassArmAssignment, Term


def get_current_user():
    """Get the current logged-in user object"""
    user_id = session.get('user_id')
    if user_id:
        return User.query.get(user_id)
    return None


# =============================================================================
# FINE-GRAINED MODULE PERMISSIONS
# =============================================================================

# All grantable modules: key -> human label (order = display order).
MODULES = {
    'students': 'Students',
    'admissions': 'Admissions',
    'academics': 'Academics (sessions/classes)',
    'events': 'Calendar & Events',
    'attendance': 'Attendance',
    'results': 'Subjects & Scores',
    'external_exams': 'WAEC / JAMB / Analytics',
    'cbt': 'CBT / Online Tests',
    'timetable': 'Timetable',
    'promotion': 'Promotion',
    'finance': 'Finance & Fees',
    'communication': 'Parent Communication',
    'hr': 'Staff / HR',
    'library': 'Library',
    'reports': 'Reports',
}

# Which module a blueprint belongs to (blueprints not listed are never gated).
BLUEPRINT_MODULE = {
    'main': 'students', 'admissions': 'admissions', 'academics': 'academics',
    'events': 'events', 'attendance': 'attendance', 'subjects': 'results',
    'results': 'external_exams', 'mock_jamb': 'external_exams', 'cbt': 'cbt',
    'timetable': 'timetable', 'generator': 'timetable', 'promotion': 'promotion',
    'finance': 'finance', 'comms': 'communication', 'hr': 'hr',
    'library': 'library', 'reports': 'reports', 'scratchcards': 'results',
}

# Endpoints always reachable by any logged-in user (the shell + own account).
_ALWAYS_ALLOWED_ENDPOINTS = {
    'main.dashboard', 'main.global_search', 'auth.logout', 'auth.change_password',
}

# Default module set when a non-admin user has no explicit allowed_modules.
ROLE_DEFAULT_MODULES = {
    'teacher': {'students', 'attendance', 'results', 'external_exams', 'cbt',
                'timetable', 'events'},
    'readonly': {'students', 'results', 'external_exams', 'reports', 'events'},
    'staff': set(),
}


def user_modules():
    """Set of module keys the current user may access (admins => all)."""
    if is_admin():
        return set(MODULES.keys())
    user = get_current_user()
    if user and user.module_list:
        return set(user.module_list) & set(MODULES.keys())
    role = session.get('role', 'teacher')
    return set(ROLE_DEFAULT_MODULES.get(role, ROLE_DEFAULT_MODULES['teacher']))


def can_access_module(key):
    return is_admin() or key in user_modules()


def enforce_module_access():
    """before_request gate: block non-admins from modules they lack."""
    if not session.get('logged_in') or is_admin():
        return None
    endpoint = request.endpoint
    if not endpoint or endpoint in _ALWAYS_ALLOWED_ENDPOINTS:
        return None
    blueprint = endpoint.split('.')[0]
    module = BLUEPRINT_MODULE.get(blueprint)
    if module and module not in user_modules():
        if request.headers.get('X-Requested-With') == 'fetch' or request.is_json:
            abort(403)
        flash('You do not have access to that section.', 'error')
        return redirect(url_for('main.dashboard'))
    return None


# Unsafe methods a read-only user may still call (managing their own account).
_READONLY_WRITE_OK = {'auth.login', 'auth.logout', 'auth.change_password'}
_SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}


def is_read_only():
    """True if the current user may browse but not change anything."""
    if is_admin():
        return False
    if session.get('role') == 'readonly':
        return True
    user = get_current_user()
    return bool(user and getattr(user, 'view_only', False))


def enforce_read_only():
    """before_request gate: block create/edit/delete for view-only users."""
    if not session.get('logged_in') or request.method in _SAFE_METHODS:
        return None
    if not is_read_only():
        return None
    if (request.endpoint or '') in _READONLY_WRITE_OK:
        return None
    if request.headers.get('X-Requested-With') == 'fetch' or request.is_json:
        abort(403)
    flash('Your account is view-only — you cannot make changes.', 'error')
    return redirect(request.referrer or url_for('main.dashboard'))


def module_required(key):
    """Decorator form for a single route."""
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not session.get('logged_in'):
                return redirect(url_for('auth.login'))
            if not can_access_module(key):
                flash('You do not have access to that section.', 'error')
                return redirect(url_for('main.dashboard'))
            return f(*args, **kwargs)
        return wrapper
    return deco


def is_admin():
    """Check if current user is admin"""
    role = session.get('role')
    return role in ('super_admin', 'admin')


def is_teacher():
    """Check if current user is teacher"""
    role = session.get('role')
    return role == 'teacher'


def get_teacher_profile():
    """Get teacher profile for current user"""
    user = get_current_user()
    if user and user.is_teacher:
        return user.teacher_profile
    return None


def get_accessible_class_ids():
    """
    Get list of class_arm_assignment_ids the current user can access.
    Admins can access all classes, teachers only their assigned classes.
    """
    if is_admin():
        # Admins can access all classes in active term
        active_term = Term.query.filter_by(is_active=True).first()
        if active_term:
            return [a.id for a in ClassArmAssignment.query.filter_by(term_id=active_term.id).all()]
        return []
    
    teacher = get_teacher_profile()
    if teacher:
        accessible = set()
        
        # Form teacher classes
        for assignment in teacher.class_assignments.filter_by(is_active=True).all():
            accessible.add(assignment.class_arm_assignment_id)
        
        # Subject teaching classes
        for assignment in teacher.subject_assignments.filter_by(is_active=True).all():
            accessible.add(assignment.class_arm_assignment_id)
        
        return list(accessible)
    
    return []


def can_access_class(class_arm_assignment_id):
    """Check if current user can access a specific class"""
    if is_admin():
        return True
    
    if class_arm_assignment_id is None:
        return True  # No class selected yet
    
    teacher = get_teacher_profile()
    if teacher:
        return teacher.can_access_class(class_arm_assignment_id)
    
    return False


def can_mark_attendance(class_arm_assignment_id=None):
    """Check if current user can mark attendance for a class"""
    if is_admin():
        return True
    
    teacher = get_teacher_profile()
    if teacher and teacher.can_mark_attendance:
        if class_arm_assignment_id is None:
            return True
        return teacher.can_access_class(class_arm_assignment_id)
    
    return False


def can_enter_results(class_arm_assignment_id=None, subject_id=None):
    """Check if current user can enter results"""
    if is_admin():
        return True
    
    teacher = get_teacher_profile()
    if teacher and teacher.can_enter_results:
        if class_arm_assignment_id is None:
            return True
        if subject_id:
            # Check specific subject assignment
            return teacher.subject_assignments.filter_by(
                class_arm_assignment_id=class_arm_assignment_id,
                subject_id=subject_id,
                is_active=True
            ).first() is not None
        return teacher.can_access_class(class_arm_assignment_id)
    
    return False


def can_view_student_details():
    """Check if current user can view student details"""
    if is_admin():
        return True
    
    teacher = get_teacher_profile()
    if teacher:
        return teacher.can_view_student_details
    
    return False


def filter_classes_for_user(assignments):
    """
    Filter a list of ClassArmAssignment objects to only those accessible by current user.
    Returns all if admin, filtered list if teacher.
    """
    if is_admin():
        return assignments
    
    accessible_ids = get_accessible_class_ids()
    return [a for a in assignments if a.id in accessible_ids]


def filter_class_ids_for_user(class_ids):
    """
    Filter a list of class_arm_assignment_ids to only those accessible by current user.
    """
    if is_admin():
        return class_ids
    
    accessible_ids = set(get_accessible_class_ids())
    return [cid for cid in class_ids if cid in accessible_ids]


# =============================================================================
# DECORATORS
# =============================================================================

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator to require admin access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        
        if not is_admin():
            flash('Admin access required.', 'error')
            return redirect(url_for('main.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function


def class_access_required(f):
    """
    Decorator to check class access.
    Looks for 'assignment_id' or 'class_id' in request args or view args.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        
        # Get class ID from various sources
        class_id = (
            kwargs.get('assignment_id') or
            kwargs.get('class_id') or
            request.args.get('assignment_id', type=int) or
            request.args.get('class_id', type=int) or
            request.form.get('assignment_id', type=int) or
            request.form.get('class_id', type=int)
        )
        
        if class_id and not can_access_class(class_id):
            flash('You do not have access to this class.', 'error')
            return redirect(url_for('main.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function


def attendance_access_required(f):
    """Decorator to check attendance marking permission"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        
        class_id = (
            kwargs.get('assignment_id') or
            request.args.get('assignment_id', type=int) or
            request.form.get('assignment_id', type=int)
        )
        
        if not can_mark_attendance(class_id):
            flash('You do not have permission to mark attendance.', 'error')
            return redirect(url_for('main.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function


def results_access_required(f):
    """Decorator to check results entry permission"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        
        class_id = (
            kwargs.get('assignment_id') or
            request.args.get('assignment_id', type=int) or
            request.form.get('assignment_id', type=int)
        )
        
        subject_id = (
            kwargs.get('subject_id') or
            request.args.get('subject_id', type=int) or
            request.form.get('subject_id', type=int)
        )
        
        if not can_enter_results(class_id, subject_id):
            flash('You do not have permission to enter results for this class/subject.', 'error')
            return redirect(url_for('main.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function


# =============================================================================
# CONTEXT PROCESSOR HELPERS
# =============================================================================

def get_user_context():
    """
    Get user context for templates.
    Returns dict with user info and permissions.
    """
    user = get_current_user()
    teacher = get_teacher_profile()
    
    return {
        'current_user': user,
        'is_admin': is_admin(),
        'is_teacher': is_teacher(),
        'teacher_profile': teacher,
        'accessible_class_ids': get_accessible_class_ids(),
        'can_mark_attendance': can_mark_attendance(),
        'can_enter_results': can_enter_results(),
        'can_view_student_details': can_view_student_details(),
    }
