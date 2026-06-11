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
