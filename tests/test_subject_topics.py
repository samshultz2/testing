"""Subject-level topic mastery across a subject's CBT exams."""
import datetime as _dt
from models import (db, Branch, Subject, CBTExam, CBTQuestion, CBTAttempt, CBTAnswer, Student)

_SEQ = [0]


def _exam(app, subject_id, title, topic_pattern):
    """Create a CBT exam whose questions carry the given topics, with 6 students
    whose correctness follows `topic_pattern` — a dict topic -> fraction correct."""
    with app.app_context():
        _SEQ[0] += 1
        bid = Branch.get_default().id
        ex = CBTExam(title=title, branch_id=bid, subject_id=subject_id, is_published=True)
        db.session.add(ex); db.session.flush()
        qs = []
        for topic in topic_pattern:
            q = CBTQuestion(exam_id=ex.id, question_text=f'{topic}?', option_a='a', option_b='b',
                            option_c='c', option_d='d', correct_option='A', marks=1, topic=topic)
            db.session.add(q); db.session.flush()
            qs.append((q, topic))
        for i in range(6):
            _SEQ[0] += 1
            st = Student(student_id=f'ST{_SEQ[0]}', first_name='S', surname='T',
                         gender='Male', is_active=True, branch_id=bid)
            db.session.add(st); db.session.flush()
            at = CBTAttempt(exam_id=ex.id, student_id=st.id, status='Submitted',
                            score=0, total=len(qs), raw_total=len(qs))
            db.session.add(at); db.session.flush()
            for q, topic in qs:
                # student i correct if i < fraction*6
                ok = i < round(topic_pattern[topic] * 6)
                db.session.add(CBTAnswer(attempt_id=at.id, question_id=q.id,
                                         selected_option='A' if ok else 'B', is_correct=ok))
        db.session.commit()
        return ex.id


def _seed(app):
    with app.app_context():
        _SEQ[0] += 1
        subj = Subject(name=f'CBTM{_SEQ[0]}', is_active=True)
        db.session.add(subj); db.session.commit()
        sid = subj.id
    # Two exams: Algebra strong both times, Geometry weak both times.
    _exam(app, sid, 'Mock 1', {'Algebra': 1.0, 'Geometry': 0.17})
    _exam(app, sid, 'Mock 2', {'Algebra': 0.83, 'Geometry': 0.33})
    return dict(subject=sid)


def test_subject_topic_mastery(app):
    from utils.subject_topics import subject_topic_mastery
    ids = _seed(app)
    with app.app_context():
        d = subject_topic_mastery(ids['subject'])
        assert d['meta']['exams'] == 2
        by = {t['topic']: t for t in d['topics']}
        assert set(by) == {'Algebra', 'Geometry'}
        # Geometry weak across both exams -> ranks first (weakest) and is 'weak'
        assert d['topics'][0]['topic'] == 'Geometry'
        assert by['Geometry']['band'] == 'weak'
        assert by['Algebra']['mastery'] > by['Geometry']['mastery']
        # each topic appears in both exams, with a 2-point trend
        assert by['Geometry']['exams'] == 2 and len(by['Geometry']['trend']) == 2
        assert any('weak' in r['title'].lower() for r in d['recommendations'])


def test_subject_topic_no_topics(app):
    """A subject whose questions have no topic tags reports insufficient."""
    from utils.subject_topics import subject_topic_mastery
    with app.app_context():
        _SEQ[0] += 1
        subj = Subject(name=f'NT{_SEQ[0]}', is_active=True); db.session.add(subj); db.session.commit()
        sid = subj.id
    _exam(app, sid, 'Untagged', {'': 1.0})     # blank topic -> untagged
    with app.app_context():
        d = subject_topic_mastery(sid)
        assert d['meta'].get('insufficient') is True


def _admin(app):
    from config import Config
    from tests.conftest import login_token
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_subject_topics_route_and_export(app):
    ids = _seed(app)
    c = _admin(app)
    r = c.get(f"/cbt/subject-topics?subject_id={ids['subject']}")
    assert r.status_code == 200 and b'Subject Topics' in r.data
    r = c.get(f"/cbt/subject-topics/export?subject_id={ids['subject']}")
    assert r.status_code == 200 and 'spreadsheetml' in r.headers['Content-Type']
    assert r.get_data()[:2] == b'PK'
