"""Timetable generator: fixed-period rules pin a subject to one specific
period number for a class (optionally one specific arm) -- whatever day it
lands on, it must always be at that exact period. The arm-level counterpart
to the excluded_periods per-class restriction (which only rules periods
out) and to GenSubjectConfig's global not_first/not_last -- neither of
those can say "always period 2" nor scope to just one arm of a class."""
from config import Config
from models import (
    db, Branch, GenSubject, GenTeacher, GenTeacherAssignment, GenClassConfig,
    GenFixedPeriodRule, GenTimetableResult,
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


def _build_two_arm_class(app, tag, periods_per_week=2):
    """SSS2 with two arms (Daisy, Iris), each with the SAME subject and its
    own fully-available teacher -- lets a rule scoped to just one arm prove
    it doesn't leak into the other. Returns (class_config_id, subject_id)."""
    with app.app_context():
        bid = Branch.get_default().id
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

        from models import GenClassSubjectConfig
        db.session.add(GenClassSubjectConfig(
            class_config_id=cc.id, subject_id=subj.id, is_enabled=True,
            periods_per_week=periods_per_week))
        db.session.commit()
        return cc.id, subj.id


def _generate(c, class_id):
    r = _post(c, '/generator/generate/ortools', **{'class_ids[]': class_id},
             time_limit='15', periods_per_day='8')
    assert r.status_code == 302
    return r


def test_add_fixed_period_rule_page_renders(app):
    cc_id, subj_id = _build_two_arm_class(app, 'FA')
    c = _admin(app)
    body = c.get('/generator/fixed-period-rules/add').get_data(as_text=True)
    assert 'fixed_period' in body
    assert 'ZzChemFA' in body


def test_add_fixed_period_rule_model_and_routes(app):
    cc_id, subj_id = _build_two_arm_class(app, 'FB')
    c = _admin(app)

    r = _post(c, '/generator/fixed-period-rules/add', name='ZzFixedChem',
             subject_id=subj_id, class_name='ZzSSS2FB', arm_name='ZzDaisyFB',
             fixed_period='2')
    assert r.status_code in (302, 200)

    with app.app_context():
        rule = GenFixedPeriodRule.query.filter_by(name='ZzFixedChem').first()
        assert rule is not None
        assert rule.is_active
        assert rule.fixed_period == 2
        assert rule.arm_name == 'ZzDaisyFB'
        rule_id = rule.id

    listing = c.get('/generator/clash-rules')
    assert listing.status_code == 200
    assert b'ZzFixedChem' in listing.data

    r2 = _post(c, f'/generator/fixed-period-rules/{rule_id}/toggle')
    assert r2.status_code in (302, 200)
    with app.app_context():
        assert GenFixedPeriodRule.query.get(rule_id).is_active is False

    r3 = _post(c, f'/generator/fixed-period-rules/{rule_id}/delete')
    assert r3.status_code in (302, 200)
    with app.app_context():
        assert GenFixedPeriodRule.query.get(rule_id) is None


def test_add_fixed_period_rule_rejects_out_of_range_period(app):
    cc_id, subj_id = _build_two_arm_class(app, 'FC')
    c = _admin(app)
    r = _post(c, '/generator/fixed-period-rules/add', name='ZzBadPeriod',
             subject_id=subj_id, class_name='ZzSSS2FC', arm_name='',
             fixed_period='999')
    assert r.status_code in (302, 200)
    with app.app_context():
        assert GenFixedPeriodRule.query.filter_by(name='ZzBadPeriod').first() is None


def test_solver_pins_subject_to_fixed_period_for_one_arm_only(app):
    """The actual feature request: Daisy's Chemistry always lands on period
    2 -- Iris's Chemistry (no rule) is unconstrained."""
    cc_id, subj_id = _build_two_arm_class(app, 'FD', periods_per_week=2)
    c = _admin(app)

    with app.app_context():
        bid = Branch.get_default().id
        db.session.add(GenFixedPeriodRule(
            branch_id=bid, name='ZzPinDaisy', subject_id=subj_id,
            class_name='ZzSSS2FD', arm_name='ZzDaisyFD', fixed_period=2, is_active=True))
        db.session.commit()

    _generate(c, cc_id)

    with app.app_context():
        daisy_rows = GenTimetableResult.query.filter_by(
            class_name='ZzSSS2FD', arm_name='ZzDaisyFD', subject_id=subj_id).all()
        assert daisy_rows, 'expected a feasible schedule for Daisy'
        assert all(r.period_number == 2 for r in daisy_rows), (
            f'expected every Daisy Chemistry period to be period 2, '
            f'got {[r.period_number for r in daisy_rows]}')


def test_fixed_period_rule_with_no_arm_applies_to_every_arm(app):
    cc_id, subj_id = _build_two_arm_class(app, 'FE', periods_per_week=1)
    c = _admin(app)

    with app.app_context():
        bid = Branch.get_default().id
        db.session.add(GenFixedPeriodRule(
            branch_id=bid, name='ZzPinAll', subject_id=subj_id,
            class_name='ZzSSS2FE', arm_name=None, fixed_period=3, is_active=True))
        db.session.commit()

    _generate(c, cc_id)

    with app.app_context():
        rows = GenTimetableResult.query.filter_by(class_name='ZzSSS2FE', subject_id=subj_id).all()
        assert rows
        assert all(r.period_number == 3 for r in rows)
        arms_seen = {r.arm_name for r in rows}
        assert arms_seen == {'ZzDaisyFE', 'ZzIrisFE'}, 'rule with no arm_name should cover every arm'
