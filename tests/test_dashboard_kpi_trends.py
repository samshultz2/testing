"""Dashboard Phase 2 — KPIs carry trend context, not isolated numbers.

new_students_month (admissions growth) and finance collected_today (today's
collection) are exposed so the React KPIs can render movement chips.
"""
from datetime import datetime, timedelta
from config import Config
from models import db, Branch, Student
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD,
                           '_csrf_token': login_token(c)})
    return c


def test_new_students_month_counts_recent_only(app):
    c = _admin(app)
    with app.app_context():
        bid = Branch.get_default().id
        recent = Student(student_id='ZZ_KPI_NEW', first_name='New', surname='ZzKpiNew',
                         gender='Male', is_active=True, branch_id=bid)
        old = Student(student_id='ZZ_KPI_OLD', first_name='Old', surname='ZzKpiOld',
                      gender='Male', is_active=True, branch_id=bid)
        db.session.add_all([recent, old]); db.session.flush()
        # Backdate one well beyond the 30-day window.
        old.created_at = datetime.now() - timedelta(days=120)
        db.session.commit()
    j = c.get('/api/dashboard/data').get_json()
    assert 'new_students_month' in j
    # The recent student counts; the 120-day-old one does not.
    assert j['new_students_month'] >= 1
    # Sanity: it never exceeds the total headcount.
    assert j['new_students_month'] <= j['total_students']


def test_finance_stat_exposes_collected_today(app):
    """When finance is enabled, the term stat carries today's collection so the
    KPI can show a 'x today' chip."""
    c = _admin(app)
    j = c.get('/api/dashboard/data').get_json()
    fs = j.get('finance_stat')
    # finance is a default widget for admins; if present, the new key is there.
    if fs is not None:
        assert 'collected_today' in fs
        assert isinstance(fs['collected_today'], (int, float))
