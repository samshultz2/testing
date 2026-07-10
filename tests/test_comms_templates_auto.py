"""Communication Phase 4 — template favourites/search/duplicate and the
automation center (per-notification enable/disable + trigger gating)."""
import re

from config import Config
from models import db, MessageTemplate
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


def _tpl(app, name, *, category='General', body='Hi {name}'):
    with app.app_context():
        t = MessageTemplate.query.filter_by(name=name).first()
        if not t:
            t = MessageTemplate(name=name, category=category, body=body, is_active=True)
            db.session.add(t)
            db.session.commit()
        return t.id


# --- templates --------------------------------------------------------------
def test_template_favorite_toggle(app):
    tid = _tpl(app, 'FAVTPL1')
    client = _admin(app)
    tok = _ptoken(client)
    r = client.post(f'/communication/templates/{tid}/favorite',
                    headers={'X-Requested-With': 'fetch'},
                    data={'_csrf_token': tok}).get_json()
    assert r['ok']
    with app.app_context():
        assert MessageTemplate.query.get(tid).is_favorite is True


def test_template_duplicate(app):
    tid = _tpl(app, 'DUPTPL1', body='Original body')
    client = _admin(app)
    tok = _ptoken(client)
    r = client.post(f'/communication/templates/{tid}/duplicate',
                    headers={'X-Requested-With': 'fetch'},
                    data={'_csrf_token': tok}).get_json()
    assert r['ok']
    with app.app_context():
        copy = MessageTemplate.query.filter_by(name='DUPTPL1 (copy)').first()
        assert copy is not None and copy.body == 'Original body' and copy.is_favorite is False


def test_template_search_and_category_filter(app):
    _tpl(app, 'SRCHTPL_UNIQUE', category='Fees', body='pay up')
    _tpl(app, 'OTHERTPL', category='Events', body='party')
    client = _admin(app)
    body = client.get('/communication/templates?q=SRCHTPL_UNIQUE').get_data(as_text=True)
    assert 'SRCHTPL_UNIQUE' in body and 'OTHERTPL' not in body
    body2 = client.get('/communication/templates?category=Fees').get_data(as_text=True)
    assert 'SRCHTPL_UNIQUE' in body2 and 'OTHERTPL' not in body2


def test_templates_page_exposes_favorites_and_categories(app):
    _tpl(app, 'CATTPL', category='Attendance')
    client = _admin(app)
    body = client.get('/communication/templates').get_data(as_text=True)
    assert '"is_favorite"' in body and '"categories"' in body and '"duplicate_url"' in body


# --- automation center ------------------------------------------------------
def test_automation_registry_defaults_enabled(app):
    from utils import automations
    with app.app_context():
        assert automations.is_enabled('student_change') is True
        assert set(automations.KEYS) >= {'admission_decision', 'attendance_alert',
                                         'results_published', 'payment_success',
                                         'payment_failed', 'student_change'}


def test_automation_toggle_persists_and_gates(app):
    from utils import automations
    from utils.notify import notify_student_change
    client = _admin(app)
    tok = _ptoken(client)
    # disable everything except we only care about student_change
    r = client.post('/communication/settings/automations',
                    headers={'X-Requested-With': 'fetch'},
                    data={'_csrf_token': tok}).get_json()   # no boxes checked = all off
    assert r['ok']
    with app.app_context():
        assert automations.is_enabled('student_change') is False
        # the gated trigger now no-ops (returns None) instead of creating a bell
        assert notify_student_change('create', detail='X') is None
    # restore ALL automations to enabled (shared session DB — don't leak 'off'
    # state into other tests that rely on notifications firing)
    restore = {k: 'on' for k in automations.KEYS}
    restore['_csrf_token'] = tok
    r2 = client.post('/communication/settings/automations',
                     headers={'X-Requested-With': 'fetch'}, data=restore).get_json()
    assert r2['ok']
    with app.app_context():
        assert all(automations.is_enabled(k) for k in automations.KEYS)


def test_settings_page_exposes_automations(app):
    client = _admin(app)
    body = client.get('/communication/settings').get_data(as_text=True)
    assert '"automations"' in body and 'save_automations' in body
