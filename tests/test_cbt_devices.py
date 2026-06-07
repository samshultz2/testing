"""Tests for CBT device fingerprinting + option ordering helpers."""
import re
from datetime import timedelta

from config import Config
from utils.useragent import parse_user_agent
from tests.conftest import login_token


def test_parse_desktop_chrome():
    info = parse_user_agent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                            'AppleWebKit/537.36 Chrome/120.0 Safari/537.36')
    assert info['browser'] == 'Chrome'
    assert info['os'] == 'Windows'
    assert info['device_type'] == 'Desktop'
    assert info['is_mobile'] is False


def test_parse_mobile_safari():
    info = parse_user_agent('Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) '
                            'AppleWebKit/605 Version/16 Mobile/15E148 Safari/604')
    assert info['os'] == 'iOS'
    assert info['device_type'] == 'Mobile'
    assert info['is_mobile'] is True


def test_parse_android_tablet():
    info = parse_user_agent('Mozilla/5.0 (Linux; Android 12; Tablet) '
                            'AppleWebKit Chrome/120 Safari')
    assert info['os'] == 'Android'
    assert info['device_type'] == 'Tablet'


def test_parse_device_model():
    redmi = parse_user_agent('Mozilla/5.0 (Linux; Android 14; Redmi 13C Build/UP1A) '
                             'AppleWebKit Chrome/120 Mobile Safari')
    assert redmi['model'] == 'Redmi 13C'
    # Reduced UA ("K") yields no usable model.
    assert parse_user_agent('Mozilla/5.0 (Linux; Android 10; K) Chrome/120 Mobile Safari')['model'] is None
    assert parse_user_agent('Mozilla/5.0 (iPhone; CPU iPhone OS 16_0) Mobile Safari')['model'] == 'iPhone'


def test_login_event_model_records(app):
    """CBTLoginEvent persists a fingerprint row."""
    from models import db, CBTLoginEvent, Student
    with app.app_context():
        s = Student.query.filter_by(student_id='STUDEV01').first()
        if not s:
            s = Student(student_id='STUDEV01', first_name='Dev', surname='Ice',
                        gender='Male', is_active=True)
            db.session.add(s)
            db.session.commit()
        ev = CBTLoginEvent(student_id=s.id, event='login', ip_address='1.2.3.4',
                           browser='Chrome', os='Windows', device_type='Desktop')
        db.session.add(ev)
        db.session.commit()
        assert ev.id is not None
        assert ev.location is None
        ev.latitude, ev.longitude = 6.5, 3.3
        assert '6.5' in ev.location


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def _exam_with_student(app, sid='STUCC1'):
    from models import db, CBTExam, CBTAttempt, Student
    with app.app_context():
        s = Student(student_id=sid, first_name='Con', surname='Cur',
                    gender='Male', is_active=True)
        db.session.add(s); db.session.flush()
        e = CBTExam(title='Concurrency Test'); db.session.add(e); db.session.flush()
        db.session.add(CBTAttempt(exam_id=e.id, student_id=s.id,
                                  status='In progress', total=10))
        db.session.commit()
        return e.id, s.id


def test_two_live_devices_flagged(app):
    from models import db, CBTDeviceSession
    from utils import timeutil
    eid, sid = _exam_with_student(app, 'STUCC1')
    now = timeutil.now()
    with app.app_context():
        db.session.add(CBTDeviceSession(student_id=sid, exam_id=eid, client_token='A',
                                        device_model='Lab PC', last_seen=now))
        db.session.add(CBTDeviceSession(student_id=sid, exam_id=eid, client_token='B',
                                        device_model='Redmi 13C', is_mobile=True, last_seen=now))
        db.session.commit()
    data = _admin(app).get(f'/cbt/exams/{eid}/monitor/data').json
    assert data['concurrent'] == 1
    assert data['rows'][0]['concurrent'] is True
    assert len(data['rows'][0]['concurrent_devices']) == 2


def test_sequential_reuse_not_flagged(app):
    """Old device stale (pinged long ago) + one fresh device => NOT concurrent."""
    from models import db, CBTDeviceSession
    from utils import timeutil
    eid, sid = _exam_with_student(app, 'STUCC2')
    now = timeutil.now()
    with app.app_context():
        db.session.add(CBTDeviceSession(student_id=sid, exam_id=eid, client_token='old',
                                        device_model='Old PC', last_seen=now - timedelta(minutes=5)))
        db.session.add(CBTDeviceSession(student_id=sid, exam_id=eid, client_token='new',
                                        device_model='New PC', last_seen=now))
        db.session.commit()
    data = _admin(app).get(f'/cbt/exams/{eid}/monitor/data').json
    assert data['concurrent'] == 0
    assert data['rows'][0]['concurrent'] is False
