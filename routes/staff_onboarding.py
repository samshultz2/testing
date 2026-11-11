"""Staff self-onboarding: admin generates a shareable invite link, staff sign up
through it, an admin approves. See models/staff_onboarding.py and
utils/staff_invite.py.

Admin routes require the user-management capability; the public ``/join`` routes
require no login (the secret token is the gate) and only ever create a PENDING
signup — never a live account or any permission.
"""
from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   session, abort)

from models import db, StaffInvite, StaffSignup, PermissionGroup, Branch, User, Department
from utils.access_control import (manage_users_required, current_manage_scope,
                                  get_current_user)
from utils import staff_invite as svc
from utils.audit import log_action
from utils.security import rate_limited

staff_onb_bp = Blueprint('staff_onboarding', __name__)


@staff_onb_bp.before_request
def _ensure_invite_schema():
    """Self-heal the preset-position / field-selection columns on the bound tenant
    DB before any invite route runs (best-effort)."""
    try:
        from utils.staff_invite_schema import ensure_staff_invite_schema
        ensure_staff_invite_schema()
    except Exception:
        pass

# Roles a BRANCH-level manager may hand out (never admin/super_admin). Central
# managers may grant any role.
_BRANCH_GRANTABLE_ROLES = {'teacher', 'staff', 'readonly'}
_ALL_ROLES = ['staff', 'teacher', 'readonly', 'admin']


def _is_central():
    return current_manage_scope() == 'central'


def _assignable_groups():
    """Permission groups the current manager may put on an invite: central sees all
    active groups; a branch manager sees central groups + their own branch's."""
    q = PermissionGroup.query.filter(PermissionGroup.is_active.isnot(False))
    if _is_central():
        return q.order_by(PermissionGroup.name).all()
    from utils.access_control import clamp_to_granter
    me = get_current_user()
    bid = me.branch_id if me else None
    # branch scope + only bundles no larger than the manager's own authority
    return [g for g in q.order_by(PermissionGroup.name).all()
            if (g.branch_id is None or g.branch_id == bid)
            and clamp_to_granter(g.permission_map, None) == g.permission_map]


def _can_grant(role, scope, branch_id):
    """Guard against privilege escalation when minting an invite / approving."""
    if _is_central():
        return True
    me = get_current_user()
    if not me:
        return False
    # a branch manager may only grant branch-scoped, non-admin roles in own branch
    return (role in _BRANCH_GRANTABLE_ROLES and scope != 'central'
            and branch_id and me.branch_id and branch_id == me.branch_id)


# --- admin: manage invite links + approve signups ---------------------------
@staff_onb_bp.route('/staff-invites')
@manage_users_required
def invites():
    groups = _assignable_groups()
    invite_rows = (StaffInvite.query.order_by(StaffInvite.is_active.desc(),
                                              StaffInvite.created_at.desc()).all())
    if not _is_central():
        me = get_current_user()
        bid = me.branch_id if me else None
        invite_rows = [i for i in invite_rows if i.branch_id == bid]
    pending = (StaffSignup.query.filter_by(status='pending')
               .order_by(StaffSignup.created_at).all())
    if not _is_central():
        me = get_current_user()
        pending = [s for s in pending if s.branch_id == (me.branch_id if me else None)]
    branches = Branch.query.order_by(Branch.name).all()
    from utils import timeutil as _tu
    now = _tu.now()
    pend_by = {}
    for sgn in StaffSignup.query.filter_by(status='pending').all():
        pend_by[sgn.invite_id] = pend_by.get(sgn.invite_id, 0) + 1
    joined = {}
    for sgn in StaffSignup.query.filter_by(status='approved').all():
        joined[sgn.invite_id] = joined.get(sgn.invite_id, 0) + 1
    meta = {i.id: {'days_left': ((i.expires_at - now).days if i.expires_at else None),
                   'pending': pend_by.get(i.id, 0), 'joined': joined.get(i.id, 0)} for i in invite_rows}
    dead = [i for i in invite_rows if not i.usable and not pend_by.get(i.id)]
    return render_template('staff_onboarding/invites.html',
                           invites=invite_rows, pending=pending, groups=groups,
                           branches=branches, roles=_ALL_ROLES, is_central=_is_central(),
                           meta=meta, dead_count=len(dead), new_id=request.args.get('new', type=int),
                           totals={'joined': sum(m['joined'] for m in meta.values()),
                                   'uses': sum((i.uses or 0) for i in invite_rows)},
                           field_labels={'email': 'Email', 'phone': 'Phone', 'position': 'Position / title',
                                         'gender': 'Gender', 'staff_type': 'Teaching / non-teaching',
                                         'department': 'Department', 'qualification': 'Qualification'})


@staff_onb_bp.route('/staff-invites/create', methods=['POST'])
@manage_users_required
def create_invite():
    role = (request.form.get('role') or 'staff').strip()
    scope = 'central' if request.form.get('scope') == 'central' else 'branch'
    gid = request.form.get('permission_group_id', type=int)
    branch_id = request.form.get('branch_id', type=int)
    if scope == 'central':
        branch_id = None
    # branch managers are pinned to their own branch and can't go central
    if not _is_central():
        me = get_current_user()
        branch_id = me.branch_id if me else None
        scope = 'branch'
    if not _can_grant(role, scope, branch_id):
        flash('You are not allowed to create an invite for that role/branch.', 'error')
        return redirect(url_for('staff_onboarding.invites'))
    # validate the chosen group is one we may assign
    if gid and gid not in {g.id for g in _assignable_groups()}:
        flash('That permission group is not available to you.', 'error')
        return redirect(url_for('staff_onboarding.invites'))
    me = get_current_user()
    # Which optional join-form fields to expose. If the form submitted the field
    # picker at all (marker present), honour the selection; otherwise leave None
    # (= show all, backward compatible).
    fields = None
    if request.form.get('fields_picker') == '1':
        fields = request.form.getlist('fields')
    inv = svc.create_invite(
        label=request.form.get('label'), role=role, permission_group_id=gid,
        branch_id=branch_id, scope=scope,
        max_uses=request.form.get('max_uses', type=int),
        expires_days=request.form.get('expires_days', type=int),
        created_by=(me.username if me else session.get('username')),
        position=request.form.get('position'), fields=fields)
    log_action('staff_invite.create', f'invite {inv.id} role={role} group={gid} branch={branch_id}')
    flash('Invite link created — copy it and send it to your staff.', 'success')
    return redirect(url_for('staff_onboarding.invites', new=inv.id))


@staff_onb_bp.route('/staff-invites/<int:invite_id>/toggle', methods=['POST'])
@manage_users_required
def toggle_invite(invite_id):
    inv = db.session.get(StaffInvite, invite_id) or abort(404)
    if not _is_central():
        me = get_current_user()
        if inv.branch_id != (me.branch_id if me else None):
            abort(403)
    inv.is_active = not inv.is_active
    db.session.commit()
    flash('Invite ' + ('activated.' if inv.is_active else 'deactivated.'), 'success')
    return redirect(url_for('staff_onboarding.invites'))


def _own_invite_or_403(invite_id):
    inv = db.session.get(StaffInvite, invite_id) or abort(404)
    if not _is_central():
        me = get_current_user()
        if inv.branch_id != (me.branch_id if me else None):
            abort(403)
    return inv


def _delete_invite(inv):
    """Delete an invite link. Refused while sign-ups through it still wait for
    approval (approving needs the link's role / group). Reviewed sign-ups keep
    their record; they just stop pointing at the deleted link."""
    if StaffSignup.query.filter_by(invite_id=inv.id, status='pending').first():
        return False
    StaffSignup.query.filter_by(invite_id=inv.id).update({StaffSignup.invite_id: None}, synchronize_session=False)
    db.session.delete(inv)
    return True


@staff_onb_bp.route('/staff-invites/<int:invite_id>/delete', methods=['POST'])
@manage_users_required
def delete_invite(invite_id):
    inv = _own_invite_or_403(invite_id)
    label = inv.label or f'{inv.role} invite'
    if not _delete_invite(inv):
        flash('Someone who joined through this link is still waiting for approval — approve or reject them first.', 'error')
        return redirect(url_for('staff_onboarding.invites'))
    db.session.commit()
    log_action('staff_invite.delete', f'invite {invite_id} ({label})')
    flash(f'Deleted “{label}”. The link no longer works.', 'success')
    return redirect(url_for('staff_onboarding.invites'))


@staff_onb_bp.route('/staff-invites/clear-dead', methods=['POST'])
@manage_users_required
def clear_dead_invites():
    """Delete every expired / used-up / switched-off link in scope (skipping any
    with sign-ups still waiting for approval)."""
    rows = StaffInvite.query.all()
    if not _is_central():
        me = get_current_user()
        rows = [i for i in rows if i.branch_id == (me.branch_id if me else None)]
    n = 0
    for inv in rows:
        if not inv.usable and _delete_invite(inv):
            n += 1
    db.session.commit()
    log_action('staff_invite.clear', f'{n} dead invite(s) deleted')
    flash(f'Deleted {n} old link{"s" if n != 1 else ""}.' if n else 'No old links to delete.', 'success')
    return redirect(url_for('staff_onboarding.invites'))


@staff_onb_bp.route('/staff-invites/signup/<int:signup_id>/<action>', methods=['POST'])
@manage_users_required
def review_signup(signup_id, action):
    s = db.session.get(StaffSignup, signup_id) or abort(404)
    inv = s.invite
    role = inv.role if inv else 'staff'
    scope = inv.scope if inv else 'branch'
    branch_id = s.branch_id or (inv.branch_id if inv else None)
    if not _can_grant(role, scope, branch_id):
        flash('You are not allowed to approve this account.', 'error')
        return redirect(url_for('staff_onboarding.invites'))
    if action == 'approve':
        user, err = svc.approve_signup(s, (get_current_user().username
                                           if get_current_user() else 'admin'))
        if err:
            flash(err, 'error')
        else:
            log_action('staff_invite.approve', f'signup {s.id} -> user {user.id} ({user.username})')
            flash(f'Approved {user.full_name or user.username} — they can now log in.', 'success')
    elif action == 'reject':
        svc.reject_signup(s, get_current_user().username if get_current_user() else 'admin')
        log_action('staff_invite.reject', f'signup {s.id} ({s.username})')
        flash('Signup rejected.', 'success')
    return redirect(url_for('staff_onboarding.invites'))


# --- public: staff sign up through a link (no login) ------------------------
def _load_invite(token):
    return StaffInvite.query.filter_by(token=token).first()


def _active_departments():
    q = Department.query
    if hasattr(Department, 'is_active'):
        q = q.filter(Department.is_active.isnot(False))
    return q.order_by(Department.name).all()


@staff_onb_bp.route('/join/<token>', methods=['GET'])
def join(token):
    inv = _load_invite(token)
    if not inv or not inv.usable:
        return render_template('staff_onboarding/join_closed.html',
                               reason=('expired or fully used' if inv else 'invalid'))
    branches = Branch.query.order_by(Branch.name).all() if not inv.branch_id else []
    return render_template('staff_onboarding/join.html', invite=inv, branches=branches,
                           departments=_active_departments(),
                           school=(session.get('school_name') or 'the school'))


@staff_onb_bp.route('/join/<token>', methods=['POST'])
@rate_limited('staff_join', max_requests=10, window_minutes=15,
              global_max=300, global_window_minutes=15)
def join_submit(token):
    inv = _load_invite(token)
    if not inv or not inv.usable:
        return render_template('staff_onboarding/join_closed.html', reason='invalid')
    signup, err = svc.submit_signup(
        inv, full_name=request.form.get('full_name'),
        username=request.form.get('username'), email=request.form.get('email'),
        phone=request.form.get('phone'), password=request.form.get('password'),
        branch_id=request.form.get('branch_id'), position=request.form.get('position'),
        gender=request.form.get('gender'), staff_type=request.form.get('staff_type'),
        department_id=request.form.get('department_id'),
        qualification=request.form.get('qualification'))
    if err:
        flash(err, 'error')
        branches = Branch.query.order_by(Branch.name).all() if not inv.branch_id else []
        return render_template('staff_onboarding/join.html', invite=inv, branches=branches,
                               form=request.form, departments=_active_departments(),
                               school=(session.get('school_name') or 'the school')), 400
    # Alert admins that someone joined via an invite and needs approval — the
    # header bell + the pending list on the invites page.
    try:
        from utils.notify import notify_branch_admins
        role_label = (inv.role or 'staff').replace('_', ' ')
        pos = getattr(signup, 'position', None)
        # Scope to the admins of the branch this signup belongs to (plus central
        # admins), not every admin in the org.
        branch_id = getattr(signup, 'branch_id', None) or inv.branch_id
        notify_branch_admins(
            'New staff signup awaiting approval',
            f'{signup.full_name} signed up via a staff invite as {role_label}'
            + (f' ({pos})' if pos else '') + '. Review and approve to activate the account.',
            url=url_for('staff_onboarding.invites'), branch_id=branch_id, category='info')
        log_action('staff_invite.signup',
                   f'signup {signup.id} ({signup.full_name}) via invite {inv.id}')
    except Exception:
        pass
    return render_template('staff_onboarding/join_done.html', signup=signup)
