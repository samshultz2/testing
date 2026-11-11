"""/account attendance: defaults to this month, filters by month / year,
'All years' totals every late-coming deduction, and is paginated."""
from datetime import date, timedelta

from models import db, StaffAttendance
from tests.conftest import login_token
from tests.test_hr_self_service import _linked_staff_user
from utils import timeutil
from utils.hr import self_attendance_view


def _seed(app, sid):
    today = timeutil.today()
    with app.app_context():
        StaffAttendance.query.filter_by(staff_id=sid).delete()
        # this month: 20 days, 4 late at N500 each
        d0 = today.replace(day=1)
        for i in range(20):
            d = d0 + timedelta(days=i)
            late = i < 4
            db.session.add(StaffAttendance(staff_id=sid, date=d, status='Late' if late else 'Present',
                                           clock_in='08:20' if late else '07:50',
                                           minutes_late=20 if late else 0, deduction=500 if late else 0))
        # two years ago: 1 late day at N1,000
        db.session.add(StaffAttendance(staff_id=sid, date=date(today.year - 2, 3, 3), status='Late',
                                       minutes_late=45, deduction=1000))
        db.session.commit()


def test_view_defaults_filters_and_all_years(app):
    _uid, sid = _linked_staff_user(app, 'att_flt', {'hr.self_attendance': 'view'})
    _seed(app, sid)
    today = timeutil.today()
    with app.app_context():
        v = self_attendance_view(sid, None, today.month)
        assert v['is_current'] and v['totals']['days'] == 20 and v['totals']['late_days'] == 4
        assert v['totals']['deduction'] == 2000 and v['pages'] == 2 and len(v['rows']) == 15
        assert len(self_attendance_view(sid, None, today.month, page=2)['rows']) == 5
        old = self_attendance_view(sid, today.year - 2, 3)
        assert old['totals']['deduction'] == 1000 and old['totals']['minutes_late'] == 45
        allv = self_attendance_view(sid, 'all', None)
        assert allv['all_years'] and allv['totals']['deduction'] == 3000 and allv['totals']['days'] == 21
        assert today.year - 2 in allv['years']


def test_account_page_uses_the_filter(app):
    _linked_staff_user(app, 'att_flt2', {'hr.self_attendance': 'view'})
    with app.app_context():
        from models import User, StaffMember
        sid = StaffMember.query.filter_by(user_id=User.query.filter_by(username='att_flt2').first().id).first().id
    _seed(app, sid)
    c = app.test_client()
    c.post('/login', data={'username': 'att_flt2', 'password': 'CorrectHorse9', '_csrf_token': login_token(c)})
    body = c.get('/account').get_data(as_text=True)
    assert 'Late-coming deductions' in body and '₦2,000.00' in body and 'Page 1 of 2' in body
    body = c.get('/account?ay=all&am=').get_data(as_text=True)
    assert '₦3,000.00' in body and 'across all years' in body
