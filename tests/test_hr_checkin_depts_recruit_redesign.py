"""Server fixes behind the Check-in, Departments and Recruitment redesign."""
import json
import re

from models import db, Department, StaffAttendance, JobVacancy, JobApplication
from tests.test_hr_checkin import _admin, _staff_user_client, _sess_csrf

FETCH = {'X-Requested-With': 'fetch'}


def _payload(client, url):
    r = client.get(url, headers={'Accept': 'application/json', **FETCH})
    if r.is_json:
        return r.get_json()
    m = re.search(r'id="[^"]*data[^"]*"[^>]*>(.*?)</script>', r.get_data(as_text=True), re.S)
    return json.loads(m.group(1))


def _manual_checkin(app, client):
    from models import SchoolSettings
    with app.app_context():
        for k in ('hr_geo_lat', 'hr_geo_lng'):
            SchoolSettings.set(k, '', 'string', 'x')
        db.session.commit()
    tok = _sess_csrf(client)
    return client.post('/hr/checkin/self', headers=FETCH,
                       data={'method': 'manual', '_csrf_token': tok}).get_json()


def test_second_checkin_does_not_overwrite_time(app):
    client, sid = _staff_user_client(app, 'RD1')
    assert _manual_checkin(app, client)['ok']
    with app.app_context():
        rec = StaffAttendance.query.filter_by(staff_id=sid).first()
        first = rec.clock_in
        rec.clock_in = '07:01'
        db.session.commit()
    r = _manual_checkin(app, client)
    assert not r['ok'] and 'already checked in' in r['error']
    with app.app_context():
        assert StaffAttendance.query.filter_by(staff_id=sid).first().clock_in == '07:01'
    assert first


def test_checkin_payload_has_week_and_hides_qr_from_staff(app):
    client, _ = _staff_user_client(app, 'RD2')
    d = _payload(client, '/hr/checkin')
    assert d['week'] and d['week'][-1]['today'] is True
    assert d['can_show_qr'] is False
    assert _payload(_admin(app), '/hr/checkin')['can_show_qr'] is True


def test_department_rename_cannot_clash(app):
    with app.app_context():
        a = Department(name='Sciences RD'); b = Department(name='Arts RD')
        db.session.add_all([a, b]); db.session.commit()
        bid = b.id
    client = _admin(app)
    tok = _sess_csrf(client)
    r = client.post(f'/hr/departments/{bid}/edit', headers=FETCH,
                    data={'name': 'sciences rd', 'is_active': 'on', '_csrf_token': tok}).get_json()
    assert not r['ok'] and 'already exists' in r['error']
    with app.app_context():
        assert db.session.get(Department, bid).name == 'Arts RD'
    d = _payload(client, '/hr/departments')
    assert 'unassigned' in d and all('staff_url' in x for x in d['departments'])


def test_vacancy_edit_requires_title_and_list_has_pipeline(app):
    with app.app_context():
        v = JobVacancy(title='Role RD', positions=2, status='Open', staff_type='Teaching', employment_type='Full-time')
        db.session.add(v); db.session.flush()
        db.session.add(JobApplication(vacancy_id=v.id, first_name='A', surname='B', status='Offered'))
        db.session.commit()
        vid = v.id
    client = _admin(app)
    tok = _sess_csrf(client)
    r = client.post(f'/hr/recruitment/{vid}/edit', headers=FETCH, data={'title': ' ', '_csrf_token': tok}).get_json()
    assert not r['ok']
    r = client.post(f'/hr/recruitment/{vid}/edit', headers=FETCH,
                    data={'title': 'Role RD2', 'positions': '3', 'status': 'Closed', '_csrf_token': tok}).get_json()
    assert r['ok']
    with app.app_context():
        v = db.session.get(JobVacancy, vid)
        assert (v.title, v.positions, v.status) == ('Role RD2', 3, 'Closed')
    row = next(x for x in _payload(client, '/hr/recruitment')['vacancies'] if x['id'] == vid)
    assert row['pipeline']['Offered'] == 1 and 'days_left' in row
