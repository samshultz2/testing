"""Audit logging captures who did what, to what, when."""
import re
from config import Config
from models import db, AuditLog
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _pt(c):
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get('/').get_data(as_text=True)).group(1)


def test_student_create_is_audited_with_target(app):
    c = _admin(app)
    c.post('/students/add',
           data={'first_name': 'Aud', 'surname': 'Kid', 'gender': 'Male',
                 '_csrf_token': _pt(c)}, follow_redirects=True)
    with app.app_context():
        a = AuditLog.query.filter_by(action='student.create').order_by(AuditLog.id.desc()).first()
        assert a is not None
        assert a.target_type == 'student'
        assert a.target_id is not None
        assert a.target_label and 'Aud' in a.target_label
        assert a.user == 'Admin'


def test_log_event_helper(app):
    from utils.audit import log_action
    from models import Branch
    with app.test_request_context('/'):
        from flask import session
        session['user'] = 'Tester'; session['role'] = 'admin'
        b = Branch.get_default()
        bname = b.name
        log_action('branch.touch', target=b)
    with app.app_context():
        a = AuditLog.query.filter_by(action='branch.touch').first()
        assert a.target_type == 'branch' and a.target_label == bname
