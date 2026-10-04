"""Recording a contribution payment or expense should alert admins -- this
module has no per-branch concept of its own (see routes/contributions.py's
models), so it's a plain role broadcast (notify_admins), gated by the
'contribution_activity' automation toggle."""
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


def test_recording_payment_notifies_admins(app):
    sid = _make_sss3_student(app, 'Pay')
    client = _client(app)
    tok = _ptoken(client)
    r = client.post('/contributions/add-payment', headers={'X-Requested-With': 'fetch'},
                    data={'student_id': str(sid), 'amount': '5000',
                          'payment_date': '2026-01-10', 'received_by': 'Mrs Bello',
                          '_csrf_token': tok})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        notes = Notification.query.filter_by(title='Contribution payment recorded', role='admin').all()
        assert any('Zz' + 'Pay' in (n.body or '') and 'Mrs Bello' in (n.body or '') for n in notes)


def test_recording_expense_notifies_admins(app):
    client = _client(app)
    tok = _ptoken(client)
    r = client.post('/contributions/expenses/add', headers={'X-Requested-With': 'fetch'},
                    data={'expense_date': '2026-01-11', 'description': 'ZzBanner printing',
                          'amount': '1500', '_csrf_token': tok})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        notes = Notification.query.filter_by(title='Contribution expense recorded', role='admin').all()
        assert any('ZzBanner printing' in (n.body or '') for n in notes)


def test_disabling_contribution_activity_automation_skips_notification(app):
    with app.app_context():
        from utils import automations
        automations.set_enabled('contribution_activity', False)
    try:
        client = _client(app)
        tok = _ptoken(client)
        r = client.post('/contributions/expenses/add', headers={'X-Requested-With': 'fetch'},
                        data={'expense_date': '2026-01-12', 'description': 'ZzQuiet expense',
                              'amount': '750', '_csrf_token': tok})
        assert r.status_code == 200 and r.get_json()['ok']
        with app.app_context():
            notes = Notification.query.filter(
                Notification.body.like('%ZzQuiet expense%')).all()
            assert not notes
    finally:
        with app.app_context():
            from utils import automations
            automations.set_enabled('contribution_activity', True)
