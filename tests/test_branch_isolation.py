"""Branch admins are full-featured but locked to their branch; dashboard scoped."""
import re
from config import Config
from models import db, Branch, Student, User
from tests.conftest import login_token


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    return c


def _setup(app):
    with app.app_context():
        a = Branch.get_default()
        b = Branch.query.filter_by(name='IsoB').first() or Branch(name='IsoB', is_active=True)
        if b.id is None:
            db.session.add(b); db.session.commit()
        if not Student.query.filter_by(student_id='ISOA1').first():
            db.session.add(Student(student_id='ISOA1', first_name='Zeb', surname='Aaa',
                                   gender='Male', is_active=True, branch_id=a.id))
        if not Student.query.filter_by(student_id='ISOB1').first():
            db.session.add(Student(student_id='ISOB1', first_name='Zeb', surname='Bbb',
                                   gender='Male', is_active=True, branch_id=b.id))
        # A branch-scoped ADMIN (full role, but tied to branch B).
        if not User.query.filter_by(username='branchadmin').first():
            u = User(username='branchadmin', role='admin', scope='branch', branch_id=b.id)
            u.set_password('secret123'); db.session.add(u)
        db.session.commit()
        return a.id, b.id


def test_branch_admin_sees_only_their_branch_students(app):
    _setup(app)
    c = _login(app, 'branchadmin')
    html = c.get('/students').get_data(as_text=True)
    assert 'ISOB1' in html
    assert 'ISOA1' not in html


def test_branch_admin_cannot_manage_users(app):
    _setup(app)
    c = _login(app, 'branchadmin')
    r = c.get('/users/', follow_redirects=False)
    assert r.status_code in (302, 303)        # central admins only
    r2 = c.get('/settings/branches', follow_redirects=False)
    assert r2.status_code in (302, 303)


def test_branch_admin_dashboard_excludes_other_branch(app):
    _setup(app)
    c = _login(app, 'branchadmin')
    html = c.get('/').get_data(as_text=True)
    assert 'ISOA1' not in html                # other branch student not on dashboard


def test_central_admin_still_manages_users(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    assert c.get('/users/').status_code == 200
