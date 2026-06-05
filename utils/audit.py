"""Audit logging for sensitive/administrative actions."""
from flask import session, request

from models import db, AuditLog


def log_action(action, detail=None):
    """Record an audited action by the current user. Never raises."""
    try:
        entry = AuditLog(
            user=session.get('user') or session.get('username') or 'unknown',
            role=session.get('role'),
            action=action,
            detail=detail,
            ip_address=request.remote_addr if request else None,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
