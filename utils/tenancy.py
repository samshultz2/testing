"""Multi-tenancy control plane (Stage 1) — the registry of schools (tenants).

Deliberately DECOUPLED from the app's request path and its ``db``:

* The registry lives in a SEPARATE control-plane database (it is the router, so
  it must never be tenant-routed) on its own engine + declarative base. It is
  never part of ``db.metadata``, so a ``tenants`` table is never created inside
  a tenant's own database.
* Nothing here runs during a normal request. The single-school deployment is
  completely unaffected until tenant routing (Stage 0) is wired in.

Control-plane location: ``CONTROL_PLANE_DATABASE_URL`` (defaults to a local
SQLite file under ``instance/`` for dev). In production this is a small Postgres
database.
"""
from __future__ import annotations

import os
import re
import datetime as _dt

from sqlalchemy import (create_engine, Column, Integer, String, DateTime, Text)
from sqlalchemy.orm import declarative_base, sessionmaker

from config import BASE_DIR

_ControlBase = declarative_base()

# Subdomain label rules (RFC 1035-ish): 1–63 chars, lowercase alnum + hyphen,
# not starting/ending with a hyphen.
VALID_SUBDOMAIN = re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$')

STATUSES = ('pending', 'provisioning', 'active', 'failed', 'suspended')


class Tenant(_ControlBase):
    __tablename__ = 'tenants'

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    subdomain = Column(String(63), nullable=False, unique=True)
    database_url = Column(String(500))            # set at provision time
    admin_email = Column(String(200))
    status = Column(String(20), nullable=False, default='pending')
    error = Column(Text)                          # last provisioning error, if any
    verification_token = Column(String(64))       # emailed at registration
    verified_at = Column(DateTime)
    # Billing. plan: 'owner' (free forever, exempt) or 'standard' (trial -> paid).
    plan = Column(String(20), nullable=False, default='standard')
    trial_ends_at = Column(DateTime)
    paid_until = Column(DateTime)
    created_at = Column(DateTime, default=_dt.datetime.utcnow)
    activated_at = Column(DateTime)

    def __repr__(self):
        return f'<Tenant {self.subdomain} {self.status}>'


class SiteContent(_ControlBase):
    """Editable content for platform-owned pages (e.g. the marketing homepage).

    Platform-level, not per-school, so it lives in the control-plane DB. Stored
    as a single JSON document per key so the marketing/sales team can edit copy
    from the platform dashboard without a code change or redeploy."""
    __tablename__ = 'site_content'

    id = Column(Integer, primary_key=True)
    key = Column(String(64), nullable=False, unique=True)
    data = Column(Text)                            # JSON document
    updated_at = Column(DateTime, default=_dt.datetime.utcnow,
                        onupdate=_dt.datetime.utcnow)


# --- control-plane engine (lazy, cached) ------------------------------------
_engine = None
_Session = None


def control_plane_url():
    return os.environ.get('CONTROL_PLANE_DATABASE_URL') or \
        'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'control_plane.db')


def _engine_and_session():
    global _engine, _Session
    if _engine is None:
        url = control_plane_url()
        if url.startswith('sqlite'):
            path = url.replace('sqlite:///', '')
            os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        _engine = create_engine(url, future=True)
        # expire_on_commit=False so returned rows stay readable after the session
        # closes (callers get a detached snapshot).
        _Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine, _Session


def _reset_engine():
    """Drop the cached engine/session (used by tests that repoint the URL)."""
    global _engine, _Session
    if _engine is not None:
        _engine.dispose()
    _engine = _Session = None


def init_control_plane():
    """Create the ``tenants`` table if missing (idempotent)."""
    engine, _ = _engine_and_session()
    _ControlBase.metadata.create_all(engine)


def _session():
    _engine_and_session()
    return _Session()


def _detach(t):
    """Return a session-independent snapshot the caller can read freely."""
    if t is None:
        return None
    return t


# --- registry operations ----------------------------------------------------
def register_tenant(name, subdomain, admin_email=None):
    """Record a new school as ``pending`` (no database created yet)."""
    subdomain = (subdomain or '').strip().lower()
    if not VALID_SUBDOMAIN.match(subdomain):
        raise ValueError(
            f'Invalid subdomain {subdomain!r}: use 1–63 lowercase letters, digits '
            'or hyphens (not starting/ending with a hyphen).')
    if not (name or '').strip():
        raise ValueError('School name is required.')
    init_control_plane()
    with _session() as s:
        if s.query(Tenant).filter_by(subdomain=subdomain).first():
            raise ValueError(f'A school with subdomain "{subdomain}" already exists.')
        t = Tenant(name=name.strip(), subdomain=subdomain,
                   admin_email=(admin_email or None), status='pending')
        s.add(t)
        s.commit()
        s.expunge(t)
        return t


def get_tenant(subdomain):
    init_control_plane()
    with _session() as s:
        t = s.query(Tenant).filter_by(subdomain=(subdomain or '').strip().lower()).first()
        if t is not None:
            s.expunge(t)
        return t


def list_tenants():
    init_control_plane()
    with _session() as s:
        rows = s.query(Tenant).order_by(Tenant.created_at).all()
        for r in rows:
            s.expunge(r)
        return rows


def set_status(subdomain, status, *, error=None, database_url=None, activated=False):
    if status not in STATUSES:
        raise ValueError(f'Unknown status: {status}')
    with _session() as s:
        t = s.query(Tenant).filter_by(subdomain=subdomain).first()
        if t is None:
            raise ValueError(f'No such tenant: {subdomain}')
        t.status = status
        if error is not None or status != 'failed':
            t.error = error            # clear the error on any non-failure transition
        if database_url is not None:
            t.database_url = database_url
        if activated:
            t.activated_at = _dt.datetime.utcnow()
        s.commit()
        s.expunge(t)
        return t


def set_billing(subdomain, *, plan=None, trial_ends_at=False, paid_until=False):
    """Update a school's billing fields. Pass trial_ends_at / paid_until as a
    datetime (or None to clear); the sentinel False leaves them unchanged."""
    with _session() as s:
        t = s.query(Tenant).filter_by(subdomain=subdomain).first()
        if t is None:
            raise ValueError(f'No such tenant: {subdomain}')
        if plan is not None:
            t.plan = plan
        if trial_ends_at is not False:
            t.trial_ends_at = trial_ends_at
        if paid_until is not False:
            t.paid_until = paid_until
        s.commit()
        s.expunge(t)
        return t


def delete_tenant(subdomain):
    """Remove the registry row (does NOT drop the tenant's database)."""
    with _session() as s:
        t = s.query(Tenant).filter_by(subdomain=subdomain).first()
        if t is not None:
            s.delete(t)
            s.commit()


def set_verification(subdomain, token):
    """Store the email-verification token for a pending registration."""
    with _session() as s:
        t = s.query(Tenant).filter_by(subdomain=subdomain).first()
        if t is None:
            raise ValueError(f'No such tenant: {subdomain}')
        t.verification_token = token
        s.commit()
        s.expunge(t)
        return t


def mark_verified(subdomain):
    """Record that a school's email was verified (clears the token)."""
    with _session() as s:
        t = s.query(Tenant).filter_by(subdomain=subdomain).first()
        if t is None:
            raise ValueError(f'No such tenant: {subdomain}')
        t.verified_at = _dt.datetime.utcnow()
        t.verification_token = None
        if t.status == 'pending':
            t.status = 'verified'
        s.commit()
        s.expunge(t)
        return t


def get_content(key):
    """Return the stored JSON document for a content key, or None."""
    import json
    init_control_plane()
    with _session() as s:
        row = s.query(SiteContent).filter_by(key=key).first()
        if row is None or not row.data:
            return None
        try:
            return json.loads(row.data)
        except (ValueError, TypeError):
            return None


def save_content(key, data):
    """Upsert the JSON document for a content key."""
    import json
    init_control_plane()
    with _session() as s:
        row = s.query(SiteContent).filter_by(key=key).first()
        if row is None:
            row = SiteContent(key=key)
            s.add(row)
        row.data = json.dumps(data)
        s.commit()


def adopt_existing(subdomain, name, database_url, admin_email=None):
    """Register an ALREADY-EXISTING, already-populated database as an active
    tenant WITHOUT provisioning it — used to bring the current single school in
    as tenant #1. The database is never opened or modified here."""
    subdomain = (subdomain or '').strip().lower()
    if not VALID_SUBDOMAIN.match(subdomain):
        raise ValueError(f'Invalid subdomain: {subdomain!r}')
    if not database_url:
        raise ValueError('database_url is required to adopt an existing school.')
    init_control_plane()
    with _session() as s:
        t = s.query(Tenant).filter_by(subdomain=subdomain).first()
        if t is None:
            t = Tenant(name=name.strip(), subdomain=subdomain)
            s.add(t)
        t.name = name.strip()
        t.database_url = database_url
        t.admin_email = admin_email or t.admin_email
        t.status = 'active'
        t.plan = 'owner'                          # free forever, exempt from billing
        t.trial_ends_at = None
        t.verified_at = _dt.datetime.utcnow()
        t.activated_at = _dt.datetime.utcnow()
        s.commit()
        s.expunge(t)
        return t
