"""Students Phase 5 — editing a student records a change summary (previous →
new) in the append-only audit log, and the profile surfaces that history.
Sensitive fields are audited as "changed" without leaking their values.
"""
from config import Config
from models import db, Student, Branch, AuditLog
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD,
                           '_csrf_token': login_token(c)})
    return c


def _csrf(c):
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return 'a' * 64


def test_edit_records_previous_values(app):
    c = _admin(app); token = _csrf(c)
    with app.app_context():
        bid = Branch.get_default().id
        s = Student(student_id='ZZ_AUD_1', first_name='Old', surname='ZzAud1',
                    gender='Male', is_active=True, branch_id=bid, house='Red')
        db.session.add(s); db.session.commit()
        sid = s.id
    c.post(f'/students/{sid}/edit', data={'_csrf_token': token, 'house': 'Blue'})
    with app.app_context():
        entry = (AuditLog.query.filter_by(action='student.update', target_type='student',
                                          target_id=sid)
                 .order_by(AuditLog.created_at.desc()).first())
        assert entry is not None
        assert 'House' in entry.detail
        assert '"Red"' in entry.detail and '"Blue"' in entry.detail


def test_sensitive_field_change_hides_value(app):
    c = _admin(app); token = _csrf(c)
    with app.app_context():
        bid = Branch.get_default().id
        s = Student(student_id='ZZ_AUD_2', first_name='S', surname='ZzAud2',
                    gender='Female', is_active=True, branch_id=bid)
        db.session.add(s); db.session.commit()
        sid = s.id
    c.post(f'/students/{sid}/edit', data={'_csrf_token': token,
                                          'medical_notes': 'Diabetic — insulin at noon'})
    with app.app_context():
        entry = (AuditLog.query.filter_by(action='student.update', target_id=sid)
                 .order_by(AuditLog.created_at.desc()).first())
        assert entry is not None
        assert 'Medical notes: changed' in entry.detail
        assert 'insulin' not in (entry.detail or '')   # value never leaks


def test_history_in_payload_for_manager(app):
    c = _admin(app); token = _csrf(c)
    with app.app_context():
        bid = Branch.get_default().id
        s = Student(student_id='ZZ_AUD_3', first_name='H', surname='ZzAud3',
                    gender='Male', is_active=True, branch_id=bid)
        db.session.add(s); db.session.commit()
        sid = s.id
    c.post(f'/students/{sid}/edit', data={'_csrf_token': token, 'religion': 'Christianity'})
    j = c.get(f'/api/students/{sid}').get_json()
    assert isinstance(j['history'], list)
    actions = {h['action'] for h in j['history']}
    assert 'student.update' in actions
