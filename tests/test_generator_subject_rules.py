"""Unified per-subject timetable rules editor: one screen writes to the same
GenSubjectConfig / GenClassSubjectConfig / GenTimetableRule the generator reads."""
import re


_SEQ = [0]


def _csrf(c):
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get('/students').get_data(as_text=True)).group(1)


def _fixture(app):
    # unique names per call — the test DB is shared and gen_subjects has a
    # (name, school_level) unique constraint
    from models import db, GenSubject, GenClassConfig
    with app.app_context():
        _SEQ[0] += 1
        n = _SEQ[0]
        s = GenSubject(name=f'Mathematics {n}', short_name='MTH', school_level='sss', is_active=True)
        cc = GenClassConfig(class_name=f'SSS1-{n}', school_level='sss', num_arms=2,
                            arm_names='Gold,Silver', is_active=True)
        db.session.add_all([s, cc]); db.session.commit()
        return s.id, cc.id


def test_rules_page_renders(auth_client, app):
    sid, cid = _fixture(app)
    r = auth_client.get(f'/generator/subject/{sid}/rules')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Mathematics' in body
    assert 'Not first period' in body and 'Back-to-back' in body
    assert 'SSS1' in body and 'Gold, Silver' in body        # class + its arms


def test_save_writes_all_three_models(auth_client, app):
    from models import db, GenSubjectConfig, GenClassSubjectConfig, GenTimetableRule
    sid, cid = _fixture(app)
    tok = _csrf(auth_client)
    auth_client.post(f'/generator/subject/{sid}/rules/save', data={
        '_csrf_token': tok,
        'periods': '5', 'double': 'on', 'double_count': '1',
        'not_first': 'on', 'preferred': 'morning',
        'max_consecutive': '1',
        'class_id[]': str(cid),
        # this class overrides the default (default checkbox NOT sent)
        f'enabled_{cid}': 'on', f'periods_{cid}': '3',
    }, follow_redirects=True)
    with app.app_context():
        cfg = GenSubjectConfig.query.filter_by(subject_id=sid, school_level='sss').first()
        assert cfg and cfg.periods_per_week == 5 and cfg.not_first_period is True
        assert cfg.needs_double_period is True and cfg.double_period_count == 1
        assert cfg.preferred_time == 'morning'
        ov = GenClassSubjectConfig.query.filter_by(class_config_id=cid, subject_id=sid).first()
        assert ov and ov.periods_per_week == 3 and ov.is_enabled is True
        rule = GenTimetableRule.query.filter_by(rule_type='max_consecutive', school_level='sss').first()
        assert rule and rule.value == '1'


def test_use_default_removes_override(auth_client, app):
    from models import db, GenClassSubjectConfig
    sid, cid = _fixture(app)
    tok = _csrf(auth_client)
    # first, create an override
    auth_client.post(f'/generator/subject/{sid}/rules/save', data={
        '_csrf_token': tok, 'periods': '4', 'class_id[]': str(cid),
        f'enabled_{cid}': 'on', f'periods_{cid}': '2'}, follow_redirects=True)
    with app.app_context():
        assert GenClassSubjectConfig.query.filter_by(class_config_id=cid, subject_id=sid).count() == 1
    # now tick "use default" for that class -> override removed (inherits default)
    auth_client.post(f'/generator/subject/{sid}/rules/save', data={
        '_csrf_token': tok, 'periods': '4', 'class_id[]': str(cid),
        f'default_{cid}': 'on'}, follow_redirects=True)
    with app.app_context():
        assert GenClassSubjectConfig.query.filter_by(class_config_id=cid, subject_id=sid).count() == 0
