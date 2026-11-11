"""Term setup: grouped readiness checklist with in-place actions."""
from config import Config
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    return c


def _ptoken(client):
    import re
    html = client.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def test_term_setup_renders(app):
    c = _admin(app)
    r = c.get('/academics/setup')
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'Term Setup' in body
    assert 'acad-data' in body or 'acad_json' in body or '"page": "setup"' in body


def test_term_setup_payload_groups_actions_and_unlocks(app):
    c = _admin(app)
    d = c.get('/academics/setup', headers={'X-Requested-With': 'fetch'}).get_json()
    d = d.get('data', d)
    if not d.get('term'):
        assert d['steps'] == [] and d['unlocks'] == []
        return
    keys = {s['key'] for s in d['steps']}
    assert {'session', 'active', 'dates', 'weeks', 'classes', 'students', 'subjects'} <= keys
    for s in d['steps']:
        assert s['group'] in {g['key'] for g in d['groups']}
        if s.get('action'):
            assert s['action']['kind'] in ('link', 'post', 'dates') and s['action']['url'].startswith('/')
    assert d['required'] == sum(1 for s in d['steps'] if not s['optional'])
    assert {u['label'] for u in d['unlocks']} >= {'Attendance', 'Score entry & CBT', 'Report cards'}


def test_term_setup_with_a_term_offers_in_place_fixes(app):
    from datetime import date
    from models import db, AcademicSession, Term
    with app.app_context():
        s = AcademicSession.query.filter_by(name='2031/2032').first() or AcademicSession(name='2031/2032', is_active=True)
        db.session.add(s); db.session.flush()
        t = Term(session_id=s.id, term_number=1, name='First Term', is_active=False)
        db.session.add(t); db.session.commit()
        tid = t.id
    c = _admin(app)
    d = c.get(f'/academics/setup?term_id={tid}', headers={'X-Requested-With': 'fetch'}).get_json()
    d = d.get('data', d)
    by = {s['key']: s for s in d['steps']}
    assert by['active']['done'] is False and by['active']['action']['kind'] == 'post'
    assert by['dates']['action']['kind'] == 'dates'
    assert by['weeks']['done'] is False and by['weeks']['action'] is None   # needs dates first
    assert {u['label'] for u in d['unlocks']} >= {'Attendance', 'Score entry & CBT', 'Report cards'}
    assert not next(u for u in d['unlocks'] if u['label'] == 'Attendance')['ready']
    # Set dates (rebuilding weeks) the way the sheet does.
    r = c.post(f'/academics/terms/{tid}/edit', headers={'X-Requested-With': 'fetch'},
               data={'start_date': '2031-09-08', 'end_date': '2031-12-12', 'regenerate_weeks': 'on',
                     '_csrf_token': _ptoken(c)})
    assert r.status_code == 200
    d = c.get(f'/academics/setup?term_id={tid}', headers={'X-Requested-With': 'fetch'}).get_json()
    d = d.get('data', d)
    by = {s['key']: s for s in d['steps']}
    assert by['dates']['done'] and by['weeks']['done'] and d['info']['weeks'] >= 13
