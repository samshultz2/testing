"""Admin per-user 'time-travel': view a past session's data without changing the
live session for everyone else."""
from config import Config
from models import db, AcademicSession
from tests.conftest import login_token, auth_csrf


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_admin_can_view_past_session(app):
    with app.app_context():
        live = AcademicSession.query.filter_by(is_active=True).first() or \
            AcademicSession(name='LIVE 25/26', is_active=True)
        db.session.add(live); db.session.commit()
        past = AcademicSession.query.filter_by(name='VS PAST 24/25').first() or \
            AcademicSession(name='VS PAST 24/25', is_active=False)
        db.session.add(past); db.session.commit()
        liveid, pastid = live.id, past.id

    c = _admin(app)
    assert 'time-travel-bar' in c.get('/students').get_data(as_text=True)
    tok = auth_csrf(c)

    c.post('/view-session', data={'_csrf_token': tok, 'session_id': pastid}, follow_redirects=True)
    page = c.get('/students').get_data(as_text=True)
    assert 'VS PAST 24/25' in page and 'read-only' in page
    with app.app_context():
        # The live session is untouched in the DB.
        assert AcademicSession.query.filter_by(is_active=True).first().id == liveid

    c.post('/view-session', data={'_csrf_token': tok, 'session_id': liveid}, follow_redirects=True)
    assert 'read-only' not in c.get('/students').get_data(as_text=True)


def test_non_admin_cannot_set_view_session(app):
    c = app.test_client()   # not logged in
    r = c.post('/view-session', data={'session_id': 1})
    # A not-logged-in POST is rejected before it can change anything — whether by
    # CSRF (400) or the admin_required redirect/abort (302/303/401/403).
    assert r.status_code in (302, 303, 400, 401, 403)
