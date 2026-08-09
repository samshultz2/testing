"""Web Push (VAPID) — server side (roadmap #8, flag/infra-gated).

Sending requires a VAPID key pair (WEBPUSH_VAPID_PUBLIC_KEY /
WEBPUSH_VAPID_PRIVATE_KEY) and the ``pywebpush`` package. Both are optional: when
either is missing every send is a safe no-op, so the app runs unchanged until an
operator provisions keys and installs the dependency. Subscriptions can still be
stored regardless, so turning the feature on later just works.

Generate a key pair once (kept out of the repo):
    pip install py-vapid
    vapid --gen           # writes private_key.pem / public_key.pem
    vapid --applicationServerKey    # the base64url public key for the browser
"""
import json
import os


def _cfg(app, key):
    try:
        from flask import current_app
        a = app or current_app
        val = a.config.get(key)
    except Exception:
        val = None
    if val is None:
        val = os.environ.get(key)
    return val


def public_key(app=None):
    """The base64url application server key the browser needs to subscribe, or
    None when web push isn't configured."""
    return _cfg(app, 'WEBPUSH_VAPID_PUBLIC_KEY')


def is_configured(app=None):
    """True only when both VAPID keys and a contact email are present."""
    return bool(public_key(app) and _cfg(app, 'WEBPUSH_VAPID_PRIVATE_KEY')
                and _cfg(app, 'WEBPUSH_VAPID_CLAIMS_EMAIL'))


def _ensure_table():
    from models import db, PushSubscription
    try:
        PushSubscription.__table__.create(bind=db.engine, checkfirst=True)
    except Exception:
        db.session.rollback()


def save_subscription(user_id, sub, user_agent=None):
    """Upsert a browser subscription (``{endpoint, keys:{p256dh, auth}}``) for a
    user. Returns the row, or None on bad input / error."""
    if not user_id or not isinstance(sub, dict):
        return None
    endpoint = sub.get('endpoint')
    keys = sub.get('keys') or {}
    p256dh, auth = keys.get('p256dh'), keys.get('auth')
    if not (endpoint and p256dh and auth):
        return None
    from models import db, PushSubscription
    try:
        _ensure_table()
        row = PushSubscription.query.filter_by(endpoint=endpoint).first()
        if row is None:
            row = PushSubscription(user_id=user_id, endpoint=endpoint)
            db.session.add(row)
        row.user_id = user_id
        row.p256dh, row.auth = p256dh, auth
        row.user_agent = (user_agent or '')[:255]
        db.session.commit()
        return row
    except Exception:
        db.session.rollback()
        return None


def delete_subscription(endpoint):
    if not endpoint:
        return False
    from models import db, PushSubscription
    try:
        _ensure_table()
        row = PushSubscription.query.filter_by(endpoint=endpoint).first()
        if row:
            db.session.delete(row)
            db.session.commit()
            return True
    except Exception:
        db.session.rollback()
    return False


def send_to_user(user_id, title, body='', url=None, app=None):
    """Push a notification to every subscription a user has. No-op (returns 0)
    when web push is unconfigured or ``pywebpush`` isn't installed. Prunes
    subscriptions the push service reports as gone (404/410). Best-effort."""
    if not user_id or not is_configured(app):
        return 0
    try:
        from pywebpush import webpush, WebPushException
    except Exception:
        return 0
    from models import db, PushSubscription
    try:
        _ensure_table()
        subs = PushSubscription.query.filter_by(user_id=user_id).all()
    except Exception:
        db.session.rollback()
        return 0
    payload = json.dumps({'title': title, 'body': body or '', 'url': url or '/'})
    claims = {'sub': f"mailto:{_cfg(app, 'WEBPUSH_VAPID_CLAIMS_EMAIL')}"}
    private = _cfg(app, 'WEBPUSH_VAPID_PRIVATE_KEY')
    sent = 0
    for s in subs:
        try:
            webpush(subscription_info=s.as_subscription_info(), data=payload,
                    vapid_private_key=private, vapid_claims=dict(claims))
            sent += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, 'response', None), 'status_code', None)
            if status in (404, 410):
                try:
                    db.session.delete(s)
                    db.session.commit()
                except Exception:
                    db.session.rollback()
        except Exception:
            pass
    return sent
