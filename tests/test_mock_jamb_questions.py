"""Mock JAMB online question bank — passages (comprehension etc.) + questions,
full CRUD, topic/sub-topic tagging, and the manager page."""
from datetime import date
from config import Config
from models import (db, Subject, Branch, MockJAMBExam, MockJAMBPassage,
                    MockJAMBQuestion, SyllabusTopic)
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


def _setup(app):
    with app.app_context():
        _SEQ[0] += 1
        subj = Subject.query.filter_by(name='English Language').first() or Subject(name='English Language', is_active=True)
        db.session.add(subj); db.session.flush()
        # a syllabus topic+subtopic for the dropdown
        t = SyllabusTopic.query.filter_by(subject_id=subj.id, title='Comprehension').first()
        if not t:
            t = SyllabusTopic(subject_id=subj.id, title='Comprehension'); db.session.add(t); db.session.flush()
            db.session.add(SyllabusTopic(subject_id=subj.id, parent_id=t.id, title='Inference'))
        bid = Branch.get_default().id
        # A dedicated session per exam so exam-number uniqueness never collides
        # with other test files sharing this DB.
        from models import AcademicSession
        s = AcademicSession(name=f'MJQ-{_SEQ[0]}')
        db.session.add(s); db.session.flush()
        ex = MockJAMBExam(name=f'Mock {_SEQ[0]}', exam_number=1, session_id=s.id,
                          exam_date=date(2025, 3, 1), branch_id=bid)
        db.session.add(ex); db.session.commit()
        return ex.id, subj.id


def test_questions_page_renders(app):
    eid, sid = _setup(app)
    c = _admin(app)
    r = c.get(f'/mock-jamb/exam/{eid}/questions?subject_id={sid}')
    assert r.status_code == 200
    assert b'Add a passage' in r.data and b'Comprehension' in r.data


def test_add_passage_then_question_under_it(app):
    eid, sid = _setup(app)
    c = _admin(app); tok = _csrf(c)
    r = c.post(f'/mock-jamb/exam/{eid}/passages/add', data={
        '_csrf_token': tok, 'subject_id': sid, 'kind': 'comprehension',
        'title': 'Passage I', 'body': 'Once upon a time in a school...'}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        p = MockJAMBPassage.query.filter_by(mock_exam_id=eid, subject_id=sid).first()
        assert p is not None and p.kind == 'comprehension'
        pid = p.id
    # add a comprehension question attached to the passage
    r = c.post(f'/mock-jamb/exam/{eid}/questions/add', data={
        '_csrf_token': tok, 'subject_id': sid, 'passage_id': pid,
        'question_text': 'What is the main idea?', 'correct_option': 'B',
        'option_a': 'a', 'option_b': 'b', 'option_c': 'c', 'option_d': 'd',
        'topic': 'Comprehension', 'subtopic': 'Inference', 'marks': '1'}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        q = MockJAMBQuestion.query.filter_by(mock_exam_id=eid, passage_id=pid).first()
        assert q is not None
        assert q.passage_id == pid          # comprehension question is bound to its passage
        assert q.correct_option == 'B'
        assert q.topic == 'Comprehension' and q.subtopic == 'Inference'


def test_add_standalone_edit_and_delete(app):
    eid, sid = _setup(app)
    c = _admin(app); tok = _csrf(c)
    r = c.post(f'/mock-jamb/exam/{eid}/questions/add', data={
        '_csrf_token': tok, 'subject_id': sid, 'question_text': 'Synonym of big?',
        'correct_option': 'A', 'option_a': 'large', 'option_b': 'small',
        'option_c': 'tiny', 'option_d': 'thin', 'marks': '1'}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        q = MockJAMBQuestion.query.filter_by(mock_exam_id=eid, passage_id=None).first()
        assert q is not None and q.correct_option == 'A'
        qid = q.id
    # edit — change the correct answer + text (CRUD on the answers)
    r = c.post(f'/mock-jamb/question/{qid}/edit', data={
        '_csrf_token': tok, 'question_text': 'Antonym of big?', 'correct_option': 'B',
        'option_a': 'large', 'option_b': 'small', 'option_c': 'tiny', 'option_d': 'thin',
        'marks': '2'}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        q = db.session.get(MockJAMBQuestion, qid)
        assert q.question_text == 'Antonym of big?' and q.correct_option == 'B' and q.marks == 2
    # delete
    r = c.post(f'/mock-jamb/question/{qid}/delete', data={'_csrf_token': tok}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        assert db.session.get(MockJAMBQuestion, qid) is None


def test_delete_passage_cascades_questions(app):
    eid, sid = _setup(app)
    c = _admin(app); tok = _csrf(c)
    c.post(f'/mock-jamb/exam/{eid}/passages/add', data={
        '_csrf_token': tok, 'subject_id': sid, 'kind': 'cloze', 'body': 'Fill the gaps ___'}, follow_redirects=True)
    with app.app_context():
        pid = MockJAMBPassage.query.filter_by(mock_exam_id=eid).first().id
    c.post(f'/mock-jamb/exam/{eid}/questions/add', data={
        '_csrf_token': tok, 'subject_id': sid, 'passage_id': pid, 'question_text': 'gap 1?',
        'correct_option': 'A', 'option_a': 'x', 'option_b': 'y', 'option_c': 'z', 'option_d': 'w'}, follow_redirects=True)
    r = c.post(f'/mock-jamb/passage/{pid}/delete', data={'_csrf_token': tok}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        assert db.session.get(MockJAMBPassage, pid) is None
        assert MockJAMBQuestion.query.filter_by(passage_id=pid).count() == 0


def test_add_question_rejects_missing_correct(app):
    eid, sid = _setup(app)
    c = _admin(app); tok = _csrf(c)
    c.post(f'/mock-jamb/exam/{eid}/questions/add', data={
        '_csrf_token': tok, 'subject_id': sid, 'question_text': 'No answer key',
        'correct_option': '', 'option_a': 'a'}, follow_redirects=True)
    with app.app_context():
        assert MockJAMBQuestion.query.filter_by(mock_exam_id=eid).count() == 0
