"""Service layer for staff self-onboarding (see models/staff_onboarding.py).

Kept free of request/permission logic so the routes stay thin and this is unit
testable. Approval is the ONLY place a real ``User`` is created from a link, so
all the account-creation rules live here.
"""
from __future__ import annotations

from datetime import datetime, timedelta


def username_available(username):
    """A username is free only if no live user AND no pending signup holds it."""
    from models import db, User, StaffSignup
    if not username:
        return False
    uname = username.strip().lower()
    if User.query.filter(db.func.lower(User.username) == uname).first():
        return False
    if (StaffSignup.query.filter(db.func.lower(StaffSignup.username) == uname,
                                 StaffSignup.status == 'pending').first()):
        return False
    return True


def email_available(email):
    from models import db, User, StaffSignup
    if not email:
        return True                     # email is optional
    e = email.strip().lower()
    if User.query.filter(db.func.lower(User.email) == e).first():
        return False
    if (StaffSignup.query.filter(db.func.lower(StaffSignup.email) == e,
                                 StaffSignup.status == 'pending').first()):
        return False
    return True


def create_invite(*, label, role, permission_group_id, branch_id, scope,
                  max_uses, expires_days, created_by):
    """Mint a reusable invite link. Returns the StaffInvite."""
    from models import db, StaffInvite
    inv = StaffInvite(
        token=StaffInvite.new_token(), label=(label or None),
        role=(role or 'staff'), permission_group_id=permission_group_id,
        branch_id=branch_id, scope=(scope or 'branch'),
        max_uses=(int(max_uses) if max_uses else None),
        expires_at=(datetime.now() + timedelta(days=int(expires_days))) if expires_days else None,
        created_by=created_by)
    db.session.add(inv)
    db.session.commit()
    return inv


def submit_signup(invite, *, full_name, username, email, phone, password, branch_id,
                  position, gender=None, staff_type=None, department_id=None, qualification=None):
    """Record a pending signup against an invite. Returns (signup, error). Never
    creates a User. ``branch_id`` is ignored when the invite pins a branch. The
    extra bio (gender/staff_type/department/qualification) is kept so approval can
    also create the joiner's HR staff record."""
    from werkzeug.security import generate_password_hash
    from models import db, StaffSignup
    full_name = (full_name or '').strip()
    username = (username or '').strip()
    email = (email or '').strip() or None
    if not full_name or not username or not password:
        return None, 'Full name, username and password are required.'
    if len(password) < 8:
        return None, 'Password must be at least 8 characters.'
    if not username_available(username):
        return None, 'That username is already taken — choose another.'
    if not email_available(email):
        return None, 'That email is already in use.'
    pinned = invite.branch_id
    chosen_branch = pinned if pinned else (int(branch_id) if branch_id else None)
    if not chosen_branch and invite.scope != 'central':
        return None, 'Please select your branch.'
    s = StaffSignup(
        invite_id=invite.id, full_name=full_name, username=username, email=email,
        phone=(phone or '').strip() or None,
        password_hash=generate_password_hash(password),
        branch_id=chosen_branch, position=(position or '').strip() or None,
        gender=(gender or '').strip() or None,
        staff_type=(staff_type or '').strip() or None,
        department_id=(int(department_id) if department_id else None),
        qualification=(qualification or '').strip() or None,
        status='pending')
    db.session.add(s)
    invite.uses = (invite.uses or 0) + 1
    db.session.commit()
    return s, None


def _split_name(full_name):
    """Best-effort split of a single "full name" into (first, surname, middle) for
    the HR record — editable in HR afterwards if the guess is off."""
    parts = [p for p in (full_name or '').split() if p]
    if not parts:
        return '', '', None
    if len(parts) == 1:
        return parts[0], parts[0], None
    return parts[0], parts[-1], (' '.join(parts[1:-1]) or None)


def approve_signup(signup, reviewer_username):
    """Create the real User from a pending signup, granting the invite's role,
    permission group and branch. Returns (user, error)."""
    from models import db, User
    if signup.status != 'pending':
        return None, 'This signup has already been reviewed.'
    # check only against LIVE users — this pending row legitimately holds the name,
    # and approving it is what turns it into a user.
    if User.query.filter(db.func.lower(User.username) == (signup.username or '').lower()).first():
        return None, f'Username "{signup.username}" is now taken by an existing account.'
    inv = signup.invite
    u = User(
        username=signup.username, email=signup.email, full_name=signup.full_name,
        phone=signup.phone, role=(inv.role if inv else 'staff'),
        permission_group_id=(inv.permission_group_id if inv else None),
        branch_id=signup.branch_id or (inv.branch_id if inv else None),
        scope=(inv.scope if inv else 'branch'),
        is_active=True, must_change_password=False)
    u.password_hash = signup.password_hash        # reuse the password they set
    db.session.add(u)
    db.session.flush()

    # Also register them in HR as a staff member, linked to this login account, so
    # they appear in HR immediately (no separate manual entry).
    _create_staff_member(signup, u)

    signup.status = 'approved'
    signup.reviewed_by = reviewer_username
    signup.reviewed_at = datetime.now()
    signup.user_id = u.id
    db.session.commit()
    return u, None


def _create_staff_member(signup, user):
    """Create the HR StaffMember record for an approved signup (best-effort — an HR
    hiccup must not block account creation). Skips if one is already linked."""
    from datetime import date
    from models import db, StaffMember
    if StaffMember.query.filter_by(user_id=user.id).first():
        return
    first, surname, middle = _split_name(signup.full_name)
    try:
        # a SAVEPOINT so an HR failure rolls back ONLY the staff insert — the new
        # User (already flushed in the outer transaction) is never lost.
        with db.session.begin_nested():
            db.session.add(StaffMember(
                staff_id=StaffMember.generate_staff_id(),
                branch_id=signup.branch_id or user.branch_id,
                first_name=first, surname=surname, middle_name=middle,
                gender=signup.gender, phone=signup.phone, email=signup.email,
                department_id=signup.department_id,
                designation=signup.position or (user.role or 'staff').replace('_', ' ').title(),
                staff_type=(signup.staff_type or 'Teaching'),
                date_employed=date.today(), qualification=signup.qualification,
                status='Active', is_active=True, user_id=user.id))
    except Exception:
        pass                              # savepoint rolled back; account stands


def reject_signup(signup, reviewer_username):
    from models import db
    if signup.status != 'pending':
        return False
    signup.status = 'rejected'
    signup.reviewed_by = reviewer_username
    signup.reviewed_at = datetime.now()
    db.session.commit()
    return True
