"""
Access Control Utilities for PosyHub
Provides decorators and helper functions for role-based access control
"""
from functools import wraps
from flask import session, redirect, url_for, flash, request, abort
from models import User, ClassArmAssignment, Term, StudentEnrollment


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
    'sales': 'Sales & Inventory',
}

# Which module a blueprint belongs to (blueprints not listed are never gated).
BLUEPRINT_MODULE = {
    'main': 'students', 'admissions': 'admissions', 'academics': 'academics',
    'events': 'events', 'attendance': 'attendance', 'subjects': 'results',
    'results': 'external_exams', 'mock_jamb': 'external_exams', 'cbt': 'cbt',
    'timetable': 'timetable', 'generator': 'timetable', 'promotion': 'promotion',
    'finance': 'finance', 'comms': 'communication', 'hr': 'hr',
    'library': 'library', 'reports': 'reports', 'scratchcards': 'results',
    'sales': 'sales',
}

# Endpoints always reachable by any logged-in user (the shell + own account).
_ALWAYS_ALLOWED_ENDPOINTS = {
    'main.dashboard', 'main.global_search', 'main.set_view_branch',
    'auth.logout', 'auth.change_password',
}

# Default module set when a non-admin user has no explicit allowed_modules.
ROLE_DEFAULT_MODULES = {
    'teacher': {'students', 'attendance', 'results', 'external_exams', 'cbt',
                'timetable', 'events'},
    'readonly': {'students', 'results', 'external_exams', 'reports', 'events'},
    'staff': set(),
}


def user_module_levels():
    """Effective {module_key: 'view'|'edit'} for the current user.

    Admins get 'edit' on everything (a globally view-only admin gets 'view').
    Otherwise the user's explicit per-module levels, falling back to the role's
    default set (granted at 'view' for the readonly role, else 'edit').
    """
    if is_admin():
        lvl = 'view' if is_read_only() else 'edit'
        return {k: lvl for k in MODULES}
    user = get_current_user()
    if user:
        pm = user.permission_map
        if pm:
            scoped = {k: v for k, v in pm.items() if k in MODULES}
            if scoped:
                if user.view_only:   # global override -> everything view
                    scoped = {k: 'view' for k in scoped}
                return scoped
    role = session.get('role', 'teacher')
    default = ROLE_DEFAULT_MODULES.get(role, ROLE_DEFAULT_MODULES['teacher'])
    lvl = 'view' if role == 'readonly' else 'edit'
    return {k: lvl for k in default}


def user_modules():
    """Set of module keys the current user may access (admins => all)."""
    return set(user_module_levels().keys())


def can_access_module(key):
    return is_admin() or key in user_module_levels()


def module_level(key):
    """The current user's level for a module: 'edit' / 'view' / None."""
    return user_module_levels().get(key)


def can_write_module(key):
    """True if the current user may make changes in a module."""
    return module_level(key) == 'edit'


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


def enforce_write_level():
    """before_request gate: block writes to a module the user can only view."""
    if not session.get('logged_in') or request.method in _SAFE_METHODS:
        return None
    if is_admin():
        return None   # admins may write (global view-only handled by enforce_read_only)
    endpoint = request.endpoint or ''
    if endpoint in _ALWAYS_ALLOWED_ENDPOINTS or endpoint in _READONLY_WRITE_OK:
        return None
    module = BLUEPRINT_MODULE.get(endpoint.split('.')[0])
    if not module:
        return None
    if module_level(module) != 'edit':
        if request.headers.get('X-Requested-With') == 'fetch' or request.is_json:
            abort(403)
        flash('You have view-only access to that section.', 'error')
        return redirect(request.referrer or url_for('main.dashboard'))
    return None


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

    Teachers: only their assigned classes. Admins / non-teacher staff: every
    class in the branch(es) currently in view (so a branch admin is limited to
    their own branch, a central user sees all).
    """
    active_term = Term.query.filter_by(is_active=True).first()
    if not active_term:
        return []

    teacher = get_teacher_profile()
    if teacher and not is_admin():
        accessible = set()
        # Form teacher classes
        for assignment in teacher.class_assignments.filter_by(is_active=True).all():
            accessible.add(assignment.class_arm_assignment_id)
        # Subject teaching classes
        for assignment in teacher.subject_assignments.filter_by(is_active=True).all():
            accessible.add(assignment.class_arm_assignment_id)
        return list(accessible)

    # Admin / non-teacher staff: all classes in the branch(es) in view.
    from utils.branch_scope import scope_query
    q = scope_query(ClassArmAssignment.query.filter_by(term_id=active_term.id),
                    ClassArmAssignment)
    return [a.id for a in q.all()]


def can_access_class(class_arm_assignment_id):
    """Check if current user can access a specific class (branch/section aware)."""
    if class_arm_assignment_id is None:
        return True  # No class selected yet

    asg = ClassArmAssignment.query.get(class_arm_assignment_id)
    if not asg:
        return False
    from utils.branch_scope import can_access_branch
    from utils.org_scope import allowed_sections
    # Branch gate applies to everyone except central users (can_access_branch
    # returns True for them) — so even a branch *admin* is held to their branch.
    if not can_access_branch(asg.branch_id):
        return False
    sections = allowed_sections()
    if sections and (not asg.school_class or asg.school_class.section not in sections):
        return False
    # Teachers are further limited to their own classes; admins/staff are not.
    teacher = get_teacher_profile()
    if teacher and not is_admin():
        return teacher.can_access_class(class_arm_assignment_id)
    return True


def can_mark_attendance(class_arm_assignment_id=None):
    """Check if current user can mark attendance for a class.

    Teachers may mark attendance only for the class they are *form teacher* of
    (not the subject classes they merely teach in).
    """
    # Branch/section gate first (applies to admins too).
    if class_arm_assignment_id is not None and not can_access_class(class_arm_assignment_id):
        return False
    if is_admin():
        return True

    teacher = get_teacher_profile()
    if teacher and teacher.can_mark_attendance:
        if class_arm_assignment_id is None:
            return True
        return teacher.is_form_teacher_of(class_arm_assignment_id)

    return False


def can_enter_results(class_arm_assignment_id=None, subject_id=None):
    """Check if current user can enter results"""
    # Branch/section gate first (applies to admins too).
    if class_arm_assignment_id is not None and not can_access_class(class_arm_assignment_id):
        return False
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


def teacher_form_student_ids():
    """Set of student ids in the current teacher's form classes (active term).

    Returns None when the current user is not a teacher (no extra restriction).
    """
    if not is_teacher():
        return None
    teacher = get_teacher_profile()
    if not teacher:
        return set()
    form_ids = teacher.form_class_ids
    if not form_ids:
        return set()
    rows = StudentEnrollment.query.filter(
        StudentEnrollment.class_arm_assignment_id.in_(form_ids),
        StudentEnrollment.is_active == True).all()
    return {e.student_id for e in rows}


def can_view_student_details():
    """Check if current user can view student details"""
    if is_admin():
        return True
    
    teacher = get_teacher_profile()
    if teacher:
        return teacher.can_view_student_details
    
    return False


def filter_classes_for_user(assignments, form_only=False):
    """Filter ClassArmAssignment objects to those the current user may access.

    Composes branch scope (branch users / a central user viewing one branch),
    section scope (Principal vs Headmaster) and, for actual teachers, their
    assigned classes. Admins / central users viewing all branches see everything.

    ``form_only`` limits a teacher to the class they are *form teacher* of (used
    by attendance and parent communication, where subject-teaching is not enough).
    """
    from utils.branch_scope import viewing_branch_id
    from utils.org_scope import allowed_sections
    result = list(assignments)
    bid = viewing_branch_id()
    if bid is not None:
        result = [a for a in result if getattr(a, 'branch_id', None) == bid]
    sections = allowed_sections()
    if sections:
        result = [a for a in result
                  if a.school_class and a.school_class.section in sections]
    if is_teacher():
        teacher = get_teacher_profile()
        if form_only:
            allowed = teacher.form_class_ids if teacher else set()
        else:
            allowed = set(get_accessible_class_ids())
        result = [a for a in result if a.id in allowed]
    return result


def filter_class_ids_for_user(class_ids):
    """
    Filter a list of class_arm_assignment_ids to only those accessible by current user.
    """
    if is_admin():
        return class_ids

    accessible_ids = set(get_accessible_class_ids())
    return [cid for cid in class_ids if cid in accessible_ids]


# =============================================================================
# DELEGATED USER MANAGEMENT (rank + branch hierarchy)
# =============================================================================

def current_manage_scope():
    """'central' / 'branch' / 'none' — how widely the current user may manage."""
    from utils.branch_scope import is_central
    if is_admin() and is_central():
        return 'central'
    user = get_current_user()
    return (user.manage_scope or 'none') if user else 'none'


def current_rank():
    """Authority level of the current user (legacy/central admin = top)."""
    user = get_current_user()
    if user:
        return user.rank or 0
    return 9999   # legacy password admin


def can_manage_users():
    """True if the user may manage at least some other accounts."""
    return current_manage_scope() in ('branch', 'central')


def can_manage(target_user):
    """May the current user edit ``target_user``'s account/permissions?

    Never themselves. Central managers manage everyone; branch managers manage
    strictly-lower-ranked users in their own branch.
    """
    if target_user is None:
        return False
    me = get_current_user()
    if me and target_user.id == me.id:
        return False                       # never manage yourself
    scope = current_manage_scope()
    if scope == 'central':
        return True
    if scope == 'branch':
        if me is None or target_user.branch_id != me.branch_id:
            return False
        return current_rank() > (target_user.rank or 0)
    return False


def manage_users_required(f):
    """Allow any user who can manage accounts (central admin, principal, HOD…)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if not can_manage_users():
            flash('You are not allowed to manage user accounts.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


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


def central_admin_required(f):
    """Require a CENTRAL admin (manages users, branches, system settings).

    A branch-scoped admin is full-featured within their branch but must not be
    able to manage accounts/permissions or cross-branch configuration.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        from utils.branch_scope import is_central
        if not (is_admin() and is_central()):
            flash('That area is for central administrators only.', 'error')
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
