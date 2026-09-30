"""Timetable generator: period-placement rules control where a subject can
land for a class (optionally one specific arm) -- always a particular
period, not first/not last, morning/afternoon only, or a range of periods.
The arm-level, more-versatile counterpart to the per-class Restrictions on
the Class Subjects page (which only rule periods out and apply to every arm
of a class at once)."""
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


def _build_two_arm_class(app, tag, periods_per_week=2):
    """SSS2 with two arms (Daisy, Iris), each with the SAME subject and its
    own fully-available teacher -- lets a rule scoped to just one arm prove
    it doesn't leak into the other. Seeded into a DEDICATED branch (not the
    shared default one): GenTimetableRule settings like break_after_period
    are per-branch, and other test files mutate them on the default branch
    without resetting, so a test here assuming e.g. "the default break is
    period 5" can silently see a different school's leftover setting
    depending on test execution order. Explicitly pins periods_per_day=8 and
    break_after_period=5 for this branch so the morning/afternoon-boundary
    tests have a value they can actually rely on. Returns
    (class_config_id, subject_id, branch_id)."""
    with app.app_context():
        b = Branch(name=f'ZzPPRBranch{tag}', code=None)
        db.session.add(b); db.session.flush()
        bid = b.id

        db.session.add_all([
            GenTimetableRule(branch_id=bid, rule_type='periods_per_day', value='8',
                             school_level='sss', is_active=True),
            GenTimetableRule(branch_id=bid, rule_type='break_after_period', value='5',
                             school_level='sss', is_active=True),
        ])

        cc = GenClassConfig(branch_id=bid, class_name=f'ZzSSS2{tag}', school_level='sss',
                            num_arms=2, arm_names=f'ZzDaisy{tag},ZzIris{tag}', has_streams=False)
        db.session.add(cc); db.session.flush()

        subj = GenSubject(branch_id=bid, name=f'ZzChem{tag}', school_level='sss')
        db.session.add(subj); db.session.flush()

        for arm in (f'ZzDaisy{tag}', f'ZzIris{tag}'):
            t = GenTeacher(branch_id=bid, name=f'Zz Teacher {arm}', school_level='sss',
                           max_periods_per_day=8, max_periods_per_week=40)
            db.session.add(t); db.session.flush()
            db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=t.id, subject_id=subj.id,
                                                class_config_id=cc.id, arm_name=arm))

        db.session.add(GenClassSubjectConfig(
            class_config_id=cc.id, subject_id=subj.id, is_enabled=True,
            periods_per_week=periods_per_week))
        db.session.commit()
        return cc.id, subj.id, bid


def _add_rule(app, branch_id, subject_id, class_name, arm_name, rule_type, **extra):
    with app.app_context():
        db.session.add(GenPeriodPlacementRule(
            branch_id=branch_id, name=f'Zz{rule_type}Rule', subject_id=subject_id,
            class_name=class_name, arm_name=arm_name, rule_type=rule_type,
            is_active=True, **extra))
        db.session.commit()


def _generate(c, class_id):
    r = _post(c, '/generator/generate/ortools', **{'class_ids[]': class_id},
             time_limit='15', periods_per_day='8')
    assert r.status_code == 302
    return r


# --- UI / CRUD -----------------------------------------------------------

def test_add_period_placement_rule_page_renders(app):
    cc_id, subj_id, bid = _build_two_arm_class(app, 'PA')
    c = _scoped_to_branch(_admin(app), bid)
    body = c.get('/generator/period-placement-rules/add').get_data(as_text=True)
    assert 'rule_type' in body
    assert 'ZzChemPA' in body
    for opt in ('fixed', 'not_first', 'not_last', 'morning_only', 'afternoon_only', 'range'):
        assert f'value="{opt}"' in body


def test_add_fixed_rule_model_and_routes(app):
    cc_id, subj_id, bid = _build_two_arm_class(app, 'PB')
    c = _scoped_to_branch(_admin(app), bid)

    r = _post(c, '/generator/period-placement-rules/add', name='ZzFixedChem',
             subject_id=subj_id, class_name='ZzSSS2PB', arm_name='ZzDaisyPB',
             rule_type='fixed', period_value='2')
    assert r.status_code in (302, 200)

    with app.app_context():
        rule = GenPeriodPlacementRule.query.filter_by(name='ZzFixedChem').first()
        assert rule is not None
        assert rule.is_active
        assert rule.rule_type == 'fixed'
        assert rule.period_value == 2
        assert rule.arm_name == 'ZzDaisyPB'
        rule_id = rule.id

    listing = c.get('/generator/clash-rules')
    assert listing.status_code == 200
    assert b'ZzFixedChem' in listing.data

    r2 = _post(c, f'/generator/period-placement-rules/{rule_id}/toggle')
    assert r2.status_code in (302, 200)
    with app.app_context():
        assert GenPeriodPlacementRule.query.get(rule_id).is_active is False

    r3 = _post(c, f'/generator/period-placement-rules/{rule_id}/delete')
    assert r3.status_code in (302, 200)
    with app.app_context():
        assert GenPeriodPlacementRule.query.get(rule_id) is None


def test_add_range_rule_persists_both_ends(app):
    cc_id, subj_id, bid = _build_two_arm_class(app, 'PC')
    c = _scoped_to_branch(_admin(app), bid)
    r = _post(c, '/generator/period-placement-rules/add', name='ZzRangeChem',
             subject_id=subj_id, class_name='ZzSSS2PC', arm_name='',
             rule_type='range', period_value='2', range_end='4')
    assert r.status_code in (302, 200)
    with app.app_context():
        rule = GenPeriodPlacementRule.query.filter_by(name='ZzRangeChem').first()
        assert rule is not None
        assert rule.rule_type == 'range'
        assert rule.period_value == 2 and rule.range_end == 4


def test_add_not_first_rule_needs_no_period_value(app):
    cc_id, subj_id, bid = _build_two_arm_class(app, 'PD')
    c = _scoped_to_branch(_admin(app), bid)
    r = _post(c, '/generator/period-placement-rules/add', name='ZzNotFirstChem',
             subject_id=subj_id, class_name='ZzSSS2PD', arm_name='',
             rule_type='not_first')
    assert r.status_code in (302, 200)
    with app.app_context():
        rule = GenPeriodPlacementRule.query.filter_by(name='ZzNotFirstChem').first()
        assert rule is not None
        assert rule.rule_type == 'not_first'
        assert rule.period_value is None


def test_add_fixed_rule_rejects_out_of_range_period(app):
    cc_id, subj_id, bid = _build_two_arm_class(app, 'PE')
    c = _scoped_to_branch(_admin(app), bid)
    r = _post(c, '/generator/period-placement-rules/add', name='ZzBadPeriod',
             subject_id=subj_id, class_name='ZzSSS2PE', arm_name='',
             rule_type='fixed', period_value='999')
    assert r.status_code in (302, 200)
    with app.app_context():
        assert GenPeriodPlacementRule.query.filter_by(name='ZzBadPeriod').first() is None


def test_add_range_rule_rejects_backwards_range(app):
    cc_id, subj_id, bid = _build_two_arm_class(app, 'PF')
    c = _scoped_to_branch(_admin(app), bid)
    r = _post(c, '/generator/period-placement-rules/add', name='ZzBackwardsRange',
             subject_id=subj_id, class_name='ZzSSS2PF', arm_name='',
             rule_type='range', period_value='5', range_end='2')
    assert r.status_code in (302, 200)
    with app.app_context():
        assert GenPeriodPlacementRule.query.filter_by(name='ZzBackwardsRange').first() is None


# --- Solver enforcement ----------------------------------------------------

def test_solver_enforces_fixed_for_one_arm_only(app):
    cc_id, subj_id, bid = _build_two_arm_class(app, 'FG', periods_per_week=2)
    c = _scoped_to_branch(_admin(app), bid)
    _add_rule(app, bid, subj_id, 'ZzSSS2FG', 'ZzDaisyFG', 'fixed', period_value=2)
    _generate(c, cc_id)
    with app.app_context():
        daisy_rows = GenTimetableResult.query.filter_by(
            class_name='ZzSSS2FG', arm_name='ZzDaisyFG', subject_id=subj_id).all()
        assert daisy_rows
        assert all(r.period_number == 2 for r in daisy_rows)


def test_solver_enforces_not_first(app):
    cc_id, subj_id, bid = _build_two_arm_class(app, 'NF', periods_per_week=3)
    c = _scoped_to_branch(_admin(app), bid)
    _add_rule(app, bid, subj_id, 'ZzSSS2NF', None, 'not_first')
    _generate(c, cc_id)
    with app.app_context():
        rows = GenTimetableResult.query.filter_by(class_name='ZzSSS2NF', subject_id=subj_id).all()
        assert rows
        assert all(r.period_number != 1 for r in rows)


def test_solver_enforces_not_last(app):
    cc_id, subj_id, bid = _build_two_arm_class(app, 'NL', periods_per_week=3)
    c = _scoped_to_branch(_admin(app), bid)
    _add_rule(app, bid, subj_id, 'ZzSSS2NL', None, 'not_last')
    _generate(c, cc_id)
    with app.app_context():
        rows = GenTimetableResult.query.filter_by(class_name='ZzSSS2NL', subject_id=subj_id).all()
        assert rows
        # this branch's own periods_per_day is pinned to 8 -- last period is 8.
        assert all(r.period_number != 8 for r in rows)


def test_solver_enforces_morning_only(app):
    cc_id, subj_id, bid = _build_two_arm_class(app, 'MO', periods_per_week=3)
    c = _scoped_to_branch(_admin(app), bid)
    _add_rule(app, bid, subj_id, 'ZzSSS2MO', None, 'morning_only')
    _generate(c, cc_id)
    with app.app_context():
        rows = GenTimetableResult.query.filter_by(class_name='ZzSSS2MO', subject_id=subj_id).all()
        assert rows
        # this branch's own break_after_period is pinned to 5.
        assert all(r.period_number <= 5 for r in rows)


def test_solver_enforces_afternoon_only(app):
    cc_id, subj_id, bid = _build_two_arm_class(app, 'AO', periods_per_week=3)
    c = _scoped_to_branch(_admin(app), bid)
    _add_rule(app, bid, subj_id, 'ZzSSS2AO', None, 'afternoon_only')
    _generate(c, cc_id)
    with app.app_context():
        rows = GenTimetableResult.query.filter_by(class_name='ZzSSS2AO', subject_id=subj_id).all()
        assert rows
        assert all(r.period_number > 5 for r in rows)


def test_solver_enforces_range(app):
    cc_id, subj_id, bid = _build_two_arm_class(app, 'RG', periods_per_week=4)
    c = _scoped_to_branch(_admin(app), bid)
    _add_rule(app, bid, subj_id, 'ZzSSS2RG', None, 'range', period_value=2, range_end=4)
    _generate(c, cc_id)
    with app.app_context():
        rows = GenTimetableResult.query.filter_by(class_name='ZzSSS2RG', subject_id=subj_id).all()
        assert rows
        assert all(2 <= r.period_number <= 4 for r in rows)


def test_rule_scoped_to_one_arm_does_not_affect_the_other(app):
    """A fixed-period rule on just Daisy must not touch the underlying
    GenPeriodPlacementRule scope for Iris, and generation for the whole
    class (both arms together) must still succeed -- an over-broad rule
    that accidentally applied to both arms would make this infeasible
    (Iris would need to double-book the same one slot Daisy already fixed
    it to, for the same subject at a different arm)."""
    cc_id, subj_id, bid = _build_two_arm_class(app, 'SC', periods_per_week=2)
    c = _scoped_to_branch(_admin(app), bid)
    _add_rule(app, bid, subj_id, 'ZzSSS2SC', 'ZzDaisySC', 'fixed', period_value=2)

    with app.app_context():
        rule = GenPeriodPlacementRule.query.filter_by(class_name='ZzSSS2SC').first()
        assert rule.arm_name == 'ZzDaisySC'   # scope persisted correctly

    _generate(c, cc_id)
    with app.app_context():
        daisy_rows = GenTimetableResult.query.filter_by(
            class_name='ZzSSS2SC', arm_name='ZzDaisySC', subject_id=subj_id).all()
        iris_rows = GenTimetableResult.query.filter_by(
            class_name='ZzSSS2SC', arm_name='ZzIrisSC', subject_id=subj_id).all()
        assert daisy_rows and iris_rows
        assert all(r.period_number == 2 for r in daisy_rows)
        assert len(iris_rows) == 2
