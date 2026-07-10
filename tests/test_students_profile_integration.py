"""Students Phase 3 — profile integrates attendance summary + communication
history. Both are read-only, best-effort, and must never break the profile.
"""
from config import Config
from models import db, Student, Branch
from models.models_comms import Message, MessageRecipient
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD,
                           '_csrf_token': login_token(c)})
    return c


def test_profile_payload_has_attendance_and_comms_keys(app):
    c = _admin(app)
    with app.app_context():
        bid = Branch.get_default().id
        s = Student(student_id='ZZ_P3_A', first_name='P3', surname='ZzP3A',
                    gender='Male', is_active=True, branch_id=bid)
        db.session.add(s); db.session.commit()
        sid = s.id
    j = c.get(f'/api/students/{sid}').get_json()
    # A brand-new student has no attendance data -> None, and no comms.
    assert 'attendance' in j and j['attendance'] is None
    assert j['communications'] == {'count': 0, 'items': []}


def test_comms_history_lists_student_messages(app):
    c = _admin(app)
    with app.app_context():
        bid = Branch.get_default().id
        s = Student(student_id='ZZ_P3_B', first_name='P3', surname='ZzP3B',
                    gender='Female', is_active=True, branch_id=bid)
        db.session.add(s); db.session.flush()
        msg = Message(title='Fee reminder', body='Please pay outstanding fees.',
                      channel='SMS', audience='students', branch_id=bid, status='Sent')
        db.session.add(msg); db.session.flush()
        db.session.add(MessageRecipient(message_id=msg.id, student_id=s.id,
                                        parent_name='Mum', phone='0801',
                                        body='Please pay outstanding fees.',
                                        status='Sent'))
        db.session.commit()
        sid = s.id
    j = c.get(f'/api/students/{sid}').get_json()
    assert j['communications']['count'] == 1
    item = j['communications']['items'][0]
    assert item['title'] == 'Fee reminder'
    assert item['channel'] == 'SMS'
    assert item['status'] == 'Sent'
    assert 'outstanding fees' in item['snippet']
