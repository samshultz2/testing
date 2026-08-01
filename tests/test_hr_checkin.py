"""HR Phase 7 — self-service attendance: QR day-code, GPS geofence, and the
token-authenticated biometric device API."""
import re
from datetime import date

from config import Config
from models import db, StaffMember, StaffAttendance, SchoolSettings, User
from tests.conftest import login_token


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def _staff_user_client(app, tag, **staff_kw):
    """A client logged in as a real user linked to a staff record."""
    with app.app_context():
        u = User(username=f'ci_{tag}', full_name=f'CI {tag}', role='teacher',
                 password_hash='x', is_active=True)
        u.set_password('pw12345')
        db.session.add(u); db.session.flush()
        s = StaffMember(staff_id=f'CI{tag}', first_name='Chk', surname=f'Zz{tag}',
                        user_id=u.id, is_active=True, **staff_kw)
        db.session.add(s); db.session.commit()
        sid = s.id
    client = app.test_client()
    tok = login_token(client)
    client.post('/login', data={'username': f'ci_{tag}', 'password': 'pw12345', '_csrf_token': tok})
    return client, sid


def _sess_csrf(client):
    with client.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return 'a' * 64


# --- day code helpers -------------------------------------------------------
def test_day_code_round_trip(app):
    from utils import hr as hr_utils
    with app.test_request_context():
        code = hr_utils.day_code()
        assert hr_utils.verify_day_code(code) is True
        assert hr_utils.verify_day_code('garbage') is False


def test_geofence_distance(app):
    from utils import hr as hr_utils
    with app.app_context():
        SchoolSettings.set('hr_geo_lat', '6.5244', 'string', 'x')
        SchoolSettings.set('hr_geo_lng', '3.3792', 'string', 'x')
        SchoolSettings.set('hr_geo_radius', '200', 'string', 'x')
        db.session.commit()
        assert hr_utils.within_geofence(6.5244, 3.3792) is True     # same spot
        assert hr_utils.within_geofence(6.6, 3.5) is False           # far away


# --- QR self check-in -------------------------------------------------------
def test_qr_self_checkin(app):
    from utils import hr as hr_utils
    client, sid = _staff_user_client(app, 'QR1')
    tok = _sess_csrf(client)
    with app.test_request_context():
        code = hr_utils.day_code()
    r = client.post('/hr/checkin/self', headers={'X-Requested-With': 'fetch'},
                    data={'method': 'qr', 'code': code, '_csrf_token': tok}).get_json()
    assert r['ok']
    with app.app_context():
        assert StaffAttendance.query.filter_by(staff_id=sid, date=date.today()).count() == 1


def test_manual_checkin_when_no_geofence(app):
    """A plain one-tap clock-in works when GPS isn't enforced."""
    from models import SchoolSettings
    with app.app_context():
        # Ensure no geofence is configured.
        for k in ('hr_geo_lat', 'hr_geo_lng'):
            SchoolSettings.set(k, '', 'string', 'x')
        db.session.commit()
    client, sid = _staff_user_client(app, 'MAN1')
    tok = _sess_csrf(client)
    r = client.post('/hr/checkin/self', headers={'X-Requested-With': 'fetch'},
                    data={'method': 'manual', '_csrf_token': tok}).get_json()
    assert r['ok']
    with app.app_context():
        rec = StaffAttendance.query.filter_by(staff_id=sid, date=date.today()).first()
        assert rec is not None and rec.clock_in


def test_manual_checkin_blocked_when_geofence_on(app):
    """With a geofence configured, a manual tap is refused (GPS required)."""
    from models import SchoolSettings
    with app.app_context():
        SchoolSettings.set('hr_geo_lat', '6.5', 'string', 'x')
        SchoolSettings.set('hr_geo_lng', '3.3', 'string', 'x')
        SchoolSettings.set('hr_geo_radius', '150', 'string', 'x')
        db.session.commit()
    client, sid = _staff_user_client(app, 'MAN2')
    tok = _sess_csrf(client)
    r = client.post('/hr/checkin/self', headers={'X-Requested-With': 'fetch'},
                    data={'method': 'manual', '_csrf_token': tok})
    assert r.status_code == 400


def test_qr_rejects_bad_code(app):
    client, sid = _staff_user_client(app, 'QR2')
    tok = _sess_csrf(client)
    r = client.post('/hr/checkin/self', headers={'X-Requested-With': 'fetch'},
                    data={'method': 'qr', 'code': 'nope', '_csrf_token': tok})
    assert r.status_code == 400


# --- GPS self check-in ------------------------------------------------------
def test_gps_checkin_inside_and_outside(app):
    with app.app_context():
        SchoolSettings.set('hr_geo_lat', '6.5', 'string', 'x')
        SchoolSettings.set('hr_geo_lng', '3.3', 'string', 'x')
        SchoolSettings.set('hr_geo_radius', '150', 'string', 'x')
        db.session.commit()
    client, sid = _staff_user_client(app, 'GPS1')
    tok = _sess_csrf(client)
    out = client.post('/hr/checkin/self', headers={'X-Requested-With': 'fetch'},
                      data={'method': 'gps', 'lat': '6.9', 'lng': '3.9', '_csrf_token': tok})
    assert out.status_code == 400   # outside premises
    inn = client.post('/hr/checkin/self', headers={'X-Requested-With': 'fetch'},
                      data={'method': 'gps', 'lat': '6.5', 'lng': '3.3', '_csrf_token': tok}).get_json()
    assert inn['ok']


# --- device API -------------------------------------------------------------
def test_device_punch_requires_token(app):
    with app.app_context():
        SchoolSettings.set('hr_device_token', 'SECRET-TOK', 'string', 'x')
        s = StaffMember(staff_id='DVP1', first_name='Dev', surname='Punch', is_active=True)
        db.session.add(s); db.session.commit()
        sid = s.id
    client = app.test_client()   # NO login — device is token-authenticated
    bad = client.post('/hr/api/attendance/punch', json={'token': 'WRONG', 'staff_id': sid})
    assert bad.status_code == 401
    ok = client.post('/hr/api/attendance/punch', json={'token': 'SECRET-TOK', 'staff_code': 'DVP1'})
    assert ok.status_code == 200 and ok.get_json()['ok'] is True
    with app.app_context():
        assert StaffAttendance.query.filter_by(staff_id=sid, date=date.today()).count() == 1


def test_regenerate_device_token(app):
    client = _admin(app)
    tok = _sess_csrf(client)
    r = client.post('/hr/settings/device-token', headers={'X-Requested-With': 'fetch'},
                    data={'_csrf_token': tok}).get_json()
    assert r['ok'] and r['token']
    with app.app_context():
        assert SchoolSettings.get('hr_device_token', '') == r['token']


def test_checkin_page_renders(app):
    client, sid = _staff_user_client(app, 'PG1')
    html = client.get('/hr/checkin').get_data(as_text=True)
    assert '"page": "checkin"' in html
    qr = client.get('/hr/attendance/qr')   # staff user is not admin
    assert qr.status_code in (302, 403)
