"""Discipline + sick bay records on the student profile."""
import re
from config import Config
from models import db, Student, DisciplineRecord, ClinicVisit
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    return c


def _student(app, sid='WELF1'):
    with app.app_context():
        s = Student.query.filter_by(student_id=sid).first()
        if not s:
            s = Student(student_id=sid, first_name='Wel', surname='Fare',
                        gender='Male', is_active=True)
            db.session.add(s); db.session.commit()
        return s.id


def _ptok(c):
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get('/students').get_data(as_text=True)).group(1)


def test_add_discipline_and_clinic(app):
    sid = _student(app)
    c = _admin(app)
    tok = _ptok(c)
    c.post(f'/welfare/discipline/{sid}/add', data={
        'date': '2026-05-20', 'category': 'Lateness', 'severity': 'Minor',
        'description': 'Late to assembly', 'action_taken': 'Warning', '_csrf_token': tok})
    c.post(f'/welfare/clinic/{sid}/add', data={
        'date': '2026-05-20', 'complaint': 'Headache', 'treatment': 'Paracetamol',
        'parent_notified': 'on', '_csrf_token': tok})
    with app.app_context():
        d = DisciplineRecord.query.filter_by(student_id=sid).first()
        v = ClinicVisit.query.filter_by(student_id=sid).first()
        assert d and d.category == 'Lateness' and d.severity == 'Minor'
        assert v and v.complaint == 'Headache' and v.parent_notified is True
    # they show on the profile
    body = c.get(f'/students/{sid}').get_data(as_text=True)
    assert 'Late to assembly' in body and 'Headache' in body


def test_discipline_and_clinic_notify_admins_without_leaking_sensitive_text(app):
    """The bell notification must name the student but never the encrypted
    description/complaint/treatment text (see models/models_welfare.py)."""
    from models import Notification
    sid = _student(app, 'WELFNOTIFY1')
    c = _admin(app)
    tok = _ptok(c)
    c.post(f'/welfare/discipline/{sid}/add', data={
        'date': '2026-05-21', 'category': 'Bullying', 'severity': 'Major',
        'description': 'Confidential incident detail XYZ', 'action_taken': 'Suspended',
        '_csrf_token': tok})
    c.post(f'/welfare/clinic/{sid}/add', data={
        'date': '2026-05-21', 'complaint': 'Confidential medical complaint ABC',
        'treatment': 'Confidential treatment DEF', '_csrf_token': tok})
    with app.app_context():
        d_notes = Notification.query.filter_by(title='Discipline record added', role='admin').all()
        c_notes = Notification.query.filter_by(title='Clinic visit recorded', role='admin').all()
        assert any('Fare Wel' in (n.body or '') or 'Wel Fare' in (n.body or '') for n in d_notes)
        assert any('Bullying' in (n.body or '') and 'Major' in (n.body or '') for n in d_notes)
        assert not any('Confidential' in (n.body or '') for n in d_notes + c_notes)
        assert c_notes


def test_disabling_welfare_record_added_automation_skips_notification(app):
    from models import Notification
    from utils import automations
    with app.app_context():
        automations.set_enabled('welfare_record_added', False)
        before = Notification.query.filter_by(title='Discipline record added', role='admin').count()
    try:
        sid = _student(app, 'WELFNOTIFYOFF1')
        c = _admin(app)
        tok = _ptok(c)
        c.post(f'/welfare/discipline/{sid}/add', data={
            'date': '2026-05-22', 'category': 'Lateness', 'severity': 'Minor',
            'description': 'Quiet incident', 'action_taken': 'Warning', '_csrf_token': tok})
        with app.app_context():
            after = Notification.query.filter_by(title='Discipline record added', role='admin').count()
            assert after == before
    finally:
        with app.app_context():
            automations.set_enabled('welfare_record_added', True)


def test_discipline_requires_description(app):
    sid = _student(app, 'WELF2')
    c = _admin(app)
    c.post(f'/welfare/discipline/{sid}/add', data={'description': '', '_csrf_token': _ptok(c)})
    with app.app_context():
        assert DisciplineRecord.query.filter_by(student_id=sid).count() == 0
