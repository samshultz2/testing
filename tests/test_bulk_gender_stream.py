"""Bulk gender assignment, and stream assignment also filling WAEC subjects."""
import re
import uuid

from models import db, Student
from utils.helpers import STREAM_WAEC_SUBJECTS


def _ptoken(client):
    html = client.get('/students').get_data(as_text=True)
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"', html).group(1)


def _make(**kw):
    kw.setdefault('gender', 'Male')
    s = Student(student_id=f'BG{uuid.uuid4().hex[:10]}', surname='Bulk',
                first_name='Tester', is_active=True, **kw)
    db.session.add(s); db.session.flush()
    return s.id


def test_bulk_set_gender(app, auth_client):
    with app.app_context():
        a = _make(gender='Male'); b = _make(gender='Male')
        db.session.commit()
    r = auth_client.post('/students/bulk-gender', headers={'X-Requested-With': 'fetch'},
                         data={'gender': 'Female', 'student_ids': [a, b],
                               '_csrf_token': _ptoken(auth_client)})
    assert r.status_code == 200 and r.get_json()['updated'] == 2
    with app.app_context():
        assert db.session.get(Student, a).gender == 'Female'
        assert db.session.get(Student, b).gender == 'Female'


def test_bulk_set_gender_rejects_invalid(app, auth_client):
    with app.app_context():
        a = _make(); db.session.commit()
    r = auth_client.post('/students/bulk-gender', headers={'X-Requested-With': 'fetch'},
                         data={'gender': 'Other', 'student_ids': [a],
                               '_csrf_token': _ptoken(auth_client)})
    assert r.status_code == 400


def test_bulk_set_stream_fills_waec_subjects(app, auth_client):
    """Assigning a stream fills WAEC subjects for students who have none yet,
    and never clobbers a student who already has a custom list."""
    with app.app_context():
        blank = _make(stream=None, waec_subjects=None)
        custom = _make(stream=None, waec_subjects='Mathematics, English Language')
        db.session.commit()
    r = auth_client.post('/students/bulk-stream', headers={'X-Requested-With': 'fetch'},
                         data={'stream': 'Science', 'student_ids': [blank, custom],
                               '_csrf_token': _ptoken(auth_client)})
    j = r.get_json()
    assert r.status_code == 200 and j['updated'] == 2 and j['waec_filled'] == 1
    with app.app_context():
        b = db.session.get(Student, blank)
        c = db.session.get(Student, custom)
        assert b.stream == 'Science' and c.stream == 'Science'
        # the blank student got the Science default WAEC subjects (per-school
        # config groups General subjects first, so compare membership not order)
        assert set(b.waec_subject_list) == set(STREAM_WAEC_SUBJECTS['Science'])
        # the custom student kept their own list
        assert c.waec_subjects == 'Mathematics, English Language'


def test_clearing_stream_leaves_waec_untouched(app, auth_client):
    with app.app_context():
        sid = _make(stream='Science', waec_subjects='Physics, Chemistry')
        db.session.commit()
    r = auth_client.post('/students/bulk-stream', headers={'X-Requested-With': 'fetch'},
                         data={'stream': '', 'student_ids': [sid],
                               '_csrf_token': _ptoken(auth_client)})
    assert r.status_code == 200 and r.get_json()['waec_filled'] == 0
    with app.app_context():
        s = db.session.get(Student, sid)
        assert s.stream is None and s.waec_subjects == 'Physics, Chemistry'
