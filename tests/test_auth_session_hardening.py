"""Regression tests for the auth/session hardening pass (M2, L1, L2).

- M2: staff login has a per-ACCOUNT throttle, so a known username is locked even
  before the per-IP cap (a distributed brute force can't bypass it).
- L1: an over-long password is rejected without ever reaching scrypt (DoS guard).
- L2: the password policy requires 12+ chars incl. a symbol.
"""
from config import Config
from models import db, Branch, User
from tests.conftest import login_token
from utils.security import login_limiter, is_password_strong


def _user(app, username, pw='StrongPass123!'):
    with app.app_context():
        if not User.query.filter_by(username=username).first():
            u = User(username=username, role='teacher', is_active=True,
                     branch_id=Branch.get_default().id)
            u.set_password(pw)
            db.session.add(u); db.session.commit()


def test_per_account_lockout_trips_before_ip_limit(app):
    """6 wrong tries for one username locks THAT account even though the per-IP
    cap (8) hasn't been hit — the correct password is then refused too."""
    _user(app, 'lockme')
    c = app.test_client()
    with app.app_context():
        login_limiter.clear_attempts('staff_login_acct:lockme')
        login_limiter.clear_attempts('staff_login:127.0.0.1')
    try:
        for _ in range(Config.LOGIN_ACCT_MAX_ATTEMPTS):
            c.post('/login', data={'username': 'lockme', 'password': 'WrongPass123!',
                                   '_csrf_token': login_token(c)})
        # Account is now locked (6 >= LOGIN_ACCT_MAX_ATTEMPTS) while IP is still
        # under LOGIN_MAX_ATTEMPTS(8): even the CORRECT password is refused.
        c.post('/login', data={'username': 'lockme', 'password': 'StrongPass123!',
                               '_csrf_token': login_token(c)})
        with c.session_transaction() as sess:
            assert not sess.get('logged_in')
        assert Config.LOGIN_ACCT_MAX_ATTEMPTS < Config.LOGIN_MAX_ATTEMPTS
    finally:
        with app.app_context():
            login_limiter.clear_attempts('staff_login_acct:lockme')
            login_limiter.clear_attempts('staff_login:127.0.0.1')


def test_overlong_password_rejected_without_auth(app):
    """A multi-KB password must not authenticate and must not reach scrypt."""
    _user(app, 'longpw')
    c = app.test_client()
    try:
        c.post('/login', data={'username': 'longpw', 'password': 'A' * 5000,
                               '_csrf_token': login_token(c)})
        with c.session_transaction() as sess:
            assert not sess.get('logged_in')
        with app.app_context():
            assert User.query.filter_by(username='longpw').first().check_password('A' * 5000) is False
    finally:
        with app.app_context():
            login_limiter.clear_attempts('staff_login_acct:longpw')
            login_limiter.clear_attempts('staff_login:127.0.0.1')


def test_password_policy_requires_length_and_symbol():
    assert is_password_strong('Password1')[0] is False        # no symbol, < 12
    assert is_password_strong('Short1!')[0] is False          # too short
    assert is_password_strong('A1!' + 'a' * 200)[0] is False  # > 128 (DoS cap)
    assert is_password_strong('StrongPass123!')[0] is True
