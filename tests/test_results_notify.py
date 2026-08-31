"""Result-release notifications: a reviewable *Draft* SMS campaign is queued for
parents — nothing is auto-sent."""
from flask import session
from models import db, Student, ParentContact, Message
from utils import comms


def _student_with_parent(app):
    with app.app_context():
        s = Student.query.filter_by(student_id='RNOT1').first()
        if not s:
            s = Student(student_id='RNOT1', first_name='Tunde', surname='Bello',
                        gender='Male', is_active=True)
            db.session.add(s)
            db.session.flush()
            db.session.add(ParentContact(student_id=s.id, name='Mr Bello',
                                         phone_number='08030001111', is_primary=True))
            db.session.commit()
        return s.id


def test_create_draft_campaign_queues_for_review(app):
    _student_with_parent(app)
    with app.test_request_context('/'):
        session['role'] = 'admin'; session['scope'] = 'central'
        msg = comms.create_draft_campaign(
            'Dear {parent}, results for {student} are out. - {school}',
            audience='all', title='Results released: Term', created_by='tester')
        assert msg is not None
        msg_id = msg.id
    with app.app_context():
        saved = db.session.get(Message, msg_id)
        assert saved.status == 'Draft'              # never auto-dispatched
        assert saved.recipient_count >= 1
        rec = saved.recipients.first() if hasattr(saved.recipients, 'first') \
            else list(saved.recipients)[0]
        assert 'Mr Bello' in rec.body               # personalised per parent
        assert rec.phone == '08030001111'


def test_create_draft_campaign_empty_body_returns_none(app):
    with app.test_request_context('/'):
        session['role'] = 'admin'; session['scope'] = 'central'
        assert comms.create_draft_campaign('   ', audience='all') is None


def test_create_draft_campaign_no_reachable_returns_none(app):
    """Selecting a specific student with no phone yields no campaign."""
    with app.app_context():
        s = Student.query.filter_by(student_id='RNOT2').first()
        if not s:
            s = Student(student_id='RNOT2', first_name='No', surname='Phone',
                        gender='Female', is_active=True)
            db.session.add(s); db.session.commit()
        sid = s.id
    with app.test_request_context('/'):
        session['role'] = 'admin'; session['scope'] = 'central'
        assert comms.create_draft_campaign('hi {student}', audience='students',
                                           student_ids=[sid]) is None
