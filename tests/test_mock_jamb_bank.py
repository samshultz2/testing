"""Central question bank + JAMB blueprint draw: a mock with NO in-exam questions
draws a per-student, JAMB-shaped paper from the shared bank (mock_exam_id NULL),
sampling each section to the blueprint counts and keeping passages whole."""
from datetime import date
from models import (db, Subject, Branch, AcademicSession, Student, MockJAMBExam,
                    MockJAMBQuestion, MockJAMBPassage, MockJAMBAttempt)

_SEQ = [0]


def _bank_maths(app, n_per_section=8):
    """A Mathematics bank (mock_exam_id NULL) with n questions in each of the
    five JAMB Maths sections, plus a published mock that owns no questions and a
    candidate registered for Maths."""
    with app.app_context():
        _SEQ[0] += 1
        bid = Branch.get_default().id
        subj = Subject.query.filter_by(name='Mathematics').first() or Subject(name='Mathematics', is_active=True)
        db.session.add(subj); db.session.flush()
        sections = ['number', 'algebra', 'geometry', 'calculus', 'statistics']
        for sec in sections:
            for i in range(n_per_section):
                db.session.add(MockJAMBQuestion(
                    mock_exam_id=None, subject_id=subj.id, section=sec,
                    question_text=f'{sec} Q{i}', option_a='a', option_b='b',
                    option_c='c', option_d='d', correct_option='A', marks=1, order=i))
        s = AcademicSession(name=f'BANK-{_SEQ[0]}'); db.session.add(s); db.session.flush()
        ex = MockJAMBExam(name=f'Bank Mock {_SEQ[0]}', exam_number=1, session_id=s.id,
                          exam_date=date(2025, 3, 1), branch_id=bid, is_published=True,
                          duration_minutes=90)
        db.session.add(ex); db.session.flush()
        st = Student(student_id=f'BNK{_SEQ[0]:03d}', first_name='B', surname='K',
                     gender='Male', is_active=True, branch_id=bid, jamb_subjects='Mathematics')
        db.session.add(st); db.session.commit()
        return ex.id, st.id, subj.id


def test_bank_draw_follows_blueprint(app):
    from utils.mock_jamb_sitting import subject_items, candidate_subject_ids
    eid, sid, subj_id = _bank_maths(app)
    with app.app_context():
        exam = db.session.get(MockJAMBExam, eid)
        student = db.session.get(Student, sid)
        # subject is discovered from the bank even though the exam owns nothing
        assert candidate_subject_ids(exam, student) == [subj_id]
        att = MockJAMBAttempt(mock_exam_id=eid, student_id=sid); db.session.add(att); db.session.flush()
        items, served = subject_items(exam, subj_id, att)
        # Maths blueprint totals 40 (10+12+10+4+4); each section has 8 in the bank,
        # so calculus/statistics (want 4) draw 4, others draw all 8 they have.
        # number(8)+algebra(8)+geometry(8)+calculus(4)+statistics(4) = 32
        assert len(served) == 32
        # every served question really is a Maths bank question
        qs = MockJAMBQuestion.query.filter(MockJAMBQuestion.id.in_(served)).all()
        assert all(q.subject_id == subj_id and q.mock_exam_id is None for q in qs)


def test_bank_draw_differs_per_student(app):
    from utils.mock_jamb_sitting import subject_items
    eid, sid, subj_id = _bank_maths(app, n_per_section=12)
    with app.app_context():
        exam = db.session.get(MockJAMBExam, eid)
        a1 = MockJAMBAttempt(mock_exam_id=eid, student_id=sid); db.session.add(a1); db.session.flush()
        st2 = Student(student_id='BNK-OTHER', first_name='O', surname='T', gender='Male',
                      is_active=True, branch_id=exam.branch_id, jamb_subjects='Mathematics')
        db.session.add(st2); db.session.flush()
        a2 = MockJAMBAttempt(mock_exam_id=eid, student_id=st2.id); db.session.add(a2); db.session.flush()
        _i1, s1 = subject_items(exam, subj_id, a1)
        _i2, s2 = subject_items(exam, subj_id, a2)
        # both drew a full 40-question blueprint paper (12 available per section)
        assert len(s1) == 40 and len(s2) == 40
        # but from a larger pool the two papers are not identical
        assert s1 != s2
        # stable on reload for the same attempt
        _i1b, s1b = subject_items(exam, subj_id, a1)
        assert s1 == s1b


def test_bank_blueprint_override_per_mock(app):
    """A per-mock blueprint JSON override changes the section counts."""
    import json
    from utils.mock_jamb_sitting import subject_items
    eid, sid, subj_id = _bank_maths(app, n_per_section=12)
    with app.app_context():
        exam = db.session.get(MockJAMBExam, eid)
        # override: only 2 from each section => 10 total
        exam.blueprint = json.dumps({'mathematics': {'number': 2, 'algebra': 2,
                                                     'geometry': 2, 'calculus': 2, 'statistics': 2}})
        db.session.commit()
        att = MockJAMBAttempt(mock_exam_id=eid, student_id=sid); db.session.add(att); db.session.flush()
        _items, served = subject_items(exam, subj_id, att)
        assert len(served) == 10


def test_bank_comprehension_keeps_passages_whole(app):
    """English comprehension draws whole passages from the bank."""
    from utils.mock_jamb_sitting import subject_items
    with app.app_context():
        _SEQ[0] += 1
        bid = Branch.get_default().id
        eng = Subject.query.filter_by(name='English Language').first() or Subject(name='English Language', is_active=True)
        db.session.add(eng); db.session.flush()
        # two comprehension passages, 5 questions each, in the bank
        for p in range(2):
            pas = MockJAMBPassage(mock_exam_id=None, subject_id=eng.id, section='comprehension',
                                  kind='comprehension', title=f'Passage {p}', body='text', order=p)
            db.session.add(pas); db.session.flush()
            for i in range(5):
                db.session.add(MockJAMBQuestion(
                    mock_exam_id=None, subject_id=eng.id, section='comprehension',
                    passage_id=pas.id, question_text=f'P{p}Q{i}', option_a='a', option_b='b',
                    option_c='c', option_d='d', correct_option='A', marks=1, order=i))
        s = AcademicSession(name=f'ENGB-{_SEQ[0]}'); db.session.add(s); db.session.flush()
        ex = MockJAMBExam(name='Eng bank', exam_number=1, session_id=s.id,
                          exam_date=date(2025, 3, 1), branch_id=bid, is_published=True)
        db.session.add(ex); db.session.flush()
        att = MockJAMBAttempt(mock_exam_id=ex.id, student_id=1); db.session.add(att); db.session.flush()
        items, served = subject_items(ex, eng.id, att)
        # blueprint wants 15 comprehension Qs but only 10 exist → both passages drawn whole
        assert len(served) == 10
        passage_items = [it for it in items if it['kind'] == 'passage']
        assert len(passage_items) == 2
        assert all(len(pi['questions']) == 5 for pi in passage_items)


# --- bank management UI + bulk import ------------------------------------

def _admin(app):
    from config import Config
    from tests.conftest import login_token
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _bank_csrf(c):
    import re
    html = c.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def test_bank_page_and_add_question(app):
    with app.app_context():
        _SEQ[0] += 1
        subj = Subject.query.filter_by(name='Mathematics').first() or Subject(name='Mathematics', is_active=True)
        db.session.add(subj); db.session.commit()
        sid = subj.id
    c = _admin(app); tok = _bank_csrf(c)
    r = c.get(f'/mock-jamb/bank?subject_id={sid}')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Question Bank' in body and 'Section coverage' in body
    # add a bank question tagged to the 'algebra' section
    r = c.post('/mock-jamb/bank/question/add', data={
        '_csrf_token': tok, 'subject_id': sid, 'question_text': 'Solve x+1=3',
        'option_a': '1', 'option_b': '2', 'option_c': '3', 'option_d': '4',
        'correct_option': 'B', 'section': 'algebra', 'exam_body': 'JAMB', 'marks': '1',
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        q = (MockJAMBQuestion.query.filter_by(subject_id=sid, mock_exam_id=None,
             question_text='Solve x+1=3').first())
        assert q is not None and q.section == 'algebra' and q.exam_body == 'JAMB'


def test_bank_bulk_import(app):
    with app.app_context():
        _SEQ[0] += 1
        subj = Subject.query.filter_by(name='Mathematics').first() or Subject(name='Mathematics', is_active=True)
        db.session.add(subj); db.session.commit()
        sid = subj.id
        before = MockJAMBQuestion.query.filter_by(subject_id=sid, mock_exam_id=None).count()
    c = _admin(app); tok = _bank_csrf(c)
    rows = ('What is 2+2? | 3 | 4 | 5 | 6 | B | number\n'
            'What is 3x2? | 5 | 6 | 7 | 8 | B | algebra | Polynomials\n'
            'malformed line only two | fields')
    r = c.post('/mock-jamb/bank/import', data={
        '_csrf_token': tok, 'subject_id': sid, 'default_section': 'number',
        'exam_body': 'JAMB', 'rows': rows,
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        after = MockJAMBQuestion.query.filter_by(subject_id=sid, mock_exam_id=None).count()
        assert after == before + 2                       # two good rows, one skipped
        q = MockJAMBQuestion.query.filter_by(subject_id=sid, question_text='What is 3x2?').first()
        assert q.section == 'algebra' and q.topic == 'Polynomials'


def test_blueprint_editor_saves_override(app):
    """The blueprint editor renders and persists a per-mock section override that
    the draw then honours."""
    import json
    from utils.mock_jamb_sitting import subject_items
    eid, sid, subj_id = _bank_maths(app, n_per_section=12)
    c = _admin(app); tok = _bank_csrf(c)
    r = c.get(f'/mock-jamb/exam/{eid}/blueprint')
    assert r.status_code == 200 and 'Paper Blueprint' in r.get_data(as_text=True)
    # set every Maths section to 2 (=> 10 total), leave others at default
    data = {'_csrf_token': tok}
    for section in ('number', 'algebra', 'geometry', 'calculus', 'statistics'):
        data[f'mathematics__{section}'] = '2'
    r = c.post(f'/mock-jamb/exam/{eid}/blueprint', data=data, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        exam = db.session.get(MockJAMBExam, eid)
        assert exam.blueprint and 'mathematics' in json.loads(exam.blueprint)
        att = MockJAMBAttempt(mock_exam_id=eid, student_id=sid); db.session.add(att); db.session.flush()
        _items, served = subject_items(exam, subj_id, att)
        assert len(served) == 10


def test_starter_seed_and_draw(app):
    """Seeding the starter bank lets a mock draw a real English paper (passages
    kept whole) with a per-student shuffle."""
    from utils.mock_bank_seed import seed_starter_bank
    from utils.mock_jamb_sitting import subject_items
    with app.app_context():
        _SEQ[0] += 1
        bid = Branch.get_default().id
        eng = Subject.query.filter_by(name='English Language').first() or Subject(name='English Language', is_active=True)
        db.session.add(eng); db.session.commit()
        p, q = seed_starter_bank(eng.id, eng.name)
        assert p == 2 and q >= 30          # 2 passages + section questions
        # a second seed does not duplicate
        p2, q2 = seed_starter_bank(eng.id, eng.name)
        assert p2 == 0 and q2 == 0
        s = AcademicSession(name=f'SEED-{_SEQ[0]}'); db.session.add(s); db.session.flush()
        ex = MockJAMBExam(name='Seeded', exam_number=1, session_id=s.id,
                          exam_date=date(2025, 3, 1), branch_id=bid, is_published=True)
        db.session.add(ex); db.session.flush()
        att = MockJAMBAttempt(mock_exam_id=ex.id, student_id=1); db.session.add(att); db.session.flush()
        items, served = subject_items(ex, eng.id, att)
        assert served                       # a paper was drawn
        # comprehension + cloze passages are served whole
        passage_items = [it for it in items if it['kind'] == 'passage']
        assert len(passage_items) == 2


def test_bank_seed_route(app):
    with app.app_context():
        subj = Subject.query.filter_by(name='Chemistry').first() or Subject(name='Chemistry', is_active=True)
        db.session.add(subj); db.session.commit(); sid = subj.id
    c = _admin(app); tok = _bank_csrf(c)
    r = c.post('/mock-jamb/bank/seed', data={'_csrf_token': tok, 'subject_id': sid},
               follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        n = MockJAMBQuestion.query.filter_by(subject_id=sid, mock_exam_id=None).count()
        assert n >= 12 and MockJAMBQuestion.query.filter_by(
            subject_id=sid, mock_exam_id=None, section='organic').first() is not None
