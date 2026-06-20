# Architecture Audit & Refactoring Strategy

_A full-project review of the EduSyncra/PosyHub school-management app: how it is
built, where the weak points are, and a prioritized plan to raise code quality,
scalability and maintainability **without changing behaviour**._

> Status legend: ✅ applied in this pass · 🔜 recommended · ⚠️ risk to watch

---

## 1. Clean architecture breakdown

**What it is:** a Flask monolith for a single school (multi-branch aware),
deployed on a phone/VPS behind a Cloudflare tunnel, installable as a PWA.

```
                         ┌──────────────────────────────────────────────┐
  Browser / PWA  ───────▶│  Flask app (app.py: create_app)              │
   - React “islands”     │   before_request: CSRF · write-level · idle  │
   - soft-nav (spa-nav)  │   blueprints (one per module)                │
   - service worker      │   context processors (theme, branch, perms)  │
                         │   error handlers (+ got_request_exception)   │
                         └───────────────┬──────────────────────────────┘
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        ▼                                ▼                                ▼
   routes/*.py                      utils/*.py                       models/*.py
   (controllers,                (cross-cutting: spa, csrf,        (SQLAlchemy ORM;
    request parsing,             access_control, branch_scope,    SQLite dev /
    response shaping)            calculations, report_card,       Postgres prod)
                                 notify, error_tracking, …)
```

**Rendering model (the defining decision).** Each feature is a **server-rendered
Jinja shell + a React “island”** built with esbuild into a committed IIFE bundle.
Pages return their data two ways from one route via
`utils/spa.render_or_json(template, var, payload)`:

- a normal browser request → the HTML shell with the payload embedded as JSON;
- a `fetch` request (`X-Requested-With: fetch`) → the **same payload as JSON**,
  so in-section navigation/filtering/refresh happen with no reload
  (`frontend/src/lib/section.js`).

A global **soft-navigation** layer (`static/js/spa-nav.js`) extends this to the
whole app: clicking any menu/page link swaps the page body (and head CSS) instead
of a full reload, falling back to a real navigation for anything it can’t handle.

**Auth & access.** Session-based login; a custom per-session CSRF token enforced
globally (`utils/csrf.py`); RBAC in `utils/access_control.py` — module +
sub-section permission levels, branch scope (`utils/branch_scope.py`),
section/stream scope, and a **form-teacher** scope for attendance/student data.

**Schema.** SQLAlchemy models; `db.create_all()` builds fresh tables, with some
**runtime column patching** in `models/models.py`, and Alembic available
(`db_migrations/`) but not the single source of truth.

---

## 2. Critical problem areas

### 2.1 Bad architecture decisions

| # | Finding | Evidence | Impact |
|---|---------|----------|--------|
| A1 | **God files.** A handful of route modules mix many responsibilities. | `generator.py` 3 650 LOC, `main.py` 2 760, `results.py` 2 049, `subjects.py` 1 821, `attendance.py` 1 687. | Hard to navigate, review, and test; high merge-conflict surface. |
| A2 | **No service/domain layer.** Business rules (score saving, report-card computation, fee billing, attendance maths) live **inside** request handlers, interleaved with `request.form` parsing. | `routes/subjects.py:save_scores`, `routes/contributions.py:dashboard`. | Logic isn’t reusable or unit-testable in isolation; controllers are fat. |
| A3 | **Two schema sources of truth.** `create_all()` + ad-hoc runtime `ALTER` **and** Alembic. | `models/models.py` (“add missing columns”), `app.py` Migrate. | Drift between environments; “works on my DB” bugs. |
| A4 | **Pervasive lazy imports** (`from utils.x import y` inside functions) to dodge circular imports. | ~everywhere in `routes/`. | Hides the dependency graph; signals module-coupling that should be untangled. |
| A5 | **Models package carries seeding/migration logic** alongside ORM definitions. | `models/models.py` `_seed_*`, runtime patching. | Mixes “what data is” with “how it’s provisioned”. |

### 2.2 Duplicate logic

| # | Finding | Evidence | Impact |
|---|---------|----------|--------|
| D1 | **SPA response helpers copy-pasted** (`_wants_json/_render/_ok/_err`, ~25 lines) in **20 blueprints**. | grep: 20 files define `_wants_json`. | ~500 lines of identical boilerplate; any change touches 20 files. ✅ **factory added; 5 migrated.** |
| D2 | **Per-section `_urls()` nav-map builders** repeated. | `contributions`, `library`, `admissions`, … | Same shape re-implemented per file. |
| D3 | **Dead duplicate auth code.** A second CSRF implementation and an unused contributions-gate helper sit in `utils/security.py`. | `verify_contributions_access`, `contributions_required` (unused); `generate_csrf_token` duplicated vs `utils/csrf.py`. | Confusion about which is authoritative. |
| D4 | **Excel/CSV import & name-matching** re-implemented per importer. | `utils/excel_utils.py` vs `routes/contributions.py:import_excel` vs `routes/subjects.py:import_scores`. | Inconsistent parsing/normalisation rules. |
| D5 | **Scope-to-current-user query patterns** repeated ad hoc. | `scope_query(...)` + teacher filters in `main`, `attendance`, `subjects`. | Easy for one path to drift and leak data (we found two such gaps). |

### 2.3 Performance bottlenecks

| # | Finding | Evidence | Impact |
|---|---------|----------|--------|
| P1 | **N+1 / per-row aggregate queries.** Loops issue one `func.sum`/`count` per student or per day. | `contributions.dashboard` (sum per student), `attendance` summaries (per student×day), `subjects.bulk_entry` nested loops. | O(students) round-trips; slow dashboards on real data. |
| P2 | **Synchronous heavy work in the request path:** report-card recompute on every score save, OR-Tools timetable generation, OCR, SMS, backups, e-mail. | `compute_term_summaries` after each save; `generator_ortools`. | Long requests hold a worker; poor tail latency. |
| P3 | **No caching of expensive reads.** Dashboards recompute from scratch each load. | dashboards across sections. | Wasted CPU/DB under repeated views. |
| P4 | **Synchronous external calls** (Paystack verify, mailer) inline. | `parent_portal.pay_callback`, `utils/mailer`. | A slow third party slows the user’s request. |

### 2.4 Scalability risks

| # | Finding | Evidence | Impact |
|---|---------|----------|--------|
| S1 | **In-process state that doesn’t survive >1 worker.** The login/CSRF rate limiter, the error-log ring buffer, and a couple of caches are plain in-memory dicts/deques. | `utils/security.RateLimiter`, `utils/error_tracking._recent`, caches in `comms.py`/`finance.py`. | With N gunicorn workers the limit is effectively N× looser; the Error Log shows only one worker’s errors. ⚠️ |
| S2 | **No task queue.** All background-style work is inline (see P2). | — | Can’t scale workers independently of web concurrency. |
| S3 | **DB pool is per-process and small-VPS sized.** | `config.py` (`pool_size` 10, `max_overflow` 20). | Postgres `max_connections` must be raised in lockstep with workers, or connections exhaust. ✅ pool already hardened (pre-ping/recycle/timeout). |
| S4 | **Service-worker page cache is device-local.** | `static/js/sw.js`. | Fine for a single-user phone install; a shared/multi-user host risks cross-user cached pages (runtime cache is cleared on logout, but note the assumption). ⚠️ |
| S5 | **Committed frontend bundles, no CI build.** | `static/js/react/*.js` tracked. | Source ↔ bundle drift if someone edits JSX without rebuilding. |

### 2.5 Maintainability issues

- **Naming drift:** `PosyHub`, `EduSyncra`, `posyhub.*` loggers coexist.
- **Fat controllers + lazy imports** make call-graphs hard to follow.
- **Session-scoped shared test DB** → tests must hand-clean state and are
  order-sensitive (we hit this twice); no per-test transaction rollback.
- **The Generator** (5 files, ~6 000 LOC, 41 templates) is a self-contained
  power-tool left on Jinja — acceptable, but it is the least-uniform corner.

---

## 3. Refactoring strategy (prioritized)

### P0 — Safe, high-value, behaviour-preserving (do first)
1. ✅ **Extract the SPA helpers** into `utils.spa.section_responders(template,
   var, default_endpoint, enrich=…)`. Done for `settings/users/timetable/
   academics/contributions`; 🔜 roll out to the remaining ~15 blueprints
   (mechanical; the test suite is the safety net).
2. 🔜 **Delete dead duplicates** (`utils/security.py` unused CSRF + contributions
   helpers) once a grep confirms zero importers.
3. 🔜 **Centralise `_urls()`/nav builders** into one helper per concept.
4. 🔜 **Wrap the rate limiter & error buffer behind a tiny interface** with an
   in-memory default and an optional Redis backend (no behaviour change now,
   scale later).

### P1 — Structural (moderate effort)
5. 🔜 **Introduce a domain/service layer** (`utils/services/…`): move scoring,
   report cards, fee billing and attendance maths out of routes; controllers
   become thin (parse → call service → `_ok/_err`).
6. 🔜 **Split the god files** by feature into sub-modules/blueprints
   (`generator`, `main`, `results`).
7. 🔜 **Kill the N+1s**: replace per-row `func.sum`/`count` loops with single
   `GROUP BY` queries and `joinedload` for the read models.
8. 🔜 **One schema source of truth**: make Alembic authoritative; restrict
   `create_all()` to dev/test; remove runtime `ALTER`.

### P2 — Scale-out
9. 🔜 **Task queue** (RQ/Celery + Redis) for report recompute, SMS, OCR,
   timetable generation, backups, e-mail.
10. 🔜 **Caching** (Flask-Caching/Redis) for expensive dashboards with explicit
    invalidation on writes.
11. 🔜 **Shared state in Redis** (rate limit, notifications fan-out, error feed)
    for multi-worker correctness.
12. 🔜 **CI pipeline**: build bundles + run tests + lint on every push; stop
    committing built JS (or verify it matches source in CI).

---

## 4. Production-grade improvements already applied

Recent passes (this and prior) raised quality without changing behaviour:

- ✅ `section_responders` factory — DRY SPA helpers (5 blueprints migrated).
- ✅ **Structured error tracking** (`utils/error_tracking`) + a global
  `got_request_exception` hook + an admin **Error Log**, and a client-side
  `window.onerror` reporter → `/client-error`.
- ✅ **React error boundaries** around every section (friendly fallback + report).
- ✅ **Form-recovery** hook (`lib/draft.useDraft`) so typed input survives
  reloads/crashes.
- ✅ **Security**: auth audited; **IDOR/branch-scope guards** on id-based routes
  (student delete, CBT exams, bulk edits, results-by-subject); CSRF on the
  contributions gate; rate limiting on login/forgot-password.
- ✅ **DB pool hardening** (pre-ping, recycle, pool_size/overflow/timeout).
- ✅ **In-app notifications** (`utils/notify`) with a reusable `notify_admins()`.

The single most impactful next step is **P1.5 (a service layer) + P1.7 (kill the
N+1s)**: together they make the app testable, fast on real data, and ready for
the P2 scale-out work.
