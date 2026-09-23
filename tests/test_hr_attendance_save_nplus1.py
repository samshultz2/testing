"""Saving daily staff attendance for the whole school used to run one
StaffAttendance SELECT per staff member inside the save loop. Regression: a
school-sized save fires a small, constant number of StaffAttendance SELECTs,
not one per staff member."""
import re
from datetime import date
from sqlalchemy import event
from config import Config
from models import db, StaffMember, StaffAttendance
from tests.conftest import login_token

_STAFF_COUNT = 15
_SEQ = [0]


def _make_select_counter(table):
    pattern = re.compile(r'^select\b.*\bfrom\s+' + re.escape(table) + r'\b',
                         re.IGNORECASE | re.DOTALL)
    counts = {'n': 0}

    def before(conn, cursor, statement, params, context, executemany):
        if pattern.match(statement):
            counts['n'] += 1
    return counts, before


def _count_selects(app, table, fn):
    counts, before = _make_select_counter(table)
    with app.app_context():
        engine = db.engine
    event.listen(engine, 'before_cursor_execute', before)
    try:
        fn()
    finally:
        event.remove(engine, 'before_cursor_execute', before)
    return counts['n']


def _setup(app):
    with app.app_context():
        _SEQ[0] += 1
        staff_ids = []
        for i in range(_STAFF_COUNT):
            s = StaffMember(staff_id=f'HRN{_SEQ[0]}{i:03d}', first_name=f'S{i}',
                            surname='Staff', is_active=True)
            db.session.add(s); db.session.flush()
            staff_ids.append(s.id)
        db.session.commit()
        return staff_ids


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _pt(c):
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get('/').get_data(as_text=True)).group(1)


def test_staff_attendance_save_does_not_scale_with_staff_count(app):
    staff_ids = _setup(app)
    c = _admin(app)
    tok = _pt(c)
    day = date(2025, 3, 3)
    data = {'date': day.isoformat(), '_csrf_token': tok,
           'staff_id': [str(sid) for sid in staff_ids]}
    for sid in staff_ids:
        data[f'status_{sid}'] = 'Present'
        data[f'clock_{sid}'] = '07:15'

    n = _count_selects(app, 'staff_attendance',
                       lambda: c.post('/hr/attendance/save', data=data, follow_redirects=True))
    assert n < _STAFF_COUNT, f'{n} StaffAttendance SELECTs for a {_STAFF_COUNT}-staff save — looks like an N+1'

    with app.app_context():
        for sid in staff_ids:
            rec = StaffAttendance.query.filter_by(staff_id=sid, date=day).first()
            assert rec is not None and rec.status in ('Present', 'Late')
