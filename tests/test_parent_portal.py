"""Parent portal: login with the child's portal credentials, view read-only info."""
import re
from models import db, Student


def _student(app, sid='PPX1', pw='pass123'):
    with app.app_context():
        s = Student.query.filter_by(student_id=sid).first()
        if not s:
            s = Student(student_id=sid, first_name='Kid', surname='Parent',
                        gender='Male', is_active=True)
            s.set_portal_password(pw); db.session.add(s); db.session.commit()
        return sid, pw


def _tok(c):
    return re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                     c.get('/parent/login').get_data(as_text=True)).group(1)


def test_login_required(app):
    _student(app)
    c = app.test_client()
    r = c.get('/parent/', follow_redirects=False)
    assert r.status_code in (302, 303) and '/parent/login' in r.headers['Location']


def test_bad_credentials_rejected(app):
    sid, _ = _student(app)
    c = app.test_client()
    c.post('/parent/login', data={'student_id': sid, 'password': 'nope', '_csrf_token': _tok(c)})
    assert c.get('/parent/', follow_redirects=False).status_code in (302, 303)


def test_login_and_view(app):
    sid, pw = _student(app)
    c = app.test_client()
    c.post('/parent/login', data={'student_id': sid, 'password': pw, '_csrf_token': _tok(c)})
    html = c.get('/parent/').get_data(as_text=True)
    assert sid in html               # the child's record is shown
    assert 'Results' in html         # the results section renders
    # logout clears access
    c.get('/parent/logout')
    assert c.get('/parent/', follow_redirects=False).status_code in (302, 303)
