"""Mock JAMB exam pages had the same class of N+1 bugs as Mock WAEC:
MockJAMBResult.query.filter_by(...).join(Student) without contains_eager()
(view_exam, export_results), a per-(student) lookup query in the whole-cohort
bulk-entry save/render (bulk_entry — worse than WAEC's grid, since it fired on
every GET too, not just save), jamb_validation() running a JAMBResult query
per candidate per exam in the session, _jamb_records() (behind /deep and
/trends), and item_analysis()'s _served_by_attempt() re-running the exam's
whole subject-pool query once per attempt via candidate_subject_ids(), even
though that query doesn't depend on the student at all."""
import re
import uuid
from datetime import date
from sqlalchemy import event
from config import Config
from models import (db, Student, AcademicSession, JAMBResult, Subject, Branch,
                    SchoolClass, ClassArm, ClassArmAssignment, StudentEnrollment,
                    Term)
from models.mock_jamb import MockJAMBExam, MockJAMBResult, MockJAMBQuestion, MockJAMBAttempt, MockJAMBAnswer
from tests.conftest import login_token, auth_csrf, enroll_sss3

_COHORT_SIZE = 12


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


def _seed(app, tag, with_actual_jamb=False):
    with app.app_context():
        sess = AcademicSession.query.filter_by(is_active=True).first() or \
            AcademicSession(name=f'{tag}-Sess', is_active=True)
        db.session.add(sess); db.session.flush()
        exam = MockJAMBExam(name=f'{tag} Mock', exam_number=1, session_id=sess.id,
                            exam_date=date(2025, 2, 1))
        db.session.add(exam); db.session.flush()
        exam_id = exam.id
        student_ids = []
        for i in range(_COHORT_SIZE):
            s = Student(student_id=f'{tag}{i:03d}', first_name=f'S{i}', surname=f'{tag}',
                       gender='Male', is_active=True)
            db.session.add(s); db.session.flush()
            score = 200 + i
            db.session.add(MockJAMBResult(
                student_id=s.id, mock_exam_id=exam_id, total_score=score,
                subject1='English', subject1_score=60, subject2='Mathematics',
                subject2_score=60, subject3='Physics', subject3_score=40,
                subject4='Chemistry', subject4_score=40))
            if with_actual_jamb:
                db.session.add(JAMBResult(student_id=s.id, exam_year=2025, total_score=score))
            student_ids.append(s.id)
        db.session.commit()
        return exam_id, student_ids


def test_view_exam_does_not_scale_with_cohort_size(app):
    exam_id, student_ids = _seed(app, f'JVN{uuid.uuid4().hex[:6]}')
    c = _admin(app)
    n = _count_selects(app, 'students', lambda: c.get(f'/mock-jamb/exam/{exam_id}'))
    assert n < _COHORT_SIZE, f'{n} Student SELECTs for a {_COHORT_SIZE}-student exam page — looks like an N+1'


def test_export_does_not_scale_with_cohort_size(app):
    exam_id, student_ids = _seed(app, f'JEN{uuid.uuid4().hex[:6]}')
    c = _admin(app)
    n = _count_selects(app, 'students', lambda: c.get(f'/mock-jamb/exam/{exam_id}/export'))
    assert n < _COHORT_SIZE, f'{n} Student SELECTs for a {_COHORT_SIZE}-student export — looks like an N+1'


def test_jamb_validation_does_not_scale_with_cohort_size(app):
    exam_id, student_ids = _seed(app, f'JLN{uuid.uuid4().hex[:6]}', with_actual_jamb=True)
    with app.app_context():
        session_id = db.session.get(MockJAMBExam, exam_id).session_id
    c = _admin(app)
    url = f'/mock-jamb/validation?mock_exam_id={exam_id}&session_id={session_id}'
    n = _count_selects(app, 'jamb_results', lambda: c.get(url))
    assert n < _COHORT_SIZE, f'{n} JAMBResult SELECTs for a {_COHORT_SIZE}-candidate validation page — looks like an N+1'
    html = c.get(url).get_data(as_text=True)
    assert 'Validation' in html or 'validation' in html.lower()


def test_bulk_entry_render_does_not_scale_with_cohort_size(app):
    """bulk_entry() built its `students` list (including an existing-result
    lookup per student) on every GET, not just on save."""
    exam_id, student_ids = _seed(app, f'JBN{uuid.uuid4().hex[:6]}')
    with app.app_context():
        new_ids = []
        for i in range(_COHORT_SIZE):
            s = Student(student_id=f'JBX{uuid.uuid4().hex[:5]}{i}', first_name=f'B{i}',
                       surname='Bulk', gender='Male', is_active=True)
            db.session.add(s); db.session.flush()
            new_ids.append(s.id)
        db.session.commit()
    for sid in new_ids:
        enroll_sss3(app, sid)
    c = _admin(app)
    n = _count_selects(app, 'mock_jamb_results', lambda: c.get(f'/mock-jamb/exam/{exam_id}/results/bulk'))
    assert n < _COHORT_SIZE, f'{n} MockJAMBResult SELECTs for a {_COHORT_SIZE}-student bulk-entry GET — looks like an N+1'


def test_item_analysis_subject_pool_query_not_repeated_per_attempt(app):
    """_served_by_attempt() used to call candidate_subject_ids() (2 queries,
    including one that doesn't even depend on the student) once per attempt."""
    from utils.mock_jamb_item_analysis import item_analysis
    with app.app_context():
        tag = f'JIA{uuid.uuid4().hex[:6]}'
        bid = Branch.get_default().id
        subj = Subject.query.filter_by(name='Physics').first() or Subject(name='Physics', is_active=True)
        db.session.add(subj); db.session.flush()
        sess = AcademicSession(name=f'{tag}-Sess'); db.session.add(sess); db.session.flush()
        exam = MockJAMBExam(name=f'{tag} Mock', exam_number=1, session_id=sess.id,
                            exam_date=date(2025, 3, 1), branch_id=bid, is_published=True,
                            duration_minutes=90)
        db.session.add(exam); db.session.flush()
        q1 = MockJAMBQuestion(mock_exam_id=exam.id, subject_id=subj.id, question_text='Q1',
                              option_a='a', option_b='b', option_c='c', option_d='d',
                              correct_option='A', marks=1, order=1, topic='Motion')
        db.session.add(q1); db.session.flush()

        for i in range(_COHORT_SIZE):
            st = Student(student_id=f'{tag}{i:03d}', first_name=f'S{i}', surname='X',
                        gender='Male', is_active=True, branch_id=bid, jamb_subjects='Physics')
            db.session.add(st); db.session.flush()
            att = MockJAMBAttempt(mock_exam_id=exam.id, student_id=st.id, status='Submitted',
                                  total_score=200)
            db.session.add(att); db.session.flush()
            db.session.add(MockJAMBAnswer(attempt_id=att.id, question_id=q1.id,
                                          selected_option='A', is_correct=True))
        db.session.commit()
        exam_id = exam.id

    with app.app_context():
        n = _count_selects(app, 'subjects', lambda: item_analysis(exam_id))
        assert n <= 2, f'{n} Subject SELECTs for {_COHORT_SIZE} attempts on one exam — the subject pool is being re-fetched per attempt'
