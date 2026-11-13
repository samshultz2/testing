"""Deleted Students page: each row carries what the page searches and filters
on — last class, when it was deleted and who deleted it."""
import json
import re
import uuid

from config import Config
from models import db, Branch, Student
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _payload(c):
    html = c.get('/students/trash').get_data(as_text=True)
    m = re.search(r'id="student-trash-data">(.*?)</script>', html, re.S)
    return json.loads(m.group(1))


def test_trash_rows_say_who_deleted_and_when(app):
    tag = uuid.uuid4().hex[:5].upper()
    with app.app_context():
        s = Student(student_id=f'TR{tag}', first_name='Bin', surname=f'Ztr{tag}', gender='Male',
                    is_active=True, branch_id=Branch.get_default().id)
        db.session.add(s); db.session.commit()
        sid = s.id
    c = _admin(app)
    with c.session_transaction() as sess:
        sess['_csrf_token'] = 'c' * 64
    c.post('/students/bulk-delete', data={'_csrf_token': 'c' * 64, 'student_ids': [str(sid)]})
    d = _payload(c)
    row = next(r for r in d['students'] if r['id'] == sid)
    assert row['deleted_on'] == d['today']
    assert row['deleted_by']                      # recorded per student, even for bulk deletes
    for k in ('last_class', 'last_session', 'view_url', 'restore_url', 'purge_url', 'photo_url', 'is_graduated'):
        assert k in row
