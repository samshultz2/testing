"""num_arms on GenClassConfig was a separately-editable counter that could
drift out of sync with arm_names (the field generation actually reads via
arm_list) -- e.g. 5 names typed into "Arm Names" while "Number of Arms" was
never bumped past 4. Every page showing an arm count read the stale
num_arms field directly, so it could say "4 arm(s)" next to a 5-name list.

Fixed by: (1) GenClassConfig.arm_count, which derives the count from
arm_names and is what every display now reads; (2) the add/update routes
now derive num_arms from the parsed arm_names on save too, so it can't
drift going forward; (3) the now-redundant "Number of Arms" input was
dropped from the add/edit forms.

Also covers the "Time Limit (seconds)" label on the Generate page, whose
dropdown options are mostly labelled in minutes."""
from config import Config
from models import db, Branch, GenClassConfig, GenTimetableRule
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
    with c.session_transaction() as s:
        s['view_branch_id'] = branch_id
    return c


def _seed_branch(app, tag):
    with app.app_context():
        b = Branch(name=f'ZzArmCountBranch{tag}', code=None)
        db.session.add(b); db.session.flush()
        bid = b.id
        db.session.add(GenTimetableRule(branch_id=bid, rule_type='periods_per_day', value='6',
                                        school_level='sss', is_active=True))
        db.session.commit()
        return bid


def test_arm_count_property_derives_from_arm_names_not_stale_num_arms(app):
    with app.app_context():
        b = Branch(name='ZzArmCountModel', code=None)
        db.session.add(b); db.session.flush()
        # The exact drifted shape from the bug report: num_arms=4 but 5 names.
        cc = GenClassConfig(branch_id=b.id, class_name='ZzDrift', school_level='sss',
                            num_arms=4, arm_names='Rose, Lily, Iris, Daisy, Violet')
        db.session.add(cc); db.session.commit()
        assert cc.arm_count == 5
        assert len(cc.arm_list) == 5


def test_arm_count_falls_back_to_num_arms_when_no_names_set(app):
    with app.app_context():
        b = Branch(name='ZzArmCountFallback', code=None)
        db.session.add(b); db.session.flush()
        cc = GenClassConfig(branch_id=b.id, class_name='ZzNoNames', school_level='sss',
                            num_arms=3, arm_names=None)
        db.session.add(cc); db.session.commit()
        assert cc.arm_count == 3


def test_add_class_config_derives_num_arms_from_arm_names(app):
    bid = _seed_branch(app, 'Add')
    c = _scoped_to_branch(_admin(app), bid)
    # Deliberately submit a mismatched num_arms -- the server must ignore it
    # and count the actual names instead.
    r = _post(c, '/generator/classes/add', class_name='ZzAddDrift',
             num_arms='1', arm_names='Rose, Lily, Iris, Daisy, Violet')
    assert r.status_code in (302, 200)
    with app.app_context():
        cc = GenClassConfig.query.filter_by(class_name='ZzAddDrift', branch_id=bid).first()
        assert cc is not None
        assert cc.num_arms == 5
        assert cc.arm_count == 5


def test_update_class_config_derives_num_arms_from_arm_names(app):
    bid = _seed_branch(app, 'Upd')
    with app.app_context():
        cc = GenClassConfig(branch_id=bid, class_name='ZzUpdDrift', school_level='sss',
                            num_arms=1, arm_names='Rose')
        db.session.add(cc); db.session.commit()
        cc_id = cc.id

    c = _scoped_to_branch(_admin(app), bid)
    r = _post(c, f'/generator/classes/{cc_id}/update', class_name='ZzUpdDrift',
             num_arms='1', arm_names='Rose, Lily, Iris')
    assert r.status_code in (302, 200)
    with app.app_context():
        cc = db.session.get(GenClassConfig, cc_id)
        assert cc.num_arms == 3


def test_generate_page_shows_real_arm_count_not_stale_field(app):
    bid = _seed_branch(app, 'Gen')
    with app.app_context():
        cc = GenClassConfig(branch_id=bid, class_name='ZzGenDrift', school_level='sss',
                            num_arms=4, arm_names='Rose, Lily, Iris, Daisy, Violet')
        db.session.add(cc); db.session.commit()

    c = _scoped_to_branch(_admin(app), bid)
    body = c.get('/generator/generate').get_data(as_text=True)
    assert '5 arm(s): Rose, Lily, Iris, Daisy, Violet' in body
    assert '4 arm(s)' not in body


def test_classes_config_and_class_subjects_pages_show_real_arm_count(app):
    bid = _seed_branch(app, 'List')
    with app.app_context():
        cc = GenClassConfig(branch_id=bid, class_name='ZzListDrift', school_level='sss',
                            num_arms=4, arm_names='Rose, Lily, Iris, Daisy, Violet')
        db.session.add(cc); db.session.commit()

    c = _scoped_to_branch(_admin(app), bid)
    classes_body = c.get('/generator/classes').get_data(as_text=True)
    assert '5 arm' in classes_body and '4 arm' not in classes_body

    subjects_body = c.get('/generator/class-subjects').get_data(as_text=True)
    assert '5 arm(s)' in subjects_body and '4 arm(s)' not in subjects_body


def test_add_and_edit_class_forms_no_longer_have_a_separate_arm_count_input(app):
    """The Number of Arms input is gone -- Arm Names is now the only input,
    since editing num_arms alone no longer has any effect on save."""
    c = _admin(app)
    add_body = c.get('/generator/classes/add').get_data(as_text=True)
    assert 'name="num_arms"' not in add_body
    assert 'name="arm_names"' in add_body

    bid = _seed_branch(app, 'EditForm')
    with app.app_context():
        cc = GenClassConfig(branch_id=bid, class_name='ZzEditFormClass', school_level='sss',
                            num_arms=2, arm_names='Rose, Lily')
        db.session.add(cc); db.session.commit()
        cc_id = cc.id
    c2 = _scoped_to_branch(_admin(app), bid)
    edit_body = c2.get(f'/generator/classes/{cc_id}').get_data(as_text=True)
    assert 'name="num_arms"' not in edit_body
    assert 'name="arm_names"' in edit_body


def test_generate_page_time_limit_label_matches_its_options():
    """The dropdown's own options are labelled in minutes (except the first,
    in seconds) -- the field label must not claim everything is seconds.
    (This block only renders once setup has no outstanding issues, so check
    the template source directly rather than requiring a full, valid
    teachers/subjects/assignments setup just to see it.)"""
    import os
    path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'generator', 'generate.html')
    with open(path, encoding='utf-8') as f:
        html = f.read()
    assert 'Time Limit (seconds)' not in html
    assert '<label class="form-label">Time Limit</label>' in html
    assert '5 minutes (recommended)' in html
