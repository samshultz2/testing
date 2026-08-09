"""Per-user notification preferences (roadmap #3, flag-gated). Web-push proper
is infra-blocked (needs pywebpush + VAPID keys); this covers the in-app channel
preference and its enforcement gate."""
from config import Config


def _admin(app):
    from tests.conftest import login_token
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_prefs_default_and_set(app):
    from utils import notify_prefs
    uid = 987001
    with app.app_context():
        assert notify_prefs.wants(uid, 'inapp') is True     # opt-out: on by default
        notify_prefs.set_pref(uid, 'inapp', False)
        assert notify_prefs.wants(uid, 'inapp') is False
        assert notify_prefs.wants(uid, 'email') is True
        prefs = notify_prefs.get_prefs(uid)
        assert prefs['inapp'] is False and prefs['sms'] is True


def test_notify_honours_pref_only_when_flag_on(app, monkeypatch):
    from utils import notify_prefs
    from utils import notify as notify_mod
    uid = 987002
    with app.app_context():
        notify_prefs.set_pref(uid, 'inapp', False)
        # flag OFF → delivered regardless of preference (unchanged behaviour)
        monkeypatch.setattr(notify_prefs, 'flag_enabled', lambda app=None: False)
        assert notify_mod.notify('A', user_id=uid) is not None
        # flag ON + in-app disabled → suppressed
        monkeypatch.setattr(notify_prefs, 'flag_enabled', lambda app=None: True)
        assert notify_mod.notify('B', user_id=uid) is None
        # re-enable → delivered again
        notify_prefs.set_pref(uid, 'inapp', True)
        assert notify_mod.notify('C', user_id=uid) is not None
        # role broadcasts (no user_id) are never gated
        assert notify_mod.notify('D', role='admin') is not None


def test_notification_prefs_page_loads(app):
    c = _admin(app)
    r = c.get('/settings/notifications')
    assert r.status_code == 200 and 'Notification Preferences' in r.get_data(as_text=True)
