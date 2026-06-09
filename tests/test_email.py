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
        assert u.must_change_password is True
        assert not u.check_password('secret123')   # password was reset
    assert sent and sent[0][0] == 'm@example.com'


def test_forgot_password_unknown_is_generic(app, monkeypatch):
    from utils import mailer
    sent = []
    monkeypatch.setattr(mailer, 'is_configured', lambda: True)
    monkeypatch.setattr(mailer, 'send_email', lambda to, s, b: sent.append(to) or True)
    c = app.test_client()
    r = c.post('/forgot-password', data={'identifier': 'nobody-here', '_csrf_token': _tok(c)},
               follow_redirects=True)
    assert r.status_code == 200 and not sent   # no email, no account disclosure
