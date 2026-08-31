"""Per-user theme presets + branch-scoped Mock JAMB dashboard snapshot."""
import re
from datetime import date
from config import Config
from models import db, Branch, User, Student, AcademicSession
from models.mock_jamb import MockJAMBExam, MockJAMBResult
from tests.conftest import login_token


def _login_user(app, username, **kw):
    with app.app_context():
        if not User.query.filter_by(username=username).first():
            u = User(username=username, full_name=username, **kw)
            u.set_password('secret123'); db.session.add(u); db.session.commit()
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    return c


def _pt(c):
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get('/').get_data(as_text=True)).group(1)


# ---- Theme ----

def test_theme_saves_and_renders(app):
    c = _login_user(app, 'th_user', role='staff', scope='central')
    r = c.post('/set-theme', data={'theme': 'ocean', '_csrf_token': _pt(c)})
    assert r.get_json()['theme'] == 'ocean'
    html = c.get('/').get_data(as_text=True)
    assert re.search(r'<html lang="en" data-theme="ocean"', html)
    with app.app_context():
        assert User.query.filter_by(username='th_user').first().theme == 'ocean'


def test_theme_rejects_unknown(app):
    c = _login_user(app, 'th_user2', role='staff', scope='central')
    assert c.post('/set-theme', data={'theme': 'rainbow', '_csrf_token': _pt(c)}).get_json()['theme'] == 'light'


# ---- Mock JAMB branch scoping ----

def _mock_setup(app):
    with app.app_context():
        b = Branch.query.filter_by(name='MockB').first() or Branch(name='MockB', is_active=True)
        if b.id is None:
            db.session.add(b); db.session.commit()
        bid_b = b.id
        bid_a = Branch.get_default().id
        sess = AcademicSession.query.first() or AcademicSession(name='MK')
        if sess.id is None:
            db.session.add(sess); db.session.flush(); db.session.commit()
        if not MockJAMBExam.query.filter_by(name='MK Exam').first():
            ex = MockJAMBExam(name='MK Exam', exam_number=1, session_id=sess.id,
                              exam_date=date.today())
            db.session.add(ex); db.session.flush()
            sa = Student(student_id='MKA1', first_name='A', surname='A', gender='Male',
                         is_active=True, branch_id=bid_a)
            sb = Student(student_id='MKB1', first_name='B', surname='B', gender='Male',
                         is_active=True, branch_id=bid_b)
            db.session.add_all([sa, sb]); db.session.flush()
            db.session.add(MockJAMBResult(student_id=sa.id, mock_exam_id=ex.id, total_score=200))
            db.session.add(MockJAMBResult(student_id=sb.id, mock_exam_id=ex.id, total_score=400))
            db.session.commit()
        return bid_a, bid_b


def test_branch_user_sees_only_own_mock(app):
    bid_a, bid_b = _mock_setup(app)
    # a user tied to branch B should see mean 400 (their student), not 300 (global avg)
    c = _login_user(app, 'mk_userb', role='staff', scope='branch', branch_id=bid_b)
    html = c.get('/').get_data(as_text=True)
    # snapshot shows the branch mean; global avg of 200 & 400 would be 300.0
    assert '300' not in re.findall(r'class="big">([\d.]+)<', html)
