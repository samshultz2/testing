"""URL-tampering / IDOR guards: a branch-scoped user must not reach another
branch's records by editing the id in the URL. Central users still can."""
from config import Config
from models import db, Branch, User, Student
from tests.conftest import login_token


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    return c


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _ptoken(client):
    import re
    html = client.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def _setup(app):
    with app.app_context():
        other = Branch.query.filter_by(name='TamperB').first()
        if not other:
            other = Branch(name='TamperB', is_active=True)
            db.session.add(other); db.session.commit()
        other_bid = other.id
        home_bid = Branch.get_default().id
        # A student that lives in the DEFAULT branch.
        s = Student.query.filter_by(student_id='TMP1').first()
        if not s:
            s = Student(student_id='TMP1', first_name='Tam', surname='Per', gender='Male',
                        is_active=True, branch_id=home_bid)
            db.session.add(s); db.session.commit()
        sid = s.id
        # A branch-scoped admin who belongs to the OTHER branch.
        u = User.query.filter_by(username='tamper_admin').first()
        if not u:
            u = User(username='tamper_admin', full_name='Tamper Admin', role='admin',
                     scope='branch', branch_id=other_bid, rank=50)
            u.set_password('secret123'); db.session.add(u); db.session.commit()
    return sid


def test_branch_admin_cannot_delete_other_branch_student(app):
    sid = _setup(app)
    c = _login(app, 'tamper_admin')
    r = c.post(f'/students/{sid}/delete', data={'_csrf_token': _ptoken(c)},
               follow_redirects=False)
    assert r.status_code == 403                      # IDOR blocked
    with app.app_context():
        assert db.session.get(Student, sid).is_active is True   # untouched


def test_central_admin_can_delete_any_student(app):
    sid = _setup(app)
    c = _admin(app)        # the built-in admin is central
    r = c.post(f'/students/{sid}/delete', data={'_csrf_token': _ptoken(c)},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(Student, sid).is_active is False
