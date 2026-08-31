"""Audit-trail regression tests for the sensitive-data audit (Tier A).

Authentication events and bulk-data exports now write an AuditLog row, so
"who logged in / who took the data out" is answerable after the fact.
"""
from config import Config
from models import db, AuditLog, User, Branch
from tests.conftest import login_token


def _count(action):
    return AuditLog.query.filter_by(action=action).count()


def test_successful_login_is_audited(app):
    with app.app_context():
        before = _count('auth.login')
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    with app.app_context():
        assert _count('auth.login') == before + 1
        row = AuditLog.query.filter_by(action='auth.login').order_by(AuditLog.id.desc()).first()
        assert row.ip_address                       # IP captured
        assert row.detail                            # who (username / 'legacy-admin')


def test_failed_login_is_audited(app):
    with app.app_context():
        before = _count('auth.login_failed')
    c = app.test_client()
    c.post('/login', data={'username': 'ghost_user', 'password': 'WrongPass123!',
                           '_csrf_token': login_token(c)})
    with app.app_context():
        assert _count('auth.login_failed') == before + 1
        row = AuditLog.query.filter_by(action='auth.login_failed').order_by(AuditLog.id.desc()).first()
        assert 'ghost_user' in (row.detail or '')    # attempted username recorded


def test_logout_is_audited(app):
    with app.app_context():
        before = _count('auth.logout')
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    c.get('/logout')
    with app.app_context():
        assert _count('auth.logout') == before + 1


def test_student_export_is_audited(auth_client, app):
    with app.app_context():
        before = _count('data.export_students')
    r = auth_client.get('/reports/export/students')
    assert r.status_code == 200
    with app.app_context():
        assert _count('data.export_students') == before + 1


def test_json_export_is_audited(auth_client, app):
    with app.app_context():
        before = _count('data.export_json')
    # The export is logged the moment it's authorized and started; whether the
    # body fully builds in a sparse test DB (200) or bails to a redirect (302),
    # the audit row must be written (a 302 auth-bounce would NOT log, and would
    # leave the count unchanged — so this still catches a broken gate).
    auth_client.get('/settings/backup/export-json')
    with app.app_context():
        assert _count('data.export_json') == before + 1


def test_staff_export_is_audited(auth_client, app):
    with app.app_context():
        before = _count('data.export_staff')
    r = auth_client.get('/hr/staff/export')
    assert r.status_code == 200
    with app.app_context():
        assert _count('data.export_staff') == before + 1
