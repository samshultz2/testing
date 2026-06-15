"""Bulk soft-delete on the student list, and bulk restore / purge in the trash."""
import re
import uuid

from models import db, Student


def _ptoken(client):
    html = client.get('/students').get_data(as_text=True)
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"', html).group(1)


def _make(n):
    ids = []
    for i in range(n):
        # A globally-unique suffix: the shared session DB persists across tests,
        # so reused-address tricks like id(object()) can collide and trip the
        # students.student_id UNIQUE constraint.
        s = Student(student_id=f'BD{uuid.uuid4().hex[:10]}', surname='Bulk',
                    first_name=f'Del{i}', gender='Male', is_active=True)
        db.session.add(s); db.session.flush(); ids.append(s.id)
    db.session.commit()
    return ids


def test_bulk_soft_delete(app, auth_client):
    with app.app_context():
        ids = _make(3)
    tok = _ptoken(auth_client)
    r = auth_client.post('/students/bulk-delete',
                         data={'student_ids': [ids[0], ids[1]], '_csrf_token': tok})
    assert r.status_code == 200 and r.get_json()['deleted'] == 2
    with app.app_context():
        assert Student.query.get(ids[0]).is_active is False
        assert Student.query.get(ids[1]).is_active is False
        assert Student.query.get(ids[2]).is_active is True   # untouched


def test_bulk_delete_requires_selection(app, auth_client):
    tok = _ptoken(auth_client)
    r = auth_client.post('/students/bulk-delete', data={'_csrf_token': tok})
    assert r.status_code == 400


def test_trash_page_react_shell(auth_client):
    html = auth_client.get('/students/trash').get_data(as_text=True)
    assert 'student-trash-app' in html and 'student-trash-data' in html


def test_bulk_restore_purge_json(app, auth_client):
    with app.app_context():
        ids = _make(2)
        for i in ids:
            Student.query.get(i).is_active = False
        db.session.commit()
    tok = _ptoken(auth_client)
    h = {'X-Requested-With': 'fetch'}

    r = auth_client.post('/students/bulk-restore', headers=h,
                         data={'student_ids': ids, '_csrf_token': tok})
    assert r.status_code == 200 and r.get_json()['restored'] == 2
    with app.app_context():
        for i in ids:
            Student.query.get(i).is_active = False
        db.session.commit()

    r = auth_client.post('/students/bulk-purge', headers=h,
                         data={'student_ids': ids, '_csrf_token': tok})
    assert r.status_code == 200 and r.get_json()['purged'] == 2
    with app.app_context():
        assert all(Student.query.get(i) is None for i in ids)


def test_bulk_restore_and_purge(app, auth_client):
    with app.app_context():
        ids = _make(2)
        for i in ids:
            Student.query.get(i).is_active = False
        db.session.commit()
    tok = _ptoken(auth_client)

    auth_client.post('/students/bulk-restore',
                     data={'student_ids': ids, '_csrf_token': tok})
    with app.app_context():
        assert all(Student.query.get(i).is_active for i in ids)
        for i in ids:
            Student.query.get(i).is_active = False
        db.session.commit()

    auth_client.post('/students/bulk-purge',
                     data={'student_ids': ids, '_csrf_token': tok})
    with app.app_context():
        assert all(Student.query.get(i) is None for i in ids)  # gone for good
