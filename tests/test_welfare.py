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


def test_discipline_requires_description(app):
    sid = _student(app, 'WELF2')
    c = _admin(app)
    c.post(f'/welfare/discipline/{sid}/add', data={'description': '', '_csrf_token': _ptok(c)})
    with app.app_context():
        assert DisciplineRecord.query.filter_by(student_id=sid).count() == 0
