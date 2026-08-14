"""Soft plan-cap enforcement: caps block ONLY the create action and only when a
tiered tenant is over its limit. Everything else (and every fail-open path) must
never block — that's the whole point of "non-blocking, especially payments"."""
import utils.platform_stats as ps
from utils import entitlements as ent


class _FakeTenant:
    tier = 'basic'                 # basic → students cap 500 (see DEFAULTS)
    entitlements_json = None
    subdomain = 'demo'
    database_url = 'sqlite://'


def test_cap_check_over_when_at_limit(app, monkeypatch):
    monkeypatch.setattr(ent, '_current_capped_tenant', lambda: _FakeTenant())
    monkeypatch.setattr(ps, 'tenant_usage', lambda url, **k: {'students': 500})
    with app.test_request_context('/'):
        info = ent.creation_cap_check('students')
    assert info and info['over'] is True and info['cap'] == 500


def test_cap_check_under_limit_allows(app, monkeypatch):
    monkeypatch.setattr(ent, '_current_capped_tenant', lambda: _FakeTenant())
    monkeypatch.setattr(ps, 'tenant_usage', lambda url, **k: {'students': 12})
    with app.test_request_context('/'):
        info = ent.creation_cap_check('students')
    assert info and info['over'] is False


def test_cap_check_fails_open_when_no_tenant(app, monkeypatch):
    # Single-school / grandfathered / owner → None, so nothing is ever capped.
    monkeypatch.setattr(ent, '_current_capped_tenant', lambda: None)
    with app.test_request_context('/'):
        assert ent.creation_cap_check('students') is None


def test_cap_check_unknown_usage_fails_open(app, monkeypatch):
    # If we can't read usage, allow the create rather than block it.
    monkeypatch.setattr(ent, '_current_capped_tenant', lambda: _FakeTenant())
    monkeypatch.setattr(ps, 'tenant_usage', lambda url, **k: {'students': None})
    with app.test_request_context('/'):
        assert ent.creation_cap_check('students') is None


def test_cap_block_redirects_only_when_over(app, monkeypatch):
    monkeypatch.setattr(ent, 'creation_cap_check',
                        lambda k: {'over': True, 'cap': 500, 'used': 500, 'tier_label': 'Basic'})
    with app.test_request_context('/'):
        resp = ent.cap_block('students', 'main.students_list', 'students')
    assert resp is not None and resp.status_code in (301, 302)


def test_cap_block_allows_when_not_over(app, monkeypatch):
    monkeypatch.setattr(ent, 'creation_cap_check', lambda k: None)
    with app.test_request_context('/'):
        assert ent.cap_block('students', 'main.students_list', 'students') is None
