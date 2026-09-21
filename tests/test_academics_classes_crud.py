"""School Classes: edit and delete (the list page already supported add) —
mirrors the same "separate edit page, soft-delete" pattern used for Arms
and Subjects."""
import uuid

from config import Config
from models import db, SchoolClass
from tests.conftest import login_token, auth_csrf


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _class(app, name=None, level=1):
    with app.app_context():
        sc = SchoolClass(name=name or ('CLS' + uuid.uuid4().hex[:8].upper()), level=level)
        db.session.add(sc); db.session.commit()
        return sc.id, sc.name


def test_classes_list_carries_edit_and_delete_urls(app):
    cid, name = _class(app)
    c = _admin(app)
    html = c.get('/academics/classes').get_data(as_text=True)
    assert f'/academics/classes/{cid}/edit' in html
    assert f'/academics/classes/{cid}/delete' in html


def test_edit_class_shell_renders(app):
    cid, _ = _class(app)
    c = _admin(app)
    html = c.get(f'/academics/classes/{cid}/edit').get_data(as_text=True)
    assert '"page": "edit_class"' in html


def test_edit_class_renames_and_relevels_it(app):
    cid, _ = _class(app, level=1)
    c = _admin(app)
    new_name = 'RENAMED' + uuid.uuid4().hex[:6].upper()
    r = c.post(f'/academics/classes/{cid}/edit', data={
        '_csrf_token': auth_csrf(c), 'name': new_name, 'level': '3', 'description': 'Updated desc',
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        sc = db.session.get(SchoolClass, cid)
        assert sc.name == new_name and sc.level == 3 and sc.description == 'Updated desc'


def test_edit_class_rejects_duplicate_name(app):
    c = _admin(app)
    existing_name = 'DUPCLS' + uuid.uuid4().hex[:6].upper()
    c.post('/academics/classes/add', data={'_csrf_token': auth_csrf(c), 'name': existing_name, 'level': '1'})
    cid2, _ = _class(app)
    r = c.post(f'/academics/classes/{cid2}/edit', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': auth_csrf(c), 'name': existing_name, 'level': '2'})
    assert r.status_code == 400
    body = r.get_json()
    assert body['ok'] is False and 'already exists' in body['error']


def test_edit_class_requires_name_and_level(app):
    cid, _ = _class(app)
    c = _admin(app)
    r = c.post(f'/academics/classes/{cid}/edit', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': auth_csrf(c), 'name': '', 'level': ''})
    assert r.status_code == 400
    assert r.get_json()['ok'] is False


def test_delete_class_soft_deletes_and_drops_it_from_the_list(app):
    cid, name = _class(app)
    c = _admin(app)
    r = c.post(f'/academics/classes/{cid}/delete', data={'_csrf_token': auth_csrf(c)},
               follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        sc = db.session.get(SchoolClass, cid)
        assert sc.is_active is False          # soft-deleted, row still exists

    html = c.get('/academics/classes').get_data(as_text=True)
    assert f'/academics/classes/{cid}/delete' not in html


def test_delete_class_does_not_touch_existing_assignments(app):
    """A deleted class keeps its historical class-arm assignments/enrollments —
    only new pickers stop offering it (they already filter on is_active)."""
    from models import Branch, ClassArm, Term, AcademicSession, ClassArmAssignment
    with app.app_context():
        cid, _ = _class(app)
        bid = Branch.get_default().id
        arm = ClassArm.default()
        sess = AcademicSession(name='ClsDelSess' + uuid.uuid4().hex[:5])
        db.session.add(sess); db.session.flush()
        term = Term(name='First Term', term_number=1, session_id=sess.id)
        db.session.add(term); db.session.flush()
        caa = ClassArmAssignment(class_id=cid, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.commit()
        caa_id = caa.id

    c = _admin(app)
    c.post(f'/academics/classes/{cid}/delete', data={'_csrf_token': auth_csrf(c)})

    with app.app_context():
        assert db.session.get(ClassArmAssignment, caa_id) is not None
        assert db.session.get(SchoolClass, cid).is_active is False
