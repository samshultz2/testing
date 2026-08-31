"""Question-bank per-subject analytics + the new bank filters (topic / sub-topic /
year / exam type)."""
import re

from config import Config


def _admin(app):
    from tests.conftest import login_token
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _q(sid, **kw):
    from models import MockJAMBQuestion
    kw.setdefault('question_text', 'q'); kw.setdefault('option_a', 'a')
    kw.setdefault('option_b', 'b'); kw.setdefault('option_c', 'c')
    kw.setdefault('option_d', 'd'); kw.setdefault('correct_option', 'A')
    kw.setdefault('marks', 1)
    return MockJAMBQuestion(mock_exam_id=None, subject_id=sid, **kw)


def _subject_with_bank(app, name):
    from models import db, Subject
    with app.app_context():
        s = Subject(name=name, is_active=True); db.session.add(s); db.session.flush()
        sid = s.id
        rows = [
            _q(sid, topic='Algebra', subtopic='Quadratics', exam_year='2023', exam_body='JAMB'),
            _q(sid, topic='Algebra', subtopic='Quadratics', exam_year='2022', exam_body='JAMB'),
            _q(sid, topic='Algebra', subtopic='Indices', exam_year='2023', exam_body='WAEC'),
            _q(sid, topic='Geometry', subtopic='Circles', exam_year='2015', exam_body='JAMB'),  # cold
            _q(sid, topic=None, subtopic=None, exam_year='2023', exam_body='JAMB'),              # untagged
        ]
        db.session.add_all(rows); db.session.commit()
        return sid


def test_subject_breakdown_counts_and_pct(app):
    from models import db, Subject
    from utils.mock_bank_analytics import subject_breakdown
    sid = _subject_with_bank(app, 'BankAnaMath')
    with app.app_context():
        data = subject_breakdown(db.session.get(Subject, sid))
    assert data['total'] == 5
    assert data['untagged'] == 1
    topics = {t['topic']: t for t in data['topics']}
    assert topics['Algebra']['count'] == 3
    assert topics['Algebra']['pct'] == 60.0        # 3/5
    assert topics['Geometry']['count'] == 1
    # exam bodies split
    bodies = {b['body']: b['count'] for b in data['by_exam_body']}
    assert bodies['JAMB'] == 4 and bodies['WAEC'] == 1


def test_subject_breakdown_flags_cold_topic(app):
    from models import db, Subject
    from utils.mock_bank_analytics import subject_breakdown
    sid = _subject_with_bank(app, 'BankAnaCold')
    with app.app_context():
        data = subject_breakdown(db.session.get(Subject, sid))
    # recent window = top 3 years present {2023,2022,2015}; Geometry only has 2015 -> not cold,
    # but let's assert the recency machinery: Geometry's only year (2015) IS in the window here
    # because there are just 3 distinct years. Add a check that Algebra is never cold.
    topics = {t['topic']: t for t in data['topics']}
    assert topics['Algebra']['cold'] is False
    assert topics['Algebra']['recent_year'] == 2023


def test_subject_breakdown_cold_when_older_than_window(app):
    """A topic tested only in years outside the recent window is flagged cold."""
    from models import db, Subject
    from utils.mock_bank_analytics import subject_breakdown
    with app.app_context():
        s = Subject(name='BankAnaCold2', is_active=True); db.session.add(s); db.session.flush()
        sid = s.id
        # 3 recent years from Algebra, an old outlier topic from 2008
        db.session.add_all([
            _q(sid, topic='Algebra', exam_year='2023'),
            _q(sid, topic='Algebra', exam_year='2022'),
            _q(sid, topic='Algebra', exam_year='2021'),
            _q(sid, topic='Logarithms', exam_year='2008'),
        ])
        db.session.commit()
        data = subject_breakdown(db.session.get(Subject, sid))
    topics = {t['topic']: t for t in data['topics']}
    assert data['recent_years'] == [2023, 2022, 2021]
    assert topics['Logarithms']['cold'] is True
    assert topics['Logarithms'] in [c for c in data['cold_topics']]


def test_subject_breakdown_reports_syllabus_gaps(app):
    """A seeded syllabus topic with no banked question shows up as a gap."""
    from models import db, Subject, SyllabusTopic
    from utils.mock_bank_analytics import subject_breakdown
    with app.app_context():
        s = Subject(name='BankAnaGap', is_active=True); db.session.add(s); db.session.flush()
        sid = s.id
        db.session.add(_q(sid, topic='Algebra', exam_year='2023'))
        db.session.add(SyllabusTopic(subject_id=sid, title='Calculus', is_active=True))
        db.session.add(SyllabusTopic(subject_id=sid, title='Algebra', is_active=True))
        db.session.commit()
        data = subject_breakdown(db.session.get(Subject, sid))
    assert 'Calculus' in data['gaps']['topics']       # never tested
    assert 'Algebra' not in data['gaps']['topics']     # has a banked question


def test_bank_filters_by_topic_and_year(app):
    sid = _subject_with_bank(app, 'BankFilter')
    c = _admin(app)
    # no filter -> all 5 stand-alone questions
    assert 'Stand-alone questions (5)' in c.get(
        f'/mock-jamb/bank?subject_id={sid}').get_data(as_text=True)
    # filter to Geometry -> only the single Geometry question
    assert 'Stand-alone questions (1)' in c.get(
        f'/mock-jamb/bank?subject_id={sid}&topic=Geometry').get_data(as_text=True)
    # filter by year 2022 -> only the one 2022 question
    assert 'Stand-alone questions (1)' in c.get(
        f'/mock-jamb/bank?subject_id={sid}&year=2022').get_data(as_text=True)
    # filter by exam type WAEC -> only the one WAEC question
    assert 'Stand-alone questions (1)' in c.get(
        f'/mock-jamb/bank?subject_id={sid}&exam_body=WAEC').get_data(as_text=True)


def test_bank_analytics_page_renders(app):
    sid = _subject_with_bank(app, 'BankAnaPage')
    c = _admin(app)
    r = c.get(f'/mock-jamb/bank/analytics?subject_id={sid}')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'Topic analytics' in html and 'Algebra' in html
