"""A form teacher can update and delete the students in their own class, but
not another class's; a teacher cannot register brand-new students."""
from models import db, Student
from tests.conftest import page_token
from tests.test_teacher_view_scoping import (
    _seed_teacher_and_students, _login_teacher, _deactivate)


def test_form_teacher_can_manage_but_not_add(app):
    _seed_teacher_and_students(app)
    c = _login_teacher(app)
    try:
        j = c.get('/api/students?per_page=50').get_json()
        assert j['can_manage'] is True    # edit/delete their own class
        assert j['can_add'] is False      # but not register new students
    finally:
        _deactivate(app)


def test_form_teacher_can_update_own_student(app):
    ids = _seed_teacher_and_students(app)
    c = _login_teacher(app)
    try:
        r = c.post(f'/students/{ids["mine_id"]}/edit', headers={'X-Requested-With': 'fetch'},
                   data={'form_complete': '1', 'surname': 'Mine', 'first_name': 'Zara',
                         'gender': 'Female', 'hobbies': 'Reading', '_csrf_token': page_token(c)})
        assert r.status_code == 200 and r.get_json()['ok']
        with app.app_context():
            assert db.session.get(Student, ids['mine_id']).hobbies == 'Reading'
    finally:
        _deactivate(app)


def test_form_teacher_can_delete_own_but_not_other(app):
    ids = _seed_teacher_and_students(app)
    c = _login_teacher(app)
    try:
        # Another class's student -> blocked.
        bad = c.post(f'/students/{ids["other_id"]}/delete',
                     data={'_csrf_token': page_token(c)}, follow_redirects=False)
        assert bad.status_code == 403
        with app.app_context():
            assert db.session.get(Student, ids['other_id']).is_active is True

        # Their own form-class student -> soft-deleted.
        ok = c.post(f'/students/{ids["mine_id"]}/delete',
                    data={'_csrf_token': page_token(c)}, follow_redirects=False)
        assert ok.status_code in (302, 303)
        with app.app_context():
            assert db.session.get(Student, ids['mine_id']).is_active is False
    finally:
        with app.app_context():       # restore for the shared session DB
            db.session.get(Student, ids['mine_id']).is_active = True
            db.session.commit()
        _deactivate(app)
