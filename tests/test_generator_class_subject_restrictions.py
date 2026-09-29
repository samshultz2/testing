"""Timetable generator: per-class subject period restrictions on
GenClassSubjectConfig (not_first_period, not_last_period, avoid_morning,
avoid_afternoon, excluded_periods) -- the class-level counterpart to
GenSubjectConfig's school-wide not_first_period/not_last_period, which used
to be the only way to restrict where a subject lands, with no way to scope
it to one class. Covers the config UI, the save route, and that the OR-tools
solver actually enforces each restriction (not just stores it)."""
from config import Config
from models import (
    db, Branch, GenClassConfig, GenSubject, GenSubjectConfig, GenClassSubjectConfig,
    GenTeacher, GenTeacherAssignment, GenTimetableResult, GenTimetableRule,
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


def _build_class(app, tag, periods_per_week=2):
    """One class-arm, one subject, one fully-available teacher -- nothing
    else constraining the solve, so any restriction's effect is unambiguous.
    Returns (class_config_id, subject_id)."""
    with app.app_context():
        bid = Branch.get_default().id
        cc = GenClassConfig(branch_id=bid, class_name=f'ZzSSS2{tag}', school_level='sss',
                            num_arms=1, arm_names=f'ZzLily{tag}', has_streams=False)
        db.session.add(cc); db.session.flush()

        subj = GenSubject(branch_id=bid, name=f'ZzGeography{tag}', school_level='sss')
        db.session.add(subj); db.session.flush()

        db.session.add(GenClassSubjectConfig(
            class_config_id=cc.id, subject_id=subj.id, is_enabled=True,
            periods_per_week=periods_per_week))

        teacher = GenTeacher(branch_id=bid, name=f'Zz Geo Teacher{tag}', school_level='sss',
                             max_periods_per_day=8, max_periods_per_week=40)
        db.session.add(teacher); db.session.flush()

        db.session.add(GenTeacherAssignment(
            branch_id=bid, teacher_id=teacher.id, subject_id=subj.id,
            class_config_id=cc.id, arm_name=f'ZzLily{tag}'))
        db.session.commit()
        return cc.id, subj.id


def _set_restriction(app, class_id, subject_id, **fields):
    with app.app_context():
        cfg = GenClassSubjectConfig.query.filter_by(
            class_config_id=class_id, subject_id=subject_id).first()
        for k, v in fields.items():
            setattr(cfg, k, v)
        db.session.commit()


def _generate(c, class_id):
    r = _post(c, '/generator/generate/ortools', **{'class_ids[]': class_id},
             time_limit='15', periods_per_day='8')
    assert r.status_code == 302
    return r


def test_class_subjects_config_page_shows_new_restriction_controls(app):
    cc_id, subj_id = _build_class(app, 'CA')
    c = _admin(app)
    body = c.get(f'/generator/class-subjects/{cc_id}').get_data(as_text=True)
    assert f'not_first_{subj_id}' in body
    assert f'not_last_{subj_id}' in body
    assert f'avoid_morning_{subj_id}' in body
    assert f'avoid_afternoon_{subj_id}' in body
    assert f'excluded_periods_{subj_id}' in body


def test_class_subjects_config_flags_global_not_first_period(app):
    """The class-level checkbox itself is NOT checked just because a global
    default exists (checking it would bake a redundant class-level flag onto
    every class the moment the page is saved) -- but the page marks it with
    an asterisk so the admin can see the global restriction already applies."""
    cc_id, subj_id = _build_class(app, 'CB')
    with app.app_context():
        bid = Branch.get_default().id
        db.session.add(GenSubjectConfig(
            branch_id=bid, subject_id=subj_id, school_level='sss',
            periods_per_week=2, not_first_period=True))
        db.session.commit()
    c = _admin(app)
    body = c.get(f'/generator/class-subjects/{cc_id}').get_data(as_text=True)
    import re
    m = re.search(rf'name="not_first_{subj_id}"[^>]*>\s*1st\*', body)
    assert m, 'expected the 1st chip to carry the * marker for the global default'
    assert 'checked' not in m.group(0), 'the class-level checkbox itself must stay unchecked'


def test_save_class_subjects_config_persists_restrictions(app):
    cc_id, subj_id = _build_class(app, 'CC')
    c = _admin(app)
    r = _post(c, f'/generator/class-subjects/{cc_id}/save', **{
        'subject_id[]': str(subj_id),
        f'enabled_{subj_id}': 'on',
        f'periods_{subj_id}': '2',
        f'not_first_{subj_id}': 'on',
        f'avoid_afternoon_{subj_id}': 'on',
        f'excluded_periods_{subj_id}': '3, 7, notanumber, 3',
    })
    assert r.status_code in (302, 200)
    with app.app_context():
        cfg = GenClassSubjectConfig.query.filter_by(class_config_id=cc_id, subject_id=subj_id).first()
        assert cfg.not_first_period is True
        assert cfg.not_last_period is False
        assert cfg.avoid_afternoon is True
        assert cfg.avoid_morning is False
        assert cfg.excluded_periods == '3,7'   # deduped, sorted, junk dropped


def test_solver_enforces_per_class_not_first_period(app):
    cc_id, subj_id = _build_class(app, 'CD', periods_per_week=3)
    _set_restriction(app, cc_id, subj_id, not_first_period=True)
    c = _admin(app)
    _generate(c, cc_id)
    with app.app_context():
        rows = GenTimetableResult.query.filter_by(class_name='ZzSSS2CD', subject_id=subj_id).all()
        assert rows, 'expected a feasible schedule with plenty of open slots'
        assert all(r.period_number != 1 for r in rows)


def test_solver_enforces_per_class_avoid_morning(app):
    cc_id, subj_id = _build_class(app, 'CE', periods_per_week=3)
    _set_restriction(app, cc_id, subj_id, avoid_morning=True)
    c = _admin(app)
    _generate(c, cc_id)
    with app.app_context():
        rows = GenTimetableResult.query.filter_by(class_name='ZzSSS2CE', subject_id=subj_id).all()
        assert rows
        # default break_after_period is 5 -- morning is periods 1-5.
        assert all(r.period_number > 5 for r in rows)


def test_solver_enforces_per_class_avoid_afternoon(app):
    cc_id, subj_id = _build_class(app, 'CF', periods_per_week=3)
    _set_restriction(app, cc_id, subj_id, avoid_afternoon=True)
    c = _admin(app)
    _generate(c, cc_id)
    with app.app_context():
        rows = GenTimetableResult.query.filter_by(class_name='ZzSSS2CF', subject_id=subj_id).all()
        assert rows
        assert all(r.period_number <= 5 for r in rows)


def test_solver_enforces_per_class_excluded_periods(app):
    cc_id, subj_id = _build_class(app, 'CG', periods_per_week=4)
    _set_restriction(app, cc_id, subj_id, excluded_periods='3,6')
    c = _admin(app)
    _generate(c, cc_id)
    with app.app_context():
        rows = GenTimetableResult.query.filter_by(class_name='ZzSSS2CG', subject_id=subj_id).all()
        assert rows
        assert all(r.period_number not in (3, 6) for r in rows)


def test_class_level_override_does_not_affect_other_classes(app):
    """Setting not_first_period on one class's override row must not leak
    into another class taking the same-named-but-distinct subject."""
    cc_a, subj_a = _build_class(app, 'CH1', periods_per_week=2)
    cc_b, subj_b = _build_class(app, 'CH2', periods_per_week=2)
    _set_restriction(app, cc_a, subj_a, not_first_period=True)
    c = _admin(app)
    _generate(c, cc_b)
    with app.app_context():
        rows = GenTimetableResult.query.filter_by(class_name='ZzSSS2CH2', subject_id=subj_b).all()
        assert rows
        # No restriction on class B -- the OTHER class's restriction didn't
        # leak in, cfg for B stays untouched.
        cfg_b = GenClassSubjectConfig.query.filter_by(class_config_id=cc_b, subject_id=subj_b).first()
        assert cfg_b.not_first_period is False
