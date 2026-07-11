"""Background refresh of external-exams analytics: shared refresh routine, the
once-a-day guard, cache warming, and the last-refreshed indicator."""
import uuid

from config import Config
from models import db, Student, WAECResult, JAMBResult, AnalyticsCache
from models.models import SchoolSettings
from tests.conftest import login_token
from utils import exam_refresh as er


def _seed_year(app, yr):
    with app.app_context():
        s = Student(student_id='RF' + uuid.uuid4().hex[:7].upper(), first_name='Re',
                    surname='Fresh', gender='Male', is_active=True)
        db.session.add(s); db.session.commit()
        db.session.add(JAMBResult(student_id=s.id, exam_year=yr, total_score=220,
                                  subject1='English', subject1_score=60))
        db.session.add(WAECResult(student_id=s.id, exam_year=yr, subject='Mathematics', grade='B2'))
        db.session.commit()
        return s.id


def test_refresh_stamps_time_and_warms_cache(app):
    yr = 2077
    _seed_year(app, yr)
    with app.app_context():
        out = er.run_exam_analytics_refresh(app, warm=True)
        assert out['at'] and yr in out['years']
        # the refresh timestamp is stored and readable back
        assert er.refreshed_at() == out['at']
        # warming primed the hub stat cache (all-branches key for the latest year)
        assert AnalyticsCache.get(f'exam_hub:jamb:{yr}:all') is not None


def test_daily_guard_runs_once_per_day(app):
    with app.app_context():
        SchoolSettings.set(er._DAILY_MARKER, '', 'string')     # force "not run today"
        first = er.run_daily_refresh_if_due(app)
        second = er.run_daily_refresh_if_due(app)
    assert first is True and second is False                   # second is a no-op


def test_recompute_route_uses_shared_refresh(app):
    _seed_year(app, 2076)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    with c.session_transaction() as sess:
        sess['_csrf_token'] = 'r' * 64
    resp = c.post('/results/analytics/recompute',
                  data={'_csrf_token': 'r' * 64}, follow_redirects=False)
    assert resp.status_code in (200, 302)
    with app.app_context():
        assert er.refreshed_at() is not None


def test_hub_shows_last_refreshed(app):
    yr = 2075
    _seed_year(app, yr)
    with app.app_context():
        er.run_exam_analytics_refresh(app, warm=False)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    html = c.get(f'/results/analytics?year={yr}').get_data(as_text=True)
    assert 'Refreshed' in html
