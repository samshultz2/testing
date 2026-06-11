"""Result-card and timetable generation require explicit capability grants,
and result-card capability is central-admin-grant-only."""
from config import Config
from models import db, Branch, AcademicSession, Term, Student, User
from tests.conftest import login_token


def _login_user(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    return c


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _mk(app, username, perms=None, **kw):
    with app.app_context():
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(username=username, full_name=username, **kw)
            u.set_password('secret123')
            if perms is not None:
                u.set_permissions(perms)
            db.session.add(u); db.session.commit()
        return u.id


def _bid(app):
    with app.app_context():
        return Branch.get_default().id


def _student(app):
    with app.app_context():
        s = Student.query.filter_by(student_id='GP_RC1').first()
        if not s:
            bid = Branch.get_default().id
            s = Student(student_id='GP_RC1', first_name='Rc', surname='Kid',
                        gender='Male', is_active=True, branch_id=bid)
            db.session.add(s); db.session.commit()
        return s.id


def test_teacher_without_capability_blocked_from_report_card(app):
    sid = _student(app)
    _mk(app, 'rc_teacher', role='teacher', scope='branch',
        branch_id=_bid(app), rank=10, manage_scope='none')
    c = _login_user(app, 'rc_teacher')
    # teacher has 'results' module by default, so reaches the route — but the
    # capability gate redirects them.
    r = c.get(f'/subjects/report-card/{sid}', follow_redirects=False)
    assert r.status_code in (302, 303)


def test_user_with_capability_can_open_report_card(app):
    sid = _student(app)
    _mk(app, 'rc_officer', role='staff', scope='branch',
        branch_id=_bid(app), rank=20, manage_scope='none',
        perms={'results': 'edit', 'results.cards': 'edit'})
    c = _login_user(app, 'rc_officer')
    assert c.get(f'/subjects/report-card/{sid}').status_code == 200


def test_central_admin_can_open_report_card(app):
    sid = _student(app)
    assert _admin(app).get(f'/subjects/report-card/{sid}').status_code == 200


def test_branch_manager_cannot_grant_result_card_capability(app):
    """A branch principal editing a teacher must NOT be able to grant the
    central-only 'results.cards' capability."""
    bid = _bid(app)
    _mk(app, 'rc_princ', role='admin', scope='branch', branch_id=bid,
        rank=60, manage_scope='branch')
    tid = _mk(app, 'rc_target', role='staff', scope='branch', branch_id=bid,
              rank=10, manage_scope='none', perms={'results': 'edit'})
    c = _login_user(app, 'rc_princ')
    # principal tries to grant results.cards via the edit form
    import re
    page = c.get(f'/users/{tid}/edit').get_data(as_text=True)
    tok = re.search(r'name="csrf-token" content="([0-9a-f]+)"', page)
    tok = tok.group(1) if tok else None
    c.post(f'/users/{tid}/edit', data={
        'role': 'staff', 'full_name': 'rc_target',
        'perm_results': 'edit', 'perm_results.cards': 'edit',
        '_csrf_token': tok,
    })
    with app.app_context():
        target = db.session.get(User, tid)
        assert 'results.cards' not in target.permission_map  # blocked by central-only rule

    # a central admin CAN grant it
    ca = _admin(app)
    page = ca.get(f'/users/{tid}/edit').get_data(as_text=True)
    tok = re.search(r'name="csrf-token" content="([0-9a-f]+)"', page).group(1)
    ca.post(f'/users/{tid}/edit', data={
        'role': 'staff', 'full_name': 'rc_target',
        'perm_results': 'edit', 'perm_results.cards': 'edit',
        '_csrf_token': tok,
    })
    with app.app_context():
        target = db.session.get(User, tid)
        assert target.permission_map.get('results.cards') == 'edit'  # central allowed
