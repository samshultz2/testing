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


def test_terms_list_groups_by_session_with_status_and_alerts(app):
    from models import db, AcademicSession, Term
    with app.app_context():
        s = AcademicSession(name='2040/2041', is_active=False)
        db.session.add(s); db.session.flush()
        from datetime import date
        db.session.add_all([
            Term(session_id=s.id, term_number=1, name='First Term', start_date=date(2040, 9, 1), end_date=date(2040, 12, 15)),
            Term(session_id=s.id, term_number=2, name='Second Term', start_date=date(2040, 12, 1), end_date=date(2041, 3, 30)),
        ])
        db.session.commit()
        sid = s.id
    c = _admin(app)
    d = c.get('/academics/terms', headers={'X-Requested-With': 'fetch'}).get_json()
    d = d.get('data', d)
    sess = next(x for x in d['sessions'] if x['id'] == sid)
    assert [t['number'] for t in sess['terms']] == [1, 2]
    assert all(t['state'] == 'upcoming' for t in sess['terms'])
    assert {'weeks', 'classes', 'students', 'setup_url', 'edit_url'} <= set(sess['terms'][0])
    assert any('overlap' in a['text'] for a in d['alerts'])


def test_new_session_with_terms_copies_dates_a_year_on(app):
    from datetime import date, timedelta
    from models import db, AcademicSession, Term, Week
    with app.app_context():
        AcademicSession.query.update({AcademicSession.is_active: False})
        s = AcademicSession(name='2050/2051', is_active=True)
        db.session.add(s); db.session.flush()
        db.session.add(Term(session_id=s.id, term_number=1, name='First Term',
                            start_date=date(2050, 9, 12), end_date=date(2050, 12, 16)))
        db.session.commit()
    c = _admin(app)
    d = c.get('/academics/sessions', headers={'X-Requested-With': 'fetch'}).get_json()
    d = d.get('data', d)
    assert d['next']['name'] == '2051/2052' and len(d['next']['terms']) == 3
    r = c.post('/academics/sessions/add', headers={'X-Requested-With': 'fetch'},
               data={'name': '2051/2052', 'with_terms': 'on', '_csrf_token': _ptoken(c)})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        ns = AcademicSession.query.filter_by(name='2051/2052').first()
        ts = sorted(ns.terms.all(), key=lambda t: t.term_number)
        assert [t.term_number for t in ts] == [1, 2, 3]
        assert ts[0].start_date == date(2050, 9, 12) + timedelta(weeks=52)
        assert ts[0].start_date.weekday() == date(2050, 9, 12).weekday()
        assert ts[1].start_date is None
        assert Week.query.filter_by(term_id=ts[0].id).count() >= 13


def test_classes_and_arms_pages_payloads(app):
    from models import db, SchoolClass
    with app.app_context():
        for n, lv in (('ZZ1', -9), ('ZZ2', -9)):
            if not SchoolClass.query.filter_by(name=n).first():
                db.session.add(SchoolClass(name=n, level=lv))
        db.session.commit()
    c = _admin(app)
    d = c.get('/academics/classes', headers={'X-Requested-With': 'fetch'}).get_json()
    d = d.get('data', d)
    assert d['page'] == 'classes'
    assert any('share level -9' in a['text'] for a in d['alerts'])
    row = next(r for r in d['classes'] if r['name'] == 'ZZ1')
    assert {'section', 'arms', 'students', 'subjects', 'edit_url'} <= set(row)
    # quick-add a suggested standard class with its section
    sug = d['suggest'][0] if d['suggest'] else None
    if sug:
        r = c.post('/academics/classes/add', headers={'X-Requested-With': 'fetch'},
                   data={**sug, '_csrf_token': _ptoken(c)})
        assert r.get_json()['ok']
        with app.app_context():
            assert SchoolClass.query.filter_by(name=sug['name']).first().section == sug['section']
    a = c.get('/academics/arms', headers={'X-Requested-With': 'fetch'}).get_json()
    a = a.get('data', a)
    assert a['page'] == 'arms' and 'uses_arms' in a and isinstance(a['grid'], list)
