"""Tests for CBT device fingerprinting + option ordering helpers."""
from utils.useragent import parse_user_agent


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
