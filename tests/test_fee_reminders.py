"""Scheduled fee reminders: opt-in, idempotent, queues a Draft (never auto-sends)."""
from datetime import datetime

from models import db, AcademicSession, Term, Student, ParentContact, Message
from utils import comms, reminders


def _active_term(app):
    sess = AcademicSession.query.filter_by(is_active=True).first()
    if not sess:
        sess = AcademicSession(name='FRSess', is_active=True)
        db.session.add(sess); db.session.flush()
    term = Term.query.filter_by(is_active=True).first()
    if not term:
        term = Term(session_id=sess.id, term_number=1, name='First Term', is_active=True)
        db.session.add(term); db.session.flush()
    db.session.commit()
    return term


def _defaulter(app):
    s = Student.query.filter_by(student_id='FRD1').first()
    if not s:
        s = Student(student_id='FRD1', first_name='Owed', surname='Money',
                    gender='Male', is_active=True)
        db.session.add(s); db.session.flush()
        db.session.add(ParentContact(student_id=s.id, name='Mum Money',
                                     phone_number='08055556666', is_primary=True))
        db.session.commit()
    return s


def _stub_defaulters(app, monkeypatch, term):
    """Make resolve_audience('defaulters', ...) return one reachable parent."""
    with app.app_context():
        student = _defaulter(app)
        target = [{'student': student, 'parent_name': 'Mum Money',
                   'phone': '08055556666', 'balance': 5000.0}]
    monkeypatch.setattr(comms, 'resolve_audience', lambda *a, **k: list(target))


def test_disabled_by_default(app):
    # FEE_REMINDER_ENABLED is off in the test config -> no work, no error.
    assert reminders.run_fee_reminders(app)['status'] == 'disabled'


def test_dry_run_reports_without_creating(app, monkeypatch):
    with app.app_context():
        term = _active_term(app)
        term_id = term.id
        before = Message.query.filter(Message.title.ilike('Fee reminder:%')).count()
    monkeypatch.setattr('utils.helpers.get_active_term',
                        lambda: db.session.get(Term, term_id))
    _stub_defaulters(app, monkeypatch, None)
    res = reminders.run_fee_reminders(app, dry_run=True)
    assert res['status'] == 'dry-run' and res['reachable'] == 1
    with app.app_context():
        after = Message.query.filter(Message.title.ilike('Fee reminder:%')).count()
    assert after == before          # nothing created on a dry run


def test_force_creates_draft_and_bells_admins(app, monkeypatch):
    with app.app_context():
        term = _active_term(app)
        term_id = term.id
    monkeypatch.setattr('utils.helpers.get_active_term',
                        lambda: db.session.get(Term, term_id))
    _stub_defaulters(app, monkeypatch, None)
    res = reminders.run_fee_reminders(app, force=True)
    assert res['status'] == 'created' and res['recipients'] == 1
    with app.app_context():
        msg = db.session.get(Message, res['message_id'])
        assert msg.status == 'Draft'           # queued for review, not sent
        assert msg.title.startswith('Fee reminder:')
        from models import Notification
        assert Notification.query.filter_by(title='Fee reminder ready').count() >= 1


def test_recent_draft_is_not_duplicated(app, monkeypatch):
    with app.app_context():
        term = _active_term(app)
        term_id = term.id
        # A reminder draft already exists for this term, created just now.
        db.session.add(Message(title=f'Fee reminder: {term.full_name}',
                               body='x', channel='SMS', audience='defaulters',
                               term_id=term.id, status='Draft',
                               created_at=datetime.now(), recipient_count=1))
        db.session.commit()
    monkeypatch.setattr('utils.helpers.get_active_term',
                        lambda: db.session.get(Term, term_id))
    _stub_defaulters(app, monkeypatch, None)
    res = reminders.run_fee_reminders(app, force=False)
    # Opt-in gate is bypassed once a run is in progress via force? No: force=False
    # and disabled -> 'disabled'. Enable it to reach the interval guard.
    from config import Config
    monkeypatch.setattr(Config, 'FEE_REMINDER_ENABLED', True, raising=False)
    res = reminders.run_fee_reminders(app, force=False)
    assert res['status'] == 'recent-exists'
