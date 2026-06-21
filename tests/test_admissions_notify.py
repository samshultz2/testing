"""Admission decisions bell admins and email the parent (when an email exists)."""
from models import db, Applicant, Notification
from utils import admissions, mailer


def _applicant(app, **kw):
    with app.app_context():
        a = Applicant(first_name=kw.get('first_name', 'Lola'),
                      surname=kw.get('surname', 'Ade'),
                      status=kw.get('status', 'Screening'),
                      parent_name='Mrs Ade',
                      parent_email=kw.get('parent_email'))
        db.session.add(a); db.session.commit()
        return a.id


def _capture_email(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, 'is_configured', lambda: True)
    monkeypatch.setattr(mailer, 'send_email_async',
                        lambda to, s, b, html=None: sent.append((to, s, b, html)))
    return sent


def test_decision_bells_admins_and_emails_parent(app, monkeypatch):
    aid = _applicant(app, parent_email='mum@example.com')
    sent = _capture_email(monkeypatch)
    with app.app_context():
        a = db.session.get(Applicant, aid)
        a.status = 'Admitted'
        admissions.notify_decision(a)
        assert Notification.query.filter(
            Notification.title.ilike('Applicant admitted:%'),
            Notification.role == 'admin').count() >= 1
    assert sent and sent[0][0] == 'mum@example.com'
    assert 'admitted' in sent[0][1].lower()
    assert sent[0][3] is not None          # HTML body included


def test_non_decision_status_does_nothing(app, monkeypatch):
    aid = _applicant(app, parent_email='mum@example.com')
    sent = _capture_email(monkeypatch)
    with app.app_context():
        a = db.session.get(Applicant, aid)
        a.status = 'Screening'             # not a decision
        before = Notification.query.filter(
            Notification.title.ilike('Applicant %')).count()
        admissions.notify_decision(a)
        after = Notification.query.filter(
            Notification.title.ilike('Applicant %')).count()
    assert before == after and sent == []


def test_decision_without_parent_email_still_bells(app, monkeypatch):
    aid = _applicant(app, parent_email=None)
    sent = _capture_email(monkeypatch)
    with app.app_context():
        a = db.session.get(Applicant, aid)
        a.status = 'Rejected'
        admissions.notify_decision(a)
        assert Notification.query.filter(
            Notification.title.ilike('Applicant rejected:%')).count() >= 1
    assert sent == []                      # no email without an address
