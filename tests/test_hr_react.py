"""HR pages converted to the React shell (JSON-aware, no-reload)."""
import re

from config import Config
from models import db, StaffMember, Department
from tests.conftest import login_token


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def _ptoken(client):
    html = client.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def test_hr_shells_render(app):
    client = _admin(app)
    for url, page in {
        '/hr/': 'dashboard',
        '/hr/staff': 'staff',
        '/hr/staff/add': 'staff_form',
        '/hr/attendance': 'attendance',
        '/hr/leave': 'leave',
        '/hr/payroll': 'payroll',
        '/hr/departments': 'departments',
        '/hr/settings': 'settings',
    }.items():
        html = client.get(url).get_data(as_text=True)
        assert 'hr-app' in html and 'hr-data' in html, url
        assert f'"page": "{page}"' in html, url


def test_add_staff_json_then_detail_shell(app):
    client = _admin(app)
    r = client.post('/hr/staff/add', headers={'X-Requested-With': 'fetch'},
                    data={'first_name': 'Grace', 'surname': 'Okon', 'staff_type': 'Teaching',
                          'salary': '85000', '_csrf_token': _ptoken(client)}).get_json()
    assert r['ok'] and '/hr/staff/' in r['redirect']
    with app.app_context():
        s = StaffMember.query.filter_by(first_name='Grace', surname='Okon').first()
        assert s is not None and s.salary == 85000
        sid = s.id
    html = client.get(f'/hr/staff/{sid}').get_data(as_text=True)
    assert '"page": "staff_detail"' in html


def test_department_json_create(app):
    client = _admin(app)
    r = client.post('/hr/departments/add', headers={'X-Requested-With': 'fetch'},
                    data={'name': 'Robotics', '_csrf_token': _ptoken(client)}).get_json()
    assert r['ok']
    with app.app_context():
        assert Department.query.filter(Department.name == 'Robotics').first() is not None


def test_add_staff_requires_names(app):
    client = _admin(app)
    r = client.post('/hr/staff/add', headers={'X-Requested-With': 'fetch'},
                    data={'first_name': '', 'surname': '', '_csrf_token': _ptoken(client)})
    assert r.status_code == 400 and 'required' in r.get_json()['error']
