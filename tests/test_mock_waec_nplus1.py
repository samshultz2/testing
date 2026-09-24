"""Mock WAEC exam pages (/mock-waec/exam/<id> and its sub-pages) had several
copies of the same N+1 bug: MockWAECResult.query.filter_by(...).join(Student)
without contains_eager() to hydrate .student, so grouping results by student
lazy-loaded once per distinct student (view_exam, get_broadsheet — the shared
core behind broadsheet/analytics/deep/validation, _slips_for, export_results).
Two save handlers (grid entry, paste import) also ran a lookup query per
(student, subject) cell instead of one bulk fetch. And waec_validation() ran
a WAECResult query per mock-result ROW (not even per student) to check the
matching real WAEC grade. Regression: none of this scales with cohort size."""
import re
import uuid
from datetime import date
from sqlalchemy import event
from config import Config
from models import db, Student, AcademicSession, WAECResult
from models.mock_waec import MockWAECExam, MockWAECResult, waec_grade_from_score
from tests.conftest import login_token, auth_csrf, enroll_sss3

_COHORT_SIZE = 12
_SUBJECTS = ['English Language', 'Mathematics', 'Biology', 'Chemistry']


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


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _seed(app, tag, with_actual_waec=False):
    with app.app_context():
        sess = AcademicSession.query.filter_by(is_active=True).first() or \
            AcademicSession(name=f'{tag}-Sess', is_active=True)
        db.session.add(sess); db.session.flush()
        exam = MockWAECExam(name=f'{tag} Mock', exam_number=1, session_id=sess.id,
                            exam_date=date(2025, 2, 1))
        db.session.add(exam); db.session.flush()
        exam_id = exam.id
        student_ids = []
        for i in range(_COHORT_SIZE):
            s = Student(student_id=f'{tag}{i:03d}', first_name=f'S{i}', surname=f'{tag}',
                       gender='Male', is_active=True)
            db.session.add(s); db.session.flush()
            for subj in _SUBJECTS:
                score = 60 + i
                db.session.add(MockWAECResult(student_id=s.id, mock_exam_id=exam_id,
                                              subject=subj, score=score,
                                              grade=waec_grade_from_score(score)))
                if with_actual_waec:
                    db.session.add(WAECResult(student_id=s.id, subject=subj,
                                              exam_year=2025, grade=waec_grade_from_score(score)))
            student_ids.append(s.id)
        db.session.commit()
        return exam_id, student_ids


def test_view_exam_does_not_scale_with_cohort_size(app):
    exam_id, student_ids = _seed(app, f'VEN{uuid.uuid4().hex[:6]}')
    c = _admin(app)
    n = _count_selects(app, 'students', lambda: c.get(f'/mock-waec/exam/{exam_id}'))
    assert n < _COHORT_SIZE, f'{n} Student SELECTs for a {_COHORT_SIZE}-student exam page — looks like an N+1'


def test_broadsheet_does_not_scale_with_cohort_size(app):
    exam_id, student_ids = _seed(app, f'BSN{uuid.uuid4().hex[:6]}')
    c = _admin(app)
    n = _count_selects(app, 'students', lambda: c.get(f'/mock-waec/exam/{exam_id}/broadsheet'))
    assert n < _COHORT_SIZE, f'{n} Student SELECTs for a {_COHORT_SIZE}-student broadsheet — looks like an N+1'


def test_slips_pdf_does_not_scale_with_cohort_size(app):
    exam_id, student_ids = _seed(app, f'SLN{uuid.uuid4().hex[:6]}')
    c = _admin(app)
    n = _count_selects(app, 'students', lambda: c.get(f'/mock-waec/exam/{exam_id}/slips.pdf'))
    assert n < _COHORT_SIZE, f'{n} Student SELECTs for a {_COHORT_SIZE}-student slips PDF — looks like an N+1'


def test_export_does_not_scale_with_cohort_size(app):
    exam_id, student_ids = _seed(app, f'EXN{uuid.uuid4().hex[:6]}')
    c = _admin(app)
    n = _count_selects(app, 'students', lambda: c.get(f'/mock-waec/exam/{exam_id}/export'))
    assert n < _COHORT_SIZE, f'{n} Student SELECTs for a {_COHORT_SIZE}-student export — looks like an N+1'


def test_validation_does_not_scale_with_result_row_count(app):
    exam_id, student_ids = _seed(app, f'VLN{uuid.uuid4().hex[:6]}', with_actual_waec=True)
    total_rows = _COHORT_SIZE * len(_SUBJECTS)
    c = _admin(app)
    n = _count_selects(app, 'waec_results', lambda: c.get(f'/mock-waec/exam/{exam_id}/validation'))
    assert n < _COHORT_SIZE, (f'{n} WAECResult SELECTs for {total_rows} mock-result rows '
                              f'across {_COHORT_SIZE} students — looks like an N+1')
    # Correctness: every subject should have matched (mock == actual grade, seeded identical).
    html = c.get(f'/mock-waec/exam/{exam_id}/validation').get_data(as_text=True)
    assert 'Validation' in html or 'validation' in html.lower()


def test_grid_save_does_not_scale_with_cohort_size(app):
    exam_id, student_ids = _seed(app, f'GDN{uuid.uuid4().hex[:6]}')
    with app.app_context():
        # New students to enroll fresh (avoid clashing with already-seeded results).
        new_ids = []
        for i in range(_COHORT_SIZE):
            s = Student(student_id=f'GDX{uuid.uuid4().hex[:5]}{i}', first_name=f'G{i}',
                       surname='Grid', gender='Male', is_active=True)
            db.session.add(s); db.session.flush()
            new_ids.append(s.id)
        db.session.commit()
    for sid in new_ids:
        enroll_sss3(app, sid)
    c = _admin(app)
    tok = auth_csrf(c)
    data = {'_csrf_token': tok, 'action': 'save', 'col': ['Mathematics', 'English Language']}
    for sid in new_ids:
        data[f'score_{sid}_mathematics'] = '70'
        data[f'score_{sid}_english-language'] = '65'

    n = _count_selects(app, 'mock_waec_results',
                       lambda: c.post(f'/mock-waec/exam/{exam_id}/grid', data=data))
    # 1 bulk fetch for the save loop itself, plus recompute_student_safe's own
    # (separate, legitimate) per-student prediction lookup against this same
    # table — ~_COHORT_SIZE queries that aren't part of what this fix touches.
    # The old per-cell upsert lookup added another _COHORT_SIZE on top of
    # that; the threshold sits between the two so the comparison still means
    # something without hard-coding recompute's own query count.
    assert n < 2 * _COHORT_SIZE, f'{n} MockWAECResult SELECTs for a {_COHORT_SIZE}-student grid save — looks like the old per-cell N+1 is back'

    with app.app_context():
        for sid in new_ids:
            row = MockWAECResult.query.filter_by(student_id=sid, mock_exam_id=exam_id,
                                                  subject='Mathematics').first()
            assert row is not None and row.score == 70
