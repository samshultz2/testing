#!/usr/bin/env python3
"""One-shot owner-school setup for a multi-tenant deployment.

Brings the control plane up, gets the owner school's database to the current
schema, seeds a first admin if the database is empty, and registers the school
as the free-forever OWNER served at the apex. Safe to run more than once.

Handles three starting points automatically:
  * a MIGRATED database (already has tables + alembic_version) -> upgrade only
  * a migrated database with NO alembic_version (created by create_all before
    Alembic) -> stamp head, so `upgrade` won't try to re-create existing tables
  * an EMPTY database -> upgrade from base creates the whole schema, then seed

    python scripts/init_owner.py \
        --subdomain myschool --name "My School" \
        --email admin@myschool.com --db-url "$DATABASE_URL"
"""
import argparse
import os
import secrets
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _bring_schema_to_head(db_url):
    """Get the owner DB to the current schema, whatever state it starts in.

    * already-tracked (has alembic_version): apply pending migrations only.
    * untracked (existing tables, or empty): build/ensure the schema with
      create_all and stamp the current head — the same Postgres-safe path
      provision() uses, so we never replay old (SQLite-only) migrations.
    """
    from sqlalchemy import create_engine, inspect, text
    from models import db                       # importing registers every table
    from utils import provisioning

    eng = create_engine(db_url)
    try:
        insp = inspect(eng)
        has_users = insp.has_table('users')
        tracked = False
        if insp.has_table('alembic_version'):
            with eng.connect() as c:
                tracked = (c.execute(text('SELECT count(*) FROM alembic_version')).scalar() or 0) > 0
    finally:
        eng.dispose()

    if tracked:
        from flask_migrate import Migrate, upgrade
        from utils.tenant_admin import tenant_app
        app = tenant_app(db_url)
        Migrate(app, db, directory='db_migrations')
        with app.app_context():
            upgrade()
        print('  · tracked database — pending migrations applied')
        return has_users

    head = provisioning._alembic_head()
    eng = create_engine(db_url)
    try:
        db.metadata.create_all(bind=eng)         # only creates MISSING tables
        with eng.begin() as conn:
            conn.execute(text('CREATE TABLE IF NOT EXISTS alembic_version '
                              '(version_num VARCHAR(32) NOT NULL)'))
            conn.execute(text('DELETE FROM alembic_version'))
            conn.execute(text('INSERT INTO alembic_version (version_num) VALUES (:v)'), {'v': head})
    finally:
        eng.dispose()
    print(f'  · schema ensured + stamped to head ({head})')
    return has_users


def _seed_admin(db_url, name, email, username, password):
    """Seed a default branch + first super-admin, only if the DB has no users."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from models import User
    from utils import provisioning
    eng = create_engine(db_url)
    try:
        with Session(eng, future=True) as s:
            if s.query(User).first():
                return None                      # already populated -> don't seed
        tenant = types.SimpleNamespace(name=name, admin_email=email)
        provisioning._seed(eng, tenant, username, password)
        return password
    finally:
        eng.dispose()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--subdomain', required=True, help='owner subdomain id (served at the apex)')
    ap.add_argument('--name', required=True, help='school name')
    ap.add_argument('--email', default=None, help='owner admin email')
    ap.add_argument('--db-url', required=True, help='owner school database URL')
    ap.add_argument('--admin-username', default='admin')
    ap.add_argument('--admin-password', default=None, help='seed password (empty DB only)')
    args = ap.parse_args(argv)

    from utils import tenancy, onboarding

    print('› control plane')
    tenancy.init_control_plane()

    print('› owner database schema')
    _bring_schema_to_head(args.db_url)

    print('› seed admin (only if empty)')
    pw = _seed_admin(args.db_url, args.name, args.email,
                     args.admin_username,
                     args.admin_password or secrets.token_urlsafe(12))

    print('› register owner school (free forever)')
    onboarding.adopt_current_school(args.subdomain, args.name, args.db_url, args.email)

    t = tenancy.get_tenant(args.subdomain)
    print(f'\n✓ owner school ready: {t.name} [{t.subdomain}] plan={t.plan}')
    if pw is not None:
        print(f'  first-login admin: username={args.admin_username}  password={pw}')
        print('  (you will be asked to change it on first login)')
    else:
        print('  existing admin accounts kept as-is (nothing seeded)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
