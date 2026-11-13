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


def test_term_view_calendar_and_break_removal(app):
    from datetime import date
    from models import db, AcademicSession, Term, Holiday
    with app.app_context():
        s = AcademicSession(name='2060/2061', is_active=False)
        db.session.add(s); db.session.flush()
        t = Term(session_id=s.id, term_number=1, name='First Term',
                 start_date=date(2060, 9, 6), end_date=date(2060, 12, 10))
        db.session.add(t); db.session.commit()
        tid = t.id
    c = _admin(app)
    tok = _ptoken(c)
    c.post(f'/academics/terms/{tid}/weeks/generate', headers={'X-Requested-With': 'fetch'}, data={'_csrf_token': tok})
    r = c.post(f'/academics/terms/{tid}/holidays/add', headers={'X-Requested-With': 'fetch'},
               data={'date': '2060-10-25', 'end_date': '2060-10-29', 'holiday_type': 'Mid-term Break',
                     'reason': 'Mid-term break', '_csrf_token': tok})
    assert r.get_json()['ok']
    d = c.get(f'/academics/terms/{tid}', headers={'X-Requested-With': 'fetch'}).get_json()
    d = d.get('data', d)
    assert d['stats']['weeks'] == d['stats']['expected_weeks'] and d['stats']['weeks'] >= 13
    assert len(d['breaks']) == 1 and d['breaks'][0]['days'] == 5
    days = [x for w in d['weeks'] for x in w['days']]
    assert all(len(w['days']) == 5 for w in d['weeks'])
    assert sum(1 for x in days if x['status'] == 'holiday') == 5
    assert all(x['status'] in ('future', 'holiday') for x in days)   # term is in the future
    r = c.post(f'/academics/terms/{tid}/holidays/remove', headers={'X-Requested-With': 'fetch'},
               data={'ids': ','.join(map(str, d['breaks'][0]['ids'])), '_csrf_token': tok})
    assert r.get_json()['ok']
    with app.app_context():
        assert Holiday.query.filter_by(term_id=tid).count() == 0


def test_class_setup_payload_and_safe_arm_removal(app):
    from models import db, AcademicSession, Term, SchoolClass, ClassArm, ClassArmAssignment, StudentEnrollment, Student
    with app.app_context():
        s = AcademicSession(name='2070/2071', is_active=False); db.session.add(s); db.session.flush()
        t1 = Term(session_id=s.id, term_number=1, name='First Term')
        t2 = Term(session_id=s.id, term_number=2, name='Second Term'); db.session.add_all([t1, t2]); db.session.flush()
        c = SchoolClass(name='CSX', level=88); db.session.add(c); db.session.flush()
        arm = ClassArm.query.filter_by(name='CsArm').first() or ClassArm(name='CsArm'); db.session.add(arm); db.session.flush()
        a1 = ClassArmAssignment(class_id=c.id, arm_id=arm.id, term_id=t1.id)
        empty = ClassArmAssignment(class_id=c.id, arm_id=arm.id, term_id=t2.id)
        db.session.add_all([a1, empty]); db.session.flush()
        st = Student(student_id='CSX1', surname='C', first_name='S', gender='Male', is_active=True)
        db.session.add(st); db.session.flush()
        db.session.add(StudentEnrollment(student_id=st.id, class_arm_assignment_id=a1.id, is_active=True))
        db.session.commit()
        t2id, a1id, eid = t2.id, a1.id, empty.id
    c_ = _admin(app)
    d = c_.get(f'/academics/assignments?term_id={t2id}', headers={'X-Requested-With': 'fetch'}).get_json()
    d = d.get('data', d)
    assert d['prev_term'] and d['prev_term']['classes'] >= 1
    assert d['unplaced'] >= 1
    tok = _ptoken(c_)
    # an arm that has had students can't be removed; an empty one can
    r = c_.post(f'/academics/assignments/{a1id}/delete', headers={'X-Requested-With': 'fetch'}, data={'_csrf_token': tok})
    assert not r.get_json()['ok']
    r = c_.post(f'/academics/assignments/{eid}/delete', headers={'X-Requested-With': 'fetch'}, data={'_csrf_token': tok})
    assert r.get_json()['ok']
    with app.app_context():
        assert db.session.get(ClassArmAssignment, eid) is None and db.session.get(ClassArmAssignment, a1id) is not None


def test_users_index_payload_has_security_signals(app):
    c = _admin(app)
    d = c.get('/users/', headers={'X-Requested-With': 'fetch'}).get_json()
    d = d.get('data', d)
    assert d['page'] == 'index' and d['users']
    u = d['users'][0]
    assert {'mfa', 'last_days', 'created_days', 'is_admin', 'group', 'branch', 'toggle_url'} <= set(u)


def test_graduates_are_not_counted_as_unplaced(app):
    """Graduates stay is_active (for the graduate pages) but have left — they
    must never show up as 'students not in any class this term'."""
    from models import (db, AcademicSession, Term, SchoolClass, ClassArm, ClassArmAssignment, Student)
    with app.app_context():
        s = AcademicSession(name='GRD 2030/2031'); db.session.add(s); db.session.flush()
        t = Term(session_id=s.id, term_number=1, name='First Term'); db.session.add(t); db.session.flush()
        c = SchoolClass(name='GRDX', level=87); db.session.add(c); db.session.flush()
        arm = ClassArm.query.filter_by(name='GrdArm').first() or ClassArm(name='GrdArm'); db.session.add(arm); db.session.flush()
        db.session.add(ClassArmAssignment(class_id=c.id, arm_id=arm.id, term_id=t.id))
        db.session.commit()
        tid = t.id
    c_ = _admin(app)

    def unplaced():
        d = c_.get(f'/academics/assignments?term_id={tid}', headers={'X-Requested-With': 'fetch'}).get_json()
        return d.get('data', d)['unplaced']
    base = unplaced()
    with app.app_context():
        grad = Student(student_id='GRD1', surname='Grad', first_name='Uate', gender='Male',
                       is_active=True, is_graduated=True, graduate_status='Graduated')
        cur = Student(student_id='GRD2', surname='Cur', first_name='Rent', gender='Female', is_active=True)
        db.session.add_all([grad, cur]); db.session.commit()
    assert unplaced() == base + 1               # only the current student counts
