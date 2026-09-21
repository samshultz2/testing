"""WAEC allows sitting at most 9 subjects; JAMB (UTME) is always exactly 4.
The subject picker on the student add/edit form makes it impossible to tick
past either cap client-side; these tests cover the server-side backstop
(add_student / edit_student) for a raw POST that ignores the UI."""
import uuid

from config import Config
from models import db, Student
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _csrf(c):
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return 'a' * 64


def _student(app):
    with app.app_context():
        s = Student(student_id='CAP' + uuid.uuid4().hex[:7].upper(), first_name='Cap',
                    surname='Test', gender='Male', is_active=True)
        db.session.add(s); db.session.commit()
        return s.id


def test_add_student_rejects_more_than_9_waec_subjects(app):
    c = _admin(app)
    token = _csrf(c)
    surname = 'ManyWaec' + uuid.uuid4().hex[:5]
    r = c.post('/students/add', headers={'X-Requested-With': 'fetch'}, data={
        '_csrf_token': token, 'first_name': 'Too', 'surname': surname,
        'gender': 'Male',
        'waec_subjects[]': [f'Subj{i}' for i in range(10)],
    })
    body = r.get_json()
    assert body['ok'] is False and 'WAEC' in body['error']
    with app.app_context():
        assert Student.query.filter_by(surname=surname).first() is None   # rejected, never created


def test_add_student_rejects_more_than_4_jamb_subjects(app):
    c = _admin(app)
    token = _csrf(c)
    r = c.post('/students/add', headers={'X-Requested-With': 'fetch'}, data={
        '_csrf_token': token, 'first_name': 'Too', 'surname': 'ManyJamb' + uuid.uuid4().hex[:5],
        'gender': 'Male',
        'jamb_subjects[]': ['English', 'Maths', 'Biology', 'Chemistry', 'Physics'],
    })
    body = r.get_json()
    assert body['ok'] is False and 'JAMB' in body['error']


def test_add_student_accepts_exactly_9_waec_and_4_jamb(app):
    c = _admin(app)
    token = _csrf(c)
    r = c.post('/students/add', headers={'X-Requested-With': 'fetch'}, data={
        '_csrf_token': token, 'first_name': 'Exact', 'surname': 'Caps' + uuid.uuid4().hex[:5],
        'gender': 'Female',
        'waec_subjects[]': [f'Subj{i}' for i in range(9)],
        'jamb_subjects[]': ['English', 'Maths', 'Biology', 'Chemistry'],
    })
    assert r.get_json()['ok'] is True


def test_edit_student_rejects_more_than_9_waec_subjects(app):
    sid = _student(app)
    c = _admin(app)
    token = _csrf(c)
    r = c.post(f'/students/{sid}/edit', headers={'X-Requested-With': 'fetch'}, data={
        '_csrf_token': token,
        'waec_subjects[]': [f'Subj{i}' for i in range(10)],
    })
    body = r.get_json()
    assert body['ok'] is False and 'WAEC' in body['error']
    with app.app_context():
        assert Student.query.get(sid).waec_subjects is None   # rejected, nothing saved


def test_edit_student_rejects_more_than_4_jamb_subjects(app):
    sid = _student(app)
    c = _admin(app)
    token = _csrf(c)
    r = c.post(f'/students/{sid}/edit', headers={'X-Requested-With': 'fetch'}, data={
        '_csrf_token': token,
        'jamb_subjects[]': ['English', 'Maths', 'Biology', 'Chemistry', 'Physics'],
    })
    body = r.get_json()
    assert body['ok'] is False and 'JAMB' in body['error']


def test_edit_student_can_still_save_within_the_caps(app):
    sid = _student(app)
    c = _admin(app)
    token = _csrf(c)
    r = c.post(f'/students/{sid}/edit', headers={'X-Requested-With': 'fetch'}, data={
        '_csrf_token': token,
        'waec_subjects[]': ['English', 'Maths', 'Biology', 'Chemistry'],
        'jamb_subjects[]': ['English', 'Maths', 'Biology', 'Chemistry'],
    })
    assert r.get_json()['ok'] is True
    with app.app_context():
        s = Student.query.get(sid)
        assert len(s.waec_subject_list) == 4 and len(s.jamb_subject_list) == 4


def test_edit_student_partial_post_checks_only_the_field_being_changed_against_the_others_existing_count(app):
    """A partial POST that only sends waec_subjects[] shouldn't be blocked by a
    pre-existing jamb_subjects count (and vice versa) — the cap check should
    compare each field's *incoming* value, falling back to what's already on
    the student for the field that wasn't submitted this time."""
    sid = _student(app)
    with app.app_context():
        s = Student.query.get(sid)
        s.jamb_subjects = 'English, Maths, Biology, Chemistry'   # already at the cap
        db.session.commit()

    c = _admin(app)
    token = _csrf(c)
    r = c.post(f'/students/{sid}/edit', headers={'X-Requested-With': 'fetch'}, data={
        '_csrf_token': token,
        'waec_subjects[]': ['English', 'Maths'],
    })
    assert r.get_json()['ok'] is True
