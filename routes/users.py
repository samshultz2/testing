"""
User Management Routes
Handles user CRUD, role management, and teacher assignments
"""
from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   session, jsonify)
from utils.helpers import get_active_term
from models import (db, ClassArmAssignment, Subject, User, Teacher, TeacherClassAssignment,
                    TeacherSubjectAssignment, PermissionGroup)
from utils.access_control import (MODULES, manage_users_required, can_manage,
                                  current_manage_scope, current_rank, get_current_user,
                                  restrict_grant_perms, CAPABILITY_SUBSECTIONS,
                                  ROLE_DEFAULT_MODULES, filter_classes_for_user)
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


# --- Permission groups: branch-scoped visibility / management ----------------
def _my_branch_id():
    me = get_current_user()
    return me.branch_id if me else None


def _group_within_authority(g):
    """A branch manager may only assign a bundle no larger than their own — a
    group that grants access they lack is not assignable. Central managers are
    unfettered."""
    from utils.access_control import clamp_to_granter
    if current_manage_scope() == 'central':
        return True
    pm = g.permission_map
    return clamp_to_granter(pm, None) == pm


def _groups_in_scope():
    """Active groups the current manager may ASSIGN: central templates (no branch)
    plus, for a branch manager, their own branch's groups — and, for a branch
    manager, only bundles within their own authority."""
    q = PermissionGroup.query.filter_by(is_active=True)
    if current_manage_scope() == 'central':
        return q.order_by(PermissionGroup.name).all()
    bid = _my_branch_id()
    rows = (q.filter((PermissionGroup.branch_id.is_(None)) | (PermissionGroup.branch_id == bid))
             .order_by(PermissionGroup.name).all())
    return [g for g in rows if _group_within_authority(g)]


def _group_assignable(g):
    """May the current manager assign this group to a user?"""
    if g is None:
        return True
    if current_manage_scope() == 'central':
        return True
    return ((g.branch_id is None or g.branch_id == _my_branch_id())
            and _group_within_authority(g))


def _group_manageable(g):
    """May the current manager edit/delete this group? (central groups are
    central-only; a branch manager owns only their own branch's groups)."""
    if g is None:
        return False
    if current_manage_scope() == 'central':
        return True
    return g.branch_id is not None and g.branch_id == _my_branch_id()


def _group_json(g):
    return {'id': g.id, 'name': g.name, 'description': g.description or '',
            'branch_id': g.branch_id, 'permissions': g.permission_map,
            'manageable': _group_manageable(g),
            'edit_url': url_for('users.edit_group', group_id=g.id),
            'delete_url': url_for('users.delete_group', group_id=g.id)}


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
    from utils.security import password_rules
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
        'groups': [_group_json(g) for g in _groups_in_scope()],
        # Password policy from the single server source of truth (utils.security),
        # so the React form's live checklist matches what add/edit will accept.
        'password_rules': password_rules(),
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
    d['mfa_enabled'] = bool(getattr(u, 'mfa_enabled', False))
    d['reset_mfa_url'] = url_for('users.reset_mfa', user_id=u.id)
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
    d['permission_map'] = dict(u.permission_map)        # effective (group + overrides)
    d['own_permissions'] = dict(u.own_permissions)      # per-user overrides only
    d['permission_group_id'] = u.permission_group_id
    d['group_permissions'] = (u.permission_group.permission_map
                              if u.permission_group else {})
    d['teacher'] = _teacher_perms(u.teacher_profile if u.is_teacher else None)
    return d



# Roles a branch-scoped manager may assign. A branch manager's new users are
# force-scoped to their own branch by _clamp_management_fields(), so an 'admin'
# here becomes a BRANCH admin (is_central=False) — full access within the branch
# only, which is the intended delegation model. 'super_admin' is deliberately
# excluded: User.is_central is True for any super_admin REGARDLESS of scope, so
# it escapes the branch clamp and is the one role a branch manager must never
# grant. Assigning it requires central authority (same gate as scope='central').
_BRANCH_ASSIGNABLE_ROLES = set(ROLE_DEFAULT_MODULES) | {'teacher', 'admin'}


def _safe_role(requested, existing=None):
    """Clamp the role a manager may assign to their own authority.

    The security invariant: a branch-scoped manager must not create a *central*
    actor. Branch/rank/scope are already clamped in _clamp_management_fields, so
    the only role that escapes that clamp is 'super_admin' (always central). Gate
    it behind central authority; allow the branch-confinable roles otherwise, and
    fall back to a safe default for unknown role strings.
    """
    requested = (requested or existing or 'teacher')
    if requested == 'super_admin':
        if current_manage_scope() == 'central':
            return 'super_admin'
        # A non-central manager cannot mint a central super-admin: keep the
        # existing role if it's branch-assignable, else drop to 'teacher'.
        return existing if existing in _BRANCH_ASSIGNABLE_ROLES else 'teacher'
    return requested if requested in _BRANCH_ASSIGNABLE_ROLES else 'teacher'


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


def _apply_group(user, role):
    """Set the user's permission group from the form, honouring assign-scope.
    Admins ignore groups (they always have full access)."""
    if role == 'admin':
        user.permission_group_id = None
        return
    gid = request.form.get('permission_group_id', type=int)
    if gid:
        g = db.session.get(PermissionGroup, gid)
        user.permission_group_id = g.id if (g and g.is_active and _group_assignable(g)) else None
    else:
        user.permission_group_id = None


def _read_perms(form, prefix='perm_'):
    """Build {module_key|module.sub: 'view'|'edit'} from per-module selects."""
    from utils.access_control import MODULE_SUBSECTIONS
    perms = {}
    for key in MODULES:
        lvl = form.get(f'{prefix}{key}')
        # 'none' is a per-user override that REVOKES a group-granted permission;
        # absent/'inherit' leaves it to the group.
        if lvl in ('view', 'edit', 'none'):
            perms[key] = lvl
        for sub in MODULE_SUBSECTIONS.get(key, {}):
            slvl = form.get(f'{prefix}{key}.{sub}')
            if slvl in ('view', 'edit', 'none'):
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
    my_super = bool(db.session.get(User, me).is_super_admin) if me else False
    users = [u for u in User.query.order_by(User.created_at.desc()).all()
             if can_manage(u)]
    return _render({
        'page': 'index',
        'matrix_url': url_for('users.matrix'),
        'groups_url': url_for('users.groups'),
        'add_url': url_for('users.add_user'),
        'users': [{
            'id': u.id, 'username': u.username, 'full_name': u.full_name or '',
            'display_role': u.get_display_role(), 'role_badge': _role_badge(u),
            'is_active': bool(u.is_active), 'is_self': u.id == me,
            'last_login': u.last_login.strftime('%d %b %Y %H:%M') if u.last_login else 'Never',
            'view_url': url_for('users.view_user', user_id=u.id),
            'edit_url': url_for('users.edit_user', user_id=u.id),
            'toggle_url': url_for('users.toggle_status', user_id=u.id),
            'delete_url': url_for('users.delete_user', user_id=u.id),
            # Deletable = not yourself, and a super-admin only by a super-admin —
            # mirrors the delete_user route guards.
            'can_delete': (u.id != me and not (u.is_super_admin and not my_super)),
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
            # the user holds as their OWN override so a coarse save can't wipe
            # them (group-inherited caps are left to the group, not frozen here).
            for ck in CAPABILITY_SUBSECTIONS:
                if ck in u.own_permissions:
                    new_perms[ck] = u.own_permissions[ck]
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
            'own_perms': dict(u.own_permissions),
            'group_perms': (u.permission_group.permission_map if u.permission_group else {}),
            'group_name': (u.permission_group.name if u.permission_group else None),
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
        role = _safe_role(request.form.get('role', 'teacher'))

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
            # Permission group (base) + fine-grained per-user overrides.
            _apply_group(user, role)
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

            # Optionally also create a linked HR/staff record from the same details.
            staff_note = ''
            if request.form.get('create_staff') == 'on':
                from utils.staff_user_link import create_staff_for_user
                s = create_staff_for_user(user)
                staff_note = f' A staff record ({s.staff_id}) was created and linked.'

            db.session.commit()
            log_action('user.create',
                       f'{username} (role={role}, modules={user.module_list or "role default"}, '
                       f'view_only={user.view_only}){", +staff" if staff_note else ""}')
            return _ok(f'User "{username}" created successfully!{staff_note}', url_for('users.index'))

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
        user.role = _safe_role(request.form.get('role', user.role), existing=user.role)
        user.is_active = request.form.get('is_active') == 'on'

        # Permission group (base) + fine-grained per-user overrides.
        _apply_group(user, user.role)
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
            teacher = user.teacher_profile
            if not teacher:
                teacher = Teacher(
                    user_id=user.id,
                    employee_id=Teacher.generate_employee_id()
                )
                db.session.add(teacher)
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

    # Prevent deleting super_admin if not super_admin. The legacy password admin
    # has no user row (current_user is None) and is treated as super.
    _me = session.get('user_id')
    current_user = db.session.get(User, _me) if _me else None
    actor_super = current_user.is_super_admin if current_user else True
    if user.is_super_admin and not actor_super:
        return _err('Only super admins can delete other super admins.', url_for('users.index'))

    username = user.username
    uid = user.id
    # Audit BEFORE the delete so the actor + who was removed is recorded even if
    # the row (and its label) is gone afterwards.
    log_action('user.delete',
               detail=f'{username} (role={user.role}, scope={user.scope}, branch={user.branch_id})',
               target_type='user', target_id=uid, target_label=username)
    # Clear the cheap/transient references that would block a clean delete but
    # carry no value once the account is gone, and unlink (don't delete) their
    # staff record so its history survives.
    try:
        from models import UserSession, Notification, StaffMember
        UserSession.query.filter_by(user_id=uid).delete(synchronize_session=False)
        Notification.query.filter_by(user_id=uid).delete(synchronize_session=False)
        StaffMember.query.filter_by(user_id=uid).update({'user_id': None},
                                                        synchronize_session=False)
        db.session.flush()
        db.session.delete(user)
        db.session.commit()
        return _ok(f'User "{username}" deleted successfully!', url_for('users.index'))
    except Exception:
        # Still referenced elsewhere (teacher profile, chat messages, created-by
        # trails, …). Keep the row but fully disable it, and end any live session.
        db.session.rollback()
        u2 = db.session.get(User, uid)
        if u2 is None:
            return _ok(f'User "{username}" deleted successfully!', url_for('users.index'))
        u2.is_active = False
        try:
            u2.token_version = (u2.token_version or 0) + 1   # invalidate live logins
        except Exception:
            pass
        db.session.commit()
        return _ok(f'"{username}" has linked records, so it was deactivated (sign-in '
                   f'blocked) instead of being permanently deleted.', url_for('users.index'))


# ============================================================================
# PERMISSION GROUPS
# ============================================================================
@users_bp.route('/groups')
@admin_required
def groups():
    """Manage permission-group templates the current manager may see."""
    from models import Branch
    from utils.access_control import MODULE_SUBSECTIONS, CAPABILITY_SUBSECTIONS as CAPS
    return _render({
        'page': 'groups',
        'add_url': url_for('users.add_group'),
        'back_url': url_for('users.index'),
        'modules': [{'key': k, 'label': v} for k, v in MODULES.items()],
        # Same granular catalogue the user editor gets, so a group can grant
        # sub-sections and capabilities (incl. self-scope) — not just modules.
        'subsections': {k: [{'sub': s, 'label': l} for s, l in subs.items()]
                        for k, subs in MODULE_SUBSECTIONS.items()},
        'capabilities': sorted(CAPS),
        'cap_modules': sorted({c.split('.')[0] for c in CAPS}),
        'can_pick_branch': current_manage_scope() == 'central',
        'branches': [{'id': b.id, 'name': b.name}
                     for b in Branch.query.order_by(Branch.name).all()],
        'groups': [{**_group_json(g),
                    'branch_name': (g.branch.name if g.branch else 'All branches'),
                    'user_count': User.query.filter_by(permission_group_id=g.id).count()}
                   for g in _groups_in_scope()],
    })


def _save_group_fields(g):
    """Apply name/description/branch/permissions from the form to ``g``."""
    g.name = (request.form.get('name') or g.name or '').strip()
    g.description = (request.form.get('description') or '').strip() or None
    if current_manage_scope() == 'central':
        g.branch_id = request.form.get('branch_id', type=int) or None
    elif g.id is None:                       # new branch-manager group => own branch
        g.branch_id = _my_branch_id()
    perms = {k: v for k, v in _read_perms(request.form).items() if v in ('view', 'edit')}
    g.set_permissions(restrict_grant_perms(perms, None))


@users_bp.route('/groups/add', methods=['POST'])
@admin_required
def add_group():
    if not (request.form.get('name') or '').strip():
        return _err('Group name is required.', url_for('users.groups'))
    g = PermissionGroup(created_by_id=session.get('user_id'))
    _save_group_fields(g)
    db.session.add(g)
    db.session.commit()
    log_action('permgroup.create', f'{g.name} (branch={g.branch_id}, perms={g.permission_map})')
    return _ok(f'Group "{g.name}" created.', url_for('users.groups'))


@users_bp.route('/groups/<int:group_id>/edit', methods=['POST'])
@admin_required
def edit_group(group_id):
    g = db.get_or_404(PermissionGroup, group_id)
    if not _group_manageable(g):
        return _err('You are not allowed to manage that group.',
                    url_for('users.groups'), status=403)
    before = dict(g.permission_map)
    _save_group_fields(g)
    db.session.commit()
    log_action('permgroup.update', f'{g.name}: perms {before}→{g.permission_map}')
    return _ok(f'Group "{g.name}" updated.', url_for('users.groups'))


@users_bp.route('/groups/<int:group_id>/delete', methods=['POST'])
@admin_required
def delete_group(group_id):
    g = db.get_or_404(PermissionGroup, group_id)
    if not _group_manageable(g):
        return _err('You are not allowed to manage that group.',
                    url_for('users.groups'), status=403)
    name = g.name
    # Detach members first: they keep their own overrides, lose the group base.
    User.query.filter_by(permission_group_id=g.id).update({'permission_group_id': None})
    db.session.delete(g)
    db.session.commit()
    log_action('permgroup.delete', f'{name}')
    return _ok(f'Group "{name}" deleted.', url_for('users.groups'))


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

        # A branch manager may only assign classes in their own branch/section —
        # otherwise they could hand a teacher (and the results they can enter) a
        # class in a branch they don't manage.
        caa = db.session.get(ClassArmAssignment, assignment_id)
        if not caa:
            return _err('Please select a valid class.', url_for('users.assign_class', user_id=user_id))
        from utils.branch_scope import can_access_branch
        if not can_access_branch(caa.branch_id):
            return _err('That class is outside the branch you manage.',
                        url_for('users.assign_class', user_id=user_id))

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
        assignments = filter_classes_for_user(
            ClassArmAssignment.query.filter_by(term_id=active_term.id).all())

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

        # Branch guard: a branch manager may only assign a teacher to classes in
        # the branch/section they manage (mirrors assign_class).
        caa = db.session.get(ClassArmAssignment, assignment_id)
        if not caa:
            return _err('Please select a valid class.', url_for('users.assign_subject', user_id=user_id))
        from utils.branch_scope import can_access_branch
        if not can_access_branch(caa.branch_id):
            return _err('That class is outside the branch you manage.',
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
        assignments = filter_classes_for_user(
            ClassArmAssignment.query.filter_by(term_id=active_term.id).all())

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
    # Reset revokes existing sessions so a stolen/old session can't linger.
    user.token_version = (user.token_version or 0) + 1
    db.session.commit()
    log_action('user.password_reset', target=user)

    # Prefer emailing the new password to the user; only fall back to showing it
    # on the admin's screen when there's no address to send it to. Either way the
    # user must change it the moment they sign in (must_change_password is set).
    emailed = False
    if user.email:
        from utils import mailer
        if mailer.is_configured():
            try:
                mailer.send_email(
                    user.email, 'Your EduSyncra password has been reset',
                    f'Hello {user.full_name or user.username},\n\n'
                    f'An administrator has reset your EduSyncra password. Use this '
                    f'temporary password to sign in:\n\n'
                    f'    Username: {user.username}\n'
                    f'    Temporary password: {temp}\n\n'
                    f'For your security, please change it immediately after you log '
                    f'in — you will be prompted to do so automatically.\n\n'
                    f'If you did not expect this, contact your administrator.\n')
                emailed = True
            except Exception:
                emailed = False

    if emailed:
        msg = (f'A temporary password for {user.username} has been emailed to '
               f'{user.email}. They must change it immediately on their next login.')
    else:
        reason = 'no email on file' if not user.email else 'email is not configured'
        # Include the password in the message too so the no-JS fallback (a plain
        # form POST) still surfaces it; the React client ignores this and shows
        # the structured temp_password in a persistent dialog instead.
        msg = (f'Temporary password for {user.username}: {temp} ({reason}) — share it '
               f'securely. They must change it immediately on next login.')
    # Structured fields let the React client show a persistent result dialog:
    # the emailed-to address, or the password itself (with a Copy button) when
    # it could not be delivered. temp is only returned when NOT emailed.
    return _ok(msg, url_for('users.view_user', user_id=user.id),
               emailed=emailed, username=user.username,
               user_email=user.email or None,
               temp_password=None if emailed else temp)


@users_bp.route('/<int:user_id>/reset-mfa', methods=['POST'])
@admin_required
def reset_mfa(user_id):
    """Turn off a locked-out user's 2FA so they can sign in again (recovery for a
    lost authenticator). They can re-enable it afterwards from Security."""
    user = db.get_or_404(User, user_id)
    blocked = _guard(user)
    if blocked:
        return blocked
    if not user.mfa_enabled:
        return _ok(f'{user.username} does not have 2FA enabled.',
                   url_for('users.view_user', user_id=user.id))
    user.disable_mfa()
    db.session.commit()
    log_action('user.mfa_reset', target=user)
    return _ok(f'Two-factor authentication turned off for {user.username}.',
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
