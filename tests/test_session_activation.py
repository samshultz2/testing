"""Activating a session at /academics/sessions switches the whole platform.

It must move both the active SESSION and the active TERM into the chosen session
(most pages scope by get_active_term), and clear the acting admin's time-travel
override so it can't mask the switch."""
from config import Config
from models import db, AcademicSession, Term
from tests.conftest import login_token, auth_csrf

_A = 'ACT 40/41'
_B = 'ACT 41/42'


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _mk(name):
    s = AcademicSession.query.filter_by(name=name).first() or AcademicSession(name=name, is_active=False)
    db.session.add(s); db.session.flush()
    for n in (1, 2, 3):
        if not Term.query.filter_by(session_id=s.id, term_number=n).first():
            db.session.add(Term(session_id=s.id, term_number=n, name=f'{name} T{n}', is_active=False))
    db.session.commit()
    return s.id


def test_activation_moves_session_and_term(app):
    with app.app_context():
        aid, bid = _mk(_A), _mk(_B)
    c = _admin(app)
    tok = auth_csrf(c)

    c.post(f'/academics/sessions/{aid}/activate', data={'_csrf_token': tok}, follow_redirects=True)
    with app.app_context():
        assert AcademicSession.query.filter_by(is_active=True).one().id == aid
        active_term = Term.query.filter_by(is_active=True).one()
        assert active_term.session_id == aid          # active TERM followed into A

    c.post(f'/academics/sessions/{bid}/activate', data={'_csrf_token': tok}, follow_redirects=True)
    with app.app_context():
        assert AcademicSession.query.filter_by(is_active=True).one().id == bid
        assert Term.query.filter_by(is_active=True).one().session_id == bid


def test_activation_clears_time_travel_override(app):
    with app.app_context():
        aid, bid = _mk(_A), _mk(_B)
    c = _admin(app)
    tok = auth_csrf(c)
    # start time-travelling to A
    c.post('/view-session', data={'_csrf_token': tok, 'session_id': aid}, follow_redirects=True)
    with c.session_transaction() as s:
        assert s.get('view_session_id') == aid
    # activating B must drop the override so the admin's view follows B
    c.post(f'/academics/sessions/{bid}/activate', data={'_csrf_token': tok}, follow_redirects=True)
    with c.session_transaction() as s:
        assert 'view_session_id' not in s


def test_active_term_follows_active_session_even_if_flag_is_stale(app):
    """Defensive: even if the is_active TERM flag still points at the old session
    (e.g. it was never moved), get_active_term() returns a term of the active
    session — so every term-scoped page follows the switch."""
    from utils.helpers import get_active_term, get_active_session
    with app.app_context():
        AcademicSession.query.update({AcademicSession.is_active: False}, synchronize_session=False)
        Term.query.update({Term.is_active: False}, synchronize_session=False)
        old = AcademicSession(name='STALE OLD', is_active=False)
        new = AcademicSession(name='STALE NEW', is_active=True)
        db.session.add_all([old, new]); db.session.flush()
        db.session.add(Term(session_id=old.id, term_number=3, name='old3', is_active=True))  # stale flag
        db.session.add(Term(session_id=new.id, term_number=1, name='new1', is_active=False))
        db.session.commit()
        new_id = new.id
        assert get_active_session().id == new_id
        assert get_active_term().session_id == new_id      # followed the active session
