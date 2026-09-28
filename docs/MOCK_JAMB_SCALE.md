# Running Mock JAMB at scale

How the online Mock JAMB sitting is built to carry a whole cohort sitting one
mock at once, mirroring the same proven pattern as CBT (see
`docs/CBT_SCALE.md`), and how to turn on its optional async-grading tier.
**800-1,500 was the original design target; a real staging load test found a
single 4 vCPU/8GB box is comfortable to ~500 and sluggish by 800 — see
"Hardware sizing" below for the measured numbers and what actually moves the
ceiling (more vCPUs), before assuming this box size covers the higher end.**

## The properties

| Requirement | How it's met |
|---|---|
| **Landing page doesn't scale with exam count** | `portal_list()` batches the student's class placement, eligible-class lookup, question-pool discovery and attempt lookup into a handful of queries total instead of once per published mock (`routes/mock_jamb.py::portal_list`). |
| **Paper drawn once, not on every load** | A candidate's drawn paper is cached as JSON on the attempt (`MockJAMBAttempt.paper`); every reload/resume rebuilds it from cheap primary-key lookups instead of re-scanning the bank (`utils/mock_jamb_sitting.py::subject_items`/`_rebuild_from_paper`). |
| **Subject discovery doesn't re-scan on reload/submit** | `subject_ids_for_attempt()` reads the candidate's subject list straight from the cached paper instead of re-running `candidate_subject_ids()`'s exam-wide, student-independent pool scan on every reload *and* at every grade — the two moments a mass simultaneous sitting hits hardest. |
| **Answers batched** | The client debounces changes (800ms) and flushes to `POST /exam/mock-jamb/<id>/save-batch` in one commit, with a 5s safety-net retry, a localStorage mirror, and a final `sendBeacon` flush on submit (`templates/mock_jamb/portal_sit.html`). |
| **Eligibility cached for the sitting** | `_portal_guard()` caches the (2-query) eligibility check in the student's session after the first check instead of re-running it on every autosave. |
| **No 500 on a start-button race** | Two near-simultaneous requests creating the same attempt (a double click, or a client retry over a flaky connection) fall back to the winning row instead of crashing on the unique constraint. |
| **Optional async (queued) grading** | `MOCKJAMB_ASYNC_GRADING=1` + Redis + the jobs worker: `submit()` marks the attempt `Submitting` and queues `mockjamb_grade` instead of grading on the web request; the done page shows a brief "grading…" state and self-heals (grades inline) if the worker hasn't finalised within 60s. The admin-triggered safety net (`auto_submit_expired()`, run on `view_exam`/`items` page loads) queues the same way, so one admin's page load never synchronously grades a whole cohort's just-expired attempts. Off by default — grades inline immediately, unchanged. |
| **PostgreSQL properly indexed** | `mock_jamb_questions`/`mock_jamb_passages` are indexed on `(subject_id, mock_exam_id)` — the pool-draw filter — and `mock_jamb_attempts`/`mock_jamb_answers` are covered by their unique constraints (`mock_exam_id, student_id` and `attempt_id, question_id` respectively, both leftmost-covering the hot lookup). |
| **Edge rate limiting sized for a shared-IP cohort** | `/exam/` traffic (both CBT and Mock JAMB) gets its own, much higher nginx `limit_req` zone (`examtraffic`, 200r/s) separate from the general app zone (30r/s) — a whole cohort's autosave traffic sharing one school NAT/proxy would otherwise false-positive-throttle against the general ceiling (see `deploy/nginx-vps.conf`). |
| **Login doesn't collapse under a simultaneous login burst** | Portal password checks use scrypt (`Student.set_portal_password`/`check_portal_password`) — deliberately CPU/memory-hard, ~100ms of real CPU per check at Werkzeug's default cost. A mass simultaneous login (hundreds of students within the same short window) queues behind however many CPU cores the box has, and everything else sharing those same gunicorn workers (autosave, page loads) queues behind *that*. Load-tested on a 4 vCPU box: 500 concurrent logins pushed median response times to 5-36s. Fixed by lowering the cost for newly-set portal passwords (`Student._PORTAL_PW_METHOD = 'scrypt:8192:8:1'`, ~4x cheaper per check) — safe because online guessing is separately throttled by the DB-backed login rate limiter (the primary defense), and portal PINs carry enough entropy (~40-bit generated) that a quarter of the default offline-attack cost is still substantial. Old hashes keep verifying at their original (higher) cost — Werkzeug reads the cost from the stored hash string itself. |

## Turning on the async-grading tier

```ini
# .env (staging/production)
DATABASE_URL=postgresql+psycopg://…      # always, for real concurrency
WEB_CONCURRENCY=4                         # web workers = ~1× vCPU (gthread; NOT 2-4x, see gunicorn.conf.py)
RUN_INPROCESS_JOBS=0                       # split jobs off the web tier
REDIS_URL=redis://127.0.0.1:6379/0         # required for the queue backend
MOCKJAMB_ASYNC_GRADING=1                   # queue grading at the deadline
GUNICORN_MAX_REQUESTS=20000                # raise well above the 1000 default for the sitting's duration —
                                            # otherwise workers recycle every 60-90s under sustained load,
                                            # each recycle briefly cutting capacity (measured, see below)
```

Same topology as CBT's tier (`docs/CBT_SCALE.md`) — run the web tier and the
dedicated jobs worker side by side (`docs/DEPLOYMENT.md` §4 / `docs/DEPLOY_CONTABO.md`
Phase 6-7). `CBT_ASYNC_GRADING` and `MOCKJAMB_ASYNC_GRADING` are independent
flags (one per feature) sharing the same Redis-backed queue (`utils/jobqueue.py`).

## Hardware sizing (4 vCPU / 8GB RAM / 100GB storage) — measured, not estimated

An earlier version of this doc claimed the ~1,800 target was "already
validated" on this box size. That was wrong — it was an *analytical estimate*
in `docs/PRODUCTION_AUDIT.md` that explicitly called for a staging load-test
run to confirm it. That run has now actually happened
(`loadtest/locustfile_mock_jamb.py`, realistic ~10-minute staggered login,
`MOCKJAMB_ASYNC_GRADING=1`, the reduced-cost portal-password hash, and
`GUNICORN_MAX_REQUESTS` disabled to isolate that variable), and the real
numbers are meaningfully worse than the estimate:

| Concurrent students | Aggregate median | p95 | p99 | Failure rate |
|---|---|---|---|---|
| 250 | 0.6s | 7.2s | 12s | 2.3% |
| 500 | 1.4s | 20s | 30s | 3.3-3.6% |
| 800 | 4.1-4.4s | 42-43s | 58-65s | 3.3-3.6% |

**250 is comfortable, 500 is workable, 800 is sluggish but not broken — the
degradation is smooth and monotonic, not a sudden cliff.** 1,800 was not
tested directly but extrapolates well past what's usable for a live exam on
this box size.

**Root cause, confirmed by live monitoring during an 800-user run**: raw CPU,
not the database. `pg_stat_activity` connection count never exceeded 30 (limit
200), active queries stayed under 13 concurrent, and no query ran longer than
1-2 seconds — Postgres had huge headroom throughout. Meanwhile host load
average hit 9-12 on this box's 4 physical cores — 2-3× oversubscribed. Every
layer (gunicorn workers doing password checks, Postgres serving those fast
queries, the jobs worker grading) was fighting over the same 4 cores. Redis,
async grading, and connection-pool tuning don't fix this — they redistribute
load, they don't create CPU capacity. **Vertical scaling (more vCPUs) or
horizontal scaling (more app VPSes / staggered real-world seating) are the
actual levers past ~500-800 concurrent on this box size.**

What's already in place and worth keeping regardless of box size:

- **Gunicorn**: `WEB_CONCURRENCY=4` (gthread, ≈1×cores — NOT 2×cores; see
  `gunicorn.conf.py`) × `GUNICORN_THREADS=4`. For a sustained mass-sitting
  window, also raise `GUNICORN_MAX_REQUESTS` well above its default of 1000
  (e.g. `GUNICORN_MAX_REQUESTS=20000`) — at the default, workers recycle every
  60-90s under this load, and each recycle briefly cuts capacity right when
  you can least afford it. Measured to reduce the failure rate in the same
  load test.
- **Postgres**: `max_connections=200`, `shared_buffers=2GB`,
  `effective_cache_size=5GB`, `work_mem=16MB`, `maintenance_work_mem=256MB`.
  Confirmed not the bottleneck up to 800 concurrent — connection count and
  query latency both had large headroom.
- **PgBouncer**: optional at this scale (a single tenant DB) — the load test
  ran without it and connections were never the constraint. Add it only if a
  future test with more tenants/DBs shows connection pressure.
- **Redis**: `maxmemory 512mb`, `allkeys-lru` — ample headroom.
- **nginx**: `worker_processes auto;` and a `worker_connections` of at least
  4096 in the distro's `nginx.conf` `events{}` block (neither repo nginx
  config sets this — it's a global directive, not per-site).

## Load testing

`loadtest/locustfile_mock_jamb.py` — a dedicated Locust harness that seeds a
throwaway cohort and drives the real endpoints (login → open → batched
autosave → occasional reload → submit near each candidate's personal
deadline, so submits cluster near the end like a real timer expiry). Run it
via `loadtest/run_mock_jamb.sh` before a real exam — see `loadtest/README.md`.
The harness can bypass nginx's per-IP rate limiting (`TENANT_HOST` +
per-request `X-Forwarded-For`) to isolate app/DB capacity from edge-throttling
effects; test the edge zones (`examtraffic`/`general`) separately if you want
to validate the shared-IP-cohort scenario specifically.
