"""Academics pages converted to the React shell (JSON-aware)."""
import re

from config import Config
from models import db, AcademicSession, Term
from tests.conftest import login_token


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def _ptoken(client):
    html = client.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def test_academics_shells_render(app):
    client = _admin(app)
    for url, page in {
        '/academics/sessions': 'sessions',
        '/academics/sessions/add': 'add_session',
        '/academics/terms': 'terms',
        '/academics/terms/add': 'add_term',
        '/academics/setup': 'setup',
        '/academics/classes': 'classes',
        '/academics/arms': 'arms',
        '/academics/assignments': 'assignments',
        '/academics/copy-term-setup': 'copy_term_setup',
    }.items():
        html = client.get(url).get_data(as_text=True)
        assert 'acad-app' in html and 'acad-data' in html, url
        assert f'"page": "{page}"' in html, url


def test_session_term_id_shells_render(app):
    client = _admin(app)
    with app.app_context():
        sess = AcademicSession(name='2099/2100', is_active=True)
        db.session.add(sess)
        db.session.flush()
        term = Term(name='First Term', term_number=1, session_id=sess.id, is_active=True)
        db.session.add(term)
        db.session.commit()
        sid, tid = sess.id, term.id
    for url, page in {
        f'/academics/sessions/{sid}/edit': 'edit_session',
        f'/academics/terms/{tid}': 'view_term',
        f'/academics/terms/{tid}/edit': 'edit_term',
    }.items():
        html = client.get(url).get_data(as_text=True)
        assert 'acad-app' in html, url
        assert f'"page": "{page}"' in html, url


def test_add_session_json(app):
    client = _admin(app)
    r = client.post('/academics/sessions/add', headers={'X-Requested-With': 'fetch'},
                    data={'name': '2100/2101', '_csrf_token': _ptoken(client)}).get_json()
    assert r['ok'] and r['redirect'].endswith('/academics/sessions')
    with app.app_context():
        assert AcademicSession.query.filter_by(name='2100/2101').first() is not None
