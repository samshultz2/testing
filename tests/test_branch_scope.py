"""Stage 2 multi-branch tests: query scoping, access guard, branch switcher."""
import re

from config import Config
from models import db, Branch, Student, User
from tests.conftest import login_token


def _login(app, username, password='secret123'):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'username': username, 'password': password,
                                '_csrf_token': token})
    return client


def _legacy_admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def _setup(app):
    """Two branches, a student in each, and a branch user for branch B."""
    with app.app_context():
        a = Branch.get_default()
        b = Branch.query.filter_by(name='ScopeB').first()
        if not b:
            b = Branch(name='ScopeB', is_active=True)
            db.session.add(b); db.session.flush()
        s_a = Student.query.filter_by(student_id='SCPA1').first()
        if not s_a:
            s_a = Student(student_id='SCPA1', first_name='Aaa', surname='Branch',
                          gender='Male', is_active=True, branch_id=a.id)
            db.session.add(s_a)
        s_b = Student.query.filter_by(student_id='SCPB1').first()
        if not s_b:
            s_b = Student(student_id='SCPB1', first_name='Bbb', surname='Branch',
                          gender='Male', is_active=True, branch_id=b.id)
            db.session.add(s_b)
        u = User.query.filter_by(username='branchscope').first()
        if not u:
            u = User(username='branchscope', role='staff', full_name='Branch U',
                     scope='branch', branch_id=b.id)
            u.set_password('secret123')
            u.set_modules(['students'])
            db.session.add(u)
        db.session.commit()
        return a.id, b.id, s_a.id, s_b.id


def test_branch_user_sees_only_their_branch(app):
    a_id, b_id, s_a, s_b = _setup(app)
    client = _login(app, 'branchscope')
    html = client.get('/students').get_data(as_text=True)
    assert 'SCPB1' in html        # their branch student shown
    assert 'SCPA1' not in html    # other branch hidden


def test_branch_user_blocked_from_other_branch_student(app):
    a_id, b_id, s_a, s_b = _setup(app)
    client = _login(app, 'branchscope')
    resp = client.get(f'/students/{s_a}', follow_redirects=False)
    assert resp.status_code in (302, 303)   # redirected away
    ok = client.get(f'/students/{s_b}')
    assert ok.status_code == 200            # own branch is fine


def test_central_admin_sees_all_and_can_filter(app):
    a_id, b_id, s_a, s_b = _setup(app)
    client = _legacy_admin(app)
    html = client.get('/students').get_data(as_text=True)
    assert 'SCPA1' in html and 'SCPB1' in html      # all branches
    # Narrow to branch A.
    client.get(f'/set-branch?branch_id={a_id}')
    html = client.get('/students').get_data(as_text=True)
    assert 'SCPA1' in html and 'SCPB1' not in html
    # Back to all.
    client.get('/set-branch?branch_id=all')
    html = client.get('/students').get_data(as_text=True)
    assert 'SCPA1' in html and 'SCPB1' in html


def test_new_student_stamped_with_branch_users_branch(app):
    a_id, b_id, s_a, s_b = _setup(app)
    client = _login(app, 'branchscope')
    html = client.get('/students/add').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    token = m.group(1) if m else None
    client.post('/students/add',
                data={'first_name': 'New', 'surname': 'Stamped', 'gender': 'Male',
                      '_csrf_token': token}, follow_redirects=True)
    with app.app_context():
        s = Student.query.filter_by(first_name='New', surname='Stamped').first()
        assert s is not None
        assert s.branch_id == b_id


def test_cbt_exams_branch_scoped(app):
    """A branch user's CBT dashboard shows only their branch's exams."""
    from models import CBTExam
    a_id, b_id, s_a, s_b = _setup(app)
    with app.app_context():
        if not CBTExam.query.filter_by(title='ExamA').first():
            db.session.add(CBTExam(title='ExamA', branch_id=a_id))
        if not CBTExam.query.filter_by(title='ExamB').first():
            db.session.add(CBTExam(title='ExamB', branch_id=b_id))
        # give the branch user the cbt module
        u = User.query.filter_by(username='branchscope').first()
        u.set_modules(['students', 'cbt'])
        db.session.commit()
    client = _login(app, 'branchscope')
    html = client.get('/cbt/?term_id=all').get_data(as_text=True)
    assert 'ExamB' in html
    assert 'ExamA' not in html
