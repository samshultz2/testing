"""
Access Control Utilities for PosyHub
Provides decorators and helper functions for role-based access control
"""
from functools import wraps
from utils.helpers import get_active_term
from flask import session, redirect, url_for, flash, request, abort
from models import db, User, ClassArmAssignment, StudentEnrollment


def get_current_user():
    """Get the current logged-in user object"""
    user_id = session.get('user_id')
    if user_id:
        return db.session.get(User, user_id)
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
    'main.dashboard', 'main.global_search', 'main.set_view_branch', 'main.set_theme',
    'main.dashboard_customize', 'auth.logout', 'auth.change_password',
}

# Default module set when a non-admin user has no explicit allowed_modules.
ROLE_DEFAULT_MODULES = {
    'teacher': {'students', 'attendance', 'results', 'external_exams', 'cbt',
                'timetable', 'events'},
    'readonly': {'students', 'results', 'external_exams', 'reports', 'events'},
    'staff': set(),
}


# Optional sub-sections within a module: {module: {sub_key: label}}. A user may
# be granted access to specific sub-sections instead of the whole module.
MODULE_SUBSECTIONS = {
    'finance': {
        'payments': 'Payments & Discounts',
        'structure': 'Fee Structure',
        'expenses': 'Expenses',
        'defaulters': 'Defaulters',
        'reports': 'Reports & Overview',
    },
    'hr': {
        'staff': 'Staff & Departments',
        'leave': 'Leave',
        'payroll': 'Payroll',
        'attendance': 'Staff Attendance',
        'settings': 'HR Settings',
    },
    'external_exams': {
        'waec': 'WAEC Results',
        'jamb': 'JAMB Results',
        'analytics': 'Analytics & Reports',
        'cutoffs': 'Cut-offs',
        'imports': 'Bulk Import',
    },
    'communication': {
        'announcements': 'Announcements',
        'templates': 'Message Templates',
        'messages': 'Messages & Compose',
        'settings': 'SMS Settings',
    },
}

# Which endpoints belong to each sub-section.
_SUBSECTION_ENDPOINTS = {
    'finance': {
        'payments': {'collections', 'collections_export', 'payments_list',
                     'record_payment', 'search_students', 'receipt', 'edit_payment',
                     'delete_payment', 'statement', 'add_discount', 'edit_discount',
                     'delete_discount'},
        'structure': {'items_list', 'add_item', 'edit_item', 'delete_item',
                      'structure', 'save_structure', 'copy_structure', 'clear_structure'},
        'expenses': {'expenses_list', 'add_expense', 'edit_expense', 'delete_expense',
                     'add_expense_category', 'delete_expense_category'},
        'defaulters': {'defaulters'},
        'reports': {'dashboard', 'reports', 'export_report'},
    },
    'hr': {
        'staff': {'dashboard', 'staff_list', 'add_staff', 'staff_detail', 'edit_staff',
                  'adjust_salary', 'delete_staff', 'export_staff', 'departments',
                  'add_department', 'edit_department', 'delete_department'},
        'leave': {'leave_list', 'add_leave', 'leave_status', 'delete_leave'},
        'payroll': {'payroll_list', 'create_payroll', 'payroll_detail', 'edit_payslip',
                    'finalize_payroll', 'mark_paid', 'delete_payroll', 'print_payslip',
                    'sync_deductions'},
        'attendance': {'attendance', 'save_attendance'},
        'settings': {'settings', 'save_hr_settings'},
    },
    'external_exams': {
        'waec': {'waec_list', 'add_waec', 'scan_waec', 'view_waec_student', 'edit_waec',
                 'delete_waec', 'delete_waec_single', 'export_waec', 'waec_analytics',
                 'waec_student_analysis', 'api_waec_grade_distribution',
                 'api_waec_subject_stats'},
        'jamb': {'jamb_list', 'add_jamb', 'scan_jamb', 'scan_batch', 'view_jamb_student',
                 'edit_jamb', 'delete_jamb', 'export_jamb', 'api_jamb_score_distribution',
                 'predictions_dashboard', 'student_predictions', 'api_student_predictions',
                 'api_predict_jamb', 'api_student_risk'},
        'analytics': {'analytics_hub', 'analytics_export', 'readiness', 'api_yoy_trends',
                      'api_waec_jamb_correlation', 'api_top_performers', 'subject_enrolment',
                      'subject_enrolment_detail', 'student_report'},
        'cutoffs': {'cutoffs_list', 'cutoffs_save', 'cutoffs_delete', 'cutoffs_reference'},
        'imports': {'import_results', 'import_template', 'import_results_run'},
    },
    'communication': {
        'announcements': {'announcements', 'add_announcement', 'edit_announcement',
                          'delete_announcement'},
        'templates': {'templates_list', 'add_template', 'edit_template', 'delete_template'},
        'messages': {'compose', 'compose_preview', 'students_search', 'cancel_schedule',
                     'process_scheduled', 'messages_list', 'message_detail', 'mark_sent',
                     'mark_all_sent', 'export_recipients', 'delete_message', 'send_gateway'},
        'settings': {'settings', 'save_settings', 'test_sms'},
    },
}

# The blueprint each sub-sectioned module's endpoints live under (blueprint name
# differs from the module key for these two).
_SUBSECTION_BLUEPRINT = {'external_exams': 'results', 'communication': 'comms'}

# Reverse map: 'finance.payments_list' -> ('finance', 'payments')
_ENDPOINT_SUBSECTION = {}
for _mod, _subs in _SUBSECTION_ENDPOINTS.items():
    _bp = _SUBSECTION_BLUEPRINT.get(_mod, _mod)
    for _sub, _eps in _subs.items():
        for _ep in _eps:
            _ENDPOINT_SUBSECTION[f'{_bp}.{_ep}'] = (_mod, _sub)


def subsection_for_endpoint(endpoint):
    """('module','sub') for a gated endpoint, or None."""
    return _ENDPOINT_SUBSECTION.get(endpoint or '')


def effective_perms():
    """Raw effective permission entries (may include 'module.sub' keys).

    Admins => 'edit' on everything (view-only admins => 'view'); else the user's
    stored map; else the role default.
    """
    if is_admin():
        lvl = 'view' if is_read_only() else 'edit'
        return {k: lvl for k in MODULES}
    user = get_current_user()
    if user:
        pm = user.permission_map
        if pm:
            scoped = {k: v for k, v in pm.items() if k.split('.', 1)[0] in MODULES}
            if scoped:
                if user.view_only:
                    scoped = {k: 'view' for k in scoped}
                return scoped
    role = session.get('role', 'teacher')
    default = ROLE_DEFAULT_MODULES.get(role, ROLE_DEFAULT_MODULES['teacher'])
    lvl = 'view' if role == 'readonly' else 'edit'
    return {k: lvl for k in default}


def module_level(key):
    """Broadest level the user has for a module (across module + sub keys)."""
    perms = effective_perms()
    best = None
    for k, v in perms.items():
        if k == key or k.startswith(key + '.'):
            if v == 'edit':
                return 'edit'
            best = 'view'
    return best


def subsection_level(module, sub):
    """Level for a specific sub-section: explicit > module grant > none."""
    perms = effective_perms()
    full = f'{module}.{sub}'
    if full in perms:
        return perms[full]
    if module in perms:
        return perms[module]
    return None   # granular user without this sub-section (or no access)


def user_module_levels():
    """{module_key: broadest level} for modules the user can access."""
    out = {}
    for m in MODULES:
        lvl = module_level(m)
        if lvl:
            out[m] = lvl
    return out


def user_modules():
    """Set of module keys the current user may access (admins => all)."""
    return set(user_module_levels().keys())


def can_access_module(key):
    return is_admin() or module_level(key) is not None


def can_write_module(key):
    """True if the current user may make changes in a module."""
    return module_level(key) == 'edit'


def page_can_write():
    """Whether the current page's module/sub-section is writable for this user.

    Used to hide create/update/delete controls on view-only pages (server-side
    enforcement still applies regardless).
    """
    ep = request.endpoint or ''
    if ep in _READONLY_WRITE_OK:
        return True
    if is_read_only():          # globally view-only account
        return False
    if is_admin():
        return True
    sub = subsection_for_endpoint(ep)
    if sub:
        return subsection_level(sub[0], sub[1]) == 'edit'
    module = BLUEPRINT_MODULE.get(ep.split('.')[0])
    if not module:
        return True             # ungated page — nothing to hide
    return module_level(module) == 'edit'


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
_READONLY_WRITE_OK = {'auth.login', 'auth.logout', 'auth.change_password',
                      'main.set_theme', 'main.dashboard_customize'}
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


def _deny_access(view_only=False):
    """Standard block response for the access gates."""
    if request.headers.get('X-Requested-With') == 'fetch' or request.is_json:
        abort(403)
    if view_only:
        flash('You have view-only access to that section.', 'error')
    else:
        flash('You do not have access to that section.', 'error')
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
    if subsection_for_endpoint(endpoint):
        return None   # handled by the finer sub-section gate
    module = BLUEPRINT_MODULE.get(endpoint.split('.')[0])
    if not module:
        return None
    if module_level(module) != 'edit':
        return _deny_access(view_only=True)
    return None


def enforce_idle_timeout():
    """Log a user out after a period of inactivity (Config.SESSION_IDLE_MINUTES)."""
    if not session.get('logged_in'):
        return None
    from config import Config
    mins = getattr(Config, 'SESSION_IDLE_MINUTES', 0)
    if not mins or request.endpoint == 'static':
        return None
    import time
    now = int(time.time())
    last = session.get('last_seen')
    session['last_seen'] = now
    if last and (now - last) > mins * 60:
        session.clear()
        if request.headers.get('X-Requested-With') == 'fetch' or request.is_json:
            abort(401)
        flash('Your session timed out due to inactivity. Please log in again.', 'warning')
        return redirect(url_for('auth.login'))
    return None


# Endpoints a user who must change their password may still reach.
_PW_CHANGE_ALLOWED = {'auth.change_password', 'auth.logout', 'static', 'main.set_theme'}


def enforce_password_change():
    """Force users flagged must_change_password onto the change-password page."""
    if not session.get('logged_in') or not session.get('must_change_password'):
        return None
    if (request.endpoint or '') in _PW_CHANGE_ALLOWED:
        return None
    if request.headers.get('X-Requested-With') == 'fetch' or request.is_json:
        abort(403)
    flash('Please set a new password to continue.', 'warning')
    return redirect(url_for('auth.change_password'))


def enforce_subsection_access():
    """before_request gate: per-sub-section access/write for granular users."""
    if not session.get('logged_in') or is_admin():
        return None
    res = subsection_for_endpoint(request.endpoint)
    if not res:
        return None
    module, sub = res
    lvl = subsection_level(module, sub)
    if lvl is None:
        return _deny_access()                              # no access to this part
    if request.method not in _SAFE_METHODS and lvl != 'edit':
        return _deny_access(view_only=True)                # view-only part
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
    active_term = get_active_term()
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

    asg = db.session.get(ClassArmAssignment, class_arm_assignment_id)
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
    if not user:
        return 'none'
    ms = user.manage_scope or 'none'
    # A branch-scoped user must never manage centrally, even if their stored
    # manage_scope says 'central' (stale data or misconfig). Otherwise they
    # could edit accounts in other branches. Clamp them to their own branch.
    if ms == 'central' and not user.is_central:
        ms = 'branch'
    return ms


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
