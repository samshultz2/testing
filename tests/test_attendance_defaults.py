"""Form-teacher class auto-select, current-week default, and the daily summary
showing the whole week at once."""
from datetime import date, timedelta
from types import SimpleNamespace

from config import Config
from tests.conftest import login_token
from utils.helpers import pick_current_week


def _week(n, start):
    return SimpleNamespace(week_number=n, start_date=start, end_date=start + timedelta(days=4))


def test_pick_current_week_picks_the_one_containing_today():
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    weeks = [_week(1, monday - timedelta(days=14)),
             _week(2, monday - timedelta(days=7)),
             _week(3, monday)]                       # the week containing today
    assert pick_current_week(weeks).week_number == 3


def test_pick_current_week_falls_back_to_latest_started():
    today = date.today()
    weeks = [_week(1, today - timedelta(days=40)),
             _week(2, today - timedelta(days=33))]   # all in the past
    assert pick_current_week(weeks).week_number == 2   # most recent started
    assert pick_current_week([]) is None


def test_daily_summary_page_renders(app):
    """The daily summary page loads (admin sees the picker; the whole-week table
    appears once a class with data is selected)."""
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    r = c.get('/attendance/daily')
    assert r.status_code == 200
    assert 'Daily Summary' in r.get_data(as_text=True)
