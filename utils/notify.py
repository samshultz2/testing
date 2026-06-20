"""In-app notifications (the header bell).

Call ``notify(...)`` from anywhere a user should be told something happened —
addressed to a specific user or broadcast to a role (``role='admin'`` reaches
every admin, including the legacy password admin). Reads are scoped to the
current recipient (their own rows + role broadcasts).

Best-effort: a failure to create a notification must never break the action
that triggered it, so creation swallows errors.
"""
from flask import session
from sqlalchemy import or_

from models import db, Notification


def notify(title, body='', url=None, *, user_id=None, role=None, category='info'):
    """Create a notification for one user or a role broadcast. Returns it (or
    None on failure)."""
    try:
        n = Notification(title=(title or '')[:150], body=body or '', url=url,
                         user_id=user_id, role=role, category=category)
        db.session.add(n)
        db.session.commit()
        return n
    except Exception:
        db.session.rollback()
        return None


def notify_admins(title, body='', url=None, category='info'):
    """Broadcast to every admin (one row, matched by role at read time)."""
    return notify(title, body, url, role='admin', category=category)


def current_recipient():
    """(user_id, role) for the logged-in user — including the legacy password
    admin (no user_id, treated as the 'admin' role)."""
    from utils.access_control import get_current_user, is_admin
    user = get_current_user()
    if user:
        return user.id, user.role
    if session.get('logged_in') and is_admin():
        return None, 'admin'
    return None, None


def _scope(user_id, role):
    conds = []
    if user_id is not None:
        conds.append(Notification.user_id == user_id)
    if role:
        conds.append(Notification.role == role)
    if not conds:
        return Notification.query.filter(db.literal(False))
    return Notification.query.filter(or_(*conds))


def for_user(user_id, role, limit=20):
    return _scope(user_id, role).order_by(Notification.created_at.desc()).limit(limit).all()


def unread_count(user_id, role):
    return _scope(user_id, role).filter(Notification.is_read.is_(False)).count()


def mark_read(user_id, role, notification_id):
    n = _scope(user_id, role).filter(Notification.id == notification_id).first()
    if n and not n.is_read:
        n.is_read = True
        db.session.commit()
    return n is not None


def mark_all_read(user_id, role):
    rows = _scope(user_id, role).filter(Notification.is_read.is_(False)).all()
    for n in rows:
        n.is_read = True
    if rows:
        db.session.commit()
    return len(rows)
