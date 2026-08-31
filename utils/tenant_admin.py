"""Per-tenant operations helpers (Stage 2): run schema migrations, backups and
other maintenance against every school's database.

Each helper binds a throwaway single-database Flask app to one tenant's URL
(MULTI_TENANT off, so `db.session` binds straight to that database) — this reuses
the app's existing migration/backup machinery per school.
"""
from __future__ import annotations

from config import Config
from utils import tenancy


def active_tenants():
    """Active schools that have a database to operate on."""
    return [t for t in tenancy.list_tenants()
            if t.status == 'active' and t.database_url]


def tenant_app(database_url):
    """A minimal Flask app bound to a single tenant database (no routing)."""
    from flask import Flask
    from models import db
    app = Flask('tenant-ops')
    app.config.update(
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS=(dict(Config.SQLALCHEMY_ENGINE_OPTIONS)
                                   if database_url.startswith('postgresql') else {}),
        MULTI_TENANT=False,
        UPLOAD_FOLDER=Config.UPLOAD_FOLDER,
        BACKUP_RETENTION=getattr(Config, 'BACKUP_RETENTION', 30),
        BACKUP_ENCRYPTION_KEY=getattr(Config, 'BACKUP_ENCRYPTION_KEY', ''),
    )
    db.init_app(app)
    return app


def migrate_tenant(database_url):
    """Run Alembic migrations up to head against one tenant database."""
    from models import db
    from flask_migrate import Migrate, upgrade
    app = tenant_app(database_url)
    Migrate(app, db, directory='db_migrations')
    with app.app_context():
        upgrade()


def backup_tenant(database_url):
    """Create a daily backup for one tenant database. Returns the path or None."""
    from utils.backup import auto_backup
    app = tenant_app(database_url)
    with app.app_context():
        return auto_backup(app)
