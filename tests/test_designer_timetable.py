"""Saved Timetable Designer designs: create / list / load / update / delete,
and branch isolation (one branch can't see, load or delete another's design)."""
import json

from models import db, Branch, User, DesignerTimetable
from tests.conftest import login_token


def _tok(c):
    """The session CSRF token after login (logins rotate it)."""
    with c.session_transaction() as s:
        return s.get('_csrf_token')


def _branch_login(app, username, branch_id):
    with app.app_context():
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(username=username, full_name=username, role='admin',
                     scope='branch', branch_id=branch_id, is_active=True)
            u.set_password('secret123')
            db.session.add(u); db.session.commit()
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    return c


SAMPLE = {
    'name': 'Sat First Term',
    'layout': 'saturday',
    'data': {'layout': 'saturday',
             'rows': [{'week': '1', 'time': '08:00', 'dur': '60', 'subject': 'Maths'}],
             'saturday': {'first': '2026-01-10', 'free': {}}},
}


def test_save_list_load_update_delete(auth_client):
    c = auth_client
    tok = _tok(c)

    # create
    r = c.post('/timetable/designer/save', json=SAMPLE, headers={'X-CSRFToken': tok})
    assert r.status_code == 200
    did = r.get_json()['id']

    # list contains it
    lst = c.get('/timetable/designer/saved').get_json()
    assert any(d['id'] == did and d['name'] == 'Sat First Term' for d in lst)

    # load returns the stored JSON (the Saturday plan round-trips)
    loaded = c.get(f'/timetable/designer/load/{did}').get_json()
    assert loaded['name'] == 'Sat First Term'
    assert json.loads(loaded['data'])['saturday']['first'] == '2026-01-10'

    # update by id (rename) — no new row is created
    r = c.post('/timetable/designer/save',
               json={'id': did, 'name': 'Renamed', 'layout': 'saturday',
                     'data': SAMPLE['data']},
               headers={'X-CSRFToken': tok})
    assert r.status_code == 200 and r.get_json()['id'] == did
    assert c.get(f'/timetable/designer/load/{did}').get_json()['name'] == 'Renamed'
    with c.application.app_context():
        assert DesignerTimetable.query.filter_by(id=did).count() == 1

    # delete
    r = c.post(f'/timetable/designer/delete/{did}', headers={'X-CSRFToken': tok})
    assert r.status_code == 200
    assert all(d['id'] != did for d in c.get('/timetable/designer/saved').get_json())


def test_designer_page_has_day_demarcation_and_editable_grid(auth_client):
    """The designer sheet must render with day separators, editable blank-grid
    cells, and the viewport-anchored export modal."""
    html = auth_client.get('/timetable/designer').get_data(as_text=True)
    # (1) export modal is reparented to <body> and locks scroll so it can't open
    # off-screen behind a transformed ancestor on mobile
    assert 'document.body.appendChild(modal)' in html
    assert "document.body.style.overflow = 'hidden'" in html
    # (2) thick visual demarcation between days (rows) and columns
    assert 'tbody.day + tbody.day' in html
    assert 'tbody class="day"' in html
    assert 'day-col' in html and 'blankgrid' in html
    # (3) the blank grid's cells are editable (contenteditable + persisted data-rc)
    assert 'grid-tt blankgrid' in html
    assert 'class="roster-cell col-sep" contenteditable="true"' in html


def test_designer_has_custom_list_table_mode(auth_client):
    """The auto-numbered custom table: layout option, S/N column, paste box +
    AI prompt, and the CSV paste handler."""
    html = auth_client.get('/timetable/designer').get_data(as_text=True)
    # the new layout choice and its render path (S/N column, listtable table)
    assert 'value="list_table"' in html
    assert 'sn-col' in html and 'blankgrid listtable' in html
    assert "isListTable()" in html
    # CSV paste keeps working here: dedicated paste box, handler and AI prompt
    assert 'id="listPasteBox"' in html
    assert 'function listPaste()' in html
    assert 'id="tt-list-prompt"' in html
    assert 'data-call="listPaste"' in html
    # row-count control + persistence of the row count
    assert 'id="listRows"' in html
    assert 'listRows:el(' in html


def test_save_requires_a_name(auth_client):
    r = auth_client.post('/timetable/designer/save',
                         json={'layout': 'saturday', 'data': {}},
                         headers={'X-CSRFToken': _tok(auth_client)})
    assert r.status_code == 400


def test_save_rejects_without_csrf(auth_client):
    # global CSRF protection guards the write (no token -> 400)
    r = auth_client.post('/timetable/designer/save', json=SAMPLE)
    assert r.status_code == 400


def test_branch_isolation(app):
    with app.app_context():
        b1 = Branch.query.filter_by(name='DTB1').first() or Branch(name='DTB1', is_active=True)
        b2 = Branch.query.filter_by(name='DTB2').first() or Branch(name='DTB2', is_active=True)
        db.session.add_all([b1, b2]); db.session.commit()
        b1id, b2id = b1.id, b2.id

    ca = _branch_login(app, 'dt_a', b1id)
    cb = _branch_login(app, 'dt_b', b2id)

    # A saves a design in branch 1
    r = ca.post('/timetable/designer/save',
                json={'name': 'A-only', 'layout': 'saturday', 'data': {}},
                headers={'X-CSRFToken': _tok(ca)})
    assert r.status_code == 200
    did = r.get_json()['id']

    # A sees it; B does not
    assert any(d['id'] == did for d in ca.get('/timetable/designer/saved').get_json())
    assert all(d['id'] != did for d in cb.get('/timetable/designer/saved').get_json())

    # B can neither load nor delete it (cross-branch IDOR guarded)
    assert cb.get(f'/timetable/designer/load/{did}').status_code == 403
    assert cb.post(f'/timetable/designer/delete/{did}',
                   headers={'X-CSRFToken': _tok(cb)}).status_code == 403
