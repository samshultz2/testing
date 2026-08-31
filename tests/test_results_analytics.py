"""Results Phase 5 — academic analytics dashboard."""
from config import Config
from models import db, StudentScore, AnalyticsCache
from tests.conftest import login_token
from tests.test_score_integrity import _setup, _student
from utils import results_analytics as ra


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _seed(app, sid, ids, value):
    with app.app_context():
        row = StudentScore.query.filter_by(student_id=sid, class_subject_id=ids['cs'],
                                           assessment_type_id=ids['at']).first()
        if row:
            row.score = value
        else:
            db.session.add(StudentScore(student_id=sid, class_subject_id=ids['cs'],
                                        assessment_type_id=ids['at'], score=value))
        db.session.commit()


def test_analytics_summary_and_intervention(app):
    ids = _setup(app)
    hi = _student(app, ids, 'AN_HI')
    lo = _student(app, ids, 'AN_LO')
    _seed(app, hi, ids, 80)
    _seed(app, lo, ids, 30)          # below pass mark (50)
    with app.app_context():
        a = ra.class_analytics(ids['term'], ids['asg'], use_cache=False)
    s = a['summary']
    assert s['assessed'] >= 2
    # single subject → student average == their subject total
    assert s['highest'] >= 80 and s['lowest'] <= 30
    # grade distribution counts one cell per assessed (student, subject)
    assert sum(g['count'] for g in a['grade_distribution']) == s['assessed']
    # subject difficulty lists the class subject
    assert any(sub['id'] == ids['cs'] for sub in a['subjects'])
    # the low scorer is flagged for intervention
    assert any(st['id'] == lo for st in a['intervention'])
    assert not any(st['id'] == hi for st in a['intervention'])


def test_analytics_includes_term_trends(app):
    ids = _setup(app)
    sid = _student(app, ids, 'AN_TREND')
    _seed(app, sid, ids, 70)
    with app.app_context():
        a = ra.class_analytics(ids['term'], ids['asg'], use_cache=False)
        tr = a['trends']
        assert 'term_names' in tr and 'averages' in tr and 'subjects' in tr
        # the current term appears in the series
        term_name = __import__('models').Term.query.get(ids['term']).name
        assert term_name in tr['term_names']


def test_analytics_route_renders_json(app):
    ids = _setup(app)
    sid = _student(app, ids, 'AN_ROUTE')
    _seed(app, sid, ids, 65)
    c = _admin(app)
    j = c.get(f"/subjects/analytics?term_id={ids['term']}&assignment_id={ids['asg']}",
              headers={'Accept': 'application/json'}).get_json()
    assert j['page'] == 'analytics' and j['has_selection'] is True
    assert j['analytics']['summary']['assessed'] >= 1


def test_cache_is_used_then_busted(app):
    ids = _setup(app)
    sid = _student(app, ids, 'AN_CACHE')
    _seed(app, sid, ids, 55)
    with app.app_context():
        ra.bust(ids['term'], ids['asg'])                # cold start (shared DB)
        first = ra.class_analytics(ids['term'], ids['asg'], use_cache=True)
        assert first['cached'] is False                 # freshly computed + stored
        second = ra.class_analytics(ids['term'], ids['asg'], use_cache=True)
        assert second['cached'] is True                 # served from cache
        ra.bust(ids['term'], ids['asg'])
        assert AnalyticsCache.get(f"results_analytics:{ids['term']}:{ids['asg']}") is None


def test_saving_scores_busts_analytics_cache(app):
    ids = _setup(app)
    sid = _student(app, ids, 'AN_SAVE')
    _seed(app, sid, ids, 40)
    c = _admin(app)
    with c.session_transaction() as sess:
        sess['_csrf_token'] = 'a' * 64
    # warm the cache
    with app.app_context():
        ra.class_analytics(ids['term'], ids['asg'], use_cache=True)
    # save a new score through the route → cache should be dropped
    c.post('/subjects/scores/save', headers={'X-Requested-With': 'fetch'},
           data={'_csrf_token': 'a' * 64, 'term_id': ids['term'], 'assignment_id': ids['asg'],
                 'class_subject_id': ids['cs'], 'assessment_type_id': ids['at'],
                 'student_id[]': [sid], 'score[]': ['90']})
    with app.app_context():
        assert AnalyticsCache.get(f"results_analytics:{ids['term']}:{ids['asg']}") is None
