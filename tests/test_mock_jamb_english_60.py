"""Use of English is always a 60-question paper in the Mock JAMB CBT — whatever
the mock's per-subject cap, per-mock blueprint override, section tagging of the
bank, or a paper cached short before the rule existed."""
import json
from datetime import date

from models import (db, Subject, Branch, AcademicSession, Student, MockJAMBExam,
                    MockJAMBQuestion, MockJAMBAttempt)

_SEQ = [0]


def _exam(app, n_tagged=15, n_untagged=70, cap=30, override=None):
    with app.app_context():
        _SEQ[0] += 1
        bid = Branch.get_default().id
        eng = Subject.query.filter_by(name='English Language').first() or Subject(name='English Language', is_active=True)
        db.session.add(eng); db.session.flush()
        s = AcademicSession(name=f'E60-{_SEQ[0]}'); db.session.add(s); db.session.flush()
        ex = MockJAMBExam(name=f'E60 {_SEQ[0]}', exam_number=1, session_id=s.id, exam_date=date(2025, 3, 1),
                          branch_id=bid, is_published=True, duration_minutes=120, questions_per_subject=cap,
                          blueprint=json.dumps({'english language': override}) if override else None)
        db.session.add(ex); db.session.flush()
        secs = ['lexis_structure', 'oral', 'synonyms']
        for i in range(n_tagged + n_untagged):
            db.session.add(MockJAMBQuestion(
                mock_exam_id=ex.id, subject_id=eng.id, question_text=f'E60 {_SEQ[0]} Q{i}',
                option_a='a', option_b='b', option_c='c', option_d='d', correct_option='A', marks=1,
                order=i, section=(secs[i % 3] if i < n_tagged else None)))
        st = Student(student_id=f'E60S{_SEQ[0]:03d}', first_name='E', surname='Sixty', gender='Male',
                     is_active=True, branch_id=bid, jamb_subjects='English Language')
        db.session.add(st); db.session.flush()
        att = MockJAMBAttempt(mock_exam_id=ex.id, student_id=st.id, duration_minutes=120)
        db.session.add(att); db.session.commit()
        return ex.id, eng.id, att.id


def test_english_blueprint_always_60():
    from utils.jamb_blueprint import blueprint_for
    assert blueprint_for('English Language')['total'] == 60
    assert blueprint_for('Use of English', {'lexis_structure': 0, 'oral': 0})['total'] == 60
    assert blueprint_for('English', {'lexis_structure': 50, 'oral': 40})['total'] == 60
    assert blueprint_for('Mathematics')['total'] == 40   # others untouched


def test_tagged_but_thin_sections_are_topped_up_to_60(app):
    """Section-tagged pool short in most sections + a mock cap of 30 + an
    override shrinking English → still 60."""
    from utils.mock_jamb_sitting import subject_items
    eid, sid, aid = _exam(app, override={'lexis_structure': 2, 'oral': 2})
    with app.app_context():
        exam = db.session.get(MockJAMBExam, eid); att = db.session.get(MockJAMBAttempt, aid)
        items, served = subject_items(exam, sid, att)
        assert len(served) == 60


def test_untagged_pool_ignores_the_mock_cap(app):
    from utils.mock_jamb_sitting import subject_items
    eid, sid, aid = _exam(app, n_tagged=0, n_untagged=90, cap=30)
    with app.app_context():
        exam = db.session.get(MockJAMBExam, eid); att = db.session.get(MockJAMBAttempt, aid)
        assert len(subject_items(exam, sid, att)[1]) == 60


def test_cached_short_paper_is_topped_up_keeping_existing_questions(app):
    from utils.mock_jamb_sitting import subject_items
    eid, sid, aid = _exam(app, n_tagged=0, n_untagged=80)
    with app.app_context():
        exam = db.session.get(MockJAMBExam, eid); att = db.session.get(MockJAMBAttempt, aid)
        first30 = [q.id for q in MockJAMBQuestion.query.filter_by(mock_exam_id=eid).order_by(MockJAMBQuestion.id).limit(30)]
        att.paper = json.dumps({str(sid): [{'q': q} for q in first30]})
        db.session.commit()
        items, served = subject_items(exam, sid, att)
        assert len(served) == 60 and set(first30) <= served
        db.session.commit()
        # persisted: the next load is the same 60
        assert subject_items(exam, sid, db.session.get(MockJAMBAttempt, aid))[1] == served


def test_small_pool_serves_everything_it_has(app):
    from utils.mock_jamb_sitting import subject_items
    eid, sid, aid = _exam(app, n_tagged=0, n_untagged=12)
    with app.app_context():
        exam = db.session.get(MockJAMBExam, eid); att = db.session.get(MockJAMBAttempt, aid)
        assert len(subject_items(exam, sid, att)[1]) == 12
