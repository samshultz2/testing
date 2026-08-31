"""CBT exams stay school-wide, but the live monitor is filterable by branch."""
from datetime import date
from config import Config
from models import db, Branch, User, Student
from models.models_cbt import CBTExam, CBTAttempt
from tests.conftest import login_token


def _setup(app):
    with app.app_context():
        bid_a = Branch.get_default().id
        b = Branch.query.filter_by(name='CbtB').first() or Branch(name='CbtB', is_active=True)
        if b.id is None:
            db.session.add(b); db.session.commit()
        bid_b = b.id
        ex = CBTExam.query.filter_by(title='Central CBT').first()
        if not ex:
            ex = CBTExam(title='Central CBT', exam_date=date.today(), is_published=True)
            db.session.add(ex); db.session.flush()
            sa = Student(student_id='CBA1', first_name='Ca', surname='A', gender='Male',
                         is_active=True, branch_id=bid_a)
            sb = Student(student_id='CBB1', first_name='Cb', surname='B', gender='Male',
                         is_active=True, branch_id=bid_b)
            db.session.add_all([sa, sb]); db.session.flush()
            db.session.add(CBTAttempt(exam_id=ex.id, student_id=sa.id, status='In progress'))
            db.session.add(CBTAttempt(exam_id=ex.id, student_id=sb.id, status='In progress'))
            db.session.commit()
        return dict(exam=ex.id, a=bid_a, b=bid_b)


def _central(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _names(rows):
    return {r['sid'] for r in rows}


def test_central_sees_all_then_filters_by_branch(app):
    ids = _setup(app)
    c = _central(app)
    allrows = c.get(f'/cbt/exams/{ids["exam"]}/monitor/data').get_json()['rows']
    assert {'CBA1', 'CBB1'} <= _names(allrows)                      # all branches by default
    only_b = c.get(f'/cbt/exams/{ids["exam"]}/monitor/data?branch={ids["b"]}').get_json()['rows']
    assert _names(only_b) == {'CBB1'}                               # filtered to branch B


def test_branch_user_restricted_to_own_branch(app):
    ids = _setup(app)
    with app.app_context():
        if not User.query.filter_by(username='cbt_branchA').first():
            u = User(username='cbt_branchA', role='staff', scope='branch',
                     branch_id=ids['a'], full_name='BranchA')
            u.set_password('secret123'); u.set_permissions({'cbt': 'edit'})
            db.session.add(u); db.session.commit()
    c = app.test_client()
    c.post('/login', data={'username': 'cbt_branchA', 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    rows = c.get(f'/cbt/exams/{ids["exam"]}/monitor/data').get_json()['rows']
    assert _names(rows) == {'CBA1'}        # cannot see branch B even without a filter
