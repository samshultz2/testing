"""Web Push server side (roadmap #8) — gated by VAPID config, degrades to a safe
no-op when unconfigured, and stores/removes subscriptions regardless."""
from models import db, User, PushSubscription

_SUB = {'endpoint': 'https://push.example.com/ep-XYZ',
        'keys': {'p256dh': 'BPk_key_material_here', 'auth': 'auth_secret_here'}}


def _make_user(app, username):
    with app.app_context():
        u = User(username=username, full_name='Push User', role='staff',
                 scope='branch')
        u.set_password('CorrectHorse9'); u.is_active = True
        db.session.add(u); db.session.commit()
        return u.id, u.token_version


def test_unconfigured_send_is_noop(app):
    from utils import webpush
    with app.app_context():
        assert webpush.is_configured() is False
        assert webpush.public_key() is None
        uid, _tv = _make_user(app, 'push_noop')
        webpush.save_subscription(uid, _SUB)
        # No VAPID keys → send is a no-op (0 sent), never raises.
        assert webpush.send_to_user(uid, 'Hi', 'there') == 0


def test_save_and_delete_subscription(app):
    from utils import webpush
    with app.app_context():
        uid, _tv = _make_user(app, 'push_save')
        row = webpush.save_subscription(uid, _SUB, user_agent='pytest')
        assert row is not None and row.user_id == uid
        # Idempotent upsert on the same endpoint (no duplicate row).
        webpush.save_subscription(uid, _SUB)
        assert PushSubscription.query.filter_by(endpoint=_SUB['endpoint']).count() == 1
        # Bad input is rejected.
        assert webpush.save_subscription(uid, {'endpoint': 'x'}) is None
        assert webpush.delete_subscription(_SUB['endpoint']) is True
        assert PushSubscription.query.filter_by(endpoint=_SUB['endpoint']).first() is None


def test_public_key_endpoint_reports_disabled(app):
    from config import Config
    c = app.test_client()
    from tests.conftest import login_token
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    j = c.get('/api/push/public-key').get_json()
    assert j['enabled'] is False and j['key'] is None


def test_subscribe_endpoint_stores_for_logged_in_user(app):
    uid, tv = _make_user(app, 'push_sub_ep')
    c = app.test_client()
    with c.session_transaction() as s:
        s['logged_in'] = True
        s['user_id'] = uid
        s['role'] = 'staff'
        s['tv'] = tv                       # match token_version or the guard 401s
        s['_csrf_token'] = 'z' * 64
    r = c.post('/api/push/subscribe', json=_SUB, headers={'X-CSRFToken': 'z' * 64})
    assert r.status_code == 200 and r.get_json()['ok'] is True
    with app.app_context():
        assert PushSubscription.query.filter_by(user_id=uid).count() == 1
    # Unsubscribe removes it.
    r = c.post('/api/push/unsubscribe', json={'endpoint': _SUB['endpoint']},
               headers={'X-CSRFToken': 'z' * 64})
    assert r.status_code == 200 and r.get_json()['ok'] is True
