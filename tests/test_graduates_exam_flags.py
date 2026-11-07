"""Graduates list: each graduate shows whether WAEC, NECO and JAMB results exist."""
import uuid

from config import Config
from models import db, Student, WAECResult, NECOResult
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    return c


def test_graduates_list_flags_neco_results(app):
    with app.app_context():
        tag = uuid.uuid4().hex[:6].upper()
        a = Student(student_id='GN' + tag, first_name='Necoone', surname='Grad', gender='Male', is_graduated=True)
        b = Student(student_id='GW' + tag, first_name='Waeconly', surname='Grad', gender='Female', is_graduated=True)
        db.session.add_all([a, b]); db.session.flush()
        db.session.add(NECOResult(student_id=a.id, exam_year=2025, subject='Mathematics', grade='B2'))
        db.session.add(WAECResult(student_id=b.id, exam_year=2025, subject='Mathematics', grade='C4'))
        db.session.commit()
        ids = {a.id: 'a', b.id: 'b'}
    c = _admin(app)
    r = c.get('/promotion/graduates', headers={'X-Requested-With': 'fetch'})
    body = r.get_json()
    data = body.get('data', body)
    rows = {ids[g['id']]: g for g in data['graduates'] if g['id'] in ids}
    assert rows['a']['has_neco'] is True and rows['a']['has_waec'] is False and rows['a']['has_jamb'] is False
    assert rows['b']['has_neco'] is False and rows['b']['has_waec'] is True


def test_graduate_profile_lists_neco_results(app):
    with app.app_context():
        tag = uuid.uuid4().hex[:6].upper()
        s = Student(student_id='GP' + tag, first_name='Necoprof', surname='Grad', gender='Male',
                    is_graduated=True, neco_reg_number='NR' + tag)
        db.session.add(s); db.session.flush()
        db.session.add_all([NECOResult(student_id=s.id, exam_year=2025, subject='Mathematics', grade='A1'),
                            NECOResult(student_id=s.id, exam_year=2025, subject='Biology', grade='C5')])
        db.session.commit()
        sid = s.id
    c = _admin(app)
    body = c.get(f'/promotion/graduates/{sid}', headers={'X-Requested-With': 'fetch'}).get_json()
    data = body.get('data', body)
    assert data['neco_by_year'] == [{'exam_year': 2025, 'exam_number': 'NR' + tag,
                                     'subjects': [{'subject': 'Biology', 'grade': 'C5'},
                                                  {'subject': 'Mathematics', 'grade': 'A1'}]}]
    assert 'student_id=%d' % sid in data['urls']['add_neco']


def test_student_profile_always_has_neco_card(app):
    with app.app_context():
        s = Student(student_id='NP' + uuid.uuid4().hex[:6].upper(), first_name='Noneco', surname='Pupil',
                    gender='Female')
        db.session.add(s); db.session.commit()
        sid = s.id
    c = _admin(app)
    body = c.get(f'/api/students/{sid}').get_json()
    data = body.get('data', body)
    assert data['neco']['count'] == 0
    assert 'student_id=%d' % sid in data['neco']['add_url']
