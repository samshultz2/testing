# Multi-Tenancy — Architecture Decision & Roadmap

**Status:** Decided in principle, deferred until after the first single-school
launch (Pioneer Education Center). This is a record so the plan survives between
work sessions — it is **not** yet implemented.

## Decision

When PosyHub serves more than one school, use the **shared-app / database-per-school**
model, with schools routed by subdomain:

- **One** application deployment (gunicorn behind nginx), not one per school.
- **One PostgreSQL database per school** — the data boundary is the database.
- Each request resolves its tenant from the host (`pioneer.posyhub.app`) and
  connects to that school's database via a per-tenant engine cache.
- A small **central "control plane"**: a `tenants` registry (subdomain →
  database name → status) plus the public marketing/registration site.

### Why this over the alternatives

| Model | Verdict |
|-------|---------|
| App **process** per school | Rejected — wasteful (N idle processes/RAM), N nginx blocks. |
| **Shared app, DB per school** | **Chosen** — strong (DB-level) isolation, tiny code change (app already reads `DATABASE_URL`; make it per-request), scales to hundreds–thousands of schools. |
| Shared app, one shared DB (`school_id` on every table) | Rejected for now — requires adding a tenant key to ~100 tables and scoping every query; one missing filter leaks students across schools. Most efficient only at very large scale. |

Rationale: student data (minors) warrants a database boundary, and the refined
model preserves essentially all of today's single-tenant code.

## What it will require (when we build it)

1. **Tenant resolution middleware** — map request host → tenant → database.
2. **Per-tenant engine/session registry** — cache one SQLAlchemy engine per
   active school; the app's `db` session binds to the resolved engine per request.
3. **Central `tenants` table** (in a control-plane DB): `subdomain`,
   `database_name`, `status` (pending/active/suspended), `created_at`, billing fields later.
4. **Provisioning script** — `CREATE DATABASE` → `create_all` + seed defaults →
   create the school's first admin → mark active → email credentials. (Builds on
   the existing per-DB `pg_dump` backup approach for per-school backups.)
5. **Registration flow** — public "Register your school" form → `pending` row.
6. **Wildcard DNS + wildcard TLS** (`*.posyhub.app`) so new schools need no
   manual DNS/cert steps.
7. **Alembic migrations + a `migrate-all-tenants` command** — replaces today's
   `create_all` so schema changes roll out safely across every school's DB.

## Open decisions (deferred)

- **Provisioning trigger:** manual-approve vs fully automatic. *Undecided.*
  Strong recommendation: do **not** let a public form create databases
  unattended (signup-abuse = unbounded DB creation). Start with
  email-verification + lightweight approval; automate later with rate limiting.
- Pricing/billing model (if commercial).
- Cross-school (super-admin) reporting surface.

## Sequencing

1. **Now → launch:** ship Pioneer single-tenant on the Linux server. No
   multi-tenant code. *(current focus)*
2. **Foundation:** tenant DB-routing + `tenants` registry, with Pioneer as
   tenant #1 — invisible to current users.
3. **Onboarding:** registration form + provisioning script + wildcard subdomain/TLS.
4. **Hardening:** Alembic + migrate-all-tenants, per-tenant backups, billing.

## Note for whoever implements step 2

Today the app builds one global engine from `DATABASE_URL` (`config.py`) and
uses a single Flask-SQLAlchemy `db`. The change is to resolve the database
per request (from the host) and bind the scoped session to a per-tenant engine —
the models, routes, and templates do not need to change.

## Implementation status

### Stage 1 — tenants registry + provisioning — **DONE**

Built and off the request path (the single-school deployment is unaffected):

- **`utils/tenancy.py`** — the control-plane `Tenant` registry on its *own*
  engine + declarative base (never part of `db.metadata`, so it is never created
  inside a tenant DB). Location: `CONTROL_PLANE_DATABASE_URL` (defaults to a
  local SQLite file). API: `register_tenant`, `get_tenant`, `list_tenants`,
  `set_status`, `delete_tenant`. Subdomains are validated.
- **`utils/provisioning.py`** — `provision(subdomain)`: creates the physical
  database (Postgres `CREATE DATABASE` via a privileged provisioner connection;
  SQLite = a file), builds the full schema (`db.metadata.create_all`), stamps
  Alembic at head, seeds a default branch + the school's first central
  super-admin (temp password, must-change), and marks the tenant `active`.
  Rollback-safe (`failed` + error on exception). `drop_tenant()` tears a tenant
  database down for rollback/testing.
- **`scripts/provision_tenant.py`** — CLI: `--list`, register + provision,
  `--register-only`, `--drop`.
- **`tests/test_tenant_provisioning.py`** — register/validate, provision two
  schools, assert full schema + seed + Alembic stamp, and prove **isolation**
  (a write in one school's DB is invisible in the other).

Config knobs: `CONTROL_PLANE_DATABASE_URL`, `TENANT_DATABASE_URL_TEMPLATE`
(Postgres, e.g. `postgresql+psycopg://user:pw@host/{name}`) or `TENANT_DB_DIR`
(SQLite dev), `PROVISIONER_DATABASE_URL` (a role WITH `createdb`, so the app's
own DB role never needs it).

Example: `python scripts/provision_tenant.py --name "Pioneer" --subdomain pioneer --admin-email head@pioneer.example`

### Still to do

- **Stage 0 — request-time routing:** resolve host → tenant → engine and bind
  `db.session` per request (a `get_bind()`-override session + engine registry);
  bind the session cookie to the tenant; namespace uploads per tenant.
- **Stage 2 — `migrate-all-tenants`** command (iterate the registry, run Alembic
  per DB); per-tenant `pg_dump` backups.
- **Stage 3 — registration + approval UI**; wildcard DNS + TLS.
