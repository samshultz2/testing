"""Settings is admin-only; welfare writes require students:edit.

Locks in the route-level gates so a non-admin staff member cannot reach the
school-configuration / backup / user-management surface by URL, and a
view-only user cannot record discipline/clinic entries.
"""
import re

from config import Config
from models import db, User, GradeScale, Student, DisciplineRecord
from tests.conftest import login_token


def _make_user(app, username, role='staff', modules=None, view_only=False):
    with app.app_context():
        if not User.query.filter_by(username=username).first():
            u = User(username=username, role=role, full_name=username.title())
            u.set_password('secret123')
            if modules is not None:
                u.set_modules(modules)
            u.view_only = view_only
            db.session.add(u)
            db.session.commit()


def _login(app, username, password='secret123'):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'username': username, 'password': password,
                                '_csrf_token': token})
    return client


def _session_token(client):
    """A CSRF token from a page the current (logged-in) user can always reach."""
    html = client.get('/').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def test_non_admin_blocked_from_settings_pages(app):
    _make_user(app, 'cfg_finance', role='staff', modules=['finance'])
    client = _login(app, 'cfg_finance')
    for path in ('/settings/', '/settings/grades', '/settings/backup'):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code in (302, 303), path


def test_non_admin_cannot_rewrite_grade_scale(app):
    _make_user(app, 'cfg_finance2', role='staff', modules=['finance'])
    with app.app_context():
        GradeScale.query.delete()
        db.session.add(GradeScale(grade='A', min_score=70, max_score=100,
                                  remark='Excellent', order=1))
        db.session.commit()
    client = _login(app, 'cfg_finance2')
    token = _session_token(client)
    resp = client.post('/settings/grades/save',
                       data={'grade[]': 'Z', 'min_score[]': '0',
                             'max_score[]': '10', 'remark[]': 'x',
                             '_csrf_token': token},
                       follow_redirects=False)
    assert resp.status_code in (302, 303)
    with app.app_context():
        # The scale is untouched — still the original 'A', not wiped to 'Z'.
        assert GradeScale.query.filter_by(grade='A').count() == 1
        assert GradeScale.query.filter_by(grade='Z').count() == 0


def test_branch_admin_cannot_manage_users_via_settings(app):
    """The legacy settings user routes are central-admin only (the crude
    duplicates bypass the delegated rank/branch checks)."""
    _make_user(app, 'branch_admin', role='admin', modules=None)
    with app.app_context():
        u = User.query.filter_by(username='branch_admin').first()
        u.scope = 'branch'   # admin assigned to a branch, not central
        db.session.commit()
    client = _login(app, 'branch_admin')
    resp = client.get('/settings/users', follow_redirects=False)
    assert resp.status_code in (302, 303)


def test_view_only_user_cannot_record_discipline(app):
    _make_user(app, 'welfare_ro', role='teacher', modules=['students'],
               view_only=True)
    with app.app_context():
        s = Student(student_id='WLF001', first_name='Test', surname='Pupil',
                    gender='Male')
        db.session.add(s)
        db.session.commit()
        sid = s.id
        before = DisciplineRecord.query.count()
    client = _login(app, 'welfare_ro')
    token = _session_token(client)
    resp = client.post(f'/welfare/discipline/{sid}/add',
                       data={'description': 'late again', '_csrf_token': token},
                       follow_redirects=False)
    assert resp.status_code in (302, 303)
    with app.app_context():
        assert DisciplineRecord.query.count() == before


def test_admin_can_still_reach_settings(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD,
                                '_csrf_token': token})
    assert client.get('/settings/').status_code == 200
    assert client.get('/settings/grades').status_code == 200
