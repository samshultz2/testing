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

STATUSES = ('pending', 'provisioning', 'active', 'failed', 'suspended', 'archived')


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
    account_manager = Column(String(120))          # assigned CSM/owner (username or name)
    priority = Column(String(20))                  # normal | high | vip
    risk = Column(String(20))                      # none | watch | high (churn risk)
    tier = Column(String(20))                      # entitlement tier: free|basic|premium|enterprise
    entitlements_json = Column(Text)               # per-tenant override overlay (JSON)

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


class PlatformAudit(_ControlBase):
    """A record of a platform-admin action against the control plane — grants,
    suspensions, deletions, note edits, pricing/homepage changes. Control-plane
    level (spans all schools), so it lives here rather than any one tenant DB."""
    __tablename__ = 'platform_audit'

    id = Column(Integer, primary_key=True)
    at = Column(DateTime, default=_dt.datetime.utcnow, index=True)
    actor = Column(String(120))                    # platform admin username
    action = Column(String(60), nullable=False)    # e.g. 'grant', 'suspend', 'delete'
    subdomain = Column(String(63))                 # affected school, if any
    detail = Column(String(300))
    # Tamper-evident hash chain: each row seals the previous row's hash, so any
    # edit or deletion downstream breaks the chain and is detectable.
    prev_hash = Column(String(64))
    row_hash = Column(String(64))


class ImpersonationGrant(_ControlBase):
    """A time-boxed, audited authorization for a platform operator to view a
    tenant's portal as its admin (read-only support session). The token is
    exchanged once, on the tenant's own host, to establish the session; the
    grant can be ended early (kill switch) and auto-expires."""
    __tablename__ = 'impersonation_grants'

    id = Column(Integer, primary_key=True)
    token = Column(String(64), nullable=False, unique=True)
    actor = Column(String(120), nullable=False)    # the platform operator
    subdomain = Column(String(63), nullable=False, index=True)
    reason = Column(String(300))                    # justification (ticket ref etc.)
    created_at = Column(DateTime, default=_dt.datetime.utcnow, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime)                      # first exchanged on the tenant host
    ended_at = Column(DateTime)                     # revoked / stopped


class PlatformBroadcast(_ControlBase):
    """A platform-wide announcement targeted at tenant admins by segment. Shown
    as an in-portal banner on matching schools between starts_at and ends_at."""
    __tablename__ = 'platform_broadcasts'

    id = Column(Integer, primary_key=True)
    message = Column(Text, nullable=False)
    level = Column(String(20), default='info')      # info | warning | critical
    segment = Column(String(40), default='all')     # all|paying|trial|unpaid|tier:<id>
    created_by = Column(String(120))
    created_at = Column(DateTime, default=_dt.datetime.utcnow, index=True)
    starts_at = Column(DateTime)
    ends_at = Column(DateTime)                       # None → until manually ended
    ended_at = Column(DateTime)


class SupportTicket(_ControlBase):
    """A support conversation bound to one school. Opened by the school's admin
    (via their portal) or by the operator; visible to both sides."""
    __tablename__ = 'support_tickets'

    id = Column(Integer, primary_key=True)
    subdomain = Column(String(63), nullable=False, index=True)
    subject = Column(String(200), nullable=False)
    status = Column(String(20), default='open')      # open | closed
    priority = Column(String(20), default='normal')  # low | normal | high | urgent
    created_by = Column(String(120))                 # opener (username)
    created_at = Column(DateTime, default=_dt.datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=_dt.datetime.utcnow, index=True)


class TicketMessage(_ControlBase):
    __tablename__ = 'ticket_messages'

    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, nullable=False, index=True)
    author = Column(String(120))
    is_staff = Column(Integer, default=0)            # 1 = platform operator, 0 = school
    body = Column(Text, nullable=False)
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
    _ensure_audit_columns(engine)


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
    'account_manager': 'VARCHAR(120)',
    'priority': 'VARCHAR(20)',
    'risk': 'VARCHAR(20)',
    'tier': 'VARCHAR(20)',
    'entitlements_json': 'TEXT',
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


_AUDIT_ADDED_COLUMNS = {'prev_hash': 'VARCHAR(64)', 'row_hash': 'VARCHAR(64)'}


def _ensure_audit_columns(engine):
    """Bring older control planes' platform_audit table up to date (hash chain)."""
    from sqlalchemy import inspect, text
    try:
        existing = {c['name'] for c in inspect(engine).get_columns('platform_audit')}
    except Exception:
        return
    for name, ddl in _AUDIT_ADDED_COLUMNS.items():
        if name not in existing:
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE platform_audit ADD COLUMN {name} {ddl}'))


def _audit_row_hash(prev_hash, at, actor, action, subdomain, detail):
    """Deterministic hash of an audit row, sealing the previous row's hash."""
    import hashlib
    payload = '|'.join([
        prev_hash or '',
        (at.isoformat() if at else ''),
        actor or '', action or '', subdomain or '', detail or '',
    ])
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


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


def set_meta(subdomain, *, notes=None, tags=None, account_manager=None,
             priority=None, risk=None):
    """Store platform-admin annotations (internal notes / tags / CRM fields) on a
    tenant. Only the fields passed (non-None) are changed."""
    init_control_plane()
    _VALID_PRIORITY = {'normal', 'high', 'vip'}
    _VALID_RISK = {'none', 'watch', 'high'}
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
        if account_manager is not None:
            t.account_manager = account_manager.strip() or None
        if priority is not None:
            p = priority.strip().lower()
            t.priority = p if p in _VALID_PRIORITY else None
        if risk is not None:
            r = risk.strip().lower()
            t.risk = r if r in _VALID_RISK else None
        s.commit()
        s.expunge(t)
        return t


def set_entitlement(subdomain, *, tier=None, overrides=None):
    """Set a tenant's entitlement tier and/or per-tenant override overlay.
    ``overrides`` is a JSON-serialisable dict ({'features':{}, 'limits':{}}) or
    None to leave unchanged; pass {} to clear it."""
    import json as _json
    init_control_plane()
    with _session() as s:
        t = s.query(Tenant).filter_by(subdomain=subdomain).first()
        if t is None:
            raise ValueError(f'No such tenant: {subdomain}')
        if tier is not None:
            t.tier = (tier.strip().lower() or None)
        if overrides is not None:
            t.entitlements_json = _json.dumps(overrides) if overrides else None
        s.commit()
        s.expunge(t)
        return t


def tenant_timeline(subdomain, *, limit=60):
    """A merged, newest-first activity timeline for one tenant, assembled from
    real control-plane history: lifecycle dates, credited payments and every
    platform-admin action recorded against the school. Each entry is a dict
    {when, kind, label, detail}."""
    init_control_plane()
    events = []
    with _session() as s:
        t = s.query(Tenant).filter_by(subdomain=subdomain).first()
        if t is None:
            return []
        if t.created_at:
            events.append({'when': t.created_at, 'kind': 'signup',
                           'label': 'Registered', 'detail': t.admin_email or ''})
        if t.verified_at:
            events.append({'when': t.verified_at, 'kind': 'verify',
                           'label': 'Email verified', 'detail': ''})
        if t.activated_at:
            events.append({'when': t.activated_at, 'kind': 'activate',
                           'label': 'Provisioned & activated', 'detail': ''})
        for p in (s.query(ProcessedPayment)
                  .filter_by(subdomain=subdomain)
                  .order_by(ProcessedPayment.at.desc()).limit(limit).all()):
            events.append({'when': p.at, 'kind': 'payment',
                           'label': 'Payment credited', 'detail': (p.reference or '')[:24]})
        for a in (s.query(PlatformAudit)
                  .filter_by(subdomain=subdomain)
                  .order_by(PlatformAudit.at.desc()).limit(limit).all()):
            events.append({'when': a.at, 'kind': 'admin',
                           'label': (a.action or 'action').replace('_', ' ').title(),
                           'detail': f'{a.detail or ""}{" · " + a.actor if a.actor else ""}'.strip(' ·')})
    events.sort(key=lambda e: e['when'] or _dt.datetime.min, reverse=True)
    return events[:limit]


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


def list_payments(limit=500):
    """All credited payments across every tenant, newest first, as dicts
    {at, reference, subdomain, name}. For the platform payments ledger."""
    init_control_plane()
    with _session() as s:
        names = {t.subdomain: t.name for t in s.query(Tenant.subdomain, Tenant.name).all()}
        rows = (s.query(ProcessedPayment)
                .order_by(ProcessedPayment.at.desc()).limit(limit).all())
        return [{'at': r.at, 'reference': r.reference, 'subdomain': r.subdomain,
                 'name': names.get(r.subdomain, r.subdomain)} for r in rows]


def create_impersonation(actor, subdomain, reason, *, ttl_minutes=30):
    """Mint a time-boxed impersonation grant and return it (detached).
    The token is a cryptographically-random URL-safe string."""
    import secrets
    init_control_plane()
    now = _dt.datetime.utcnow()
    g = ImpersonationGrant(
        token=secrets.token_urlsafe(32), actor=actor, subdomain=subdomain,
        reason=(reason or '').strip()[:300] or None,
        created_at=now, expires_at=now + _dt.timedelta(minutes=ttl_minutes))
    with _session() as s:
        s.add(g)
        s.commit()
        s.refresh(g)
        s.expunge(g)
        return g


def get_impersonation(token=None, *, grant_id=None):
    init_control_plane()
    with _session() as s:
        q = s.query(ImpersonationGrant)
        g = (q.filter_by(token=token).first() if token
             else q.filter_by(id=grant_id).first() if grant_id else None)
        if g is not None:
            s.expunge(g)
        return g


def validate_impersonation(token, subdomain):
    """Return the grant if it is a live authorization for ``subdomain`` (exists,
    right school, not ended, not expired); mark it used on first exchange.
    Returns None otherwise."""
    init_control_plane()
    now = _dt.datetime.utcnow()
    with _session() as s:
        g = s.query(ImpersonationGrant).filter_by(token=token).first()
        if (g is None or g.subdomain != subdomain or g.ended_at is not None
                or g.expires_at is None or g.expires_at <= now):
            return None
        if g.used_at is None:
            g.used_at = now
            s.commit()
        s.expunge(g)
        return g


def end_impersonation(*, token=None, grant_id=None):
    """End (revoke) an impersonation grant. Idempotent."""
    init_control_plane()
    with _session() as s:
        q = s.query(ImpersonationGrant)
        g = (q.filter_by(token=token).first() if token
             else q.filter_by(id=grant_id).first() if grant_id else None)
        if g is not None and g.ended_at is None:
            g.ended_at = _dt.datetime.utcnow()
            s.commit()
        return g is not None


def list_impersonations(*, limit=100, active_only=False):
    """Impersonation grants, newest first, as detached rows."""
    init_control_plane()
    now = _dt.datetime.utcnow()
    with _session() as s:
        q = s.query(ImpersonationGrant).order_by(ImpersonationGrant.created_at.desc())
        rows = q.limit(limit).all()
        out = []
        for g in rows:
            active = (g.ended_at is None and g.expires_at and g.expires_at > now)
            if active_only and not active:
                continue
            s.expunge(g)
            g_active = active
            out.append((g, g_active))
        return out


_BROADCAST_SEGMENTS = ('all', 'paying', 'trial', 'unpaid',
                       'tier:free', 'tier:basic', 'tier:premium', 'tier:enterprise')


def create_broadcast(message, *, level='info', segment='all', created_by=None,
                     ends_at=None):
    init_control_plane()
    seg = segment if segment in _BROADCAST_SEGMENTS else 'all'
    lvl = level if level in ('info', 'warning', 'critical') else 'info'
    now = _dt.datetime.utcnow()
    b = PlatformBroadcast(message=message.strip(), level=lvl, segment=seg,
                          created_by=created_by, created_at=now, starts_at=now,
                          ends_at=ends_at)
    with _session() as s:
        s.add(b)
        s.commit()
        s.refresh(b)
        s.expunge(b)
        _LIVE_BC_CACHE['exp'] = 0.0            # invalidate the live cache
        return b


def end_broadcast(broadcast_id):
    init_control_plane()
    with _session() as s:
        b = s.query(PlatformBroadcast).filter_by(id=broadcast_id).first()
        if b is not None and b.ended_at is None:
            b.ended_at = _dt.datetime.utcnow()
            s.commit()
        _LIVE_BC_CACHE['exp'] = 0.0            # invalidate the live cache
        return b is not None


def list_broadcasts(*, limit=100):
    """All broadcasts newest-first as (broadcast, is_live) tuples."""
    init_control_plane()
    now = _dt.datetime.utcnow()
    with _session() as s:
        rows = (s.query(PlatformBroadcast)
                .order_by(PlatformBroadcast.created_at.desc()).limit(limit).all())
        out = []
        for b in rows:
            live = (b.ended_at is None and (b.ends_at is None or b.ends_at > now))
            s.expunge(b)
            out.append((b, live))
        return out


_LIVE_BC_CACHE = {'exp': 0.0, 'val': None}


def _live_broadcasts():
    import time as _time
    tnow = _time.time()
    if _LIVE_BC_CACHE['val'] is not None and _LIVE_BC_CACHE['exp'] > tnow:
        return _LIVE_BC_CACHE['val']
    now = _dt.datetime.utcnow()
    with _session() as s:
        rows = (s.query(PlatformBroadcast)
                .filter(PlatformBroadcast.ended_at.is_(None))
                .order_by(PlatformBroadcast.created_at.desc()).all())
        live = []
        for b in rows:
            if b.starts_at and b.starts_at > now:
                continue
            if b.ends_at and b.ends_at <= now:
                continue
            s.expunge(b)
            live.append(b)
        _LIVE_BC_CACHE['val'] = live
        _LIVE_BC_CACHE['exp'] = tnow + 60
        return live


def broadcasts_for(tenant):
    """Live broadcasts whose segment matches this tenant. Never raises."""
    try:
        init_control_plane()
        from utils import billing
        st = billing.status(tenant)
        tier = (getattr(tenant, 'tier', None) or 'basic').lower()
        bucket = ('paying' if (st['active'] and not st['on_trial']
                               and getattr(tenant, 'status', '') == 'active')
                  else 'trial' if st['on_trial']
                  else 'unpaid' if not st['active'] else None)
        out = []
        for b in _live_broadcasts():
            seg = b.segment or 'all'
            if seg == 'all' or seg == bucket or seg == f'tier:{tier}':
                out.append(b)
        return out
    except Exception:
        return []


def create_ticket(subdomain, subject, body, *, created_by=None, priority='normal',
                  is_staff=False):
    """Open a support ticket with its first message. Returns the ticket id."""
    init_control_plane()
    now = _dt.datetime.utcnow()
    pr = priority if priority in ('low', 'normal', 'high', 'urgent') else 'normal'
    with _session() as s:
        t = SupportTicket(subdomain=subdomain, subject=subject.strip()[:200],
                          status='open', priority=pr, created_by=created_by,
                          created_at=now, updated_at=now)
        s.add(t)
        s.flush()
        s.add(TicketMessage(ticket_id=t.id, author=created_by,
                            is_staff=1 if is_staff else 0, body=body.strip(), at=now))
        s.commit()
        return t.id


def add_ticket_message(ticket_id, body, *, author=None, is_staff=False):
    init_control_plane()
    now = _dt.datetime.utcnow()
    with _session() as s:
        t = s.query(SupportTicket).filter_by(id=ticket_id).first()
        if t is None:
            return False
        s.add(TicketMessage(ticket_id=ticket_id, author=author,
                            is_staff=1 if is_staff else 0, body=body.strip(), at=now))
        t.updated_at = now
        if t.status == 'closed':
            t.status = 'open'                       # a reply reopens
        s.commit()
        return True


def set_ticket_status(ticket_id, status):
    init_control_plane()
    with _session() as s:
        t = s.query(SupportTicket).filter_by(id=ticket_id).first()
        if t is None:
            return False
        t.status = 'closed' if status == 'closed' else 'open'
        t.updated_at = _dt.datetime.utcnow()
        s.commit()
        return True


def get_ticket(ticket_id, *, subdomain=None):
    """A ticket with its messages: (ticket, [messages]) or (None, [])."""
    init_control_plane()
    with _session() as s:
        t = s.query(SupportTicket).filter_by(id=ticket_id).first()
        if t is None or (subdomain and t.subdomain != subdomain):
            return None, []
        msgs = (s.query(TicketMessage).filter_by(ticket_id=ticket_id)
                .order_by(TicketMessage.at.asc()).all())
        for m in msgs:
            s.expunge(m)
        s.expunge(t)
        return t, msgs


def list_tickets(*, subdomain=None, status=None, limit=200):
    """Tickets newest-updated first, optionally scoped to one school / status."""
    init_control_plane()
    with _session() as s:
        q = s.query(SupportTicket)
        if subdomain:
            q = q.filter_by(subdomain=subdomain)
        if status in ('open', 'closed'):
            q = q.filter_by(status=status)
        rows = q.order_by(SupportTicket.updated_at.desc()).limit(limit).all()
        for t in rows:
            s.expunge(t)
        return rows


def count_open_tickets():
    init_control_plane()
    with _session() as s:
        return s.query(SupportTicket).filter_by(status='open').count()


def log_platform(action, *, subdomain=None, detail=None, actor=None):
    """Append a platform-admin action to the control-plane audit trail, sealed
    into a tamper-evident hash chain. Best-effort — auditing must never break the
    action it records."""
    try:
        init_control_plane()
        with _session() as s:
            last = (s.query(PlatformAudit)
                    .order_by(PlatformAudit.id.desc()).first())
            prev_hash = last.row_hash if last else ''
            at = _dt.datetime.utcnow()
            row = PlatformAudit(at=at, action=action, subdomain=subdomain,
                                detail=(detail or None), actor=(actor or None),
                                prev_hash=prev_hash)
            row.row_hash = _audit_row_hash(prev_hash, at, actor, action, subdomain,
                                           detail)
            s.add(row)
            s.commit()
    except Exception:
        pass


def verify_audit_chain():
    """Recompute the audit hash chain and report integrity.
    Returns {'ok': bool, 'checked': int, 'broken_at': id-or-None}."""
    init_control_plane()
    with _session() as s:
        rows = s.query(PlatformAudit).order_by(PlatformAudit.id.asc()).all()
        prev = ''
        for r in rows:
            expect = _audit_row_hash(prev, r.at, r.actor, r.action, r.subdomain, r.detail)
            # A row written before the chain existed has no hash — skip, don't fail.
            if r.row_hash and (r.prev_hash or '') != prev:
                return {'ok': False, 'checked': len(rows), 'broken_at': r.id}
            if r.row_hash and r.row_hash != expect:
                return {'ok': False, 'checked': len(rows), 'broken_at': r.id}
            prev = r.row_hash or prev
        return {'ok': True, 'checked': len(rows), 'broken_at': None}


def list_platform_audit(*, limit=300, action=None, subdomain=None, q=None):
    """Recent platform-audit rows, newest first, with optional filters."""
    init_control_plane()
    with _session() as s:
        query = s.query(PlatformAudit)
        if action:
            query = query.filter(PlatformAudit.action == action)
        if subdomain:
            query = query.filter(PlatformAudit.subdomain == subdomain)
        if q:
            like = f'%{q.strip().lower()}%'
            from sqlalchemy import func, or_
            query = query.filter(or_(
                func.lower(PlatformAudit.subdomain).like(like),
                func.lower(PlatformAudit.detail).like(like),
                func.lower(PlatformAudit.actor).like(like)))
        rows = query.order_by(PlatformAudit.at.desc()).limit(limit).all()
        for r in rows:
            s.expunge(r)
        return rows


def audit_actions():
    """Distinct action names present in the audit log (for the filter dropdown)."""
    init_control_plane()
    with _session() as s:
        return sorted({r[0] for r in s.query(PlatformAudit.action).distinct().all() if r[0]})


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
