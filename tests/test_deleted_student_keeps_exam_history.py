"""A student who sat BECE in JSS3 last session and then left (moved to the
trash) must still count in that year's BECE analysis — deleting a leaver must
never rewrite past results."""
from config import Config
from models import db, Student, Branch
from models.models_school_exams import get_scheme
from tests.conftest import login_token, auth_csrf
from utils import school_exams as svc


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_trashed_leaver_keeps_bece_history(app):
    c = _admin(app)
    year = 2091
    with app.app_context():
        svc.ensure_school_exam_schema()
        sc = get_scheme('jss3', 'state')
        s = Student(student_id='BECE_LEAVER', first_name='Left', surname='Lastsession', gender='Male',
                    is_active=True, branch_id=Branch.get_default().id)
        db.session.add(s); db.session.flush()
        sid = s.id
        rows = [(subj, 70, None) for subj in sc.subjects[:9]]
        svc.save_student_results(sc, sid, year, rows, candidate={'exam_number': 'X/1'})
        db.session.commit()

    def snapshot():
        with app.test_request_context('/'):
            from flask import session
            session['logged_in'] = True
            session['role'] = 'super_admin'
            st = svc.year_stats('jss3', 'state', year)
            return (st['kpis'], len(st['candidates']), st['kind_counts'],
                    [x['subject'] for x in st['subjects']], [x['id'] for x in st['candidates']])

    before = snapshot()
    assert sid in before[4]

    c.post(f'/students/{sid}/delete', data={'_csrf_token': auth_csrf(c)})
    with app.app_context():
        assert db.session.get(Student, sid).is_active is False

    after = snapshot()
    assert after == before                                   # identical analysis
    # the BECE pages still show the candidate
    body = c.get(f'/jss3-exams/?body=state&year={year}').get_data(as_text=True)
    assert 'Lastsession' in body                             # still listed as a candidate
    an = c.get(f'/jss3-exams/analytics?body=state&year={year}')
    assert an.status_code == 200
