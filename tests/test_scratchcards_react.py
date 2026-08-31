"""Scratch-card admin pages converted to the React shell (JSON-aware).
The public result-checker portal stays a standalone page."""
import re

from config import Config
from models import db, ScratchCard, Term, AcademicSession
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


def test_scratchcard_shells_render(app):
    client = _admin(app)
    for url, page in {'/scratch-cards/': 'index', '/scratch-cards/logs': 'logs'}.items():
        html = client.get(url).get_data(as_text=True)
        assert 'sc-app' in html and 'sc-data' in html, url
        assert f'"page": "{page}"' in html, url


def test_public_portal_stays_standalone(app):
    """The /check-result portal is public and not part of the admin shell."""
    html = app.test_client().get('/check-result/').get_data(as_text=True)
    assert 'sc-app' not in html


def test_generate_json_returns_print_redirect(app):
    client = _admin(app)
    r = client.post('/scratch-cards/generate', headers={'X-Requested-With': 'fetch'},
                    data={'count': '3', 'max_uses': '4', '_csrf_token': _ptoken(client)}).get_json()
    assert r['ok'] and '/scratch-cards/print' in r['redirect']
    with app.app_context():
        assert ScratchCard.query.count() >= 3


def test_toggle_card_json(app):
    client = _admin(app)
    with app.app_context():
        card = ScratchCard.generate_unique(max_uses=5)
        db.session.add(card)
        db.session.commit()
        cid, was_active = card.id, card.is_active
    r = client.post(f'/scratch-cards/{cid}/toggle', headers={'X-Requested-With': 'fetch'},
                    data={'_csrf_token': _ptoken(client)}).get_json()
    assert r['ok']
    with app.app_context():
        assert db.session.get(ScratchCard, cid).is_active is (not was_active)


def test_publish_toggle_json(app):
    client = _admin(app)
    with app.app_context():
        t = Term.query.first()
        if not t:
            s = AcademicSession(name='SC-Sess', is_active=True)
            db.session.add(s); db.session.flush()
            t = Term(session_id=s.id, term_number=1, name='SC-Term', is_active=True)
            db.session.add(t); db.session.commit()
        tid, before = t.id, bool(t.results_published)
    r = client.post(f'/scratch-cards/publish/{tid}', headers={'X-Requested-With': 'fetch'},
                    data={'_csrf_token': _ptoken(client)}).get_json()
    assert r['ok']
    with app.app_context():
        assert bool(db.session.get(Term, tid).results_published) is (not before)
