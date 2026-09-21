"""Class Arms: edit and delete (the list page already supported add) — mirrors
the same "separate edit page, soft-delete" pattern the Subjects section uses."""
import uuid

from config import Config
from models import db, ClassArm
from tests.conftest import login_token, auth_csrf


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _arm(app, name=None):
    with app.app_context():
        a = ClassArm(name=name or ('Arm' + uuid.uuid4().hex[:8]))
        db.session.add(a); db.session.commit()
        return a.id, a.name


def test_arms_list_carries_edit_and_delete_urls(app):
    aid, name = _arm(app)
    c = _admin(app)
    html = c.get('/academics/arms').get_data(as_text=True)
    assert f'/academics/arms/{aid}/edit' in html
    assert f'/academics/arms/{aid}/delete' in html


def test_edit_arm_shell_renders(app):
    aid, _ = _arm(app)
    c = _admin(app)
    html = c.get(f'/academics/arms/{aid}/edit').get_data(as_text=True)
    assert '"page": "edit_arm"' in html


def test_edit_arm_renames_it(app):
    aid, _ = _arm(app)
    c = _admin(app)
    new_name = 'Renamed' + uuid.uuid4().hex[:6]
    r = c.post(f'/academics/arms/{aid}/edit', data={
        '_csrf_token': auth_csrf(c), 'name': new_name, 'description': 'Updated desc',
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        a = db.session.get(ClassArm, aid)
        assert a.name == new_name.title() and a.description == 'Updated desc'


def test_edit_arm_rejects_duplicate_name(app):
    # add_arm/edit_arm both .title()-case the name server-side, so create the
    # "existing" arm through the real add endpoint to get a name that matches
    # what edit_arm will normalise the duplicate attempt to.
    c = _admin(app)
    existing_name = 'Duparm' + uuid.uuid4().hex[:6]
    c.post('/academics/arms/add', data={'_csrf_token': auth_csrf(c), 'name': existing_name})
    aid2, _ = _arm(app)
    r = c.post(f'/academics/arms/{aid2}/edit', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': auth_csrf(c), 'name': existing_name})
    assert r.status_code == 400
    body = r.get_json()
    assert body['ok'] is False and 'already exists' in body['error']


def test_edit_arm_requires_a_name(app):
    aid, _ = _arm(app)
    c = _admin(app)
    r = c.post(f'/academics/arms/{aid}/edit', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': auth_csrf(c), 'name': ''})
    assert r.status_code == 400
    assert r.get_json()['ok'] is False


def test_delete_arm_soft_deletes_and_drops_it_from_the_list(app):
    aid, name = _arm(app)
    c = _admin(app)
    r = c.post(f'/academics/arms/{aid}/delete', data={'_csrf_token': auth_csrf(c)},
               follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        a = db.session.get(ClassArm, aid)
        assert a.is_active is False          # soft-deleted, row still exists

    html = c.get('/academics/arms').get_data(as_text=True)
    assert f'/academics/arms/{aid}/delete' not in html


def test_delete_arm_does_not_touch_existing_assignments(app):
    """A deleted arm keeps its historical class-arm assignments/enrollments —
    only new pickers stop offering it (they already filter on is_active)."""
    from models import Branch, SchoolClass, Term, AcademicSession, ClassArmAssignment
    with app.app_context():
        aid, _ = _arm(app)
        bid = Branch.get_default().id
        sess = AcademicSession(name='ArmDelSess' + uuid.uuid4().hex[:5])
        db.session.add(sess); db.session.flush()
        term = Term(name='First Term', term_number=1, session_id=sess.id)
        sc = SchoolClass(name='ArmDelClass' + uuid.uuid4().hex[:5], level=1)
        db.session.add_all([term, sc]); db.session.flush()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=aid, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.commit()
        caa_id = caa.id

    c = _admin(app)
    c.post(f'/academics/arms/{aid}/delete', data={'_csrf_token': auth_csrf(c)})

    with app.app_context():
        assert db.session.get(ClassArmAssignment, caa_id) is not None
        assert db.session.get(ClassArm, aid).is_active is False


def test_default_arm_cannot_be_edited_or_deleted(app):
    with app.app_context():
        default_id = ClassArm.default().id
        db.session.commit()
    c = _admin(app)
    r1 = c.post(f'/academics/arms/{default_id}/edit', headers={'X-Requested-With': 'fetch'},
                data={'_csrf_token': auth_csrf(c), 'name': 'Hacked'})
    assert r1.get_json()['ok'] is False

    r2 = c.post(f'/academics/arms/{default_id}/delete', headers={'X-Requested-With': 'fetch'},
                data={'_csrf_token': auth_csrf(c)})
    assert r2.get_json()['ok'] is False

    with app.app_context():
        a = db.session.get(ClassArm, default_id)
        assert a.name == ClassArm.DEFAULT_NAME and a.is_active is True
