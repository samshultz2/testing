# EduSyncra — Production-Readiness & Performance Audit

Audit for the move to a dedicated Contabo VPS (4 vCPU / 8 GB / 100 GB SSD /
200 Mbps, Ubuntu). Scope: performance, scalability, concurrency, DB efficiency,
CBT bottlenecks, security, tenant isolation, backups, deployment.

> **Stack correction.** The application is **Flask + SQLAlchemy + gunicorn
> (gthread)**, Jinja + React islands (esbuild), PostgreSQL in production, with an
> optional Redis cache/queue. It is **not** Django/Waitress (waitress is only a
> fallback WSGI server for the Termux/phone deployment). Every finding below is
> grounded in the actual code, cited by file.

## Method

Static code inspection of the request paths that matter at scale (CBT + Mock-JAMB
portals, admin monitor, dashboards), the data layer (`models/`, the central index
registry, per-tenant engine routing), the background-job loop, config, and the
deploy assets. Load *harness* built and reviewed; a real 5,000-user run must be
executed on staging (this repo ships that harness in `loadtest/`).

---

## A. Current architecture

- **Web tier:** gunicorn `gthread`, `WEB_CONCURRENCY` workers × `GUNICORN_THREADS`
  (default 4). `max_requests=1000`+jitter recycles workers to bound memory.
  `preload_app=False` (the in-process job thread must survive fork).
- **Multi-tenancy:** *database per school*. `utils/tenant_runtime.route_tenant`
  resolves the subdomain → `Tenant` → a **per-tenant SQLAlchemy engine cached per
  worker** (`_engines`), binds `db.session` for the request, and stamps the
  session cookie to the tenant. Branches live **inside** one school DB (a
  `branch_id` column), so all 6 branches of a school share one database.
- **Data layer:** SQLAlchemy models; a **central performance-index registry**
  (`models/__init__:_INDEXES`) applied with `CREATE INDEX CONCURRENTLY` on
  Postgres; a self-heal (`finance_ledger.ensure_tables`) that adds
  post-baseline tables/columns/indexes to pre-existing tenant DBs on first use.
- **CBT / Mock-JAMB:** server-rendered exam pages; **batched autosave** +
  on-device `localStorage` + `sendBeacon`; **coalesced heartbeat**; per-attempt
  **cached paper draw** (Mock-JAMB); optional **async grading** + **async
  analytics** via the Redis queue; answer-key cache.
- **Background jobs:** an advisory-locked in-process loop (or a dedicated
  `scripts/run_jobs.py` process when `RUN_INPROCESS_JOBS=0`) runs the daily tick
  (backups, reminders, analytics refresh) once/day via DB-shared markers, and
  drains the optional Redis job queue.
- **Optional Redis:** `utils/cache.py` (cache + transient state) and
  `utils/jobqueue.py` (queue) — active only when `REDIS_URL` is set, with an
  in-process fallback otherwise.
- **Backups:** daily `pg_dump` + media tar, **encrypted at rest**, retention-
  pruned, **shipped offsite** (dir/rclone/command), with `verify_backup` that
  restores into a scratch DB.
- **Media:** student/staff photos stored in-DB as JPEG **re-compressed to
  ≤600 KB**; logos at a fixed path; website media pluggable (db/local/s3); comm
  attachments are loose files with an **orphan sweep**.
- **Monitoring:** `/platform` live metrics (CPU/RAM/swap/disk/disk-IO, PG
  connections, Redis memory + queue depth, request p95, concurrent users,
  background-job duration).
- **Security:** fail-closed production secrets (`security_errors`), secure
  cookies + HSTS + `SameSite=Strict` in prod, opt-in CSP, global + login rate
  limiting, field-level encryption at rest, CSRF, branch scoping + tenant
  isolation, HTTPS forcing.

## B. Current strengths (leave unchanged)

- Database-per-tenant gives **hard data isolation** — the strongest possible
  tenant boundary; no cross-tenant `WHERE school_id=` mistakes are even possible
  at the row level.
- The index registry is **comprehensive and uses `CONCURRENTLY`** (no deploy
  write-lock). CBT/Mock-JAMB hot FKs are covered.
- CBT autosave is **already batched + durable** (device localStorage + beacon +
  reconnect resync) — not a write-per-click.
- Mock-JAMB paper draw is **cached per attempt** and index-backed — the 1,800-
  candidate path is already optimised.
- `monitor_data` (polled *during* a sitting) is **batched with `contains_eager`**
  — not N+1.
- Backups are **encrypted, offsite-capable, and verifiable** — well beyond VPS
  snapshots.
- Config is **fail-closed** and secure-by-default in production.

## Status legend

Much of the classic P0/P1 hardening was implemented across this engagement and is
already merged. Items are tagged **[DONE]** (shipped) or **[OPEN]** (recommended,
not yet done — mostly ops/config the app can't self-apply).

---

## C–R. Findings, ranked

### P0 — must fix before deployment

| # | Finding | Files | Status |
|---|---|---|---|
| P0-1 | **Redis cache keys not tenant-namespaced.** With one Redis shared by all schools, `cbt:key:<exam_id>` etc. collide across tenants → cross-tenant **mis-grading** and analytics/heartbeat leakage. Fixed by namespacing every CBT cache key per tenant (`cbt:<sub>:…`). | `routes/cbt.py` | **[DONE]** |
| P0-2 | **Queued jobs had no tenant binding.** A queued grade/analytics job would run against whatever DB the worker had bound. `enqueue` now captures the school (sub + DB URL); `drain` rebinds `g.tenant_engine` + cache namespace before running the handler. | `utils/jobqueue.py` | **[DONE]** |
| P0-3 | **Secrets must be set for production.** `security_errors()` already blocks boot without `SECRET_KEY` + `FIELD_ENCRYPTION_KEY` under `ProductionConfig`. Action: set them (+ `APP_ENV=production`) in `.env`. | `config.py` | **[OPEN — ops]** |
| P0-4 | **Postgres `max_connections` must be sized for the pool.** Each worker holds up to `DB_POOL_SIZE+DB_MAX_OVERFLOW` (10+20) **per active tenant DB**. Set `max_connections` and/or front with PgBouncer (see K). | PG config | **[OPEN — ops]** |

### P1 — strongly recommended before deployment

| # | Finding | Files | Status |
|---|---|---|---|
| P1-1 | CBT hot-path index `cbt_questions.exam_id` was missing. | `models/__init__` | **[DONE]** |
| P1-2 | Answer-key re-query on every autosave batch → cached (auto-invalidated on question change). | `routes/cbt.py`, `utils/cache.py` | **[DONE]** |
| P1-3 | Heavy psychometric analytics could run on a user request → moved async + cached. | `routes/cbt.py`, `utils/jobqueue.py` | **[DONE]** |
| P1-4 | Deadline submission spike graded synchronously → optional async grading (`CBT_ASYNC_GRADING`) with self-healing result state. | `routes/cbt.py` | **[DONE]** |
| P1-5 | Static exam bundles not long-cached → immutable 1-year `Cache-Control` for versioned assets. | `app.py` | **[DONE]** |
| P1-6 | Redis memory + queue depth not observable → added to `/platform`. | `utils/sys_metrics.py`, `templates/platform/health.html` | **[DONE]** |
| P1-7 | Backups: DB + media, encrypted, offsite, verifiable. | `utils/backup.py`, `utils/offsite.py` | **[DONE]** |
| P1-8 | Web vs. background-worker split (`RUN_INPROCESS_JOBS=0` + `edusyncra-jobs.service`). | `app.py`, `scripts/run_jobs.py`, `deploy/` | **[DONE]** |
| P1-9 | **Production nginx** (TLS, gzip, immutable static, edge security headers, login/general rate-limit zones, keepalive, 16 MB body cap, 120 s long-op timeout). | `deploy/nginx-vps.conf` | **[DONE]** |
| P1-10 | **PgBouncer** in transaction-pooling mode in front of Postgres, so N workers × M tenant pools don't exhaust `max_connections`. | ops | **[OPEN — ops]** |
| P1-11 | **Redis hardening**: `maxmemory` + `allkeys-lru` eviction, `bind 127.0.0.1`, `requirepass`, never public. | ops | **[OPEN — ops]** |
| P1-12 | **Log rotation + disk thresholds** for `instance/errors.jsonl`, gunicorn/nginx logs, `instance/backups`. | ops (`logrotate`) | **[OPEN — ops]** |

### P2 — recommended after deployment

- Enable `CONTENT_SECURITY_POLICY` once verified against the templates (config
  already supports it; off by default to avoid breaking inline scripts). **[OPEN]**
- Move the very largest report/PDF exports (whole-school broadsheets) to the job
  queue if they approach the 120 s worker timeout under load. Most are fine
  synchronous. **[OPEN]**
- Add `pg_stat_statements` and periodic `EXPLAIN` review of the dashboard
  aggregate queries under production data volume. **[OPEN]**

### P3 — future scaling (3,000–10,000+)

- Horizontal web scale: run 2–3 app VPSes behind the nginx/load balancer. The app
  is **already scale-ready** — cookie sessions (no server session state), the
  Redis cache/queue for shared transient state, advisory-locked idempotent jobs,
  and in-DB/on-device answer durability. Move the answer-key/heartbeat state fully
  onto shared Redis (already the case when `REDIS_URL` is set). **[Ready]**
- Dedicated Postgres box (or managed PG) once the DB is the bottleneck. **[Future]**
- Read replicas for analytics-heavy reporting. **[Future]**

---

## I. Redis verdict — **INTRODUCE (optional, namespaced)**

Justified by three concrete needs at CBT scale: (1) offload the answer-key read
and heartbeat write-coalescing from Postgres; (2) a cross-worker job queue for
async grading/analytics; (3) shared transient state for horizontal scale. It is
implemented as an **optional** layer (`REDIS_URL`) with an in-process fallback, so
a single box runs fine without it. **Cache vs. durable data is cleanly separated:
Redis holds only recomputable cache/transient state — candidate answers live in
Postgres + the device's localStorage, never Redis-only.** Redis failure degrades
to DB/inline paths; it never loses answers.

## J. Waitress verdict — **KEEP gunicorn (gthread)**

gunicorn `gthread` is the production server; waitress remains only for the
phone/Termux fallback. For 4 vCPU: `WEB_CONCURRENCY=4`, `GUNICORN_THREADS=4`
(≈16 concurrent slots — CBT requests are short and I/O-bound on Postgres, so
threads are the right multiplier; more workers would multiply memory + DB pools
without helping a GIL-bound CPU). Keep `timeout=120` for OCR/PDF.

## K. Nginx verdict — **USE (`deploy/nginx-vps.conf`)**

Terminate TLS, serve `/static/` from disk (never touches gunicorn), gzip JSON/HTML,
long-cache hashed bundles, apply edge rate-limit zones, cap body at 16 MB. For the
database-per-tenant connection multiplication, add **PgBouncer** (transaction
pooling) so Postgres sees a bounded connection count regardless of workers × tenants.

---

## S. Expected VPS capacity (evidence-based)

Assumptions from the code: with the optimised client, a candidate generates
**~2 requests / 30 s** steady state (one batched autosave per change + one
coalesced heartbeat/30 s), each a short indexed DB op. The web tier offers
≈`workers×threads` = **16 concurrent slots**; at ~30 ms/request that is a
**theoretical ceiling of a few hundred short req/s**, lower under GIL + PG
contention. Bursts (mass start / mass reconnect) are the real stressor, not steady
state.

| Scenario | Steady req/s (est.) | Single 4vCPU/8GB VPS | Bottleneck / note |
|---|---|---|---|
| Normal school management (10 schools) | < 5 | **PASS** | Trivial load; admin CRUD. |
| 100 concurrent CBT | ~7 | **PASS** | Comfortable. |
| 500 concurrent CBT | ~35 | **PASS** | Comfortable. |
| 1,000 concurrent CBT | ~70 | **PASS** | Fine with `WEB_CONCURRENCY=4` + tuned PG. |
| **1,800 JAMB Mock** (6 branches, one school DB) | ~120 | **PASS (target)** | One tenant DB; cached paper draw + subject-pool index. Bursty start/submit within capacity. **Enable Redis + PgBouncer; validate on staging.** |
| 3,000 concurrent CBT | ~200 | **MARGINAL** | Feasible with Redis, async grading, PgBouncer, `WEB_CONCURRENCY=4`; mass-reconnect bursts are the risk. Validate; be ready to add a second app VPS. |
| 5,000 concurrent CBT | ~335 | **LIKELY EXCEEDS one box for bursts** | Steady state ~at the edge; simultaneous start/reconnect of 5,000 exceeds 16 slots. Needs **horizontal web scale (2–3 app VPSes) + PgBouncer + Redis**, or staggered start windows. The app is scale-ready for this; the single 4-vCPU box is not. |

These are analytical estimates from code + request-rate math. **They must be
confirmed by the `loadtest/` harness on staging** before relying on the higher
tiers — do not treat the numbers as measured.

## T. Load-test plan

Ship-ready in `loadtest/`: `seed_loadtest.py` (N candidates), `locustfile.py`
(login → start → questions → navigate → autosave → heartbeat → reconnect →
submit, with per-candidate `X-Forwarded-For` and an rps/p95/p99/submit-latency
summary), and the Mock-JAMB variants (`locustfile_mock_jamb.py`,
`run_mock_jamb.sh` with a pass/fail failure-ratio gate). Run 100 → 500 → 1,000 →
1,800 → 3,000 → 5,000 against staging with `TRUST_PROXY=1`, capturing
`/platform/health.json` at peak. Measure rps, p50/p95/p99, error/dropped rate,
submit latency, CPU/RAM/swap, PG connections, Redis memory, disk I/O, job duration.

## U. Recommended architecture (initial, inexpensive)

One Contabo VPS: **nginx** (TLS/static/gzip/rate-limit) → **gunicorn** (4 workers
× 4 threads) → **PostgreSQL** (tuned `max_connections`, `shared_buffers≈2GB`,
`effective_cache_size≈6GB`) **behind PgBouncer** → **Redis** (localhost,
`maxmemory` + LRU, password) → **dedicated jobs worker** (`edusyncra-jobs.service`,
`RUN_INPROCESS_JOBS=0`). Backups encrypted + shipped offsite; `/platform` + host
metrics for monitoring; `logrotate` + disk alerts. This carries normal load,
100–1,800 CBT comfortably, and is **scale-ready**: adding app VPSes later needs no
code change.

---

## Deployment verdict

**DEPLOY** to the single VPS for normal operations and up to **~1,800 concurrent
JAMB-Mock candidates**, conditional on the P0-OPEN ops items (production `.env`
secrets, Postgres `max_connections`/PgBouncer, Redis hardening) and a **staging
load-test run** confirming the 1,800 tier. For **3,000–5,000 concurrent CBT**, the
application is ready but a single 4-vCPU/8-GB box is not — plan a second app VPS
(and PgBouncer/Redis already in place) before scheduling exams at that size.
