"""Per-student & cohort topic mastery from online Mock JAMB answers."""
from datetime import date

_SEQ = [0]


def _seed(app):
    from models import (db, MockJAMBExam, MockJAMBQuestion, MockJAMBAttempt,
                        MockJAMBAnswer, Student, Subject, AcademicSession, Branch)
    with app.app_context():
        _SEQ[0] += 1
        n = _SEQ[0]
        bid = Branch.get_default().id
        subj = Subject(name=f'MasteryChem{n}', is_active=True)
        db.session.add(subj); db.session.flush()
        s = AcademicSession(name=f'MST-{n}'); db.session.add(s); db.session.flush()
        st = Student(student_id=f'MST{n:03d}', first_name='Mas', surname='Tery',
                     gender='Male', is_active=True, branch_id=bid)
        db.session.add(st); db.session.flush()

        # two mocks; student weak on 'Organic', strong on 'Acids'
        aids = []
        for m in range(2):
            ex = MockJAMBExam(name=f'M{m}', exam_number=m + 1, session_id=s.id,
                              exam_date=date(2025, 1 + m, 1), branch_id=bid)
            db.session.add(ex); db.session.flush()
            att = MockJAMBAttempt(mock_exam_id=ex.id, student_id=st.id, status='Submitted',
                                  total_score=100 + m * 40)
            db.session.add(att); db.session.flush()
            for i in range(4):
                topic = 'Organic' if i < 2 else 'Acids'
                q = MockJAMBQuestion(mock_exam_id=ex.id, subject_id=subj.id, topic=topic,
                                     question_text=f'q{m}{i}', option_a='a', option_b='b',
                                     option_c='c', option_d='d', correct_option='A', marks=1)
                db.session.add(q); db.session.flush()
                # Organic wrong, Acids correct; Organic improves on 2nd mock
                correct = (topic == 'Acids') or (topic == 'Organic' and m == 1 and i == 0)
                db.session.add(MockJAMBAnswer(attempt_id=att.id, question_id=q.id,
                                              selected_option='A' if correct else 'B',
                                              is_correct=correct))
            aids.append(att.id)
        db.session.commit()
        return st.id, subj.name


def test_student_mastery_flags_weak_and_strong(app):
    from utils.mock_student_mastery import student_mastery
    sid, subj = _seed(app)
    with app.app_context():
        data = student_mastery(sid, min_attempts=2)
    assert data['has_data'] and data['meta']['mocks'] == 2
    weak_topics = {w['topic'] for w in data['weaknesses']}
    strong_topics = {s['topic'] for s in data['strengths']}
    assert 'Organic' in weak_topics          # mostly wrong
    assert 'Acids' in strong_topics          # always right
    assert len(data['trend']) == 2           # two mocks in order


def test_cohort_topic_gaps(app):
    from utils.mock_student_mastery import cohort_topic_gaps
    sid, subj = _seed(app)
    # scope to just this seeded student so the shared test DB's other attempts
    # don't pollute the cohort aggregate.
    with app.app_context():
        data = cohort_topic_gaps(allowed_ids=[sid], min_attempts=2)
    assert data['has_data']
    # the weakest topic overall should be Organic (lowest correct-rate)
    assert data['weak_topics'][0]['topic'] == 'Organic'
