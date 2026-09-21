"""Add Promotion Rule: the "Required Subjects" field is a set of checkbox
chips client-rendered from d.subjects (React SPA — verified visually via
Playwright, not asserted here since the server response is just the shell),
replacing the old native <select multiple> for a friendlier, touch-usable
picker. The chips still post as required_subjects[] exactly like the old
<option>s did, so the rule-save flow (JSON-encoded subject id list) below
is what actually matters and is unaffected by the UI change."""
import json
import uuid

from config import Config
from tests.conftest import login_token, auth_csrf


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _fixture(app):
    from models import db, Subject, SchoolClass
    with app.app_context():
        n = uuid.uuid4().hex[:6]
        s1 = Subject(name=f'Chip Subject A {n}', is_active=True)
        s2 = Subject(name=f'Chip Subject B {n}', is_active=True)
        c1 = SchoolClass(name=f'CHP1{n}', level=90)
        c2 = SchoolClass(name=f'CHP2{n}', level=91)
        db.session.add_all([s1, s2, c1, c2]); db.session.commit()
        return s1.id, s2.id, c1.id, c2.id


def test_submitting_chip_selected_subjects_saves_the_rule(app):
    from models import db, PromotionRule
    s1, s2, c1, c2 = _fixture(app)
    c = _admin(app)
    r = c.post('/promotion/rules/add', data={
        '_csrf_token': auth_csrf(c), 'from_class_id': c1, 'to_class_id': c2,
        'stream_name': 'Science', 'min_average': '55', 'priority': '1',
        'required_subjects[]': [str(s1), str(s2)],
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        rule = PromotionRule.query.filter_by(from_class_id=c1, to_class_id=c2).first()
        assert rule is not None
        assert sorted(json.loads(rule.required_subjects)) == sorted([s1, s2])


def test_leaving_all_chips_unchecked_means_no_required_subjects(app):
    from models import db, PromotionRule
    _, _, c1, c2 = _fixture(app)
    c = _admin(app)
    r = c.post('/promotion/rules/add', data={
        '_csrf_token': auth_csrf(c), 'from_class_id': c1, 'to_class_id': c2,
        'min_average': '50', 'priority': '0',
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        rule = PromotionRule.query.filter_by(from_class_id=c1, to_class_id=c2).first()
        assert rule is not None and rule.required_subjects is None
