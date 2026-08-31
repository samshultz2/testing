"""Psychometric item analysis for CBT exams — difficulty, discrimination,
point-biserial, distractor analysis, KR-20 reliability."""
from models import (db, Branch, Student, CBTExam, CBTQuestion, CBTAttempt, CBTAnswer)

_SEQ = [0]


def _seed(app, n_students=12):
    """A 4-item exam with a designed, deterministic answer pattern (students
    created in strength order, so the upper/lower 27% groups are stable):
      Q1 correct for everyone except the last student (very easy)
      Q2 correct for the top half (strong positive discrimination — keep)
      Q3 correct for the top quarter only (hard, discriminating)
      Q4 correct for the bottom half (NEGATIVE discrimination — reject/mis-key)
    Total scores vary across students, so KR-20 is defined."""
    with app.app_context():
        _SEQ[0] += 1
        tag = f'PSY{_SEQ[0]}'
        bid = Branch.get_default().id
        exam = CBTExam(title=f'{tag} Test', branch_id=bid, is_published=True)
        db.session.add(exam); db.session.flush()
        # Q1,Q2 tagged 'Algebra'; Q3,Q4 tagged 'Geometry' (for topic mastery).
        topics = ['Algebra', 'Algebra', 'Geometry', 'Geometry']
        qs = []
        for i in range(4):
            q = CBTQuestion(exam_id=exam.id, question_text=f'Q{i + 1}?', option_a='a',
                            option_b='b', option_c='c', option_d='d', topic=topics[i],
                            correct_option='A', marks=1, order=i)
            db.session.add(q); db.session.flush()
            qs.append(q)
        half, quarter = n_students // 2, n_students // 4
        for si in range(n_students):
            st = Student(student_id=f'{tag}-{si}', first_name=f'S{si}', surname='T',
                         gender='Male', is_active=True, branch_id=bid)
            db.session.add(st); db.session.flush()
            at = CBTAttempt(exam_id=exam.id, student_id=st.id, status='Submitted',
                            score=0, total=4, raw_total=4)
            db.session.add(at); db.session.flush()
            pattern = [si != n_students - 1, si < half, si < quarter, si >= half]
            raw = 0
            for q, ok in zip(qs, pattern):
                # correct -> pick A (key); wrong -> pick B (a working distractor)
                db.session.add(CBTAnswer(attempt_id=at.id, question_id=q.id,
                                         selected_option='A' if ok else 'B', is_correct=ok))
                raw += 1 if ok else 0
            at.raw_score = raw; at.score = raw
        db.session.commit()
        return dict(exam=exam.id)


def test_item_analysis_core_metrics(app):
    from utils.psychometrics import item_analysis
    ids = _seed(app, n_students=12)
    with app.app_context():
        a = item_analysis(ids['exam'])
        assert a['meta']['respondents'] == 12 and a['meta']['question_count'] == 4
        items = {it['number']: it for it in a['items']}
        # Q1 correct for all but one -> very easy
        assert items[1]['p'] > 0.9 and items[1]['p_band'] == 'too_easy'
        # Q2 top-half correct -> difficulty 0.5, strong POSITIVE discrimination
        assert abs(items[2]['p'] - 0.5) < 0.001
        assert items[2]['d'] is not None and items[2]['d'] > 0.5
        assert items[2]['verdict'] == 'keep'
        # Q3 top-quarter correct -> hard
        assert abs(items[3]['p'] - 0.25) < 0.001
        # Q4 bottom-half correct -> NEGATIVE discrimination -> reject
        assert items[4]['d'] is not None and items[4]['d'] < 0
        assert items[4]['verdict'] == 'reject'


def test_kr20_and_summary(app):
    from utils.psychometrics import item_analysis
    ids = _seed(app, n_students=12)
    with app.app_context():
        a = item_analysis(ids['exam'])
        s = a['summary']
        assert 'kr20' in s and s['kr20'] is not None
        assert s['keep'] >= 1 and s['reject'] >= 1
        assert a['recommendations']              # not empty
        # a reject item should surface in the recommendations
        assert any('reject' in r['title'].lower() for r in a['recommendations'])


def test_topic_mastery(app):
    from utils.psychometrics import item_analysis
    ids = _seed(app, n_students=12)
    with app.app_context():
        a = item_analysis(ids['exam'])
        tm = a['topics']
        assert tm['has_topics'] is True
        by = {t['topic']: t for t in tm['items']}
        assert set(by) == {'Algebra', 'Geometry'}
        # Algebra = Q1 (all correct) + Q2 (half) -> ~75% mastery
        # Geometry = Q3 (top quarter) + Q4 (bottom half) -> lower mastery
        assert by['Algebra']['mastery'] > by['Geometry']['mastery']
        assert by['Geometry']['band'] in ('weak', 'developing')
        # weakest topic surfaces in the recommendations
        assert any('topic' in r['title'].lower() for r in a['recommendations'])
        # items carry their topic
        assert all(it['topic'] in ('Algebra', 'Geometry') for it in a['items'])
        # per-student topic matrix: one row per candidate, weakest-topic named
        assert tm['columns'] == [t['topic'] for t in tm['items']]   # weakest-first order
        assert len(tm['students']) == 12
        row = tm['students'][0]
        assert set(row['cells']) == {'Algebra', 'Geometry'}
        assert row['weakest'] in ('Algebra', 'Geometry')
        assert 0 <= row['overall'] <= 100


def test_insufficient_attempts(app):
    from utils.psychometrics import item_analysis
    ids = _seed(app, n_students=3)
    with app.app_context():
        a = item_analysis(ids['exam'])
        assert a['meta'].get('insufficient') is True


def _admin(app):
    from config import Config
    from tests.conftest import login_token
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_item_analysis_routes_and_exports(app):
    ids = _seed(app, n_students=12)
    c = _admin(app)
    r = c.get(f"/cbt/exams/{ids['exam']}/item-analysis")
    assert r.status_code == 200 and b'Item Analysis' in r.data
    r = c.get(f"/cbt/exams/{ids['exam']}/item-analysis/export?format=pdf")
    assert r.status_code == 200 and r.get_data()[:4] == b'%PDF'
    r = c.get(f"/cbt/exams/{ids['exam']}/item-analysis/export?format=excel")
    assert r.status_code == 200 and 'spreadsheetml' in r.headers['Content-Type']
    assert r.get_data()[:2] == b'PK'
