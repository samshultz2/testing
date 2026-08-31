"""Configurable behavioural traits seed, render, and editing."""
import re
from config import Config
from models import db, BehaviouralTrait
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _pt(c):
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get('/').get_data(as_text=True)).group(1)


def test_defaults_seeded_and_used(app):
    with app.app_context():
        assert BehaviouralTrait.query.filter_by(is_active=True).count() >= 12
    from utils.report_card import active_traits
    with app.app_context():
        keys = [k for k, _ in active_traits()]
        assert 'punctuality' in keys and 'initiative' in keys


def test_add_and_deactivate_trait(app):
    c = _admin(app)
    assert c.get('/settings/traits').status_code == 200
    # keep punctuality active, add a new trait, drop the rest from the form
    c.post('/settings/traits/save', data={
        '_csrf_token': _pt(c),
        'key[]': ['punctuality', ''],
        'label[]': ['Punctuality', 'Leadership'],
        'active[]': ['0', '1'],
    }, follow_redirects=True)
    with app.app_context():
        active = {t.key for t in BehaviouralTrait.query.filter_by(is_active=True).all()}
        assert 'punctuality' in active
        assert any(t.label == 'Leadership' for t in BehaviouralTrait.query.all())
        # a dropped default is deactivated, not deleted (rating keys survive)
        hon = BehaviouralTrait.query.filter_by(key='honesty').first()
        assert hon is not None and hon.is_active is False
