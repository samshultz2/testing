"""Link a login account (``User``) with an HR record (``StaffMember``).

Historically the two were created separately: adding a staff member did not give
them a way to log in, and adding a user did not create their HR record. They are
already connected by ``StaffMember.user_id`` — this module just makes creating
one *optionally* create and link the other, and keeps the shared fields (name,
email, phone, branch) in step.

Both helpers are idempotent: if the counterpart already exists (or is already
linked) they return it instead of creating a duplicate.
"""
from __future__ import annotations

import re
import secrets


def split_name(full_name: str):
    """Best-effort (first_name, surname) from a single name string."""
    parts = [p for p in re.split(r'\s+', (full_name or '').strip()) if p]
    if not parts:
        return ('', '')
    if len(parts) == 1:
        return (parts[0], parts[0])
    return (parts[0], parts[-1])


def _unique_username(base: str) -> str:
    from models import User
    base = re.sub(r'[^a-z0-9._]', '', (base or 'user').lower()) or 'user'
    base = base[:40]
    cand = base
    n = 1
    while User.query.filter_by(username=cand).first():
        n += 1
        cand = f'{base}{n}'
    return cand


def temp_password() -> str:
    """A strong random temporary password that passes is_password_strong."""
    alpha = 'ABCDEFGHJKMNPQRSTUVWXYZ'
    lower = 'abcdefghijkmnpqrstuvwxyz'
    digits = '23456789'
    core = (secrets.choice(alpha) + secrets.choice(lower) + secrets.choice(digits)
            + ''.join(secrets.choice(alpha + lower + digits) for _ in range(7)))
    return core + '!'


def _email_free(email, exclude_user_id=None):
    from models import User
    if not email:
        return False
    q = User.query.filter(User.email == email)
    if exclude_user_id:
        q = q.filter(User.id != exclude_user_id)
    return q.first() is None


def create_staff_for_user(user, *, staff_type='Teaching', designation=None):
    """Create (or return the existing) HR record for a login ``user`` and link it.
    Returns the ``StaffMember``. Caller commits."""
    from models import db, StaffMember
    existing = StaffMember.query.filter_by(user_id=user.id).first()
    if existing:
        return existing
    first, surname = split_name(user.full_name or user.username)
    s = StaffMember(
        staff_id=StaffMember.generate_staff_id(), user_id=user.id,
        first_name=first or user.username, surname=surname or first or user.username,
        email=user.email or None, phone=getattr(user, 'phone', None),
        branch_id=getattr(user, 'branch_id', None),
        staff_type=staff_type,
        designation=designation or (user.role or 'Staff').replace('_', ' ').title(),
        is_active=True)
    db.session.add(s)
    return s


def create_user_for_staff(staff, *, role=None, require_pw_change=True, created_by_id=None):
    """Create (or return the existing linked) login ``User`` for a ``StaffMember``
    and link it. Returns ``(user, temp_password_or_None)`` — the temp password is
    only present when a brand-new account was made. Caller commits."""
    from models import db, User, Teacher
    if staff.user_id:
        return db.session.get(User, staff.user_id), None
    if role is None:
        role = 'teacher' if (staff.staff_type or '').lower().startswith('teach') else 'staff'
    username = _unique_username(
        (staff.email.split('@')[0] if staff.email else '') or
        f'{staff.first_name}.{staff.surname}'.strip('.'))
    temp = temp_password()
    email = staff.email if _email_free(staff.email) else None
    u = User(username=username, email=email, full_name=staff.display_name,
             phone=staff.phone, role=role, branch_id=staff.branch_id,
             must_change_password=require_pw_change, created_by_id=created_by_id)
    u.set_password(temp)
    db.session.add(u)
    db.session.flush()                      # need u.id for the link + teacher row
    staff.user_id = u.id
    if role == 'teacher' and not Teacher.query.filter_by(user_id=u.id).first():
        db.session.add(Teacher(user_id=u.id, employee_id=Teacher.generate_employee_id(),
                               branch_id=u.branch_id))
    return u, temp
