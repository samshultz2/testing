"""
User Management Routes
Handles user CRUD, role management, and teacher assignments
"""
from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   session, jsonify)
from utils.helpers import get_active_term
from models import db, ClassArmAssignment, Subject, User, Teacher, TeacherClassAssignment, TeacherSubjectAssignment
from utils.access_control import (MODULES, manage_users_required, can_manage,
                                  current_manage_scope, current_rank, get_current_user,
                                  restrict_grant_perms, CAPABILITY_SUBSECTIONS)
from utils.audit import log_action
from utils.db_tx import safe_transaction
from utils.security import is_password_strong

users_bp = Blueprint('users', __name__, url_prefix='/users')

# Backwards-compatible alias: every users route requires manage capability;
# per-target authority is checked with can_manage().
admin_required = manage_users_required


# --- SPA helpers (no-reload React shell + JSON-aware action responses) -------
from utils.spa import section_responders
_wants_json, _render, _ok, _err = section_responders(
    'users/app.html', 'users_json', 'users.index')


def _guard(target):
    """JSON-aware: 403/redirect if the current user may not manage ``target``."""
    if not can_manage(target):
        return _err('You are not allowed to manage that account.',
                    url_for('users.index'), status=403)
    return None


def _role_badge(u):
    if u.is_super_admin:
        return 'danger'
    if u.is_admin:
        return 'warning'
    if u.is_teacher:
        return 'info'
    return 'secondary'


def _form_meta():
    """Shared metadata for the add/edit user forms (modules, presets, etc.)."""
    from models import Branch
    from utils.role_presets import presets_for_form
    from utils.access_control import (MODULE_SUBSECTIONS, ROLE_DEFAULT_MODULES,
                                      CAPABILITY_SUBSECTIONS as CAPS)
    return {
        'modules': [{'key': k, 'label': v} for k, v in MODULES.items()],
        'subsections': {k: [{'sub': s, 'label': l} for s, l in subs.items()]
                        for k, subs in MODULE_SUBSECTIONS.items()},
        'capabilities': sorted(CAPS),
        'cap_modules': sorted({c.split('.')[0] for c in CAPS}),
        'role_defaults': {r: sorted(m) for r, m in ROLE_DEFAULT_MODULES.items()},
        'branches': [{'id': b.id, 'name': b.name, 'is_default': b.is_default}
                     for b in Branch.query.order_by(Branch.name).all()],
        'presets': presets_for_form(),
    }


def _teacher_perms(t):
    if not t:
        return None
    return {'can_mark_attendance': bool(t.can_mark_attendance),
            'can_view_student_details': bool(t.can_view_student_details),
            'can_print_reports': bool(t.can_print_reports),
            'can_enter_results': bool(t.can_enter_results),
            'can_edit_results': bool(t.can_edit_results)}


def _user_core(u):
    return {'id': u.id, 'username': u.username, 'full_name': u.full_name or '',
            'email': u.email or '', 'phone': u.phone or '',
            'role': u.role, 'display_role': u.get_display_role(),
            'role_badge': _role_badge(u), 'is_active': bool(u.is_active),
            'is_admin': bool(u.is_admin), 'is_super_admin': bool(u.is_super_admin),
            'is_teacher': bool(u.is_teacher)}


def _user_view(u):
    d = _user_core(u)
    d['last_login'] = u.last_login.strftime('%d %b %Y %H:%M') if u.last_login else 'Never'
    d['created'] = u.created_at.strftime('%d %b %Y') if u.created_at else ''
    t = u.teacher_profile if u.is_teacher else None
    d['teacher'] = _teacher_perms(t)
    granted = u.permission_map
    d['module_access'] = (None if u.is_admin else
                          [{'key': k, 'label': v, 'level': granted.get(k)}
                           for k, v in MODULES.items()])
    d['has_custom_modules'] = bool(granted)
    if t:
        d['class_assignments'] = [
            {'id': a.id, 'name': a.class_arm_assignment.display_name,
             'is_form_teacher': bool(a.is_form_teacher),
             'remove_url': url_for('users.remove_assignment', assignment_id=a.id)}
            for a in t.class_assignments.filter_by(is_active=True).all()]
        d['subject_assignments'] = [
            {'id': a.id, 'subject': a.subject.name,
             'class': a.class_arm_assignment.display_name,
             'remove_url': url_for('users.remove_assignment', assignment_id=a.id)}
            for a in t.subject_assignments.filter_by(is_active=True).all()]
        d['assign_class_url'] = url_for('users.assign_class', user_id=u.id)
        d['assign_subject_url'] = url_for('users.assign_subject', user_id=u.id)
    d['edit_url'] = url_for('users.edit_user', user_id=u.id)
    d['reset_password_url'] = url_for('users.reset_password', user_id=u.id)
    d['back_url'] = url_for('users.index')
    return d


def _user_edit(u):
    d = _user_core(u)
    d['scope'] = u.scope
    d['branch_id'] = u.branch_id
    d['section'] = u.section or ''
    d['stream'] = u.stream or ''
    d['manage_scope'] = u.manage_scope or 'none'
    d['rank'] = u.rank or 0
    d['view_only'] = bool(u.view_only)
    d['permission_map'] = dict(u.permission_map)
    d['teacher'] = _teacher_perms(u.teacher_profile if u.is_teacher else None)
    return d



def _clamp_management_fields(user, role):
    """Apply branch/rank/manage-scope limits a branch manager cannot exceed.

    Central managers may set anything. Branch managers can only create/edit
    accounts in *their* branch, strictly below their own rank, and may not
    grant central management.
    """
    scope = current_manage_scope()
    if scope == 'central':
        user.scope = 'central' if request.form.get('scope') == 'central' else 'branch'
        user.branch_id = (None if user.scope == 'central'
                          else request.form.get('branch_id', type=int))
        user.rank = request.form.get('rank', type=int) or 0
        user.manage_scope = request.form.get('manage_scope') or 'none'
        if user.manage_scope not in ('none', 'branch', 'central'):
            user.manage_scope = 'none'
    else:   # branch manager
        me = get_current_user()
        user.scope = 'branch'
        user.branch_id = me.branch_id if me else None
        # strictly below the manager's rank
        want = request.form.get('rank', type=int) or 0
        user.rank = min(want, current_rank() - 1)
        ms = request.form.get('manage_scope') or 'none'
        user.manage_scope = ms if ms in ('none', 'branch') else 'none'


def _read_perms(form, prefix='perm_'):
    """Build {module_key|module.sub: 'view'|'edit'} from per-module selects."""
    from utils.access_control import MODULE_SUBSECTIONS
    perms = {}
    for key in MODULES:
        lvl = form.get(f'{prefix}{key}')
        if lvl in ('view', 'edit'):
            perms[key] = lvl
        for sub in MODULE_SUBSECTIONS.get(key, {}):
            slvl = form.get(f'{prefix}{key}.{sub}')
            if slvl in ('view', 'edit'):
                perms[f'{key}.{sub}'] = slvl
    # Legacy checkbox fallback (older form posts a 'modules' list = full access).
    if not perms:
        for key in form.getlist('modules'):
            if key in MODULES:
                perms[key] = 'edit'
    return perms


@users_bp.route('/')
@admin_required
def index():
    """List the users the current manager may manage."""
    me = session.get('user_id')
    users = [u for u in User.query.order_by(User.created_at.desc()).all()
             if can_manage(u)]
    return _render({
        'page': 'index',
        'matrix_url': url_for('users.matrix'),
        'add_url': url_for('users.add_user'),
        'users': [{
            'id': u.id, 'username': u.username, 'full_name': u.full_name or '',
            'display_role': u.get_display_role(), 'role_badge': _role_badge(u),
            'is_active': bool(u.is_active), 'is_self': u.id == me,
            'last_login': u.last_login.strftime('%d %b %Y %H:%M') if u.last_login else 'Never',
            'view_url': url_for('users.view_user', user_id=u.id),
            'edit_url': url_for('users.edit_user', user_id=u.id),
            'toggle_url': url_for('users.toggle_status', user_id=u.id),
        } for u in users],
    })


@users_bp.route('/matrix', methods=['GET', 'POST'])
@admin_required
def matrix():
    """Grid view of module access for the users this manager may manage."""
    users = [u for u in User.query.order_by(User.username).all() if can_manage(u)]
    editable = [u for u in users if u.role != 'admin']

    if request.method == 'POST':
        changed = 0
        for u in editable:
            before = (dict(u.permission_map), bool(u.view_only))
            new_perms = _read_perms(request.form, prefix=f'perm_{u.id}_')
            # The matrix grid doesn't manage capability sub-sections — keep any
            # the user already has so a coarse save can't wipe them.
            for ck in CAPABILITY_SUBSECTIONS:
                if ck in u.permission_map:
                    new_perms[ck] = u.permission_map[ck]
            u.set_permissions(restrict_grant_perms(new_perms, u))
            u.view_only = request.form.get(f'view_{u.id}') == 'on'
            after = (dict(u.permission_map), bool(u.view_only))
            if after != before:
                changed += 1
                log_action('user.permissions',
                           f'{u.username} (matrix): perms {before[0]}→{after[0]}, '
                           f'view_only {before[1]}→{after[1]}')
        db.session.commit()
        return _ok(f'Updated access for {changed} user(s).', url_for('users.matrix'))

    return _render({
        'page': 'matrix',
        'save_url': url_for('users.matrix'),
        'back_url': url_for('users.index'),
        'add_url': url_for('users.add_user'),
        'modules': [{'key': k, 'label': v} for k, v in MODULES.items()],
        'has_editable': bool(editable),
        'users': [{
            'id': u.id, 'name': u.full_name or u.username,
            'display_role': u.get_display_role(), 'is_admin': u.role == 'admin',
            'view_only': bool(u.view_only), 'perms': dict(u.permission_map),
            'view_url': url_for('users.view_user', user_id=u.id),
        } for u in users],
    })


@users_bp.route('/add', methods=['GET', 'POST'])
@admin_required
def add_user():
    """Add new user"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip() or None
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip() or None
        role = request.form.get('role', 'teacher')
        
        # Validation
        if not username or not password:
            return _err('Username and password are required.', url_for('users.add_user'))

        if password != confirm_password:
            return _err('Passwords do not match.', url_for('users.add_user'))

        ok, msg = is_password_strong(password)
        if not ok:
            return _err(msg, url_for('users.add_user'))

        # Check if username exists
        if User.query.filter_by(username=username).first():
            return _err('Username already exists.', url_for('users.add_user'))

        # Check if email exists
        if email and User.query.filter_by(email=email).first():
            return _err('Email already exists.', url_for('users.add_user'))
        
        try:
            # Create user
            user = User(
                username=username,
                email=email,
                full_name=full_name,
                phone=phone,
                role=role,
                created_by_id=session.get('user_id')
            )
            user.set_password(password)
            user.must_change_password = request.form.get('require_pw_change') == 'on'
            # Fine-grained per-module access levels (admins always have full access).
            if role != 'admin':
                user.set_permissions(restrict_grant_perms(_read_perms(request.form), user))
            user.view_only = request.form.get('view_only') == 'on'
            user.section = request.form.get('section') or None
            user.stream = request.form.get('stream') or None
            # Branch scope + delegated-management limits.
            _clamp_management_fields(user, role)
            db.session.add(user)
            db.session.flush()  # Get user ID

            # Create teacher profile if role is teacher
            if role == 'teacher':
                teacher = Teacher(
                    user_id=user.id,
                    employee_id=Teacher.generate_employee_id(),
                    branch_id=user.branch_id,
                    can_mark_attendance=request.form.get('can_mark_attendance') == 'on',
                    can_enter_results=request.form.get('can_enter_results') == 'on',
                    can_edit_results=request.form.get('can_edit_results') == 'on',
                    can_view_student_details=request.form.get('can_view_student_details') == 'on',
                    can_print_reports=request.form.get('can_print_reports') == 'on',
                )
                db.session.add(teacher)
            
            db.session.commit()
            log_action('user.create',
                       f'{username} (role={role}, modules={user.module_list or "role default"}, '
                       f'view_only={user.view_only})')
            return _ok(f'User "{username}" created successfully!', url_for('users.index'))

        except Exception as e:
            db.session.rollback()
            return _err(f'Error creating user: {str(e)}', url_for('users.add_user'))

    return _render({
        'page': 'add',
        'submit_url': url_for('users.add_user'),
        'back_url': url_for('users.index'),
        **_form_meta(),
    })


@users_bp.route('/<int:user_id>')
@admin_required
def view_user(user_id):
    """View user details"""
    user = db.get_or_404(User, user_id)
    blocked = _guard(user)
    if blocked:
        return blocked
    return _render({'page': 'view', 'user': _user_view(user)})


@users_bp.route('/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    """Edit user"""
    user = db.get_or_404(User, user_id)
    blocked = _guard(user)
    if blocked:
        return blocked

    if request.method == 'POST':
        # Snapshot access-related fields so we can audit any change.
        before = (user.role, dict(user.permission_map), bool(user.view_only),
                  user.scope, user.branch_id)

        user.email = request.form.get('email', '').strip() or None
        user.full_name = request.form.get('full_name', '').strip()
        user.phone = request.form.get('phone', '').strip() or None
        user.role = request.form.get('role', user.role)
        user.is_active = request.form.get('is_active') == 'on'

        # Fine-grained per-module access levels (admins always have full access).
        if user.role == 'admin':
            user.set_permissions({})
        else:
            user.set_permissions(restrict_grant_perms(_read_perms(request.form), user))
        user.view_only = request.form.get('view_only') == 'on'
        user.section = request.form.get('section') or None
        user.stream = request.form.get('stream') or None
        # Branch scope + delegated-management limits.
        _clamp_management_fields(user, user.role)

        # Update password if provided
        new_password = request.form.get('new_password', '')
        if new_password:
            ok, msg = is_password_strong(new_password)
            if not ok:
                return _err(msg, url_for('users.edit_user', user_id=user_id))
            user.set_password(new_password)
        
        # Update teacher permissions if teacher
        if user.role == 'teacher':
            if not user.teacher_profile:
                teacher = Teacher(
                    user_id=user.id,
                    employee_id=Teacher.generate_employee_id()
                )
                db.session.add(teacher)
                db.session.flush()
            
            teacher = user.teacher_profile
            teacher.can_mark_attendance = request.form.get('can_mark_attendance') == 'on'
            teacher.can_enter_results = request.form.get('can_enter_results') == 'on'
            teacher.can_edit_results = request.form.get('can_edit_results') == 'on'
            teacher.can_view_student_details = request.form.get('can_view_student_details') == 'on'
            teacher.can_print_reports = request.form.get('can_print_reports') == 'on'
            teacher.branch_id = user.branch_id

        try:
            db.session.commit()
            after = (user.role, dict(user.permission_map), bool(user.view_only),
                     user.scope, user.branch_id)
            if after != before:
                log_action('user.permissions',
                           f'{user.username}: role {before[0]}→{after[0]}, '
                           f'perms {before[1]}→{after[1]}, '
                           f'view_only {before[2]}→{after[2]}, '
                           f'scope {before[3]}→{after[3]}, branch {before[4]}→{after[4]}')
            return _ok('User updated successfully!',
                       url_for('users.view_user', user_id=user_id))
        except Exception as e:
            db.session.rollback()
            return _err(f'Error updating user: {str(e)}',
                        url_for('users.edit_user', user_id=user_id))

    return _render({
        'page': 'edit',
        'user': _user_edit(user),
        'submit_url': url_for('users.edit_user', user_id=user.id),
        'view_url': url_for('users.view_user', user_id=user.id),
        'back_url': url_for('users.index'),
        **_form_meta(),
    })


@users_bp.route('/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    """Delete user"""
    user = db.get_or_404(User, user_id)
    blocked = _guard(user)
    if blocked:
        return blocked

    # Prevent deleting self
    if user.id == session.get('user_id'):
        return _err('You cannot delete your own account.', url_for('users.index'))

    # Prevent deleting super_admin if not super_admin
    current_user = db.session.get(User, session.get('user_id'))
    if user.is_super_admin and not current_user.is_super_admin:
        return _err('Only super admins can delete other super admins.', url_for('users.index'))

    username = user.username
    try:
        db.session.delete(user)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return _err(f'Error deleting user: {str(e)}', url_for('users.index'))
    return _ok(f'User "{username}" deleted successfully!', url_for('users.index'))


@users_bp.route('/<int:user_id>/assign-class', methods=['GET', 'POST'])
@admin_required
def assign_class(user_id):
    """Assign teacher to a class as form teacher"""
    user = db.get_or_404(User, user_id)
    blocked = _guard(user)
    if blocked:
        return blocked

    if not user.is_teacher or not user.teacher_profile:
        return _err('User must be a teacher to assign classes.',
                    url_for('users.view_user', user_id=user_id))

    teacher = user.teacher_profile
    active_term = get_active_term()

    if request.method == 'POST':
        assignment_id = request.form.get('assignment_id', type=int)
        is_form_teacher = request.form.get('is_form_teacher') == 'on'

        if not assignment_id:
            return _err('Please select a class.', url_for('users.assign_class', user_id=user_id))

        # Check if already assigned
        existing = TeacherClassAssignment.query.filter_by(
            teacher_id=teacher.id,
            class_arm_assignment_id=assignment_id
        ).first()

        if existing:
            existing.is_form_teacher = is_form_teacher
            existing.is_active = True
        else:
            assignment = TeacherClassAssignment(
                teacher_id=teacher.id,
                class_arm_assignment_id=assignment_id,
                is_form_teacher=is_form_teacher
            )
            db.session.add(assignment)

        try:
            db.session.commit()
            return _ok('Class assigned successfully!', url_for('users.view_user', user_id=user_id))
        except Exception as e:
            db.session.rollback()
            return _err(f'Error: {str(e)}', url_for('users.assign_class', user_id=user_id))

    assignments = []
    if active_term:
        assignments = ClassArmAssignment.query.filter_by(term_id=active_term.id).all()

    return _render({
        'page': 'assign_class',
        'user': {'id': user.id, 'name': user.full_name or user.username},
        'assignments': [{'id': a.id, 'display_name': a.display_name} for a in assignments],
        'has_term': active_term is not None,
        'submit_url': url_for('users.assign_class', user_id=user.id),
        'back_url': url_for('users.view_user', user_id=user.id),
    })


@users_bp.route('/<int:user_id>/assign-subject', methods=['GET', 'POST'])
@admin_required
def assign_subject(user_id):
    """Assign teacher to teach a subject in a class"""
    user = db.get_or_404(User, user_id)
    blocked = _guard(user)
    if blocked:
        return blocked

    if not user.is_teacher or not user.teacher_profile:
        return _err('User must be a teacher to assign subjects.',
                    url_for('users.view_user', user_id=user_id))

    teacher = user.teacher_profile
    active_term = get_active_term()

    if request.method == 'POST':
        assignment_id = request.form.get('assignment_id', type=int)
        subject_id = request.form.get('subject_id', type=int)

        if not assignment_id or not subject_id:
            return _err('Please select both class and subject.',
                        url_for('users.assign_subject', user_id=user_id))

        # Check if already assigned
        existing = TeacherSubjectAssignment.query.filter_by(
            teacher_id=teacher.id,
            class_arm_assignment_id=assignment_id,
            subject_id=subject_id
        ).first()

        if existing:
            existing.is_active = True
        else:
            assignment = TeacherSubjectAssignment(
                teacher_id=teacher.id,
                class_arm_assignment_id=assignment_id,
                subject_id=subject_id
            )
            db.session.add(assignment)

        try:
            db.session.commit()
            return _ok('Subject assigned successfully!', url_for('users.view_user', user_id=user_id))
        except Exception as e:
            db.session.rollback()
            return _err(f'Error: {str(e)}', url_for('users.assign_subject', user_id=user_id))

    assignments = []
    if active_term:
        assignments = ClassArmAssignment.query.filter_by(term_id=active_term.id).all()

    subjects = Subject.query.filter_by(is_active=True).order_by(Subject.name).all()

    return _render({
        'page': 'assign_subject',
        'user': {'id': user.id, 'name': user.full_name or user.username},
        'assignments': [{'id': a.id, 'display_name': a.display_name} for a in assignments],
        'subjects': [{'id': s.id, 'name': s.name} for s in subjects],
        'has_term': active_term is not None,
        'submit_url': url_for('users.assign_subject', user_id=user.id),
        'back_url': url_for('users.view_user', user_id=user.id),
    })


@users_bp.route('/assignment/<int:assignment_id>/remove', methods=['POST'])
@admin_required
def remove_assignment(assignment_id):
    """Remove a class or subject assignment"""
    assignment_type = request.form.get('type', 'class')
    user_id = request.form.get('user_id', type=int)
    
    if assignment_type == 'class':
        assignment = db.get_or_404(TeacherClassAssignment, assignment_id)
    else:
        assignment = db.get_or_404(TeacherSubjectAssignment, assignment_id)
    
    try:
        db.session.delete(assignment)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('users.view_user', user_id=user_id))
    return _ok('Assignment removed successfully!', url_for('users.view_user', user_id=user_id))


@users_bp.route('/<int:user_id>/reset-password', methods=['POST'])
@admin_required
def reset_password(user_id):
    """Reset a managed user's password to a one-time temporary value."""
    user = db.get_or_404(User, user_id)
    blocked = _guard(user)
    if blocked:
        return blocked
    import secrets
    temp = secrets.token_urlsafe(6)
    user.set_password(temp)
    user.must_change_password = True
    db.session.commit()
    log_action('user.password_reset', target=user)
    return _ok(f'Temporary password for {user.username}: {temp} — '
               f'they will be required to change it at next login.',
               url_for('users.view_user', user_id=user.id))


@users_bp.route('/<int:user_id>/toggle-status', methods=['POST'])
@admin_required
def toggle_status(user_id):
    """Toggle user active status"""
    user = db.get_or_404(User, user_id)
    blocked = _guard(user)
    if blocked:
        return blocked

    if user.id == session.get('user_id'):
        return _err('You cannot deactivate your own account.', url_for('users.index'))

    user.is_active = not user.is_active

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('users.index'))
    status = 'activated' if user.is_active else 'deactivated'
    return _ok(f'User {status} successfully!', url_for('users.index'))
