"""The audit trail is evidence: rows are append-only (no delete, no update via
the ORM) and every entry carries the actor's identity (id, name, role, branch).
"""
import pytest
from config import Config
from models import db, AuditLog
from models.models.settings import AuditLogImmutableError
from tests.conftest import login_token


def _seed(app, action='test.seed', **kw):
    with app.app_context():
        row = AuditLog(action=action, user='Seed', **kw)
        db.session.add(row); db.session.commit()
        return row.id


def test_audit_row_cannot_be_deleted(app):
    rid = _seed(app)
    with app.app_context():
        row = db.session.get(AuditLog, rid)
        with pytest.raises(AuditLogImmutableError):
            db.session.delete(row)
            db.session.commit()
        db.session.rollback()
        assert db.session.get(AuditLog, rid) is not None      # survived


def test_audit_row_cannot_be_updated(app):
    rid = _seed(app)
    with app.app_context():
        row = db.session.get(AuditLog, rid)
        with pytest.raises(AuditLogImmutableError):
            row.detail = 'tampered'
            db.session.commit()
        db.session.rollback()
        assert (db.session.get(AuditLog, rid).detail or '') != 'tampered'


def test_bulk_delete_query_is_also_blocked(app):
    """A .delete() on the query also fires the ORM guard (fetch strategy)."""
    _seed(app, action='test.bulkdel')
    with app.app_context():
        with pytest.raises(AuditLogImmutableError):
            AuditLog.query.filter_by(action='test.bulkdel').delete()
            db.session.commit()
        db.session.rollback()
        assert AuditLog.query.filter_by(action='test.bulkdel').count() >= 1


def test_actor_identity_captured(app):
    """A real (non-legacy) user's action records id + name + role + branch."""
    from models import User, Branch
    with app.app_context():
        bid = Branch.get_default().id
        u = User.query.filter_by(username='audit_actor').first()
        if not u:
            u = User(username='audit_actor', full_name='Audit Actor', role='teacher',
                     scope='branch', branch_id=bid)
            u.set_password('secret123'); db.session.add(u); db.session.commit()
        uid = u.id

    c = app.test_client()
    c.post('/login', data={'username': 'audit_actor', 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    # A login already writes an auth.login row with full actor context.
    with app.app_context():
        row = (AuditLog.query.filter_by(action='auth.login', user_id=uid)
               .order_by(AuditLog.id.desc()).first())
        assert row is not None
        assert row.user == 'Audit Actor'          # name
        assert row.role == 'teacher'              # position
        assert row.user_id == uid                 # stable id
        assert row.branch_id is not None          # branch
