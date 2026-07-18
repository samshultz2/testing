"""Mock JAMB Phase 4 — item- & topic-level analysis of the online sitting:
difficulty (p-value), discrimination, distractor analysis, topic/sub-topic
mastery, flagged items and the report route."""
from datetime import date
from config import Config
from models import (db, Subject, Branch, AcademicSession, Student, MockJAMBExam,
                    MockJAMBQuestion, MockJAMBAttempt, MockJAMBAnswer, MockJAMBResult)
from tests.conftest import login_token

_SEQ = [0]


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _build(app, n_students=6):
    """A one-subject (Physics) mock, ``n_students`` who each sit it online, and a
    tagged 4-question paper with a mix of difficulties so item analysis has
    signal:
      Q1 topic Motion  — everyone right      (too easy, no discrimination)
      Q2 topic Motion  — strong right, weak wrong (good discrimination)
      Q3 topic Waves   — everyone wrong       (too hard)
      Q4 topic Waves   — NEGATIVE: weak right, strong wrong (mis-key signal)
    """
    with app.app_context():
        _SEQ[0] += 1
        bid = Branch.get_default().id
        subj = Subject.query.filter_by(name='Physics').first() or Subject(name='Physics', is_active=True)
        db.session.add(subj); db.session.flush()
        s = AcademicSession(name=f'ITM-{_SEQ[0]}'); db.session.add(s); db.session.flush()
        ex = MockJAMBExam(name=f'Mock {_SEQ[0]}', exam_number=1, session_id=s.id,
                          exam_date=date(2025, 3, 1), branch_id=bid, is_published=True,
                          duration_minutes=90)
        db.session.add(ex); db.session.flush()

        def q(text, correct, order, topic, subtopic):
            row = MockJAMBQuestion(mock_exam_id=ex.id, subject_id=subj.id, question_text=text,
                                   option_a='a', option_b='b', option_c='c', option_d='d',
                                   correct_option=correct, marks=1, order=order,
                                   topic=topic, subtopic=subtopic)
            db.session.add(row); db.session.flush()
            return row
        q1 = q('Q1 easy', 'A', 1, 'Motion', 'Velocity')
        q2 = q('Q2 discriminating', 'A', 2, 'Motion', 'Acceleration')
        q3 = q('Q3 hard', 'A', 3, 'Waves', 'Sound')
        q4 = q('Q4 miskeyed', 'A', 4, 'Waves', 'Light')

        students = []
        for i in range(n_students):
            st = Student(student_id=f'ITM{_SEQ[0]}{i:02d}', first_name=f'S{i}', surname='X',
                         gender='Male', is_active=True, branch_id=bid, jamb_subjects='Physics')
            db.session.add(st); db.session.flush()
            students.append(st)

        # Rank: first half are "strong", second half "weak" (via total_score set below)
        half = n_students // 2
        for i, st in enumerate(students):
            strong = i < half
            att = MockJAMBAttempt(mock_exam_id=ex.id, student_id=st.id, status='Submitted',
                                  total_score=(300 if strong else 120))
            db.session.add(att); db.session.flush()

            def ans(qq, opt):
                db.session.add(MockJAMBAnswer(attempt_id=att.id, question_id=qq.id,
                                              selected_option=opt,
                                              is_correct=(opt == qq.correct_option)))
            ans(q1, 'A')                                  # everyone right
            ans(q2, 'A' if strong else 'B')               # strong right, weak wrong
            ans(q3, 'B')                                  # everyone wrong
            ans(q4, 'B' if strong else 'A')               # NEGATIVE: weak right, strong wrong
            # also write a MockJAMBResult so nothing else complains
        db.session.commit()
        return ex.id, subj.id


def test_item_analysis_difficulty_and_discrimination(app):
    from utils.mock_jamb_item_analysis import item_analysis
    eid, subj_id = _build(app, n_students=6)
    with app.app_context():
        data = item_analysis(eid)
        assert not data['meta']['empty']
        assert data['meta']['sitters'] == 6
        items = {it['text']: it for it in data['items']}
        # Q1 everyone right → p 100%, too easy
        assert items['Q1 easy']['p_value'] == 100.0
        assert items['Q1 easy']['diff_band'] == 'easy'
        # Q3 everyone wrong → p 0%, too hard
        assert items['Q3 hard']['p_value'] == 0.0
        assert items['Q3 hard']['diff_band'] == 'hard'
        # Q2 discriminates positively (strong right, weak wrong) → D > 0
        assert items['Q2 discriminating']['discrimination'] > 0
        # Q4 mis-keyed pattern → negative discrimination, flagged
        assert items['Q4 miskeyed']['discrimination'] < 0
        assert items['Q4 miskeyed']['disc_band'] == 'negative'
        assert items['Q4 miskeyed']['needs_review']
        assert any(it['disc_band'] == 'negative' for it in data['flagged'])


def test_topic_mastery_rollup(app):
    from utils.mock_jamb_item_analysis import item_analysis
    eid, subj_id = _build(app, n_students=6)
    with app.app_context():
        data = item_analysis(eid)
        topics = {t['topic']: t for t in data['topics']}
        assert 'Motion' in topics and 'Waves' in topics
        # Waves = Q3 (all wrong) + Q4 (half right) → lower mastery than Motion
        assert topics['Waves']['mastery'] < topics['Motion']['mastery']
        # sub-topic drill-down present
        motion_subs = {s['subtopic'] for s in topics['Motion']['subtopics']}
        assert {'Velocity', 'Acceleration'} <= motion_subs
        # weakest-first ordering
        masteries = [t['mastery'] for t in data['topics'] if t['mastery'] is not None]
        assert masteries == sorted(masteries)


def test_empty_when_no_sittings(app):
    from utils.mock_jamb_item_analysis import item_analysis
    with app.app_context():
        _SEQ[0] += 1
        bid = Branch.get_default().id
        subj = Subject.query.filter_by(name='Physics').first() or Subject(name='Physics', is_active=True)
        db.session.add(subj); db.session.flush()
        s = AcademicSession(name=f'EMP-{_SEQ[0]}'); db.session.add(s); db.session.flush()
        ex = MockJAMBExam(name='Untaken', exam_number=1, session_id=s.id,
                          exam_date=date(2025, 3, 1), branch_id=bid, is_published=True)
        db.session.add(ex); db.session.flush()
        db.session.add(MockJAMBQuestion(mock_exam_id=ex.id, subject_id=subj.id,
                                        question_text='Q', option_a='a', option_b='b',
                                        option_c='c', option_d='d', correct_option='A'))
        db.session.commit()
        data = item_analysis(ex.id)
        assert data['meta']['empty'] is True
        assert data['items'] == []


def test_items_route_renders(app):
    eid, subj_id = _build(app, n_students=6)
    c = _admin(app)
    r = c.get(f'/mock-jamb/exam/{eid}/items')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Item &amp; Topic Analysis' in body or 'Item & Topic Analysis' in body
    assert 'Motion' in body and 'Waves' in body
