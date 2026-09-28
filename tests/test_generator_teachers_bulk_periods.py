"""Timetable generator: /generator/teachers back button, and bulk-raising max
periods/week for selected teachers with max periods/day auto-recalculated."""
from config import Config
from models import db, Branch, GenTeacher, GenTimetableRule
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return c


def _seed_teacher(app, tag, max_week=30, max_day=6, available_days=None):
    with app.app_context():
        bid = Branch.get_default().id
        t = GenTeacher(branch_id=bid, name=f'Zz Teacher{tag}', school_level='sss',
                       max_periods_per_day=max_day, max_periods_per_week=max_week,
                       available_days=available_days)
        db.session.add(t); db.session.commit()
        return t.id


def _seed_periods_per_day_rule(app, value=8):
    with app.app_context():
        bid = Branch.get_default().id
        db.session.add(GenTimetableRule(branch_id=bid, rule_type='periods_per_day',
                                        value=str(value), school_level='sss'))
        db.session.commit()


def test_teachers_page_has_back_button(app):
    c = _admin(app)
    r = c.get('/generator/teachers')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert '/generator/level/sss' in body
    assert 'Back to SSS Dashboard' in body


def test_teachers_page_has_checkboxes_and_bulk_controls(app):
    _seed_teacher(app, 'A')
    c = _admin(app)
    r = c.get('/generator/teachers')
    body = r.get_data(as_text=True)
    assert 'teacher-checkbox' in body
    assert 'bulk_increase_teacher_periods' in body or 'bulkIncreaseForm' in body
    assert 'Increase Selected' in body


def test_add_teacher_page_has_back_button(app):
    c = _admin(app)
    r = c.get('/generator/teachers/add')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert '/generator/teachers' in body
    assert 'Back to Teachers' in body


def test_edit_teacher_page_has_back_button(app):
    tid = _seed_teacher(app, 'I', max_week=30, max_day=6)
    c = _admin(app)
    r = c.get(f'/generator/teachers/{tid}')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert '/generator/teachers' in body
    assert 'Back to Teachers' in body


def test_bulk_increase_raises_week_and_recalculates_day(app):
    """5 working days (default), week 30 -> +10 = 40 -> ceil(40/5) = 8 per day."""
    _seed_periods_per_day_rule(app, value=10)   # cap well above 8 so it isn't what limits this
    tid = _seed_teacher(app, 'B', max_week=30, max_day=6, available_days='0,1,2,3,4')
    c = _admin(app)
    r = c.post('/generator/teachers/bulk-increase-periods', follow_redirects=True, data={
        '_csrf_token': 'a' * 64, 'increment': '10', 'teacher_ids[]': [str(tid)],
    })
    assert r.status_code == 200
    assert '1 teacher(s)' in r.get_data(as_text=True)
    with app.app_context():
        t = db.session.get(GenTeacher, tid)
        assert t.max_periods_per_week == 40
        assert t.max_periods_per_day == 8


def test_bulk_increase_spreads_over_teachers_own_working_days(app):
    """A 3-day-a-week teacher: week 12 -> +9 = 21 -> ceil(21/3) = 7 per day,
    not divided by the default 5 days."""
    _seed_periods_per_day_rule(app, value=10)
    tid = _seed_teacher(app, 'C', max_week=12, max_day=4, available_days='0,2,4')
    c = _admin(app)
    c.post('/generator/teachers/bulk-increase-periods', follow_redirects=True, data={
        '_csrf_token': 'a' * 64, 'increment': '9', 'teacher_ids[]': [str(tid)],
    })
    with app.app_context():
        t = db.session.get(GenTeacher, tid)
        assert t.max_periods_per_week == 21
        assert t.max_periods_per_day == 7


def test_bulk_increase_caps_day_at_school_periods_per_day(app):
    """Week pushed high enough that the even split would exceed the school's
    actual periods-per-day structure -- the day cap wins."""
    _seed_periods_per_day_rule(app, value=8)
    tid = _seed_teacher(app, 'D', max_week=30, max_day=6, available_days='0,1,2,3,4')
    c = _admin(app)
    c.post('/generator/teachers/bulk-increase-periods', follow_redirects=True, data={
        '_csrf_token': 'a' * 64, 'increment': '50', 'teacher_ids[]': [str(tid)],
    })
    with app.app_context():
        t = db.session.get(GenTeacher, tid)
        assert t.max_periods_per_week == 80        # 30 + 50, uncapped -- only /day is capped
        assert t.max_periods_per_day == 8           # ceil(80/5)=16, capped to the rule's 8


def test_bulk_increase_leaves_unselected_teachers_alone(app):
    _seed_periods_per_day_rule(app, value=10)
    tid1 = _seed_teacher(app, 'E1', max_week=30, max_day=6, available_days='0,1,2,3,4')
    tid2 = _seed_teacher(app, 'E2', max_week=30, max_day=6, available_days='0,1,2,3,4')
    c = _admin(app)
    c.post('/generator/teachers/bulk-increase-periods', follow_redirects=True, data={
        '_csrf_token': 'a' * 64, 'increment': '5', 'teacher_ids[]': [str(tid1)],
    })
    with app.app_context():
        assert db.session.get(GenTeacher, tid1).max_periods_per_week == 35
        assert db.session.get(GenTeacher, tid2).max_periods_per_week == 30


def test_bulk_increase_with_no_selection_flashes_error_and_changes_nothing(app):
    tid = _seed_teacher(app, 'F', max_week=30, max_day=6)
    c = _admin(app)
    r = c.post('/generator/teachers/bulk-increase-periods', follow_redirects=True, data={
        '_csrf_token': 'a' * 64, 'increment': '5',
    })
    assert r.status_code == 200
    assert 'Select at least one teacher' in r.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(GenTeacher, tid).max_periods_per_week == 30


def test_bulk_increase_with_zero_or_missing_increment_flashes_error_and_changes_nothing(app):
    tid = _seed_teacher(app, 'G', max_week=30, max_day=6)
    c = _admin(app)
    r = c.post('/generator/teachers/bulk-increase-periods', follow_redirects=True, data={
        '_csrf_token': 'a' * 64, 'increment': '0', 'teacher_ids[]': [str(tid)],
    })
    assert 'Enter a positive number' in r.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(GenTeacher, tid).max_periods_per_week == 30


def test_bulk_increase_skips_ids_from_another_branch(app):
    """A stale/tampered id from a branch the current user can't access must be
    silently skipped, not applied and not allowed to 403 the whole batch."""
    from models import User

    with app.app_context():
        other = Branch(name='ZzTPOtherBranch', is_default=False)
        db.session.add(other); db.session.flush()
        u = User(username='zztp_branch_admin', full_name='Zz TP Branch Admin', role='admin',
                 scope='branch', branch_id=other.id, rank=50, manage_scope='branch',
                 is_active=True, must_change_password=False)
        u.set_password('Str0ng!Passw0rd1')
        other_teacher = GenTeacher(branch_id=other.id, name='Zz Other Teacher', school_level='sss',
                                   max_periods_per_day=6, max_periods_per_week=30)
        db.session.add_all([u, other_teacher]); db.session.commit()
        other_bid = other.id
        other_tid = other_teacher.id

    own_tid = _seed_teacher(app, 'H', max_week=30, max_day=6, available_days='0,1,2,3,4')
    _seed_periods_per_day_rule(app, value=10)
    with app.app_context():
        # own_tid's rule above is on the default branch; give the other branch
        # a permissive rule too so a leak wouldn't be masked by the cap.
        db.session.add(GenTimetableRule(branch_id=other_bid, rule_type='periods_per_day',
                                        value='10', school_level='sss'))
        db.session.commit()

    c = app.test_client()
    c.post('/login', data={'username': 'zztp_branch_admin', 'password': 'Str0ng!Passw0rd1',
                           '_csrf_token': login_token(c)})
    from tests.conftest import auth_csrf
    r = c.post('/generator/teachers/bulk-increase-periods', follow_redirects=True, data={
        '_csrf_token': auth_csrf(c), 'increment': '5',
        'teacher_ids[]': [str(other_tid), str(own_tid)],
    })
    assert r.status_code == 200

    with app.app_context():
        # The branch-B admin's own teacher is updated...
        assert db.session.get(GenTeacher, other_tid).max_periods_per_week == 35
        # ...but the default-branch teacher they have no access to is untouched.
        assert db.session.get(GenTeacher, own_tid).max_periods_per_week == 30


def test_teachers_page_has_delete_controls(app):
    _seed_teacher(app, 'DelUI')
    c = _admin(app)
    r = c.get('/generator/teachers')
    body = r.get_data(as_text=True)
    assert 'bulk_delete_teachers' in body or 'bulkDeleteForm' in body
    assert 'Delete Selected' in body


def test_bulk_delete_removes_every_selected_teacher(app):
    tid1 = _seed_teacher(app, 'Del1')
    tid2 = _seed_teacher(app, 'Del2')
    c = _admin(app)
    r = c.post('/generator/teachers/bulk-delete', follow_redirects=True, data={
        '_csrf_token': 'a' * 64, 'teacher_ids[]': [str(tid1), str(tid2)],
    })
    assert r.status_code == 200
    assert '2 teacher(s)' in r.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(GenTeacher, tid1).is_active is False
        assert db.session.get(GenTeacher, tid2).is_active is False


def test_bulk_delete_leaves_unselected_teachers_alone(app):
    tid1 = _seed_teacher(app, 'Del3')
    tid2 = _seed_teacher(app, 'Del4')
    c = _admin(app)
    c.post('/generator/teachers/bulk-delete', follow_redirects=True, data={
        '_csrf_token': 'a' * 64, 'teacher_ids[]': [str(tid1)],
    })
    with app.app_context():
        assert db.session.get(GenTeacher, tid1).is_active is False
        assert db.session.get(GenTeacher, tid2).is_active is True


def test_bulk_delete_with_no_selection_flashes_error_and_deletes_nothing(app):
    tid = _seed_teacher(app, 'Del5')
    c = _admin(app)
    r = c.post('/generator/teachers/bulk-delete', follow_redirects=True, data={
        '_csrf_token': 'a' * 64,
    })
    assert r.status_code == 200
    assert 'Select at least one teacher' in r.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(GenTeacher, tid).is_active is True


def test_bulk_delete_skips_ids_from_another_branch(app):
    """Same isolation guarantee as the bulk period raise: an id from a branch
    the current user can't access is silently skipped, not deleted."""
    from models import User

    with app.app_context():
        other = Branch(name='ZzTPDelOtherBranch', is_default=False)
        db.session.add(other); db.session.flush()
        u = User(username='zztpdel_branch_admin', full_name='Zz TP Del Branch Admin', role='admin',
                 scope='branch', branch_id=other.id, rank=50, manage_scope='branch',
                 is_active=True, must_change_password=False)
        u.set_password('Str0ng!Passw0rd1')
        other_teacher = GenTeacher(branch_id=other.id, name='Zz Other Del Teacher', school_level='sss',
                                   max_periods_per_day=6, max_periods_per_week=30)
        db.session.add_all([u, other_teacher]); db.session.commit()
        other_tid = other_teacher.id

    own_tid = _seed_teacher(app, 'Del6')
    c = app.test_client()
    c.post('/login', data={'username': 'zztpdel_branch_admin', 'password': 'Str0ng!Passw0rd1',
                           '_csrf_token': login_token(c)})
    from tests.conftest import auth_csrf
    r = c.post('/generator/teachers/bulk-delete', follow_redirects=True, data={
        '_csrf_token': auth_csrf(c), 'teacher_ids[]': [str(other_tid), str(own_tid)],
    })
    assert r.status_code == 200

    with app.app_context():
        assert db.session.get(GenTeacher, other_tid).is_active is False
        assert db.session.get(GenTeacher, own_tid).is_active is True
