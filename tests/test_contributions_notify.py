"""Contributions is financially sensitive and semi-hidden; recording a payment
or expense must NEVER post an in-app notification (the automations registry's
old 'contribution_activity' toggle was removed along with the notify calls —
this is now an unconditional, not a configurable, behaviour)."""
import re

from config import Config
from models import db, ContributionSettings, Notification, Student
from tests.conftest import login_token, enroll_sss3

ACCESS_CODE = '64665842'


def _set_code(app, code=ACCESS_CODE):
    with app.app_context():
        ContributionSettings.set('access_code', code)


def _client(app):
    _set_code(app)
    c = app.test_client()
    token = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    token = _ptoken(c)
    c.post('/contributions/access', data={'access_code': ACCESS_CODE, '_csrf_token': token})
    return c


def _ptoken(client):
    html = client.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def _make_sss3_student(app, tag):
    with app.app_context():
        s = Student(student_id=Student.generate_student_id(), first_name='Contrib',
                    surname=f'Zz{tag}', gender='Male', is_active=True)
        db.session.add(s); db.session.commit()
        sid = s.id
    enroll_sss3(app, sid)
    return sid


def test_recording_payment_never_notifies(app):
    sid = _make_sss3_student(app, 'Pay')
    client = _client(app)
    tok = _ptoken(client)
    with app.app_context():
        before = Notification.query.count()
    r = client.post('/contributions/add-payment', headers={'X-Requested-With': 'fetch'},
                    data={'student_id': str(sid), 'amount': '5000',
                          'payment_date': '2026-01-10', 'received_by': 'Mrs Bello',
                          '_csrf_token': tok})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        assert Notification.query.count() == before


def test_recording_expense_never_notifies(app):
    client = _client(app)
    tok = _ptoken(client)
    with app.app_context():
        before = Notification.query.count()
    r = client.post('/contributions/expenses/add', headers={'X-Requested-With': 'fetch'},
                    data={'expense_date': '2026-01-11', 'description': 'ZzBanner printing',
                          'amount': '1500', '_csrf_token': tok})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        assert Notification.query.count() == before


def test_contribution_activity_automation_no_longer_registered():
    """The toggle was removed, not just disabled -- confirm it's gone from the
    registry rather than lingering as dead config."""
    from utils import automations
    assert all(key != 'contribution_activity' for key, *_ in automations.REGISTRY)
