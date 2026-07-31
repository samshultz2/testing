"""Provision a tenant's own database (Stage 1 of multi-tenancy).

Given a registered (``pending``) tenant, this:
  1. creates the physical database  (Postgres ``CREATE DATABASE``; SQLite = a file),
  2. builds the full schema          (``db.metadata.create_all`` — every model),
  3. stamps Alembic at head          (so a later ``migrate-all-tenants`` works),
  4. seeds the essentials            (a default branch + the school's first
     central super-admin, who must change the temp password on first login),
  5. marks the tenant ``active``.

Rollback-safe: any failure marks the tenant ``failed`` with the error and
re-raises. Nothing here touches the running app's ``db.session`` — schema and
seed run against a dedicated engine, so provisioning is safe to run while the
app serves other tenants.
"""
from __future__ import annotations

import os
import re
import glob
import secrets
import string
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from config import BASE_DIR, Config
from models import db          # importing models registers every table on db.metadata
from utils import tenancy


# --- helpers ----------------------------------------------------------------
def _db_name(subdomain):
    """A safe physical database name derived from the subdomain."""
    return 'tenant_' + re.sub(r'[^a-z0-9]+', '_', subdomain.lower()).strip('_')


def tenant_database_url(subdomain):
    """Where a tenant's database lives.

    * ``TENANT_DATABASE_URL_TEMPLATE`` (e.g.
      ``postgresql+psycopg://user:pw@host/{name}``) — production Postgres.
    * otherwise a per-tenant SQLite file under ``TENANT_DB_DIR`` — dev/test.
    """
    name = _db_name(subdomain)
    tmpl = os.environ.get('TENANT_DATABASE_URL_TEMPLATE')
    if tmpl:
        return tmpl.format(name=name, slug=name)
    d = os.environ.get('TENANT_DB_DIR') or os.path.join(BASE_DIR, 'instance', 'tenants')
    os.makedirs(d, exist_ok=True)
    return 'sqlite:///' + os.path.join(d, f'{name}.db')


def _engine_opts(url):
    # Only real (pooled) backends take the pool sizing options.
    return dict(Config.SQLALCHEMY_ENGINE_OPTIONS) if url.startswith('postgresql') else {}


def _alembic_head():
    """The single head revision in db_migrations/versions (leaf of the graph)."""
    versions = os.path.join(BASE_DIR, 'db_migrations', 'versions')
    revs, downs = set(), set()
    for f in glob.glob(os.path.join(versions, '*.py')):
        with open(f) as fh:
            txt = fh.read()
        m = re.search(r"^revision = '([^']+)'", txt, re.M)
        if m:
            revs.add(m.group(1))
        for d in re.findall(r"^down_revision = '([^']+)'", txt, re.M):
            downs.add(d)
        dm = re.search(r"^down_revision = \(([^)]*)\)", txt, re.M)
        if dm:
            downs.update(re.findall(r"'([^']+)'", dm.group(1)))
    heads = [r for r in revs if r not in downs]
    if len(heads) != 1:
        raise RuntimeError(f'Expected exactly one Alembic head, found {sorted(heads)}')
    return heads[0]


def _gen_password():
    """A strong temp password that satisfies is_password_strong()."""
    from utils.security import is_password_strong
    alphabet = string.ascii_letters + string.digits + '!@#$%^&*?'
    for _ in range(100):
        pw = ''.join(secrets.choice(alphabet) for _ in range(16))
        if is_password_strong(pw)[0]:
            return pw
    raise RuntimeError('Could not generate a compliant password')   # practically unreachable


def _create_physical_db(url):
    """Create the empty database. SQLite needs nothing (the file is created on
    first connect); Postgres runs CREATE DATABASE via the maintenance database
    using a privileged provisioner connection."""
    if url.startswith('sqlite'):
        return
    parts = urlsplit(url)
    dbname = parts.path.lstrip('/')
    if not re.match(r'^[A-Za-z0-9_]+$', dbname):
        raise ValueError(f'Unsafe database name: {dbname!r}')
    # A dedicated provisioner URL (a role WITH createdb) is strongly preferred so
    # the app's own DB role never needs CREATE DATABASE. Fall back to the same
    # server's maintenance db.
    maint_url = os.environ.get('PROVISIONER_DATABASE_URL') or \
        urlunsplit(parts._replace(path='/postgres'))
    eng = create_engine(maint_url, isolation_level='AUTOCOMMIT', future=True)
    try:
        with eng.connect() as conn:
            exists = conn.execute(
                text('SELECT 1 FROM pg_database WHERE datname = :n'), {'n': dbname}).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    finally:
        eng.dispose()


def _seed(engine, tenant, admin_username, temp_password):
    """Seed a default branch, the school's first central super-admin, and the
    built-in permission-group templates."""
    from models import Branch, User
    from utils.permission_seed import seed_permission_groups
    with Session(engine, future=True) as s:
        if not s.query(Branch).filter_by(is_default=True).first():
            name = os.environ.get('POSYHUB_DEFAULT_BRANCH') or (tenant.name or 'Main')
            s.add(Branch(name=name, is_default=True, is_active=True))
        if not s.query(User).filter_by(role='super_admin').first():
            u = User(username=admin_username, full_name='Administrator',
                     email=tenant.admin_email, role='super_admin', scope='central',
                     is_active=True, must_change_password=True)
            u.set_password(temp_password)
            s.add(u)
        s.commit()
        # Default permission-group templates, so a brand-new school opens
        # /users/groups to ready-made access bundles.
        seed_permission_groups(s)


# --- public API -------------------------------------------------------------
def provision(subdomain, admin_username='admin', admin_password=None):
    """Create + initialise a tenant's database and mark it active.

    Returns ``(tenant, admin_username, temp_password)``. Idempotency: refuses to
    re-provision an already-active tenant.
    """
    t = tenancy.get_tenant(subdomain)
    if t is None:
        raise ValueError(f'No such tenant: {subdomain!r} (register it first).')
    if t.status == 'active':
        raise ValueError(f'Tenant {subdomain!r} is already active.')

    url = tenant_database_url(subdomain)
    tenancy.set_status(subdomain, 'provisioning', database_url=url)
    temp_password = admin_password or _gen_password()
    try:
        _create_physical_db(url)
        engine = create_engine(url, **_engine_opts(url))
        try:
            db.metadata.create_all(bind=engine)
            head = _alembic_head()
            with engine.begin() as conn:
                conn.execute(text(
                    'CREATE TABLE IF NOT EXISTS alembic_version '
                    '(version_num VARCHAR(32) NOT NULL)'))
                conn.execute(text('DELETE FROM alembic_version'))
                conn.execute(text('INSERT INTO alembic_version (version_num) VALUES (:v)'),
                             {'v': head})
            _seed(engine, t, admin_username, temp_password)
        finally:
            engine.dispose()
        tenancy.set_status(subdomain, 'active', activated=True)
        # New schools start their free trial now (owner-adoption doesn't come
        # through here, so it stays exempt).
        from utils import billing
        billing.start_trial(subdomain)
        return tenancy.get_tenant(subdomain), admin_username, temp_password
    except Exception as e:
        tenancy.set_status(subdomain, 'failed', error=str(e))
        raise


def drop_tenant(subdomain, forget=False):
    """Tear down a tenant's database (rollback / test cleanup). With
    ``forget=True`` the registry row is removed too; otherwise it is reset to
    ``pending`` so it can be re-provisioned."""
    t = tenancy.get_tenant(subdomain)
    if t is None:
        return
    url = t.database_url
    if url and url.startswith('sqlite'):
        path = url.replace('sqlite:///', '')
        if os.path.exists(path):
            os.remove(path)
    elif url and url.startswith('postgresql'):
        parts = urlsplit(url)
        dbname = parts.path.lstrip('/')
        maint_url = os.environ.get('PROVISIONER_DATABASE_URL') or \
            urlunsplit(parts._replace(path='/postgres'))
        eng = create_engine(maint_url, isolation_level='AUTOCOMMIT', future=True)
        try:
            with eng.connect() as conn:
                conn.execute(text(
                    'SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
                    'WHERE datname = :n AND pid <> pg_backend_pid()'), {'n': dbname})
                conn.execute(text(f'DROP DATABASE IF EXISTS "{dbname}"'))
        finally:
            eng.dispose()
    if forget:
        tenancy.delete_tenant(subdomain)
    else:
        tenancy.set_status(subdomain, 'pending', database_url=None)
