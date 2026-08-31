"""Brute-force throttling on the public, unauthenticated endpoints:
the parent login and the scratch-card result checker."""
import re

from models import db, Student
from utils.security import login_limiter


def _tok(c, url):
    return re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                     c.get(url).get_data(as_text=True)).group(1)


def test_parent_login_throttled(app):
    with app.app_context():
        if not Student.query.filter_by(student_id='THR1').first():
            s = Student(student_id='THR1', first_name='T', surname='H',
                        gender='Male', is_active=True)
            s.set_portal_password('right-pass')
            db.session.add(s); db.session.commit()
    with app.app_context():
        login_limiter.clear_attempts('parent_login:127.0.0.1')
    c = app.test_client()
    for _ in range(10):           # 10 wrong attempts are allowed
        c.post('/parent/login',
               data={'student_id': 'THR1', 'password': 'wrong', '_csrf_token': _tok(c, '/parent/login')})
    r = c.post('/parent/login',   # the 11th is throttled
               data={'student_id': 'THR1', 'password': 'wrong', '_csrf_token': _tok(c, '/parent/login')},
               follow_redirects=True)
    assert 'Too many attempts' in r.get_data(as_text=True)
    with app.app_context():
        login_limiter.clear_attempts('parent_login:127.0.0.1')


def test_result_checker_throttled(app):
    with app.app_context():
        login_limiter.clear_attempts('result_check:127.0.0.1')
    c = app.test_client()
    for _ in range(20):           # 20 attempts allowed
        c.post('/check-result/',
               data={'student_id': 'NOPE', 'pin': 'x', '_csrf_token': _tok(c, '/check-result/')})
    r = c.post('/check-result/',  # the 21st is throttled
               data={'student_id': 'NOPE', 'pin': 'x', '_csrf_token': _tok(c, '/check-result/')})
    assert 'Too many attempts' in r.get_data(as_text=True)
    with app.app_context():
        login_limiter.clear_attempts('result_check:127.0.0.1')
