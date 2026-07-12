"""Active-session / device tracking for signed-in users.

One :class:`UserSession` row is created per login, keyed by a random ``sid``
kept in the signed session cookie. The per-request guard
(``enforce_session_version``) checks the row still exists and isn't revoked, so
a user (or admin) can sign a specific device out and it takes effect on that
device's next request. A persistent ``device_id`` cookie groups repeat logins
from the same browser and backs the "trusted device" flag.
"""
from __future__ import annotations

import re
import secrets

DEVICE_COOKIE = 'edu_device'          # long-lived, identifies the browser
_SEEN_THROTTLE = 300                    # seconds between last_seen DB writes


def new_sid():
    return secrets.token_hex(24)


def device_label(user_agent: str) -> str:
    """A short, friendly device label from a User-Agent string."""
    ua = user_agent or ''
    browser = next((b for b in ('Edg', 'OPR', 'Opera', 'Chrome', 'Firefox',
                                'Safari') if b in ua), 'Browser')
    browser = {'Edg': 'Edge', 'OPR': 'Opera'}.get(browser, browser)
    if 'Chrome' in ua and browser == 'Safari':
        browser = 'Chrome'
    os = ('Android' if 'Android' in ua else 'iPhone' if 'iPhone' in ua
          else 'iPad' if 'iPad' in ua else 'Windows' if 'Windows' in ua
          else 'Mac' if 'Macintosh' in ua or 'Mac OS' in ua else 'Linux' if 'Linux' in ua
          else 'device')
    return f'{browser} on {os}'


def start_session(user, *, sid, device_id, user_agent, ip, trusted=False):
    """Record a new active session for ``user``. Caller commits."""
    from models import db, UserSession
    row = UserSession(user_id=user.id, sid=sid, device_id=device_id,
                      device_label=device_label(user_agent),
                      user_agent=(user_agent or '')[:300], ip=(ip or '')[:45],
                      trusted=bool(trusted))
    db.session.add(row)
    # Keep the table tidy: drop this user's oldest revoked rows beyond a cap.
    try:
        old = (UserSession.query.filter_by(user_id=user.id, revoked=True)
               .order_by(UserSession.last_seen.desc()).offset(20).all())
        for r in old:
            db.session.delete(r)
    except Exception:
        pass
    return row


def touch(sid):
    """Throttled last_seen update for the current session's row (best-effort)."""
    from flask import session
    import time
    from models import db, UserSession
    now = time.time()
    if now - (session.get('_sid_seen') or 0) < _SEEN_THROTTLE:
        return
    session['_sid_seen'] = now
    try:
        from models.models import local_now
        UserSession.query.filter_by(sid=sid).update({'last_seen': local_now()})
        db.session.commit()
    except Exception:
        db.session.rollback()


def is_live(sid) -> bool:
    """True if the session row exists and is not revoked."""
    from models import UserSession
    row = UserSession.query.filter_by(sid=sid).first()
    return bool(row and not row.revoked)


def device_is_trusted(user_id, device_id) -> bool:
    """True if this browser (device_id) was marked "trusted" — used to skip the
    2FA step on a device the user vouched for. Trust survives a normal logout
    (the row is revoked but keeps ``trusted=True``); it is cleared only when the
    user explicitly signs the device out from Active devices, which also flips
    ``trusted`` off, so revoked rows are intentionally still considered here."""
    if not device_id:
        return False
    from models import UserSession
    return UserSession.query.filter_by(
        user_id=user_id, device_id=device_id, trusted=True).first() is not None


def is_new_device(user_id, device_id) -> bool:
    """True when this browser has never been seen for the user AND the user has
    signed in before (so we alert on a genuinely new device, not first login)."""
    if not device_id:
        return False
    from models import UserSession
    seen_here = UserSession.query.filter_by(user_id=user_id, device_id=device_id).first()
    if seen_here:
        return False
    return UserSession.query.filter_by(user_id=user_id).first() is not None


def alert_new_device(user, user_agent, ip):
    """Best-effort email + in-app alert that the account was accessed from a new
    device — the pragmatic form of "verify suspicious logins". Never raises."""
    label = device_label(user_agent)
    try:
        from utils.notify import notify
        notify('New sign-in to your account',
               f'Your account was just signed in on a new device ({label}, IP {ip or "unknown"}). '
               f'If this was not you, change your password and review your active devices.',
               url='/account/sessions', user_id=user.id, category='warning')
    except Exception:
        pass
    try:
        from utils import mailer
        if user.email and mailer.is_configured():
            mailer.send_email(user.email, 'New sign-in to your EduSyncra account',
                              f'Hello {user.full_name or user.username},\n\n'
                              f'Your account was just accessed from a new device:\n'
                              f'  Device: {label}\n  IP: {ip or "unknown"}\n\n'
                              f'If this was you, no action is needed. If not, please change your '
                              f'password immediately and sign out other devices from '
                              f'My profile → Active devices.\n')
    except Exception:
        pass


def revoke(user_id, session_row_id) -> bool:
    """Revoke one of the user's own sessions. Returns True if a row changed."""
    from models import db, UserSession
    row = UserSession.query.filter_by(id=session_row_id, user_id=user_id).first()
    if not row or row.revoked:
        return False
    row.revoked = True
    # Explicitly signing a device out also un-trusts every session from that
    # browser, so it must pass 2FA again on the next sign-in.
    if row.device_id:
        UserSession.query.filter_by(user_id=user_id, device_id=row.device_id).update(
            {'trusted': False}, synchronize_session=False)
    db.session.commit()
    return True


def revoke_others(user, keep_sid):
    """Revoke every active session for ``user`` except ``keep_sid``. Returns count."""
    from models import db, UserSession
    n = (UserSession.query.filter(UserSession.user_id == user.id,
                                  UserSession.sid != keep_sid,
                                  UserSession.revoked.is_(False))
         .update({'revoked': True}, synchronize_session=False))
    # Un-trust every OTHER browser so signed-out devices must pass 2FA again.
    keep_device = None
    keep_row = UserSession.query.filter_by(sid=keep_sid).first()
    if keep_row:
        keep_device = keep_row.device_id
    q = UserSession.query.filter(UserSession.user_id == user.id, UserSession.trusted.is_(True))
    if keep_device:
        q = q.filter(UserSession.device_id != keep_device)
    q.update({'trusted': False}, synchronize_session=False)
    db.session.commit()
    return n


def list_for(user_id):
    """Active (non-revoked) sessions for a user, most-recent first."""
    from models import UserSession
    return (UserSession.query.filter_by(user_id=user_id, revoked=False)
            .order_by(UserSession.last_seen.desc()).all())
