"""HR Phase 5 — reports hub, CSV/Excel export, bulk staff import, HR→Comms
notify, and dashboard enrichment."""
import io
import re
from datetime import date, timedelta

from config import Config
from models import db, StaffMember, Department, Message
from tests.conftest import login_token


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def _csrf(client):
    with client.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return 'a' * 64


# --- reports -----------------------------------------------------------------
def test_report_builders_all_render(app):
    from utils import hr_reports as R
    with app.app_context():
        s = StaffMember(staff_id='RPT1', first_name='Rep', surname='Zzort',
                        gender='Female', staff_type='Teaching', status='Active',
                        date_employed=date(2019, 9, 1), date_of_birth=date(1968, 7, 15),
                        qualification='B.Ed', is_active=True)
        db.session.add(s); db.session.commit()
    client = _admin(app)
    for rtype, _ in R.REPORTS:
        html = client.get(f'/hr/reports?type={rtype}').get_data(as_text=True)
        assert '"page": "reports"' in html
        assert f'"type": "{rtype}"' in html


def test_retirement_and_birthday_windows(app):
    with app.app_context():
        # someone turning 60 within a couple of years, birthday soon
        soon = date.today() + timedelta(days=10)
        dob = date(date.today().year - 58, soon.month, soon.day)
        s = StaffMember(staff_id='RET1', first_name='Old', surname='Zztimer',
                        date_of_birth=dob, is_active=True, status='Active')
        db.session.add(s); db.session.commit()
        name = s.full_name
    client = _admin(app)
    assert name in client.get('/hr/reports?type=retirement').get_data(as_text=True)
    assert name in client.get('/hr/reports?type=birthdays').get_data(as_text=True)


def test_reports_export_csv(app):
    client = _admin(app)
    r = client.get('/hr/reports/export?type=directory&format=csv')
    assert r.status_code == 200
    assert 'text/csv' in r.headers['Content-Type']
    assert b'Staff ID' in r.data


# --- bulk import -------------------------------------------------------------
def test_import_staff_csv(app):
    client = _admin(app)
    tok = _csrf(client)
    csv_text = (
        'First name,Surname,Gender,Department,Designation,Staff type,Salary\n'
        'Grace,Import-Test,Female,Chemistry,Chemistry Teacher,Teaching,95000\n'
        'John,Import-Test2,Male,Chemistry,Lab Technician,Non-teaching,\n'
        ',NoFirstName,,,,,\n'
    )
    r = client.post('/hr/staff/import', content_type='multipart/form-data',
                    headers={'X-Requested-With': 'fetch'},
                    data={'_csrf_token': tok,
                          'file': (io.BytesIO(csv_text.encode()), 'staff.csv')}).get_json()
    assert r['ok']
    with app.app_context():
        g = StaffMember.query.filter_by(surname='Import-Test').first()
        assert g is not None and g.salary == 95000 and g.staff_type == 'Teaching'
        # department auto-created and shared
        assert Department.query.filter(Department.name == 'Chemistry').count() == 1
        j = StaffMember.query.filter_by(surname='Import-Test2').first()
        assert j is not None and j.department_id == g.department_id


def test_import_requires_name_columns(app):
    client = _admin(app)
    tok = _csrf(client)
    r = client.post('/hr/staff/import', content_type='multipart/form-data',
                    headers={'X-Requested-With': 'fetch'},
                    data={'_csrf_token': tok,
                          'file': (io.BytesIO(b'Phone,Email\n0800,x@y.z\n'), 'bad.csv')})
    assert r.status_code == 400


# --- HR -> Communication -----------------------------------------------------
def test_notify_staff_drafts_campaign(app):
    with app.app_context():
        dep = Department(name='Notify Dept'); db.session.add(dep); db.session.flush()
        s = StaffMember(staff_id='NTF1', first_name='Note', surname='Zzify',
                        department_id=dep.id, phone='08099999999', staff_type='Teaching',
                        is_active=True)
        db.session.add(s); db.session.commit()
        did = dep.id
    client = _admin(app)
    tok = _csrf(client)
    r = client.post('/hr/staff/notify', headers={'X-Requested-With': 'fetch'},
                    data={'channel': 'SMS', 'title': 'Meeting', 'body': 'Staff meeting at 2pm',
                          'department_id': did, '_csrf_token': tok}).get_json()
    assert r['ok'] and '/communication/' in r['redirect']
    with app.app_context():
        assert Message.query.filter_by(title='Meeting').count() >= 1


def test_notify_staff_requires_body(app):
    client = _admin(app)
    tok = _csrf(client)
    r = client.post('/hr/staff/notify', headers={'X-Requested-With': 'fetch'},
                    data={'channel': 'SMS', 'body': '', '_csrf_token': tok})
    assert r.status_code == 400


# --- dashboard ---------------------------------------------------------------
def test_dashboard_exposes_enriched_keys(app):
    client = _admin(app)
    html = client.get('/hr/').get_data(as_text=True)
    for key in ('"birthdays"', '"contracts"', '"new_hires"', '"contract_expiring"'):
        assert key in html


# --- reports redesign: filters every report honours ---------------------------
def test_leave_and_attendance_honour_filters_and_dates(app):
    from models import LeaveRecord, StaffAttendance
    from utils import hr_reports as R
    with app.app_context():
        t = StaffMember(staff_id='LVT1', first_name='Teach', surname='Zzleave', staff_type='Teaching',
                        status='Active', is_active=True)
        n = StaffMember(staff_id='LVN1', first_name='Admin', surname='Zzleave', staff_type='Non-teaching',
                        status='Active', is_active=True)
        db.session.add_all([t, n]); db.session.flush()
        for s in (t, n):
            db.session.add(LeaveRecord(staff_id=s.id, leave_type='Annual', start_date=date(2001, 3, 1),
                                       end_date=date(2001, 3, 5), days=5, status='Approved'))
            db.session.add(StaffAttendance(staff_id=s.id, date=date(2001, 3, 9), status='Late'))
        db.session.commit()
    with app.test_request_context('/'):
        from flask import session
        session['logged_in'] = True; session['role'] = 'super_admin'
        rng = {'from': date(2001, 3, 1), 'to': date(2001, 3, 31)}
        # leave: the chosen period is used (it used to be "this year" only)
        names = [r['name'] for r in R.build('leave', dict(rng))['rows'] if 'Zzleave' in r['name']]
        assert len(names) == 2
        assert not [r for r in R.build('leave', {})['rows'] if 'Zzleave' in r['name']]   # not this year
        # staff type now applies to leave and attendance (it used to be ignored)
        teach = dict(rng, staff_type='Teaching')
        assert [r['name'] for r in R.build('leave', teach)['rows'] if 'Zzleave' in r['name']] == ['Zzleave Teach']
        att = [r for r in R.build('attendance', teach)['rows'] if 'Zzleave' in r['name']]
        assert [r['name'] for r in att] == ['Zzleave Teach'] and att[0]['late'] == 1
        # money summaries say so, for the screen and exports
        assert any(sm.get('money') for sm in R.build('attendance', dict(rng))['summary'])


def test_report_catalogue_drives_the_screen(app):
    from utils import hr_reports as R
    cat = {c['key']: c for c in R.catalogue()}
    assert set(cat) == {k for k, _ in R.REPORTS}
    assert cat['directory']['dates'] is None and cat['leave']['dates'] == 'range'
    assert cat['contracts']['dates'] == 'until' and cat['by_department']['chart'] is True
    client = _admin(app)
    d = client.get('/hr/reports?type=leave', headers={'X-Requested-With': 'fetch'}).get_json()
    d = d.get('data', d)
    assert d['report_groups'] == R.GROUPS and d['report_types'][0]['icon']
