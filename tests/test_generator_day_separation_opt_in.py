"""The school-wide day-separation default (Rules -> Scheduling Constraints)
used to apply to every subject unless individually exempted on that
subject's own rules page -- stressful with many subjects, since turning the
rule on meant visiting each one to opt it back out. Flipped: the rule is now
opt-IN. A subject with no GenSubjectConfig row, or one whose row doesn't
explicitly say day_separation_exempt=False, is exempt by default. Turning the
rule on and picking subjects now happens on the Rules page itself, in one
place, via a day_separation_subjects[] checklist."""
from config import Config
from models import (
    db, Branch, GenSubject, GenTeacher, GenTeacherAssignment, GenClassConfig,
    GenSubjectConfig, GenClassSubjectConfig, GenTimetableRule, GenTimetableResult,
)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return c


def _post(c, url, follow_redirects=False, **data):
    data.setdefault('_csrf_token', 'a' * 64)
    return c.post(url, data=data, follow_redirects=follow_redirects)


def _scoped_to_branch(c, branch_id):
    with c.session_transaction() as s:
        s['view_branch_id'] = branch_id
    return c


def _build_needs_both_days_class(app, tag, explicit_config=None):
    """One class/arm/subject whose only available teacher slots are Monday
    and Friday -- the default separated days -- with periods_per_week=2, so
    it genuinely needs BOTH of them to fit. If the day-separation default
    applies to this subject, generation must fail; if it's exempt, it must
    succeed. `explicit_config`, if given, is passed straight to
    GenSubjectConfig (e.g. {'day_separation_exempt': False}); omit it to
    leave the subject with no config row at all."""
    with app.app_context():
        b = Branch(name=f'ZzDaySepOptIn{tag}', code=None)
        db.session.add(b); db.session.flush()
        bid = b.id

        db.session.add_all([
            GenTimetableRule(branch_id=bid, rule_type='periods_per_day', value='6',
                             school_level='sss', is_active=True),
            GenTimetableRule(branch_id=bid, rule_type='break_after_period', value='3',
                             school_level='sss', is_active=True),
            GenTimetableRule(branch_id=bid, rule_type='day_separation_enabled', value='true',
                             school_level='sss', is_active=True),
            GenTimetableRule(branch_id=bid, rule_type='day_separation_day_a', value='0',
                             school_level='sss', is_active=True),
            GenTimetableRule(branch_id=bid, rule_type='day_separation_day_b', value='4',
                             school_level='sss', is_active=True),
        ])

        cc = GenClassConfig(branch_id=bid, class_name=f'ZzDS{tag}', school_level='sss',
                            num_arms=1, arm_names=f'ZzArm{tag}')
        subj = GenSubject(branch_id=bid, name=f'ZzSubj{tag}', school_level='sss')
        db.session.add_all([cc, subj]); db.session.flush()

        if explicit_config is not None:
            db.session.add(GenSubjectConfig(branch_id=bid, subject_id=subj.id, school_level='sss',
                                            periods_per_week=2, **explicit_config))

        db.session.add(GenClassSubjectConfig(class_config_id=cc.id, subject_id=subj.id,
                                             is_enabled=True, is_active=True, periods_per_week=2))

        teacher = GenTeacher(branch_id=bid, name=f'ZzTeacher{tag}', school_level='sss',
                             max_periods_per_day=6, max_periods_per_week=30)
        db.session.add(teacher); db.session.flush()
        db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=teacher.id, subject_id=subj.id,
                                            class_config_id=cc.id, arm_name=f'ZzArm{tag}'))
        # Only Monday and Friday available -- forces both separated days.
        from models import GenTeacherAvailability
        for day in range(5):
            if day in (0, 4):
                continue
            for period in range(1, 7):
                db.session.add(GenTeacherAvailability(teacher_id=teacher.id, day_of_week=day,
                                                      period_number=period, is_available=False))
        db.session.commit()
        return cc.id, subj.id, bid


def test_subject_with_no_config_row_is_exempt_by_default(app):
    """No GenSubjectConfig row at all for this subject -- under the new
    opt-in default it must be exempt, so needing both Monday and Friday is
    fine and generation succeeds."""
    cc_id, subj_id, bid = _build_needs_both_days_class(app, 'A', explicit_config=None)
    c = _scoped_to_branch(_admin(app), bid)
    r = _post(c, '/generator/generate/ortools', **{'class_ids[]': cc_id},
             time_limit='20', periods_per_day='6', follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        rows = GenTimetableResult.query.filter_by(subject_id=subj_id).all()
        assert rows, 'expected generation to succeed (subject exempt by default) — check flash message'
        assert len(rows) == 2
        assert {row.day_of_week for row in rows} == {0, 4}


def test_subject_explicitly_included_is_still_constrained(app):
    """An explicit day_separation_exempt=False row opts this subject IN --
    needing both Monday and Friday must now fail cleanly, same as the old
    "on by default" behaviour for a subject an admin has chosen to include."""
    cc_id, subj_id, bid = _build_needs_both_days_class(
        app, 'B', explicit_config={'day_separation_exempt': False})
    c = _scoped_to_branch(_admin(app), bid)
    r = _post(c, '/generator/generate/ortools', **{'class_ids[]': cc_id},
             time_limit='20', periods_per_day='6', follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        rows = GenTimetableResult.query.filter_by(subject_id=subj_id).all()
        assert not rows, (
            f'expected generation to fail cleanly (subject included, needs both '
            f'separated days), but got {len(rows)} saved rows')


def test_rules_page_lists_subjects_with_correct_checked_state(app):
    bid = None
    with app.app_context():
        b = Branch(name='ZzDaySepRulesPage', code=None)
        db.session.add(b); db.session.flush(); bid = b.id
        s_in = GenSubject(branch_id=bid, name='ZzIncludedSubj', school_level='sss')
        s_out = GenSubject(branch_id=bid, name='ZzExemptSubj', school_level='sss')
        db.session.add_all([s_in, s_out]); db.session.flush()
        db.session.add(GenSubjectConfig(branch_id=bid, subject_id=s_in.id, school_level='sss',
                                        day_separation_exempt=False))
        # s_out: no config row at all -- must show unchecked.
        db.session.commit()

    c = _scoped_to_branch(_admin(app), bid)
    body = c.get('/generator/rules').get_data(as_text=True)
    assert 'ZzIncludedSubj' in body and 'ZzExemptSubj' in body
    assert 'name="day_separation_subjects[]"' in body
    # The included subject's checkbox is checked; the exempt one's isn't.
    import re
    m_in = re.search(r'value="\d+"\s+checked>\s*<span>ZzIncludedSubj</span>', body)
    m_out = re.search(r'value="\d+"\s+checked>\s*<span>ZzExemptSubj</span>', body)
    assert m_in is not None, 'included subject should be pre-checked'
    assert m_out is None, 'exempt (unconfigured) subject should NOT be pre-checked'


def test_rules_page_save_sets_exempt_for_every_subject_at_this_level(app):
    bid = None
    with app.app_context():
        b = Branch(name='ZzDaySepRulesSave', code=None)
        db.session.add(b); db.session.flush(); bid = b.id
        s1 = GenSubject(branch_id=bid, name='ZzPickMe', school_level='sss')
        s2 = GenSubject(branch_id=bid, name='ZzLeaveMe', school_level='sss')
        db.session.add_all([s1, s2]); db.session.flush()
        s1_id, s2_id = s1.id, s2.id
        db.session.commit()

    c = _scoped_to_branch(_admin(app), bid)
    r = _post(c, '/generator/rules/save',
             periods_per_day='8', break_after_period='5', day_start='8:00',
             period_minutes='40', break_minutes='30', max_consecutive='3',
             day_separation_enabled='on', day_separation_day_a='0', day_separation_day_b='4',
             **{'day_separation_subjects[]': str(s1_id)})
    assert r.status_code in (302, 200)

    with app.app_context():
        cfg1 = GenSubjectConfig.query.filter_by(subject_id=s1_id, school_level='sss').first()
        cfg2 = GenSubjectConfig.query.filter_by(subject_id=s2_id, school_level='sss').first()
        assert cfg1 is not None and cfg1.day_separation_exempt is False
        assert cfg2 is not None and cfg2.day_separation_exempt is True


def test_subject_rules_page_checkbox_is_unchecked_by_default_and_unrelated_save_keeps_exempt(app):
    """Loading a never-configured subject's own rules page shows the
    day-separation checkbox unchecked (matching exempt-by-default); saving
    that page for an unrelated reason (e.g. changing periods/week) without
    touching the checkbox must NOT silently opt the subject in."""
    bid = None
    with app.app_context():
        b = Branch(name='ZzDaySepSubjPage', code=None)
        db.session.add(b); db.session.flush(); bid = b.id
        subj = GenSubject(branch_id=bid, name='ZzNeverTouched', school_level='sss')
        db.session.add(subj); db.session.flush()
        subj_id = subj.id
        db.session.commit()

    c = _scoped_to_branch(_admin(app), bid)
    body = c.get(f'/generator/subject/{subj_id}/rules').get_data(as_text=True)
    assert 'name="day_separation_included"' in body
    assert 'name="day_separation_included" checked' not in body

    # Save without checking it (e.g. just bumping periods/week).
    r = _post(c, f'/generator/subject/{subj_id}/rules/save', periods='5')
    assert r.status_code in (302, 200)
    with app.app_context():
        cfg = GenSubjectConfig.query.filter_by(subject_id=subj_id, school_level='sss').first()
        assert cfg is not None
        assert cfg.day_separation_exempt is True, (
            'an unrelated save left the checkbox unchecked -- the subject must stay exempt')

    # Now explicitly check it and save -- must flip to included.
    r2 = _post(c, f'/generator/subject/{subj_id}/rules/save', periods='5',
              day_separation_included='on')
    assert r2.status_code in (302, 200)
    with app.app_context():
        cfg = GenSubjectConfig.query.filter_by(subject_id=subj_id, school_level='sss').first()
        assert cfg.day_separation_exempt is False
