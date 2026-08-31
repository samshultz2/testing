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
        assert notify_prefs.wants(uid, 'inapp') is True     # in-app: opt-out (on by default)
        assert notify_prefs.wants(uid, 'email') is False    # email: opt-in (off by default)
        assert notify_prefs.wants(uid, 'sms') is False      # sms:   opt-in (off by default)
        notify_prefs.set_pref(uid, 'inapp', False)
        notify_prefs.set_pref(uid, 'email', True)
        assert notify_prefs.wants(uid, 'inapp') is False
        assert notify_prefs.wants(uid, 'email') is True     # explicit row overrides default
        prefs = notify_prefs.get_prefs(uid)
        assert prefs['inapp'] is False and prefs['email'] is True and prefs['sms'] is False


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


def test_deliver_to_user_fans_out_by_preference(app, monkeypatch):
    """deliver_to_user() sends in-app always, and email/SMS only when the flag is
    on, the user opted in, the channel is configured, and the user has an
    address/number."""
    from utils import notify as notify_mod
    from utils import notify_prefs, mailer, sms_gateway
    from models import db, User
    with app.app_context():
        u = User(username='deliverme', full_name='Deliver Me', role='staff',
                 scope='branch', email='deliver@example.com', phone='08030000000')
        u.set_password('CorrectHorse9'); u.is_active = True
        db.session.add(u); db.session.commit()
        uid = u.id

        sent = {'email': [], 'sms': []}
        monkeypatch.setattr(mailer, 'is_configured', lambda: True)
        monkeypatch.setattr(mailer, 'send_email_async',
                            lambda to, subj, body, html=None: sent['email'].append(to))
        monkeypatch.setattr(sms_gateway, 'is_configured', lambda cfg=None: True)

        def _fake_sms(phone, msg, cfg=None):
            sent['sms'].append(phone)
            return True, 'msg-id'
        monkeypatch.setattr(sms_gateway, 'send_sms', _fake_sms)

        # Flag OFF → only in-app, no email/SMS regardless of prefs.
        monkeypatch.setattr(notify_prefs, 'flag_enabled', lambda app=None: False)
        used = notify_mod.deliver_to_user(uid, 'Hi', 'body')
        assert used['inapp'] is True and used['email'] is False and used['sms'] is False
        assert sent == {'email': [], 'sms': []}

        # Flag ON but email/SMS still opt-in (default off) → still no email/SMS.
        monkeypatch.setattr(notify_prefs, 'flag_enabled', lambda app=None: True)
        used = notify_mod.deliver_to_user(uid, 'Hi', 'body')
        assert used['email'] is False and used['sms'] is False

        # Opt into email + SMS → both fire.
        notify_prefs.set_pref(uid, 'email', True)
        notify_prefs.set_pref(uid, 'sms', True)
        used = notify_mod.deliver_to_user(uid, 'Alert', 'details')
        assert used['email'] is True and used['sms'] is True
        assert sent['email'] == ['deliver@example.com'] and sent['sms'] == ['08030000000']


def test_push_topic_mapping_and_defaults(app):
    from utils import notify_prefs as np
    assert np.topic_for_category('attendance') == 'attendance'
    assert np.topic_for_category('warning') == 'alerts'
    assert np.topic_for_category('info') == 'general'      # unknown → general
    uid = 987010
    with app.app_context():
        assert np.push_topic_enabled(uid, 'attendance') is True   # opt-out default
        np.set_push_topic(uid, 'attendance', False)
        assert np.push_topic_enabled(uid, 'attendance') is False
        topics = np.get_push_topics(uid)
        assert topics['attendance'] is False and topics['finance'] is True


def test_notify_push_respects_category_toggle_without_flag(app, monkeypatch):
    """A muted push category is skipped while others still push — and this applies
    even with the NOTIFY_PREFS flag OFF (push opt-outs are always honoured)."""
    from utils import notify as notify_mod
    from utils import notify_prefs, webpush
    from models import db, User
    with app.app_context():
        u = User(username='pushcat_user', full_name='Cat User', role='staff', scope='branch')
        u.set_password('CorrectHorse9'); u.is_active = True
        db.session.add(u); db.session.commit()
        uid = u.id

        pushed = []
        monkeypatch.setattr(webpush, 'is_configured', lambda app=None: True)
        monkeypatch.setattr(webpush, 'push_to_users',
                            lambda user_ids, title, body='', url=None, app=None: pushed.append((list(user_ids), title)))
        # Flag OFF (the default) — push preferences must still apply.
        monkeypatch.setattr(notify_prefs, 'flag_enabled', lambda app=None: False)

        notify_prefs.set_push_topic(uid, 'attendance', False)   # mute attendance push
        notify_mod.notify('Register marked', user_id=uid, category='attendance')
        assert pushed == []                                     # muted → no push, no flag needed

        notify_mod.notify('Fee paid', user_id=uid, category='finance')
        assert pushed and pushed[0][0] == [uid]                 # other category still pushes

        # Master push opt-out is honoured without the flag too.
        pushed.clear()
        notify_prefs.set_pref(uid, 'push', False)
        notify_mod.notify('Anything', user_id=uid, category='general')
        assert pushed == []


def test_notification_prefs_page_loads(app):
    c = _admin(app)
    r = c.get('/settings/notifications')
    assert r.status_code == 200 and 'Notification Preferences' in r.get_data(as_text=True)
