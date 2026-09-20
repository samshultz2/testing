"""Teacher Assignments page: the Arm(s) picker is a set of checkbox chips
(populated by JS from /generator/api/class/<id>/arms), not the old native
<select multiple> — chips are far friendlier on both desktop and mobile than
ctrl/cmd-click. The chips still post as arm_names[] exactly like the old
<option>s did, so the add-assignment flow (one assignment per selected arm)
is unaffected."""
import re

from config import Config
from tests.conftest import login_token


_SEQ = [0]


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _csrf(c):
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', c.get('/students').get_data(as_text=True))
    return m.group(1)


def _fixture(app):
    # Unique names per call — the test DB is shared across the whole suite.
    # branch_id must match gen_bid()'s default branch, or the assignments
    # page (branch-scoped) won't show this class/teacher/subject at all.
    from models import db, GenSubject, GenClassConfig, GenTeacher, Branch
    with app.app_context():
        _SEQ[0] += 1
        n = _SEQ[0]
        bid = Branch.get_default().id
        t = GenTeacher(name=f'Chip Teacher {n}', school_level='sss', is_active=True, branch_id=bid)
        s = GenSubject(name=f'Chip Subject {n}', short_name='CHP', school_level='sss', is_active=True, branch_id=bid)
        cc = GenClassConfig(class_name=f'SSS1-CH{n}', school_level='sss', num_arms=3,
                            arm_names='Gold,Silver,Bronze', is_active=True, branch_id=bid)
        db.session.add_all([t, s, cc]); db.session.commit()
        return t.id, s.id, cc.id


def test_assignments_page_uses_chip_checkboxes_not_native_multiselect(app):
    c = _admin(app)
    html = c.get('/generator/assignments').get_data(as_text=True)
    assert 'id="armChips"' in html
    # The checkboxes are built client-side (one per arm from the class-arms
    # API): the server-rendered page carries the JS that builds them, not the
    # checkboxes themselves — the old native multiselect is gone.
    assert "label.className = 'arm-chip'" in html
    assert "input.name = 'arm_names[]'" in html
    assert '<select name="arm_names[]"' not in html
    assert 'id="armSelect"' not in html
    assert '<select' not in html.split('id="armChips"')[1].split('<script')[0]


def test_class_arms_api_still_feeds_the_chip_builder(app):
    _, _, cid = _fixture(app)
    c = _admin(app)
    r = c.get(f'/generator/api/class/{cid}/arms')
    assert r.status_code == 200
    assert r.get_json() == ['Gold', 'Silver', 'Bronze']


def test_submitting_two_arm_checkboxes_creates_one_assignment_each(app):
    tid, sid, cid = _fixture(app)
    c = _admin(app)
    tok = _csrf(c)
    r = c.post('/generator/assignments/add', data={
        '_csrf_token': tok, 'teacher_id': tid, 'subject_id': sid, 'class_config_id': cid,
        'arm_names[]': ['Gold', 'Bronze'],
    }, follow_redirects=True)
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert '2 assignment(s) added!' in body
    assert 'Gold' in body and 'Bronze' in body and 'Silver' not in body


def test_leaving_all_chips_unchecked_means_all_arms(app):
    tid, sid, cid = _fixture(app)
    c = _admin(app)
    tok = _csrf(c)
    r = c.post('/generator/assignments/add', data={
        '_csrf_token': tok, 'teacher_id': tid, 'subject_id': sid, 'class_config_id': cid,
    }, follow_redirects=True)
    assert r.status_code == 200
    assert 'All Arms' in r.get_data(as_text=True)
