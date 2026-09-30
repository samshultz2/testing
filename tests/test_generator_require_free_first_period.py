"""Timetable generator: per-class "require free first period" toggle (Class
Configuration). When on, any day this class(-arm) ends up with at least one
free period, period 1 must be one of them -- a fully-packed day is
unaffected. Off by default; each class has its own independent toggle."""
from config import Config
from models import (
    db, Branch, GenSubject, GenTeacher, GenTeacherAssignment, GenClassConfig,
    GenClassSubjectConfig, GenPeriodPlacementRule, GenTimetableResult, GenTimetableRule,
)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return c


def _post(c, url, **data):
    data.setdefault('_csrf_token', 'a' * 64)
    return c.post(url, data=data)


def _scoped_to_branch(c, branch_id):
    """View just this one branch for the rest of this client's session."""
    with c.session_transaction() as s:
        s['view_branch_id'] = branch_id
    return c


def _build_single_arm_class(app, tag, periods_per_week=20, periods_per_day=6, break_after=3,
                            require_free_first_period=True):
    """One class, one arm, one subject/teacher -- seeded into a DEDICATED
    branch (GenTimetableRule settings like periods_per_day are per-branch and
    other test files leave theirs mutated, so nothing here relies on shared
    defaults). periods_per_week is deliberately below periods_per_day * 5 so
    the class-arm's week has real free periods to place. Returns
    (class_config_id, subject_id, branch_id)."""
    with app.app_context():
        b = Branch(name=f'ZzRFPBranch{tag}', code=None)
        db.session.add(b); db.session.flush()
        bid = b.id

        db.session.add_all([
            GenTimetableRule(branch_id=bid, rule_type='periods_per_day', value=str(periods_per_day),
                             school_level='sss', is_active=True),
            GenTimetableRule(branch_id=bid, rule_type='break_after_period', value=str(break_after),
                             school_level='sss', is_active=True),
            # Irrelevant to this feature and would otherwise fight a
            # high-periods_per_week subject (needs every school day, which
            # the Mon/Fri day-separation default forbids) -- switched off so
            # these tests isolate the free-first-period toggle specifically.
            GenTimetableRule(branch_id=bid, rule_type='day_separation_enabled', value='false',
                             school_level='sss', is_active=True),
        ])

        cc = GenClassConfig(branch_id=bid, class_name=f'ZzRFP{tag}', school_level='sss',
                            num_arms=1, arm_names=f'ZzArm{tag}', has_streams=False,
                            require_free_first_period=require_free_first_period)
        db.session.add(cc); db.session.flush()

        subj = GenSubject(branch_id=bid, name=f'ZzSubj{tag}', school_level='sss')
        db.session.add(subj); db.session.flush()

        t = GenTeacher(branch_id=bid, name=f'Zz Teacher {tag}', school_level='sss',
                       max_periods_per_day=periods_per_day, max_periods_per_week=periods_per_day * 5)
        db.session.add(t); db.session.flush()
        db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=t.id, subject_id=subj.id,
                                            class_config_id=cc.id, arm_name=f'ZzArm{tag}'))

        db.session.add(GenClassSubjectConfig(
            class_config_id=cc.id, subject_id=subj.id, is_enabled=True,
            periods_per_week=periods_per_week))
        db.session.commit()
        return cc.id, subj.id, bid


def _build_multi_subject_class(app, tag, num_subjects, periods_per_week_each, periods_per_day=6,
                               break_after=3, require_free_first_period=True):
    """One class, one arm, several subjects (each its own teacher) -- unlike
    _build_single_arm_class, this can carry real weekly load without hitting
    the solver's "a non-double subject appears at most once a day" cap: each
    subject here only ever wants ONE period/day (periods_per_week_each <= 5),
    so num_subjects of them together fill num_subjects periods/day, every
    day, deterministically leaving periods_per_day - num_subjects free each
    day. Returns (class_config_id, branch_id)."""
    with app.app_context():
        b = Branch(name=f'ZzRFPMBranch{tag}', code=None)
        db.session.add(b); db.session.flush()
        bid = b.id

        db.session.add_all([
            GenTimetableRule(branch_id=bid, rule_type='periods_per_day', value=str(periods_per_day),
                             school_level='sss', is_active=True),
            GenTimetableRule(branch_id=bid, rule_type='break_after_period', value=str(break_after),
                             school_level='sss', is_active=True),
            # periods_per_week_each == 5 means every subject here needs every
            # school day, which the Mon/Fri day-separation default forbids --
            # switched off so this scenario isolates the free-first-period
            # toggle specifically.
            GenTimetableRule(branch_id=bid, rule_type='day_separation_enabled', value='false',
                             school_level='sss', is_active=True),
        ])

        cc = GenClassConfig(branch_id=bid, class_name=f'ZzRFPM{tag}', school_level='sss',
                            num_arms=1, arm_names=f'ZzArm{tag}', has_streams=False,
                            require_free_first_period=require_free_first_period)
        db.session.add(cc); db.session.flush()

        for i in range(num_subjects):
            subj = GenSubject(branch_id=bid, name=f'ZzSubj{tag}{i}', school_level='sss')
            db.session.add(subj); db.session.flush()
            t = GenTeacher(branch_id=bid, name=f'Zz Teacher {tag}{i}', school_level='sss',
                           max_periods_per_day=periods_per_day, max_periods_per_week=periods_per_day * 5)
            db.session.add(t); db.session.flush()
            db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=t.id, subject_id=subj.id,
                                                class_config_id=cc.id, arm_name=f'ZzArm{tag}'))
            db.session.add(GenClassSubjectConfig(
                class_config_id=cc.id, subject_id=subj.id, is_enabled=True,
                periods_per_week=periods_per_week_each))
        db.session.commit()
        return cc.id, bid


def _add_fixed_first_period_rule(app, branch_id, subject_id, class_name):
    """Pins a subject to always land on period 1 -- used to force period 1
    occupied on every day it's scheduled, so the toggle's effect can be
    proven deterministically instead of relying on solver randomization."""
    with app.app_context():
        db.session.add(GenPeriodPlacementRule(
            branch_id=branch_id, name='ZzForcePeriod1', subject_id=subject_id,
            class_name=class_name, arm_name=None, rule_type='fixed', period_value=1,
            is_active=True))
        db.session.commit()


def _generate(c, class_id, periods_per_day):
    return _post(c, '/generator/generate/ortools', **{'class_ids[]': class_id},
                time_limit='20', periods_per_day=str(periods_per_day))


# --- UI / CRUD -------------------------------------------------------------

def _fresh_branch(app, tag):
    with app.app_context():
        b = Branch(name=f'ZzRFPCrudBranch{tag}', code=None)
        db.session.add(b); db.session.commit()
        return b.id


def test_add_class_config_page_has_toggle(app):
    bid = _fresh_branch(app, 'PAGE')
    c = _scoped_to_branch(_admin(app), bid)
    body = c.get('/generator/classes/add').get_data(as_text=True)
    assert 'require_free_first_period' in body


def test_toggle_persists_through_add_and_edit(app):
    bid = _fresh_branch(app, 'PERSIST')
    c = _scoped_to_branch(_admin(app), bid)
    r = _post(c, '/generator/classes/add', class_name='ZzToggleClass',
             num_arms='1', arm_names='ZzOnly', require_free_first_period='on')
    assert r.status_code in (302, 200)
    with app.app_context():
        cc = GenClassConfig.query.filter_by(class_name='ZzToggleClass', branch_id=bid).first()
        assert cc is not None
        assert cc.require_free_first_period is True
        cc_id = cc.id

    edit_body = c.get(f'/generator/classes/{cc_id}').get_data(as_text=True)
    assert 'checked' in edit_body.split('require_free_first_period')[1][:60]

    r2 = _post(c, f'/generator/classes/{cc_id}/update', class_name='ZzToggleClass',
              num_arms='1', arm_names='ZzOnly')  # omitted -> unchecked
    assert r2.status_code in (302, 200)
    with app.app_context():
        cc = GenClassConfig.query.get(cc_id)
        assert cc.require_free_first_period is False


def test_toggle_defaults_off_for_new_class(app):
    bid = _fresh_branch(app, 'DEFOFF')
    c = _scoped_to_branch(_admin(app), bid)
    r = _post(c, '/generator/classes/add', class_name='ZzDefaultOffClass',
             num_arms='1', arm_names='ZzOnly')
    assert r.status_code in (302, 200)
    with app.app_context():
        cc = GenClassConfig.query.filter_by(class_name='ZzDefaultOffClass', branch_id=bid).first()
        assert cc is not None
        assert not cc.require_free_first_period


# --- Solver enforcement ------------------------------------------------------

def test_solver_keeps_period_1_free_on_free_days_when_toggle_on(app):
    """4 subjects x 5 periods/week each = 20 of this class's 30 weekly slots
    (a single subject is capped at one period/day unless it's a double
    period, so the load has to come from several subjects, not one big
    one) -- every day lands exactly 4 occupied, 2 free, deterministically,
    so every day is a day this toggle must act on."""
    cc_id, bid = _build_multi_subject_class(
        app, 'ON', num_subjects=4, periods_per_week_each=5, periods_per_day=6,
        require_free_first_period=True)
    c = _scoped_to_branch(_admin(app), bid)
    r = _generate(c, cc_id, periods_per_day=6)
    assert r.status_code == 302

    with app.app_context():
        rows = GenTimetableResult.query.filter_by(class_name='ZzRFPMON', arm_name='ZzArmON').all()
        assert rows
        occupied_by_day = {}
        for row in rows:
            occupied_by_day.setdefault(row.day_of_week, set()).add(row.period_number)

        assert len(occupied_by_day) == 5
        for day, periods in occupied_by_day.items():
            assert len(periods) == 4, f'day {day}: expected 4 occupied periods, got {sorted(periods)}'
            assert 1 not in periods, (
                f'day {day} has a free period but period 1 is occupied: {sorted(periods)}')


def test_toggle_on_makes_forced_period_1_occupancy_infeasible(app):
    """The only subject in this class needs just one period/week, pinned to
    period 1 -- so wherever the solver lands it, that day has period 1
    occupied and every other period that day (nothing else is scheduled)
    free. With the toggle ON that's a direct violation on whichever day it
    picks, so this whole scenario must fail to generate. (periods_per_week=1
    keeps this independent of the separate, always-on "a subject can only
    open the day on one day a week" cap.)"""
    cc_id, subj_id, bid = _build_single_arm_class(
        app, 'INF', periods_per_week=1, periods_per_day=6, require_free_first_period=True)
    _add_fixed_first_period_rule(app, bid, subj_id, 'ZzRFPINF')
    c = _scoped_to_branch(_admin(app), bid)
    r = _generate(c, cc_id, periods_per_day=6)
    assert r.status_code == 302

    with app.app_context():
        rows = GenTimetableResult.query.filter_by(class_name='ZzRFPINF', arm_name='ZzArmINF').all()
        assert not rows, 'expected generation to fail: period 1 pinned occupied on a day with free periods'


def test_toggle_off_allows_period_1_occupied_alongside_free_periods(app):
    """Same forced-period-1, one-period-a-week subject as the infeasibility
    test above, but with the toggle OFF -- proving the earlier failure came
    from the toggle, not from the scenario itself being unsolvable for some
    unrelated reason."""
    cc_id, subj_id, bid = _build_single_arm_class(
        app, 'OFF', periods_per_week=1, periods_per_day=6, require_free_first_period=False)
    _add_fixed_first_period_rule(app, bid, subj_id, 'ZzRFPOFF')
    c = _scoped_to_branch(_admin(app), bid)
    r = _generate(c, cc_id, periods_per_day=6)
    assert r.status_code == 302

    with app.app_context():
        rows = GenTimetableResult.query.filter_by(class_name='ZzRFPOFF', arm_name='ZzArmOFF').all()
        assert rows
        assert all(row.period_number == 1 for row in rows)
        assert len(rows) == 1
