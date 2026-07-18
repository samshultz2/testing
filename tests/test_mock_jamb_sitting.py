"""Mock JAMB online sitting — publish, the student portal flow (start → save →
submit), grading into MockJAMBResult, and permission gating."""
from datetime import date
from config import Config
from models import (db, Subject, Branch, AcademicSession, Student, MockJAMBExam,
                    MockJAMBQuestion, MockJAMBAttempt, MockJAMBResult)
from tests.conftest import login_token

_SEQ = [0]


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _csrf(c):
    import re
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', c.get('/students').get_data(as_text=True))
    return m.group(1) if m else None


def _build_exam(app, publish=True):
    """A mock exam with English (2 Qs) + Maths (2 Qs), a student who registered
    both, and their portal password set."""
    with app.app_context():
        _SEQ[0] += 1
        bid = Branch.get_default().id
        eng = Subject.query.filter_by(name='English Language').first() or Subject(name='English Language', is_active=True)
        mth = Subject.query.filter_by(name='Mathematics').first() or Subject(name='Mathematics', is_active=True)
        db.session.add_all([eng, mth]); db.session.flush()
        s = AcademicSession(name=f'SIT-{_SEQ[0]}'); db.session.add(s); db.session.flush()
        ex = MockJAMBExam(name=f'Mock {_SEQ[0]}', exam_number=1, session_id=s.id,
                          exam_date=date(2025, 3, 1), branch_id=bid,
                          is_published=publish, duration_minutes=90)
        db.session.add(ex); db.session.flush()

        def q(subj, text, correct, order):
            db.session.add(MockJAMBQuestion(
                mock_exam_id=ex.id, subject_id=subj.id, question_text=text,
                option_a='a', option_b='b', option_c='c', option_d='d',
                correct_option=correct, marks=1, order=order))
        q(eng, 'Eng Q1', 'A', 1); q(eng, 'Eng Q2', 'B', 2)
        q(mth, 'Maths Q1', 'C', 1); q(mth, 'Maths Q2', 'D', 2)

        st = Student(student_id=f'SIT{_SEQ[0]:03d}', first_name='Sitter', surname='One',
                     gender='Male', is_active=True, branch_id=bid,
                     jamb_subjects='English Language, Mathematics')
        st.set_portal_password('pass1234') if hasattr(st, 'set_portal_password') else None
        db.session.add(st); db.session.commit()
        return ex.id, st.id, eng.id, mth.id


def test_publish_requires_questions(app):
    with app.app_context():
        _SEQ[0] += 1
        bid = Branch.get_default().id
        s = AcademicSession(name=f'PUB-{_SEQ[0]}'); db.session.add(s); db.session.flush()
        ex = MockJAMBExam(name='Empty', exam_number=1, session_id=s.id,
                          exam_date=date(2025, 3, 1), branch_id=bid)
        db.session.add(ex); db.session.commit(); eid = ex.id
    c = _admin(app); tok = _csrf(c)
    c.post(f'/mock-jamb/exam/{eid}/publish', data={'_csrf_token': tok}, follow_redirects=True)
    with app.app_context():
        assert db.session.get(MockJAMBExam, eid).is_published is False   # no questions → refused


def test_candidate_subjects_and_grading(app):
    """The engine sits the student's registered subjects and grades to /400."""
    from utils.mock_jamb_sitting import candidate_subject_ids, grade_attempt
    eid, sid, eng_id, mth_id = _build_exam(app)
    with app.app_context():
        exam = db.session.get(MockJAMBExam, eid)
        student = db.session.get(Student, sid)
        subs = candidate_subject_ids(exam, student)
        # English is compulsory → placed first
        assert subs[0] == eng_id and set(subs) == {eng_id, mth_id}
        # create an attempt, answer English fully-right, Maths half-right
        att = MockJAMBAttempt(mock_exam_id=eid, student_id=sid, duration_minutes=90)
        db.session.add(att); db.session.flush()
        from models import MockJAMBAnswer
        qs = {q.subject_id: [] for q in []}
        qmap = MockJAMBQuestion.query.filter_by(mock_exam_id=eid).all()
        for q in qmap:
            right = q.correct_option if q.subject_id == eng_id else ('C' if q.question_text.endswith('Q1') else 'A')
            db.session.add(MockJAMBAnswer(attempt_id=att.id, question_id=q.id,
                                          selected_option=right, is_correct=(right == q.correct_option)))
        db.session.commit()
        per = grade_attempt(att)
        by = dict(per)
        assert by['English Language'] == 100      # both right
        assert by['Mathematics'] == 50            # one of two right
        # MockJAMBResult written so analytics see it
        res = MockJAMBResult.query.filter_by(student_id=sid, mock_exam_id=eid).first()
        assert res is not None and res.total_score == 150
        assert att.status == 'Submitted'


def _portal_login(app, student_id):
    """Log a student into the exam portal (reuses the CBT portal login)."""
    with app.app_context():
        st = db.session.get(Student, student_id)
        st.set_portal_password('pass1234')
        db.session.commit()
        sid_code = st.student_id
    c = app.test_client()
    # the portal login form: student_id + portal password
    import re
    html = c.get('/exam/login').get_data(as_text=True)
    m = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', html) or re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    tok = m.group(1) if m else None
    c.post('/exam/login', data={'student_id': sid_code, 'password': 'pass1234', '_csrf_token': tok},
           follow_redirects=True)
    return c


def test_portal_flow_start_save_submit(app):
    eid, sid, eng_id, mth_id = _build_exam(app)
    c = _portal_login(app, sid)
    # list shows the mock
    r = c.get('/exam/mock-jamb/')
    assert r.status_code == 200 and b'Mock JAMB' in r.data
    # start creates an attempt and renders the sitting
    r = c.get(f'/exam/mock-jamb/{eid}')
    assert r.status_code == 200 and b'Submit' in r.data
    with app.app_context():
        att = MockJAMBAttempt.query.filter_by(mock_exam_id=eid, student_id=sid).first()
        assert att is not None and att.status == 'In progress'
        qids = [q.id for q in MockJAMBQuestion.query.filter_by(mock_exam_id=eid).all()]
    import re
    tok = re.search(r'name="csrf-token" content="([0-9a-f]+)"', c.get(f'/exam/mock-jamb/{eid}').get_data(as_text=True)).group(1)
    # answer every question correctly
    with app.app_context():
        for q in MockJAMBQuestion.query.filter_by(mock_exam_id=eid).all():
            c.post(f'/exam/mock-jamb/{eid}/save',
                   data={'_csrf_token': tok, 'question_id': q.id, 'option': q.correct_option})
    # submit
    r = c.post(f'/exam/mock-jamb/{eid}/submit', data={'_csrf_token': tok}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        att = MockJAMBAttempt.query.filter_by(mock_exam_id=eid, student_id=sid).first()
        assert att.status == 'Submitted' and att.total_score == 200   # both subjects 100
        res = MockJAMBResult.query.filter_by(student_id=sid, mock_exam_id=eid).first()
        assert res.total_score == 200


def _exam_with_n(app, n, per_subject=None):
    """A one-subject exam with n stand-alone questions + a candidate."""
    with app.app_context():
        _SEQ[0] += 1
        bid = Branch.get_default().id
        subj = Subject.query.filter_by(name='Physics').first() or Subject(name='Physics', is_active=True)
        db.session.add(subj); db.session.flush()
        s = AcademicSession(name=f'RND-{_SEQ[0]}'); db.session.add(s); db.session.flush()
        ex = MockJAMBExam(name=f'Mock {_SEQ[0]}', exam_number=1, session_id=s.id,
                          exam_date=date(2025, 3, 1), branch_id=bid, is_published=True,
                          duration_minutes=90, questions_per_subject=per_subject)
        db.session.add(ex); db.session.flush()
        for i in range(n):
            db.session.add(MockJAMBQuestion(
                mock_exam_id=ex.id, subject_id=subj.id, question_text=f'Q{i + 1}',
                option_a='a', option_b='b', option_c='c', option_d='d',
                correct_option='A', marks=1, order=i + 1))
        st = Student(student_id=f'RND{_SEQ[0]:03d}', first_name='R', surname='N',
                     gender='Male', is_active=True, branch_id=bid, jamb_subjects='Physics')
        db.session.add(st); db.session.commit()
        return ex.id, st.id, subj.id


def test_options_shuffled_and_stable(app):
    """Option order is shuffled per candidate but identical on a reload."""
    from utils.mock_jamb_sitting import sitting_payload
    eid, sid, subj_id = _exam_with_n(app, 6)
    with app.app_context():
        exam = db.session.get(MockJAMBExam, eid)
        att = MockJAMBAttempt(mock_exam_id=eid, student_id=sid); db.session.add(att); db.session.flush()
        p1 = sitting_payload(exam, [subj_id], att)
        p2 = sitting_payload(exam, [subj_id], att)
        # each question's option order is a permutation of the 4 original letters
        for qd in p1[0]['standalone']:
            letters = [l for l, _t in qd['options']]
            assert sorted(letters) == ['A', 'B', 'C', 'D']
        # identical across the two renders (stable for resume)
        o1 = [[l for l, _ in qd['options']] for qd in p1[0]['standalone']]
        o2 = [[l for l, _ in qd['options']] for qd in p2[0]['standalone']]
        assert o1 == o2
        # ... but not the trivial A,B,C,D for every question (something was shuffled)
        assert any(order != ['A', 'B', 'C', 'D'] for order in o1)


def test_different_candidates_get_different_papers(app):
    from utils.mock_jamb_sitting import sitting_payload
    eid, sid, subj_id = _exam_with_n(app, 8)
    with app.app_context():
        exam = db.session.get(MockJAMBExam, eid)
        a1 = MockJAMBAttempt(mock_exam_id=eid, student_id=sid); db.session.add(a1); db.session.flush()
        st2 = Student(student_id='RND-OTHER', first_name='O', surname='T', gender='Male',
                      is_active=True, branch_id=exam.branch_id, jamb_subjects='Physics')
        db.session.add(st2); db.session.flush()
        a2 = MockJAMBAttempt(mock_exam_id=eid, student_id=st2.id); db.session.add(a2); db.session.flush()
        p1 = sitting_payload(exam, [subj_id], a1)
        p2 = sitting_payload(exam, [subj_id], a2)
        order1 = [qd['q'].id for qd in p1[0]['standalone']]
        order2 = [qd['q'].id for qd in p2[0]['standalone']]
        opts1 = [[l for l, _ in qd['options']] for qd in p1[0]['standalone']]
        opts2 = [[l for l, _ in qd['options']] for qd in p2[0]['standalone']]
        # two candidates differ in question order and/or option order
        assert order1 != order2 or opts1 != opts2


def test_random_subset_and_grading(app):
    """questions_per_subject serves a random subset; grading counts only served."""
    from utils.mock_jamb_sitting import subject_items, grade_attempt
    eid, sid, subj_id = _exam_with_n(app, 6, per_subject=2)
    with app.app_context():
        exam = db.session.get(MockJAMBExam, eid)
        att = MockJAMBAttempt(mock_exam_id=eid, student_id=sid); db.session.add(att); db.session.flush()
        items, served = subject_items(exam, subj_id, att)
        assert len(served) == 2                     # only 2 of 6 served
        # answer both served correctly (correct is 'A')
        from models import MockJAMBAnswer
        for qid in served:
            db.session.add(MockJAMBAnswer(attempt_id=att.id, question_id=qid,
                                          selected_option='A', is_correct=True))
        db.session.commit()
        per = grade_attempt(att)
        assert dict(per)['Physics'] == 100          # 2/2 served correct → full, blanks ignored


def test_unpublished_not_sittable(app):
    eid, sid, eng_id, mth_id = _build_exam(app, publish=False)
    c = _portal_login(app, sid)
    r = c.get(f'/exam/mock-jamb/{eid}', follow_redirects=True)
    # redirected to the list with a "not open" flash; no attempt created
    with app.app_context():
        assert MockJAMBAttempt.query.filter_by(mock_exam_id=eid, student_id=sid).first() is None
