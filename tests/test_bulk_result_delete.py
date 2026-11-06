"""Delete several students' exam results at once (WAEC, JAMB, JSS3 / Basic 6)."""
import uuid

from config import Config
from models import db, Student, WAECResult, JAMBResult
from models.models_school_exams import SchoolExamResult, SchoolExamCandidate
from tests.conftest import login_token, auth_csrf, enroll_sss3


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _students(app, n, tag):
    with app.app_context():
        out = []
        for i in range(n):
            s = Student(student_id=f'BD{tag}{uuid.uuid4().hex[:5]}', first_name=f'{tag}{i}',
                        surname='Bulkdel', gender='Male')
            db.session.add(s); db.session.flush(); out.append(s.id)
        db.session.commit()
        return out


def test_waec_bulk_delete_only_selected_students_and_year(app):
    a, b, keep = _students(app, 3, 'W')
    with app.app_context():
        for sid in (a, b, keep):
            for y in (2032, 2033):
                db.session.add(WAECResult(student_id=sid, exam_year=y, subject='Mathematics', grade='B3'))
                db.session.add(WAECResult(student_id=sid, exam_year=y, subject='Biology', grade='C4'))
        db.session.commit()
    for sid in (a, b, keep):
        enroll_sss3(app, sid)
    c = _admin(app)
    html = c.get('/results/waec?year=2033').get_data(as_text=True)
    assert 'id="bulkDel"' in html and f'name="ids" value="{a}" form="bulkDel"' in html
    r = c.post('/results/waec/delete-bulk', data={'_csrf_token': auth_csrf(c), 'year': 2033,
                                                  'ids': [str(a), str(b), str(a), 'junk']})
    assert r.status_code == 302 and 'year=2033' in r.headers['Location']
    with app.app_context():
        left = {(w.student_id, w.exam_year) for w in WAECResult.query.filter(
            WAECResult.student_id.in_([a, b, keep]))}
    assert left == {(a, 2032), (b, 2032), (keep, 2032), (keep, 2033)}


def test_jamb_bulk_delete(app):
    a, b, keep = _students(app, 3, 'J')
    with app.app_context():
        for sid in (a, b, keep):
            db.session.add(JAMBResult(student_id=sid, exam_year=2033, total_score=220))
        db.session.commit()
    c = _admin(app)
    r = c.post('/results/jamb/delete-bulk', data={'_csrf_token': auth_csrf(c), 'year': 2033,
                                                  'ids': [str(a), str(b)]})
    assert r.status_code == 302
    with app.app_context():
        assert {j.student_id for j in JAMBResult.query.filter(
            JAMBResult.student_id.in_([a, b, keep]))} == {keep}


def test_jss3_bulk_delete_removes_results_and_sitting_for_that_body_only(app):
    from tests.test_school_exams import _enroll
    a, b, keep = _students(app, 3, 'S')
    for sid in (a, b, keep):
        _enroll(app, 'JSS3', 3, sid)
    c = _admin(app)
    tok = auth_csrf(c)
    for sid in (a, b, keep):
        for body in ('state', 'federal'):
            c.post(f'/jss3-exams/{body}/add', data={
                '_csrf_token': tok, 'student_id': sid, 'exam_year': 2033, 'exam_number': f'X{sid}',
                'subject[]': ['Mathematics', 'English Studies'], 'score[]': ['60', '55'], 'grade[]': ['', '']})
    html = c.get('/jss3-exams/?body=state&year=2033').get_data(as_text=True)
    assert 'id="bulkDel"' in html and f'value="{a}" form="bulkDel"' in html
    r = c.post('/jss3-exams/state/delete-bulk', data={'_csrf_token': tok, 'year': 2033,
                                                      'ids': [str(a), str(b)]})
    assert r.status_code == 302
    with app.app_context():
        rows = {(x.student_id, x.body) for x in SchoolExamResult.query.filter(
            SchoolExamResult.student_id.in_([a, b, keep]), SchoolExamResult.exam_year == 2033)}
        cands = {(x.student_id, x.body) for x in SchoolExamCandidate.query.filter(
            SchoolExamCandidate.student_id.in_([a, b, keep]))}
    assert rows == {(a, 'federal'), (b, 'federal'), (keep, 'state'), (keep, 'federal')}
    assert cands == rows
    # Basic 6's endpoint exists separately and touches only Basic 6.
    assert c.post('/basic6-exams/state/delete-bulk', data={'_csrf_token': tok, 'year': 2033,
                                                          'ids': [str(keep)]}).status_code == 302
    with app.app_context():
        assert SchoolExamResult.query.filter_by(student_id=keep, level='jss3').count() == 4


def test_bulk_delete_endpoints_are_delete_permissions():
    from utils.access_control import subsection_for_endpoint
    assert subsection_for_endpoint('results.delete_waec_bulk') == ('external_exams', 'waec_delete')
    assert subsection_for_endpoint('results.delete_jamb_bulk') == ('external_exams', 'jamb_delete')
    assert subsection_for_endpoint('jss3_exams.delete_bulk') == ('external_exams', 'jss3_delete')
    assert subsection_for_endpoint('basic6_exams.delete_bulk') == ('external_exams', 'basic6_delete')
