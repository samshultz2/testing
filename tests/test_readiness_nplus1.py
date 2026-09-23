"""The SSS3 exam-readiness checklist (/results/readiness) used to call
.mock_jamb_results.count()/.all() and .mock_waec_results.count() per student
— each a fresh SELECT (both relationships are lazy='dynamic', so unlike a
scalar relationship there's no identity-map reuse). Regression: a whole-cohort
page load fires a small, constant number of mock-result SELECTs, not one (or
two) per student."""
import re
from datetime import date
from sqlalchemy import event
from config import Config
from models import (db, Branch, Student, AcademicSession, MockJAMBExam,
                    MockJAMBResult, MockWAECExam, MockWAECResult)
from tests.conftest import login_token, enroll_sss3

_COHORT_SIZE = 10
_SEQ = [0]


def _count_selects(app, table, fn):
    pattern = re.compile(r'^select\b.*\bfrom\s+' + re.escape(table) + r'\b',
                         re.IGNORECASE | re.DOTALL)
    counts = {'n': 0}

    def before(conn, cursor, statement, params, context, executemany):
        if pattern.match(statement):
            counts['n'] += 1
    with app.app_context():
        engine = db.engine
    event.listen(engine, 'before_cursor_execute', before)
    try:
        fn()
    finally:
        event.remove(engine, 'before_cursor_execute', before)
    return counts['n']


def _setup(app):
    with app.app_context():
        _SEQ[0] += 1
        bid = Branch.get_default().id
        sess = AcademicSession.query.filter_by(is_active=True).first()
        if not sess:
            sess = AcademicSession(name=f'RDN-Sess-{_SEQ[0]}', is_active=True)
            db.session.add(sess); db.session.flush()
        sess_id = sess.id
        jexam = MockJAMBExam(name=f'RDN-JAMB-{_SEQ[0]}', exam_number=1000 + _SEQ[0],
                             session_id=sess_id, exam_date=date(2025, 3, 1), branch_id=bid)
        wexam = MockWAECExam(name=f'RDN-WAEC-{_SEQ[0]}', exam_number=1000 + _SEQ[0],
                             session_id=sess_id, exam_date=date(2025, 3, 1), branch_id=bid)
        db.session.add_all([jexam, wexam]); db.session.flush()
        jid, wid = jexam.id, wexam.id

        student_ids = []
        for i in range(_COHORT_SIZE):
            s = Student(student_id=f'RDN{_SEQ[0]}{i:03d}', first_name=f'R{i}', surname='Ready',
                       gender='Male', is_active=True, branch_id=bid,
                       stream='Science', jamb_target=200)
            db.session.add(s); db.session.flush()
            db.session.add(MockJAMBResult(student_id=s.id, mock_exam_id=jid, total_score=250))
            db.session.add(MockWAECResult(student_id=s.id, mock_exam_id=wid, subject='English', score=80))
            student_ids.append(s.id)
        db.session.commit()
    for sid in student_ids:
        enroll_sss3(app, sid)
    return student_ids


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_readiness_does_not_scale_with_cohort_size(app):
    _setup(app)
    c = _admin(app)

    n = _count_selects(app, 'mock_jamb_results', lambda: c.get('/results/readiness'))
    assert n < _COHORT_SIZE, f'{n} MockJAMBResult SELECTs for a {_COHORT_SIZE}-student cohort — looks like an N+1'

    n2 = _count_selects(app, 'mock_waec_results', lambda: c.get('/results/readiness'))
    assert n2 < _COHORT_SIZE, f'{n2} MockWAECResult SELECTs — looks like an N+1'

    html = c.get('/results/readiness').get_data(as_text=True)
    assert html  # smoke: page still renders with the batched data
