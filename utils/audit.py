"""Audit logging for sensitive/administrative actions.

Records *who* did *what*, to *what*, and *when*. Use ``log_action`` with explicit
fields, or ``log_event`` to derive the target from a model instance.
"""
from flask import session, request

from models import db, AuditLog


def _derive_target(obj):
    """Return (type, id, label) for a model instance, best-effort."""
    if obj is None:
        return None, None, None
    ttype = type(obj).__name__.lower()
    tid = getattr(obj, 'id', None)
    for attr in ('full_name', 'name', 'title', 'receipt_no', 'student_id',
                 'username', 'serial'):
        val = getattr(obj, attr, None)
        if val:
            return ttype, tid, str(val)[:150]
    return ttype, tid, None


def log_action(action, detail=None, target=None, target_type=None,
               target_id=None, target_label=None):
    """Record an audited action by the current user. Never raises.

    Pass ``target`` (a model instance) to auto-fill the target fields, or set
    ``target_type`` / ``target_id`` / ``target_label`` explicitly.
    """
    try:
        if target is not None:
            dt, di, dl = _derive_target(target)
            target_type = target_type or dt
            target_id = target_id or di
            target_label = target_label or dl
        branch_id = session.get('view_branch_id') or session.get('branch_id')
        entry = AuditLog(
            user=session.get('user') or session.get('username') or 'unknown',
            role=session.get('role'),
            action=action,
            detail=detail,
            target_type=target_type,
            target_id=target_id,
            target_label=target_label,
            branch_id=branch_id,
            ip_address=request.remote_addr if request else None,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass


def log_event(action, target, detail=None):
    """Convenience: log an action against a model instance."""
    log_action(action, detail=detail, target=target)
