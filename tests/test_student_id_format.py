"""Configurable student-ID format: a school sets a prefix + minimum digit width,
and auto-generated ids follow it (defaulting to STU#####)."""
from models import db, Student
from models.models import SchoolSettings


def test_default_format(app):
    with app.app_context():
        sid = Student.generate_student_id()
        assert sid.startswith('STU') and sid[3:].isdigit() and len(sid[3:]) == 5


def test_custom_prefix_and_width(app):
    with app.app_context():
        SchoolSettings.set('student_id_prefix', 'PIO', 'string')
        SchoolSettings.set('student_id_digits', 6, 'int')
        assert Student.student_id_format() == ('PIO', 6)
        s = Student(student_id='PIO000042', first_name='A', surname='B',
                    gender='Male', is_active=True)
        db.session.add(s); db.session.commit()
        try:
            nxt = Student.generate_student_id()
            assert nxt == 'PIO000043'                 # continues the running number
        finally:
            db.session.delete(s)
            SchoolSettings.set('student_id_prefix', 'STU', 'string')
            SchoolSettings.set('student_id_digits', 5, 'int')
            db.session.commit()


def test_academic_settings_saves_format(app):
    from config import Config
    from tests.conftest import login_token, auth_csrf
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    csrf = auth_csrf(c)
    r = c.post('/settings/academic', data={
        'student_id_prefix': 'abc', 'student_id_digits': '7', '_csrf_token': csrf},
        headers={'X-Requested-With': 'fetch'})
    assert r.status_code in (200, 302)
    with app.app_context():
        assert SchoolSettings.get('student_id_prefix') == 'ABC'   # upper-cased
        assert SchoolSettings.get('student_id_digits') == 7
        # restore
        SchoolSettings.set('student_id_prefix', 'STU', 'string')
        SchoolSettings.set('student_id_digits', 5, 'int')
        db.session.commit()
