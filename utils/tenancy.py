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
    # Auto-renew (Approach B): a reusable Paystack authorization is stored after a
    # successful payment where the admin opted in; the daily job then charges the
    # saved card near expiry. Only card metadata is kept for display — never a PAN.
    auto_renew = Column(Integer, nullable=False, default=0)
    renew_plan = Column(String(20))                # tier id to charge on renewal
    paystack_auth_code = Column(String(120))       # reusable authorization_code
    card_brand = Column(String(20))
    card_last4 = Column(String(4))
    card_exp = Column(String(7))                   # MM/YYYY, for display only
    auto_renew_last_attempt = Column(DateTime)     # guards one attempt per day
    auto_renew_last_error = Column(String(300))    # surfaced on the billing page
    # Platform-admin annotations (internal, never shown to the school).
    notes = Column(Text)                           # free-text operator notes
    tags = Column(String(200))                     # comma-separated labels

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


class BillingNotice(_ControlBase):
    """The last billing reminder emailed to a school, so the daily job sends
    each lifecycle notice (trial-ending, renewal, lapsed, purge) only once."""
    __tablename__ = 'billing_notices'

    id = Column(Integer, primary_key=True)
    subdomain = Column(String(63), nullable=False, unique=True)
    marker = Column(String(32))                    # e.g. 'sub_7d', 'lapsed'
    sent_at = Column(DateTime, default=_dt.datetime.utcnow)


class ProcessedPayment(_ControlBase):
    """A Paystack transaction reference we've already credited — so the browser
    callback and the server webhook (which both fire for one payment) can't
    double-credit, and a receipt is emailed only once."""
    __tablename__ = 'processed_payments'

    id = Column(Integer, primary_key=True)
    reference = Column(String(120), nullable=False, unique=True)
    subdomain = Column(String(63))
    at = Column(DateTime, default=_dt.datetime.utcnow)


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
    """Create the ``tenants`` table if missing (idempotent), and add any columns
    introduced after a control-plane DB was first created."""
    engine, _ = _engine_and_session()
    _ControlBase.metadata.create_all(engine)
    _ensure_columns(engine)


# Columns added after the first release; ``create_all`` won't add columns to an
# existing table, so bring older control-plane DBs up to date in place. Kept as a
# tiny dialect-portable ADD COLUMN (no defaults/constraints beyond the type).
_ADDED_COLUMNS = {
    'auto_renew': 'INTEGER DEFAULT 0',
    'renew_plan': 'VARCHAR(20)',
    'paystack_auth_code': 'VARCHAR(120)',
    'card_brand': 'VARCHAR(20)',
    'card_last4': 'VARCHAR(4)',
    'card_exp': 'VARCHAR(7)',
    'auto_renew_last_attempt': 'TIMESTAMP',
    'auto_renew_last_error': 'VARCHAR(300)',
    'notes': 'TEXT',
    'tags': 'VARCHAR(200)',
}


def _ensure_columns(engine):
    from sqlalchemy import inspect, text
    try:
        existing = {c['name'] for c in inspect(engine).get_columns('tenants')}
    except Exception:
        return
    for name, ddl in _ADDED_COLUMNS.items():
        if name not in existing:
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE tenants ADD COLUMN {name} {ddl}'))


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


def set_meta(subdomain, *, notes=None, tags=None):
    """Store platform-admin annotations (internal notes / tags) on a tenant."""
    init_control_plane()
    with _session() as s:
        t = s.query(Tenant).filter_by(subdomain=subdomain).first()
        if t is None:
            raise ValueError(f'No such tenant: {subdomain}')
        if notes is not None:
            t.notes = notes.strip() or None
        if tags is not None:
            # normalise "a, b ,c" -> "a, b, c"
            parts = [p.strip() for p in tags.split(',') if p.strip()]
            t.tags = ', '.join(parts) or None
        s.commit()
        s.expunge(t)
        return t


def recent_payments(subdomain, limit=10):
    """Recent credited payment references for a tenant (control-plane record),
    newest first — a lightweight billing timeline for the profile page."""
    init_control_plane()
    with _session() as s:
        rows = (s.query(ProcessedPayment)
                .filter_by(subdomain=(subdomain or '').strip().lower())
                .order_by(ProcessedPayment.at.desc()).limit(limit).all())
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


_AUTORENEW_FIELDS = ('auto_renew', 'renew_plan', 'paystack_auth_code', 'card_brand',
                     'card_last4', 'card_exp', 'auto_renew_last_attempt',
                     'auto_renew_last_error')


def set_autorenew(subdomain, **fields):
    """Update auto-renew fields on a school. Only the keys in _AUTORENEW_FIELDS
    are accepted; a value of the sentinel False leaves that field unchanged."""
    with _session() as s:
        t = s.query(Tenant).filter_by(subdomain=subdomain).first()
        if t is None:
            raise ValueError(f'No such tenant: {subdomain}')
        for k, v in fields.items():
            if k not in _AUTORENEW_FIELDS:
                raise ValueError(f'Unknown auto-renew field: {k}')
            if v is not False:
                setattr(t, k, v)
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


def get_notice(subdomain):
    """The marker of the last billing notice emailed to this school, or None."""
    init_control_plane()
    with _session() as s:
        row = s.query(BillingNotice).filter_by(subdomain=subdomain).first()
        return row.marker if row else None


def set_notice(subdomain, marker):
    """Record that a billing notice (marker) was emailed to this school."""
    init_control_plane()
    with _session() as s:
        row = s.query(BillingNotice).filter_by(subdomain=subdomain).first()
        if row is None:
            row = BillingNotice(subdomain=subdomain)
            s.add(row)
        row.marker = marker
        row.sent_at = _dt.datetime.utcnow()
        s.commit()


def clear_notice(subdomain):
    """Reset a school's notice state (called on payment, so the next billing
    cycle's reminders fire again)."""
    with _session() as s:
        row = s.query(BillingNotice).filter_by(subdomain=subdomain).first()
        if row is not None:
            row.marker = None
            s.commit()


def claim_payment(reference, subdomain=None):
    """Atomically claim a Paystack transaction reference. Returns True if it is
    new (caller should credit + email the receipt), False if already processed."""
    if not reference:
        return True                    # no reference (e.g. test mode) -> don't dedupe
    from sqlalchemy.exc import IntegrityError
    init_control_plane()
    with _session() as s:
        s.add(ProcessedPayment(reference=reference, subdomain=subdomain))
        try:
            s.commit()
            return True
        except IntegrityError:
            s.rollback()
            return False


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
