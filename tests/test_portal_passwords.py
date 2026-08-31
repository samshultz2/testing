"""Hash-only portal passwords: generation shows the raw PIN ONCE and it matches
the stored hash (so the shown PIN actually works), regenerate issues a fresh one,
and there is no route that reveals an existing password."""
import re

from config import Config
from models import db, Branch, Student
from tests.conftest import login_token, auth_csrf

_PIN_RE = re.compile(r'<code[^>]*>([A-HJ-NP-Z2-9]{8})</code>')


def _central_admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c, auth_csrf(c)


def _make_student(app, sid='PW_GEN1'):
    with app.app_context():
        if not Student.query.filter_by(student_id=sid).first():
            s = Student(student_id=sid, first_name='Gen', surname='Pw',
                        gender='Male', is_active=True, branch_id=Branch.get_default().id)
            db.session.add(s); db.session.commit()
        s = Student.query.filter_by(student_id=sid).first()
        return s.id, s.student_id


def test_generate_shows_pin_once_and_it_matches_the_hash(app):
    sid, student_id = _make_student(app)
    c, tok = _central_admin(app)
    r = c.post('/cbt/passwords', data={
        'action': 'generate', 'student_id': sid, 'output': 'html', '_csrf_token': tok})
    assert r.status_code == 200
    m = _PIN_RE.search(r.get_data(as_text=True))
    assert m, 'generated PIN not shown once in the response'
    pin = m.group(1)
    # The PIN shown on screen is exactly what the stored one-way hash verifies.
    with app.app_context():
        s = db.session.get(Student, sid)
        assert s.portal_password_hash and s.check_portal_password(pin)
        assert not hasattr(s, 'portal_password_plain')   # nothing recoverable stored


def test_regenerate_one_issues_a_new_working_pin(app):
    sid, _ = _make_student(app, 'PW_GEN2')
    c, tok = _central_admin(app)
    r = c.post('/cbt/passwords', data={
        'action': 'generate_one', 'one_student_id': sid, 'output': 'html', '_csrf_token': tok})
    assert r.status_code == 200
    pin = _PIN_RE.search(r.get_data(as_text=True)).group(1)
    with app.app_context():
        assert db.session.get(Student, sid).check_portal_password(pin)


def test_download_credential_sheet_at_generation(app):
    sid, _ = _make_student(app, 'PW_GEN3')
    c, tok = _central_admin(app)
    r = c.post('/cbt/passwords', data={
        'action': 'generate', 'student_id': sid, 'output': 'xlsx', '_csrf_token': tok})
    assert r.status_code == 200
    assert 'spreadsheet' in r.headers.get('Content-Type', '')
    assert 'attachment' in r.headers.get('Content-Disposition', '')


def test_no_route_reveals_existing_passwords(app):
    """The old plaintext export route is gone — passwords can't be recovered."""
    c, _ = _central_admin(app)
    assert c.get('/cbt/passwords/export?format=xlsx').status_code == 404
