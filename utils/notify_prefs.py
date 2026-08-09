"""Per-user notification-channel preferences (feature-flagged via NOTIFY_PREFS).

Opt-out model: no row means the channel is on. Enforcement is gated by the flag,
and today only the in-app channel is enforced (in utils.notify) — the safest
channel to suppress. Email/SMS/push preferences are captured for future use.
"""
import os

CHANNELS = ('inapp', 'email', 'sms', 'push')
CHANNEL_LABELS = {'inapp': 'In-app (bell)', 'email': 'Email', 'sms': 'SMS', 'push': 'Web push'}


def flag_enabled(app=None):
    try:
        from flask import current_app
        a = app or current_app
        val = a.config.get('NOTIFY_PREFS')
    except Exception:
        val = None
    if val is None:
        val = os.environ.get('NOTIFY_PREFS')
    return str(val).strip().lower() in ('1', 'true', 'yes', 'on') if val is not None else False


def _ensure_table():
    from models import db, NotificationPreference
    try:
        NotificationPreference.__table__.create(bind=db.engine, checkfirst=True)
    except Exception:
        db.session.rollback()


def wants(user_id, channel, default=True):
    """Whether a user wants notifications on a channel (default when no row)."""
    if not user_id:
        return default
    from models import db, NotificationPreference
    try:
        _ensure_table()
        row = NotificationPreference.query.filter_by(user_id=user_id, channel=channel).first()
        return default if row is None else bool(row.enabled)
    except Exception:
        db.session.rollback()
        return default


def set_pref(user_id, channel, enabled):
    if not user_id or channel not in CHANNELS:
        return
    from models import db, NotificationPreference
    try:
        _ensure_table()
        row = NotificationPreference.query.filter_by(user_id=user_id, channel=channel).first()
        if row is None:
            row = NotificationPreference(user_id=user_id, channel=channel, enabled=bool(enabled))
            db.session.add(row)
        else:
            row.enabled = bool(enabled)
        db.session.commit()
    except Exception:
        db.session.rollback()


def get_prefs(user_id):
    return {ch: wants(user_id, ch) for ch in CHANNELS}
