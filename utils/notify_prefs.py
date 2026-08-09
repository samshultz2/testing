"""Per-user notification-channel preferences (feature-flagged via NOTIFY_PREFS).

Opt-out model: no row means the channel is on. Enforcement is gated by the flag,
and today only the in-app channel is enforced (in utils.notify) — the safest
channel to suppress. Email/SMS/push preferences are captured for future use.
"""
import os

CHANNELS = ('inapp', 'email', 'sms', 'push')
CHANNEL_LABELS = {'inapp': 'In-app (bell)', 'email': 'Email', 'sms': 'SMS', 'push': 'Web push'}

# Per-channel default when the user has no explicit row. The in-app bell and web
# push are opt-out (on unless turned off) — both are free, so every bell
# notification also reaches the browser by default. Email and SMS stay opt-in
# (off unless turned on): SMS costs money and email is easy to over-send.
CHANNEL_DEFAULTS = {'inapp': True, 'email': False, 'sms': False, 'push': True}


def default_for(channel):
    return CHANNEL_DEFAULTS.get(channel, True)


# Push topics: raw notification categories are bucketed into this short list so a
# user gets a meaningful set of per-category push toggles rather than one per
# freeform category string. Each topic is opt-out (pushes unless turned off).
PUSH_TOPICS = ('attendance', 'student', 'finance', 'admissions', 'alerts', 'general')
PUSH_TOPIC_LABELS = {
    'attendance': 'Attendance', 'student': 'Student records',
    'finance': 'Finance & fees', 'admissions': 'Admissions',
    'alerts': 'Alerts & warnings', 'general': 'General',
}
_CATEGORY_TO_TOPIC = {
    'attendance': 'attendance', 'student': 'student', 'finance': 'finance',
    'admissions': 'admissions', 'warning': 'alerts', 'error': 'alerts',
}


def topic_for_category(category):
    """Map a raw notification category onto a push topic (default 'general')."""
    return _CATEGORY_TO_TOPIC.get((category or '').strip().lower(), 'general')


def push_topic_enabled(user_id, topic):
    """Whether a user wants push for a topic (opt-out — on unless turned off)."""
    return wants(user_id, 'push:' + topic, default=True)


def set_push_topic(user_id, topic, enabled):
    if topic in PUSH_TOPICS:
        set_pref(user_id, 'push:' + topic, enabled)


def get_push_topics(user_id):
    return {t: wants(user_id, 'push:' + t, default=True) for t in PUSH_TOPICS}


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


def wants(user_id, channel, default=None):
    """Whether a user wants notifications on a channel. With no stored row the
    per-channel default applies (in-app opt-out, email/SMS/push opt-in), unless
    an explicit ``default`` is passed."""
    if default is None:
        default = default_for(channel)
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
    if not user_id or (channel not in CHANNELS and not channel.startswith('push:')):
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
