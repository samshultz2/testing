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
    # Honour a user's channel preference for the in-app bell (opt-out), but only
    # when the NOTIFY_PREFS flag is on — otherwise delivery is unchanged.
    try:
        if user_id:
            from utils.notify_prefs import flag_enabled, wants
            if flag_enabled() and not wants(user_id, 'inapp'):
                return None
    except Exception:
        pass
    try:
        n = Notification(title=(title or '')[:150], body=body or '', url=url,
                         user_id=user_id, role=role, category=category)
        db.session.add(n)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return None
    # Also fire a web push for the addressed user(s) so every bell notification
    # reaches the browser too. Best-effort, off the request thread, and a no-op
    # unless web push is configured — so it costs nothing when push is off.
    try:
        _push_fanout(title, body, url, user_id, role, category)
    except Exception:
        pass
    return n


def _push_targets(user_id, role):
    """The user ids a notification should web-push to: the addressed user, or
    every active user carrying the broadcast role."""
    if user_id:
        return [user_id]
    if role:
        try:
            from models import User
            return [u.id for u in User.query.filter_by(role=role, is_active=True).all()]
        except Exception:
            from models import db
            db.session.rollback()
    return []


def _push_allowed(user_id, category='info'):
    """Push is on by default, but a user's master push opt-out and per-category
    (topic) toggle are ALWAYS honoured — independent of the NOTIFY_PREFS flag.
    They're pure opt-outs (defaults push everything), so respecting them can never
    suppress a notification the user didn't ask to mute."""
    try:
        from utils.notify_prefs import wants, topic_for_category
        if not wants(user_id, 'push', default=True):
            return False
        topic = topic_for_category(category)
        if not wants(user_id, 'push:' + topic, default=True):
            return False
    except Exception:
        pass
    return True


def _push_fanout(title, body, url, user_id, role, category='info'):
    from utils import webpush
    if not webpush.is_configured():
        return
    targets = [uid for uid in _push_targets(user_id, role)
               if _push_allowed(uid, category)]
    if targets:
        webpush.push_to_users(targets, title or '', body or '', url)


def deliver_to_user(user_id, title, body='', url=None, *, category='info',
                    email_subject=None):
    """Fan a notification out to a user across the channels they've enabled.

    In-app (the bell) is always attempted and honours the user's opt-out, and web
    push rides along with it (handled inside notify()). Email and SMS are opt-in
    and only fire when the NOTIFY_PREFS flag is on, the user enabled that channel,
    the channel is configured, and the user has an address/number. Best-effort — a
    failure on one channel never blocks another, and nothing raises. Returns a
    dict of which channels were used.
    """
    used = {'inapp': False, 'email': False, 'sms': False, 'push': False}
    n = notify(title, body, url, user_id=user_id, category=category)
    used['inapp'] = n is not None
    try:                               # push is fired by notify() alongside the bell
        from utils import webpush
        used['push'] = bool(n is not None and webpush.is_configured())
    except Exception:
        pass
    if not user_id:
        return used
    try:
        from utils.notify_prefs import flag_enabled, wants
        if not flag_enabled():
            return used
        from models import User
        user = db.session.get(User, user_id)
        if user is None:
            return used
        if wants(user_id, 'email') and getattr(user, 'email', None):
            from utils import mailer
            if mailer.is_configured():
                mailer.send_email_async(user.email, email_subject or title,
                                        body or title)
                used['email'] = True
        if wants(user_id, 'sms') and getattr(user, 'phone', None):
            from utils import sms_gateway
            if sms_gateway.is_configured():
                text = f'{title}\n{body}'.strip() if body else title
                ok, _info = sms_gateway.send_sms(user.phone, text)
                used['sms'] = bool(ok)
    except Exception:
        db.session.rollback()
    return used


def current_actor():
    """Display name of the acting user, or None when there is no user in context
    (a background job / scheduled tick). Used to stamp "who did it" on admin
    notifications automatically."""
    try:
        from utils.access_control import get_current_user, is_admin
        u = get_current_user()
        if u:
            return getattr(u, 'full_name', None) or getattr(u, 'username', None)
        if session.get('logged_in') and is_admin():
            return 'Administrator'
    except Exception:
        pass
    return None


def _with_actor(body):
    """Append '· by {actor}' to an admin-notification body when a real user is
    acting and it isn't already stamped — so every module's "someone did X"
    notification says WHO, without each call site passing it. No-op for background
    jobs (no actor) and for bodies already carrying a 'by' attribution."""
    body = body or ''
    if '· by ' in body or body.endswith(' by system'):
        return body
    a = current_actor()
    return f'{body} · by {a}' if a else body


def notify_admins(title, body='', url=None, category='info'):
    """Broadcast to every admin (one row, matched by role at read time). The acting
    user is stamped on automatically (see _with_actor)."""
    return notify(title, _with_actor(body), url, role='admin', category=category)


def notify_branch_admins(title, body='', url=None, *, branch_id=None, category='info'):
    """Notify the admins responsible for one branch: admins scoped to that branch
    plus every central/super admin (who oversee all branches). Falls back to a
    role broadcast when no branch is given. Creates one row per recipient admin
    (so it can be branch-targeted, unlike the role broadcast). Best-effort."""
    if not branch_id:
        return notify_admins(title, body, url, category=category)
    body = _with_actor(body)
    try:
        from models import User
        admins = User.query.filter(
            User.role.in_(['admin', 'super_admin']), User.is_active.is_(True),
            or_(User.role == 'super_admin', User.scope == 'central',
                User.branch_id == branch_id)).all()
        last = None
        for u in admins:
            last = notify(title, body, url, user_id=u.id, category=category)
        return last
    except Exception:
        db.session.rollback()
        return None


_STUDENT_CHANGE_TITLES = {
    'create': 'Student added',
    'update': 'Student updated',
    'delete': 'Student removed',
    'import': 'Students imported',
    'bulk_delete': 'Students deleted',
}


def notify_student_change(action, *, student=None, detail='', changes='', actor='', url=None):
    """Bell admins when a student record changes — with detail.

    ``action`` is one of create/update/delete/import/bulk_delete. When a
    ``student`` is given, the body names WHO ("Name (ID)"); ``changes`` adds WHAT
    changed (a "Field: old → new" summary) and ``actor`` adds WHO did it, so an
    update reads e.g. *"John Doe (STU00007) — JAMB target: (empty) → 250 · by
    Mrs Bello"*. Best-effort — never breaks the triggering action.
    """
    from utils import automations
    if not automations.is_enabled('student_change'):
        return None
    title = _STUDENT_CHANGE_TITLES.get(action, 'Student change')
    who = ''
    if student is not None:
        name = getattr(student, 'full_name', '') or ''
        sid = getattr(student, 'student_id', '') or ''
        who = f'{name} ({sid})'.strip()
    # Assemble the body: whose record — what changed · by whom.
    body = detail or who
    if changes:
        body = f'{who} — {changes}' if who else changes
    if actor:
        body = f'{body} · by {actor}' if body else f'by {actor}'
    return notify_admins(title, body=body, url=url, category='student')


_STAFF_CHANGE_TITLES = {
    'create': 'Staff added',
    'update': 'Staff updated',
    'delete': 'Staff removed',
}


def notify_staff_change(action, *, staff=None, detail='', changes='', actor='', url=None,
                        branch_id=None):
    """Bell admins when a staff record changes — with detail, mirroring
    ``notify_student_change``.

    ``action`` is create/update/delete. When ``staff`` is given the body names
    WHO ("Name (ID)"); ``changes`` adds WHAT changed and ``actor`` adds WHO did
    it, so an update reads e.g. *"Bello Musa (STF007) — Designation: "Teacher" →
    "HOD" · by Mrs Bello"*. Branch-scoped when a ``branch_id`` is given.
    Best-effort — never breaks the triggering action."""
    from utils import automations
    if not automations.is_enabled('staff_change'):
        return None
    title = _STAFF_CHANGE_TITLES.get(action, 'Staff change')
    who = ''
    if staff is not None:
        name = getattr(staff, 'full_name', '') or ''
        sid = getattr(staff, 'staff_id', '') or ''
        who = f'{name} ({sid})'.strip()
    body = detail or who
    if changes:
        body = f'{who} — {changes}' if who else changes
    if actor:
        body = f'{body} · by {actor}' if body else f'by {actor}'
    return notify_branch_admins(title, body=body, url=url, branch_id=branch_id,
                                category='staff')


def actor_label(default='an administrator'):
    """Display name of the acting user for a notification body (falls back for the
    legacy password admin). Best-effort."""
    try:
        from utils.access_control import get_current_user
        u = get_current_user()
        if u:
            return (getattr(u, 'full_name', None) or getattr(u, 'username', None) or default)
    except Exception:
        pass
    return default


def notify_attendance_marked(*, class_label, date_label='', session_label='',
                             present=None, total=None, marked_by='', url=None):
    """Bell admins that a class register was marked.

    Best-effort like all notifications — never breaks the save that triggered it.
    """
    title = f'Register marked: {class_label}'.strip()
    if date_label:
        title += f' — {date_label}'
    bits = []
    if present is not None and total is not None:
        absent = max(total - present, 0)
        bits.append(f'{present}/{total} present')
        if absent:
            bits.append(f'{absent} absent')
    if session_label:
        bits.append(session_label)
    if marked_by:
        bits.append(f'by {marked_by}')
    return notify_admins(title, body=' · '.join(bits), url=url, category='attendance')


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


def _stamp_campaign_read(notification):
    """If this bell came from an in-app campaign, mark its campaign recipient read
    (read-receipt). Best-effort."""
    rid = getattr(notification, 'origin_recipient_id', None)
    if not rid:
        return
    from models import MessageRecipient
    from models.models import local_now
    rec = db.session.get(MessageRecipient, rid)
    if rec and rec.read_at is None:
        rec.read_at = local_now()


def mark_read(user_id, role, notification_id):
    n = _scope(user_id, role).filter(Notification.id == notification_id).first()
    if n and not n.is_read:
        n.is_read = True
        _stamp_campaign_read(n)
        db.session.commit()
    return n is not None


def mark_all_read(user_id, role):
    rows = _scope(user_id, role).filter(Notification.is_read.is_(False)).all()
    for n in rows:
        n.is_read = True
        _stamp_campaign_read(n)
    if rows:
        db.session.commit()
    return len(rows)
