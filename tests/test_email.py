"""Email channel: disabled by default; forgot-password resets via email."""
import re
from models import db, User


def _tok(c):
    return re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                     c.get('/forgot-password').get_data(as_text=True)).group(1)


def test_email_disabled_by_default(app):
    from utils import mailer
    assert mailer.is_configured() is False


def test_forgot_password_resets_and_emails(app, monkeypatch):
    from utils import mailer
    with app.app_context():
        if not User.query.filter_by(username='mailuser').first():
            u = User(username='mailuser', email='m@example.com', role='staff',
                     scope='central', full_name='Mail User')
            u.set_password('secret123'); db.session.add(u); db.session.commit()
    sent = []
    monkeypatch.setattr(mailer, 'is_configured', lambda: True)
    monkeypatch.setattr(mailer, 'send_email', lambda to, s, b: sent.append((to, s, b)) or True)
    c = app.test_client()
    c.post('/forgot-password', data={'identifier': 'mailuser', '_csrf_token': _tok(c)},
           follow_redirects=True)
    with app.app_context():
        u = User.query.filter_by(username='mailuser').first()
        # New flow: a single-use reset LINK is emailed; the live password is NOT
        # changed until the user follows the link and sets a new one.
        assert u.check_password('secret123')        # still valid
        assert u.reset_token_hash and u.reset_token_expires
    assert sent and sent[0][0] == 'm@example.com'
    body = sent[0][2]
    assert '/reset-password/' in body               # a link, not a password
    path = re.search(r'/reset-password/\S+', body).group(0).rstrip('.')
    c.post(path, data={'password': 'NewPass123', 'confirm': 'NewPass123',
                       '_csrf_token': _tok(c)}, follow_redirects=True)
    with app.app_context():
        u = User.query.filter_by(username='mailuser').first()
        assert u.check_password('NewPass123')        # now changed
        assert not u.check_password('secret123')
        assert u.reset_token_hash is None            # token consumed (single use)


class _FakeSMTP:
    """Captures the message a send would produce, without touching the network."""
    sent = []

    def __init__(self, host, port, timeout=20):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        pass

    def login(self, user, pwd):
        pass

    def send_message(self, msg, to_addrs=None):
        _FakeSMTP.sent.append((msg, to_addrs))


def _enable_smtp(monkeypatch):
    from config import Config
    monkeypatch.setattr(Config, 'SMTP_HOST', 'smtp.test', raising=False)
    monkeypatch.setattr(Config, 'SMTP_FROM', 'no-reply@test', raising=False)
    _FakeSMTP.sent = []
    import utils.mailer as mailer
    monkeypatch.setattr(mailer.smtplib, 'SMTP', _FakeSMTP)


def test_send_email_disabled_returns_false(app):
    from utils import mailer
    # No SMTP config in tests -> disabled, returns False, never raises.
    assert mailer.send_email('a@b.com', 'Hi', 'body') is False


def test_send_email_html_and_multiple_recipients(app, monkeypatch):
    from utils import mailer
    _enable_smtp(monkeypatch)
    ok = mailer.send_email(['a@b.com', 'a@b.com', 'c@d.com'], 'Subj',
                           'plain body', html='<b>rich</b>')
    assert ok is True
    msg, to_addrs = _FakeSMTP.sent[0]
    assert to_addrs == ['a@b.com', 'c@d.com']           # de-duplicated
    assert msg['Subject'] == 'Subj'
    # multipart/alternative: both text and html parts present
    types = {p.get_content_type() for p in msg.walk()}
    assert 'text/plain' in types and 'text/html' in types


def test_branded_html_escapes_and_links(app):
    from utils import mailer
    html = mailer.branded_html('Results <ready>', ['Hi & welcome'],
                               button={'label': 'View', 'url': 'https://x/y'})
    assert 'Results &lt;ready&gt;' in html      # heading escaped
    assert 'Hi &amp; welcome' in html           # paragraph escaped
    assert 'https://x/y' in html and 'View' in html


def test_forgot_password_unknown_is_generic(app, monkeypatch):
    from utils import mailer
    sent = []
    monkeypatch.setattr(mailer, 'is_configured', lambda: True)
    monkeypatch.setattr(mailer, 'send_email', lambda to, s, b: sent.append(to) or True)
    c = app.test_client()
    r = c.post('/forgot-password', data={'identifier': 'nobody-here', '_csrf_token': _tok(c)},
               follow_redirects=True)
    assert r.status_code == 200 and not sent   # no email, no account disclosure
