"""Mass-assign (gender/stream) is available to teachers but scoped to their own
form-class students; the SSS3 tools are gated; admins keep full reach."""
from config import Config
from models import db, Student
from tests.conftest import login_token, page_token
from tests.test_teacher_view_scoping import _seed_teacher_and_students, _login_teacher, _deactivate


def test_teacher_bulk_gender_scoped_to_form_students(app):
    ids = _seed_teacher_and_students(app)
    with app.app_context():
        db.session.get(Student, ids['mine_id']).gender = 'Female'
        db.session.get(Student, ids['other_id']).gender = 'Female'
        db.session.commit()
    c = _login_teacher(app)
    try:
        tok = page_token(c)
        r = c.post('/students/bulk-gender', headers={'X-Requested-With': 'fetch'},
                   data={'gender': 'Male', 'student_ids': [ids['mine_id'], ids['other_id']],
                         '_csrf_token': tok})
        assert r.status_code == 200 and r.get_json()['updated'] == 1   # only their form student
        with app.app_context():
            assert db.session.get(Student, ids['mine_id']).gender == 'Male'     # updated
            assert db.session.get(Student, ids['other_id']).gender == 'Female'  # other class untouched
    finally:
        _deactivate(app)


def test_teacher_with_no_form_class_cannot_bulk(app):
    """A teacher who isn't a form teacher of the target can't bulk-edit it."""
    ids = _seed_teacher_and_students(app)
    c = _login_teacher(app)
    try:
        tok = page_token(c)
        r = c.post('/students/bulk-gender', headers={'X-Requested-With': 'fetch'},
                   data={'gender': 'Male', 'student_ids': [ids['other_id']], '_csrf_token': tok})
        assert r.status_code == 403   # none of the selected students are theirs
    finally:
        _deactivate(app)


def test_students_payload_exposes_bulk_flags(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    j = c.get('/api/students?per_page=5').get_json()
    # Admin: all tools available.
    assert j['can_bulk'] is True and j['can_admin'] is True and j['can_sss3'] is True


def test_teacher_payload_bulk_but_not_admin(app):
    ids = _seed_teacher_and_students(app)
    c = _login_teacher(app)
    try:
        j = c.get('/api/students?per_page=5').get_json()
        assert j['can_bulk'] is True      # can mass-assign (their class)
        assert j['can_admin'] is False    # but not the admin-only delete/subject
        assert j['can_add'] is False
    finally:
        _deactivate(app)
