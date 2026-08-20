"""The enriched exam-trends page renders (insights + subject-mover panels) even
with no results, and the per-subject credit-rate trend function is well-formed.
"""
from config import Config
from tests.conftest import login_token


def test_trends_page_renders(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    r = c.get('/results/analytics/trends')
    assert r.status_code == 200


def test_waec_subject_trends_shape(app):
    with app.app_context():
        from utils.analytics_service import AcademicAnalytics
        st = AcademicAnalytics.get_waec_subject_trends(None)
        assert set(st.keys()) == {'years', 'subjects', 'series', 'movers'}
        assert isinstance(st['movers'], list)
