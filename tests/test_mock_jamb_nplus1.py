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


def _seed_multi_subject_sitting(app, tag):
    """One student registered for 4 JAMB subjects (English + 3 electives),
    each with a couple of questions, and a portal password set — enough to
    exercise sitting_payload()'s per-subject Subject lookup with more than
    one subject."""
    from tests.test_mock_jamb_sitting import _portal_login
    with app.app_context():
        bid = Branch.get_default().id
        subject_names = ['English Language', 'Mathematics', 'Physics', 'Chemistry']
        subjects = []
        for name in subject_names:
            subj = Subject.query.filter_by(name=f'{tag}{name}').first() or \
                Subject(name=f'{tag}{name}', is_active=True)
            db.session.add(subj)
            subjects.append(subj)
        db.session.flush()
        sess = AcademicSession(name=f'{tag}-Sess')
        db.session.add(sess); db.session.flush()
        exam = MockJAMBExam(name=f'{tag} Mock', exam_number=1, session_id=sess.id,
                            exam_date=date(2025, 3, 1), branch_id=bid,
                            is_published=True, duration_minutes=90)
        db.session.add(exam); db.session.flush()
        for subj in subjects:
            for i in range(2):
                db.session.add(MockJAMBQuestion(
                    mock_exam_id=exam.id, subject_id=subj.id, question_text=f'{subj.name} Q{i+1}',
                    option_a='a', option_b='b', option_c='c', option_d='d',
                    correct_option='A', marks=1, order=i + 1))
        student = Student(student_id=f'{tag}ST', first_name='Sit', surname=tag,
                          gender='Male', is_active=True, branch_id=bid,
                          jamb_subjects=', '.join(f'{tag}{n}' for n in subject_names))
        db.session.add(student); db.session.commit()
        return exam.id, student.id


def test_portal_sit_does_not_scale_with_subject_count(app):
    from tests.test_mock_jamb_sitting import _portal_login
    exam_id, student_id = _seed_multi_subject_sitting(app, f'PS{uuid.uuid4().hex[:6]}')
    c = _portal_login(app, student_id)
    n = _count_selects(app, 'subjects', lambda: c.get(f'/exam/mock-jamb/{exam_id}'))
    assert n <= 2, (
        f'{n} Subject SELECTs sitting a 4-subject mock — sitting_payload() looks '
        f'like it fetches each subject with its own query instead of one batched IN')


def _seed_many_bank_exams(app, tag, n_exams=6):
    """One student, one bank-drawn subject with a couple of stand-alone
    questions, and several PUBLISHED bank-drawn mocks (no exam-owned
    questions) that all share that identical bank pool -- what a school
    running several concurrent/rolling mocks looks like."""
    with app.app_context():
        bid = Branch.get_default().id
        subj = Subject(name=f'{tag}Physics', is_active=True)
        db.session.add(subj); db.session.flush()
        for i in range(2):
            db.session.add(MockJAMBQuestion(
                mock_exam_id=None, subject_id=subj.id, question_text=f'{tag} Q{i+1}',
                option_a='a', option_b='b', option_c='c', option_d='d',
                correct_option='A', marks=1, order=i + 1))
        exam_ids = []
        for i in range(n_exams):
            sess = AcademicSession(name=f'{tag}-Sess{i}')
            db.session.add(sess); db.session.flush()
            exam = MockJAMBExam(name=f'{tag} Mock {i}', exam_number=1, session_id=sess.id,
                                exam_date=date(2025, 4, 1), branch_id=bid,
                                is_published=True, is_active=True, duration_minutes=90)
            db.session.add(exam); db.session.flush()
            exam_ids.append(exam.id)
        student = Student(student_id=f'{tag}ST', first_name='Many', surname=tag,
                          gender='Male', is_active=True, branch_id=bid,
                          jamb_subjects=subj.name)
        db.session.add(student); db.session.commit()
        return exam_ids, student.id


def test_portal_list_does_not_scale_with_exam_count(app, monkeypatch):
    """Every student hits this landing page before sitting anything -- with many
    students loading it around the same time, an N+1 per exam multiplies fast.
    Each bank-drawn exam shares the identical question-pool query, so the
    per-exam Subject/attempt lookups must not scale with how many published
    mocks exist. Counts calls to exam_subject_pool() directly (rather than raw
    'subjects' SELECTs) so this isn't thrown off by other tests' leftover
    published exams sharing the session-scoped test DB -- those get their own,
    legitimately separate pool-cache entry and must not inflate this count."""
    import utils.mock_jamb_sitting as mjs
    from tests.test_mock_jamb_sitting import _portal_login
    exam_ids, student_id = _seed_many_bank_exams(app, f'PL{uuid.uuid4().hex[:6]}', n_exams=6)
    c = _portal_login(app, student_id)

    calls = {'bank': 0}
    real_pool = mjs.exam_subject_pool
    def _counting(exam):
        if not mjs._exam_owns_questions(exam):
            calls['bank'] += 1
        return real_pool(exam)
    monkeypatch.setattr(mjs, 'exam_subject_pool', _counting)

    r = c.get('/exam/mock-jamb/')
    assert r.status_code == 200
    assert calls['bank'] <= 1, (
        f"exam_subject_pool() called {calls['bank']}x for the shared bank pool across "
        f"{len(exam_ids)} bank-drawn mocks -- looks like it's being re-fetched once per exam "
        f"instead of cached")

    n_att = _count_selects(app, 'mock_jamb_attempts', lambda: c.get('/exam/mock-jamb/'))
    assert n_att <= 2, (
        f'{n_att} mock_jamb_attempts SELECTs listing {len(exam_ids)} mocks -- attempts look '
        f'like they are fetched one exam at a time instead of one batched IN query')
    html = c.get('/exam/mock-jamb/').get_data(as_text=True)
    assert html.count('First Mock JAMB') >= len(exam_ids)   # every exam still rendered


def test_grade_attempt_does_not_rescan_pool_per_submission(app):
    """grade_attempt() used to call candidate_subject_ids() on EVERY submission --
    which reruns exam_subject_pool()'s exam-wide, student-independent DISTINCT
    scan of the question pool -- exactly the moment a whole cohort auto-submits
    near the timer deadline. Once an attempt's paper is cached (always true by
    submission time), grading must read the subject list straight from it."""
    from utils.mock_jamb_sitting import grade_attempt, sitting_payload
    tag = f'GA{uuid.uuid4().hex[:6]}'
    with app.app_context():
        bid = Branch.get_default().id
        subj = Subject(name=f'{tag}Physics', is_active=True)
        db.session.add(subj); db.session.flush()
        q = MockJAMBQuestion(mock_exam_id=None, subject_id=subj.id, question_text='Q1',
                             option_a='a', option_b='b', option_c='c', option_d='d',
                             correct_option='A', marks=1, order=1)
        db.session.add(q); db.session.flush()
        sess = AcademicSession(name=f'{tag}-Sess'); db.session.add(sess); db.session.flush()
        exam = MockJAMBExam(name=f'{tag} Mock', exam_number=1, session_id=sess.id,
                            exam_date=date(2025, 5, 1), branch_id=bid,
                            is_published=True, is_active=True, duration_minutes=90)
        db.session.add(exam); db.session.flush()
        exam_id, subj_id = exam.id, subj.id

        att_ids = []
        for i in range(_COHORT_SIZE):
            st = Student(student_id=f'{tag}{i:03d}', first_name=f'S{i}', surname=tag,
                        gender='Male', is_active=True, branch_id=bid, jamb_subjects=subj.name)
            db.session.add(st); db.session.flush()
            att = MockJAMBAttempt(mock_exam_id=exam_id, student_id=st.id, duration_minutes=90)
            db.session.add(att); db.session.flush()
            # draw + cache the paper exactly as portal_sit's first render would.
            sitting_payload(db.session.get(MockJAMBExam, exam_id), [subj_id], att)
            att_ids.append(att.id)
        db.session.commit()

    def _grade_all():
        with app.app_context():
            for aid in att_ids:
                grade_attempt(db.session.get(MockJAMBAttempt, aid))

    n = _count_selects(app, 'mock_jamb_questions', _grade_all)
    # Each attempt legitimately costs 2 mock_jamb_questions SELECTs even fully
    # fixed (rebuilding the cached paper + fetching the served rows to mark) --
    # anywhere near 3 per attempt means the pool-wide scan is still running once
    # per submission on top of that.
    assert n <= 2 * _COHORT_SIZE + 2, (
        f'{n} mock_jamb_questions SELECTs grading {_COHORT_SIZE} attempts on one exam -- '
        f'grade_attempt() looks like it re-runs the exam-wide subject-pool scan per submission')


def test_portal_guard_caches_eligibility_across_the_sitting(app, monkeypatch):
    """_portal_guard() calls student_eligible() (2 queries: class placement +
    the mock's eligible-class lookup) on EVERY request -- including every
    autosave, which fires every ~1-30s for the whole exam duration across a
    whole cohort. The verdict can't change mid-sitting, so it must be cached
    (in the student's own session) after the first check, not re-derived on
    every save."""
    from tests.test_mock_jamb_sitting import _build_exam, _portal_login
    eid, sid, eng_id, mth_id = _build_exam(app)
    c = _portal_login(app, sid)

    calls = {'n': 0}
    real = __import__('utils.mock_jamb_sitting', fromlist=['student_eligible']).student_eligible
    def _counting(*a, **k):
        calls['n'] += 1
        return real(*a, **k)
    monkeypatch.setattr('utils.mock_jamb_sitting.student_eligible', _counting)

    r1 = c.get(f'/exam/mock-jamb/{eid}')
    assert r1.status_code == 200
    assert calls['n'] == 1, f'student_eligible() called {calls["n"]}x on first load -- expected exactly 1'

    r2 = c.get(f'/exam/mock-jamb/{eid}')
    assert r2.status_code == 200
    assert calls['n'] == 1, (
        f'student_eligible() called again on a reload ({calls["n"]} total) -- the '
        f'per-exam eligibility cache in _portal_guard() looks like it is not being hit')


def test_portal_sit_survives_concurrent_attempt_creation_race(app, monkeypatch):
    """Two near-simultaneous requests for the same (exam, student) -- a double
    click on Start, or a client retry over a flaky school connection, both of
    which get more likely exactly when a whole cohort starts together -- must
    not 500 on the unique_mock_attempt constraint. Simulates the race
    deterministically: a "concurrent" row is inserted via a raw connection the
    instant our own commit fires, so our own commit hits the real unique-
    constraint violation exactly as a second real request would."""
    from tests.test_mock_jamb_sitting import _build_exam, _portal_login
    from models import db, MockJAMBAttempt
    from sqlalchemy import text
    eid, sid, eng_id, mth_id = _build_exam(app)
    c = _portal_login(app, sid)

    real_commit = db.session.commit
    fired = {'n': 0}

    def _racing_commit(*a, **k):
        if fired['n'] == 0:
            fired['n'] += 1
            with app.app_context():
                with db.engine.begin() as conn:
                    conn.execute(text(
                        "INSERT INTO mock_jamb_attempts "
                        "(mock_exam_id, student_id, duration_minutes, status, total_score) "
                        "VALUES (:eid, :sid, 90, 'In progress', 0)"), {'eid': eid, 'sid': sid})
        return real_commit(*a, **k)

    monkeypatch.setattr(db.session, 'commit', _racing_commit)
    r = c.get(f'/exam/mock-jamb/{eid}')
    assert r.status_code == 200, f'race produced a {r.status_code} instead of falling back to the winning row'

    with app.app_context():
        rows = MockJAMBAttempt.query.filter_by(mock_exam_id=eid, student_id=sid).all()
        assert len(rows) == 1, f'{len(rows)} attempts survived the race -- expected exactly 1'


def test_portal_sit_questions_do_not_get_reloaded_after_cache_commit(app):
    """The paper-persisting db.session.commit() in portal_sit() must not expire
    the Question objects already loaded into the payload — otherwise the very
    next line (show_calc) and the template render force a fresh reload of
    every question sitting_payload() just fetched (one SELECT per question,
    not per subject). A first-time draw legitimately costs one pool-fetch
    query per subject (4 here) plus one subject-discovery query — that part
    is bounded by subject count, not question count, and reloads/resume reuse
    the cached paper via cheap PK lookups instead of re-scanning the pool."""
    from tests.test_mock_jamb_sitting import _portal_login
    exam_id, student_id = _seed_multi_subject_sitting(app, f'PQ{uuid.uuid4().hex[:6]}')
    c = _portal_login(app, student_id)
    n = _count_selects(app, 'mock_jamb_questions', lambda: c.get(f'/exam/mock-jamb/{exam_id}'))
    # 4 subjects: 1 discovery query + up to 1 fresh pool-draw query per subject.
    # Anywhere near double this (e.g. 14) means the post-fetch commit is
    # expiring and reloading questions one at a time.
    assert n <= 7, (
        f'{n} mock_jamb_questions SELECTs sitting a 4-subject/8-question mock — '
        f'the paper-cache commit in portal_sit() looks like it is expiring '
        f'already-loaded Question objects, forcing a reload per question')
