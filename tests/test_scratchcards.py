"""Tests for the scratch-card result checker."""
import re

from config import Config
from models import db, ScratchCard, Term, AcademicSession, Student
from tests.conftest import login_token


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def _page_token(client):
    html = client.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def _published_term(app):
    with app.app_context():
        sess = AcademicSession.query.first()
        if not sess:
            sess = AcademicSession(name='2025/2026', is_active=True)
            db.session.add(sess)
            db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='First Term',
                    is_active=True, results_published=True)
        db.session.add(term)
        db.session.commit()
        return term.id


def _student(app, sid='STU90001'):
    with app.app_context():
        s = Student.query.filter_by(student_id=sid).first()
        if not s:
            s = Student(student_id=sid, first_name='Test', surname='Student',
                    gender='Male', is_active=True)
            db.session.add(s)
            db.session.commit()
        return s.id


def test_generate_creates_cards(app):
    client = _admin(app)
    before = None
    with app.app_context():
        before = ScratchCard.query.count()
    client.post('/scratch-cards/generate',
                data={'count': 4, 'max_uses': 3, '_csrf_token': _page_token(client)},
                follow_redirects=True)
    with app.app_context():
        assert ScratchCard.query.count() == before + 4


def test_invalid_pin_rejected(app):
    _published_term(app)
    _student(app, 'STU90002')
    client = app.test_client()
    token = login_token(client)  # reuse the public form's csrf
    # The public form provides its own token; fetch it.
    html = client.get('/check-result/').get_data(as_text=True)
    m = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', html)
    tok = m.group(1)
    resp = client.post('/check-result/',
                       data={'student_id': 'STU90002', 'pin': 'WRONGPIN0000',
                             '_csrf_token': tok}, follow_redirects=True)
    assert b'Student ID or card PIN is incorrect' in resp.data


def test_valid_card_not_consumed_without_result(app):
    """A valid card on a published term with no enrolment must NOT lose a use."""
    term_id = _published_term(app)
    _student(app, 'STU90003')
    with app.app_context():
        card = ScratchCard.generate_unique(max_uses=5, term_id=term_id)
        db.session.add(card)
        db.session.commit()
        pin = card.pin

    client = app.test_client()
    html = client.get('/check-result/').get_data(as_text=True)
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', html).group(1)
    resp = client.post('/check-result/',
                       data={'student_id': 'STU90003', 'pin': pin, '_csrf_token': tok},
                       follow_redirects=True)
    assert b'No result found' in resp.data
    with app.app_context():
        c = ScratchCard.query.filter_by(pin=pin).first()
        assert c.used_count == 0  # not consumed on a failed lookup


def test_bound_card_rejects_other_student(app):
    """Security: once a card is bound to a student it cannot read another
    student's result — this is what the trust-on-first-use binding guarantees,
    so a valid PIN can't walk the (guessable, sequential) Student-ID range."""
    _published_term(app)
    bound = _student(app, 'STU90020')
    _student(app, 'STU90021')
    with app.app_context():
        card = ScratchCard.generate_unique(max_uses=5, student_id=bound)
        db.session.add(card)
        db.session.commit()
        pin = card.pin

    client = app.test_client()
    html = client.get('/check-result/').get_data(as_text=True)
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', html).group(1)
    resp = client.post('/check-result/',
                       data={'student_id': 'STU90021', 'pin': pin, '_csrf_token': tok},
                       follow_redirects=True)
    assert b'Student ID or card PIN is incorrect' in resp.data
    with app.app_context():
        assert ScratchCard.query.filter_by(pin=pin).first().used_count == 0
