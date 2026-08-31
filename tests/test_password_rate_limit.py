"""The reset-password and change-password endpoints must be rate limited too,
not just login — otherwise the reset token can be brute-forced and the
change-password form can be used to guess a hijacked session's current password.
"""
from models import db, User
from tests.conftest import login_token, auth_csrf


def _make_user(app, username, password):
    with app.app_context():
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(username=username, full_name=username.title(), role='staff')
            db.session.add(u)
        u.set_password(password)
        u.is_active = True
        db.session.commit()
        return u.id


def test_reset_password_throttles_bad_token_guesses(app):
    uid = _make_user(app, 'rl_reset', 'CorrectHorse9')
    # Unique client IP so this test's per-IP throttle rows (shared session DB)
    # don't leak into other auth tests that reset from 127.0.0.1.
    c = app.test_client()
    ip = {'REMOTE_ADDR': '10.55.0.1'}
    # 10 bad-token hits are allowed (each just says "invalid"); the 11th is
    # blocked by the per-IP throttle.
    last = None
    for _ in range(11):
        last = c.get(f'/reset-password/{uid}/deadbeefbadtoken',
                     environ_base=ip, follow_redirects=True)
    body = last.get_data(as_text=True)
    assert 'Too many attempts' in body


def test_change_password_throttles_wrong_current_password(app):
    _make_user(app, 'rl_change', 'CorrectHorse9')
    c = app.test_client()
    c.post('/login', data={'username': 'rl_change', 'password': 'CorrectHorse9',
                           '_csrf_token': login_token(c)})
    tok = auth_csrf(c)
    # 8 wrong "current password" tries are counted; the 9th is throttled.
    last = None
    for _ in range(9):
        last = c.post('/change-password', data={
            'current_password': 'WrongGuess000', 'new_password': 'BrandNewPw7#',
            'confirm_password': 'BrandNewPw7#', '_csrf_token': tok},
            follow_redirects=True)
    assert 'Too many attempts' in last.get_data(as_text=True)


def test_change_password_success_still_works_and_clears_counter(app):
    """A couple of wrong tries then the correct one succeeds (counter cleared)."""
    _make_user(app, 'rl_change_ok', 'CorrectHorse9')
    c = app.test_client()
    c.post('/login', data={'username': 'rl_change_ok', 'password': 'CorrectHorse9',
                           '_csrf_token': login_token(c)})
    tok = auth_csrf(c)
    for _ in range(3):
        c.post('/change-password', data={
            'current_password': 'WrongGuess000', 'new_password': 'BrandNewPw7#',
            'confirm_password': 'BrandNewPw7#', '_csrf_token': tok}, follow_redirects=True)
    r = c.post('/change-password', data={
        'current_password': 'CorrectHorse9', 'new_password': 'BrandNewPw7#',
        'confirm_password': 'BrandNewPw7#', '_csrf_token': tok}, follow_redirects=True)
    assert 'changed successfully' in r.get_data(as_text=True).lower()
