"""Live at-risk watchlist (roadmap #6): projects SSS3 candidates' readiness now
and flags those off track, grouped by class arm — page renders and the service
returns a sane shape."""
from config import Config


def _admin(app):
    from tests.conftest import login_token
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_live_at_risk_shape_empty_is_safe(app):
    from utils.at_risk_live import live_at_risk
    # Branch scoping in get_sss3_students() needs a request context.
    with app.test_request_context():
        from flask import session
        session['role'] = 'super_admin'
        session['scope'] = 'central'
        data = live_at_risk()
    assert {'total_flagged', 'counts', 'by_class', 'total', 'all_counts', 'projected', 'rows',
            'blockers', 'groups', 'classes'} <= set(data.keys())
    assert isinstance(data['by_class'], list)
    assert data['total_flagged'] == sum(g['count'] for g in data['by_class'])


def test_watchlist_page_renders(app):
    c = _admin(app)
    r = c.get('/results/analytics/watchlist')
    assert r.status_code == 200
    assert 'At-Risk Watchlist' in r.get_data(as_text=True)


def test_watchlist_rows_groups_and_page(app):
    """Flagged candidates become flat rows with tags, intervention groups are
    built from those tags, and the redesigned page renders them."""
    import unittest.mock as mock
    from utils import at_risk_live as L

    class S:
        def __init__(self, i):
            self.id, self.full_name, self.student_id, self.target_course_id = 9000 + i, 'Pupil %d' % i, 'WL%d' % i, None

    pupils = [S(1), S(2), S(3)]
    readiness = {
        9001: {'status': 'NOT_READY', 'blockers': ['Projected 3 credits — needs 5', 'No Mathematics credit projected'],
               'waec': {'credits': 3, 'missing_core': ['Mathematics']}, 'jamb': {'score': 150}, 'jamb_threshold': 200},
        9002: {'status': 'READY', 'blockers': [], 'waec': {'credits': 7, 'missing_core': []}, 'jamb': {'score': 260},
               'jamb_threshold': 200},
        9003: {'status': 'NO_DATA', 'blockers': [], 'waec': None, 'jamb': None},
    }
    coh = {'rows': [{'student': p, 'readiness': readiness[p.id]} for p in pupils], 'total': 3, 'assessed': 2,
           'counts': {'READY': 1, 'CONDITIONAL': 0, 'AT_RISK': 0, 'NOT_READY': 1, 'NO_DATA': 1},
           'projected_5_incl_core': 1, 'projected_5_incl_core_pct': 33.3, 'projected_jamb_ok': 1,
           'projected_jamb_ok_pct': 33.3, 'projected_both': 1, 'projected_both_pct': 33.3}
    with mock.patch('utils.helpers.get_sss3_students', return_value=pupils), \
            mock.patch('utils.exam_insights.cohort_readiness', return_value=coh), \
            mock.patch('utils.focus_areas._cohort', return_value={9001: {'class': 'Gold'}, 9002: {'class': 'Gold'}}):
        d = L.live_at_risk()
    assert d['total_flagged'] == 1 and d['total'] == 3
    row = d['rows'][0]
    assert row['name'] == 'Pupil 1' and row['jamb_gap'] == -50 and set(row['tags']) == {'credits', 'maths', 'jamb'}
    assert {g['key'] for g in d['groups']} == {'credits', 'maths', 'jamb'}
    assert d['blockers']['maths'] == 1 and d['blockers']['english'] == 0
    assert [x['name'] for x in d['no_data']] == ['Pupil 3']
    gold = next(c for c in d['classes'] if c['class'] == 'Gold')
    assert gold['total'] == 2 and gold['READY'] == 1 and gold['NOT_READY'] == 1

    c = _admin(app)
    with mock.patch('utils.at_risk_live.live_at_risk', return_value=d):
        body = c.get('/results/analytics/watchlist').get_data(as_text=True)
    for want in ('1 of 3 SSS3 candidates need attention', 'Intervention groups', 'Maths clinic',
                 'Flagged candidates', 'Pupil 1', 'No mock results yet', 'Pupil 3'):
        assert want in body, want
