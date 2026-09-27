# Running Mock JAMB at scale

How the online Mock JAMB sitting is built to carry a whole cohort — 800-1,500
candidates sitting one mock at once — mirroring the same proven pattern as
CBT (see `docs/CBT_SCALE.md`), and how to turn on its optional async-grading
tier.

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

## Turning on the async-grading tier

```ini
# .env (staging/production)
DATABASE_URL=postgresql+psycopg://…      # always, for real concurrency
WEB_CONCURRENCY=4                         # web workers = ~2–4× vCPU
RUN_INPROCESS_JOBS=0                       # split jobs off the web tier
REDIS_URL=redis://127.0.0.1:6379/0         # required for the queue backend
MOCKJAMB_ASYNC_GRADING=1                   # queue grading at the deadline
```

Same topology as CBT's tier (`docs/CBT_SCALE.md`) — run the web tier and the
dedicated jobs worker side by side (`docs/DEPLOYMENT.md` §4 / `docs/DEPLOY_CONTABO.md`
Phase 6-7). `CBT_ASYNC_GRADING` and `MOCKJAMB_ASYNC_GRADING` are independent
flags (one per feature) sharing the same Redis-backed queue (`utils/jobqueue.py`).

## Hardware sizing (4 vCPU / 8GB RAM / 100GB storage)

Already validated for a *larger* cohort (~1,800) on this exact box size —
see `docs/DEPLOY_CONTABO.md` and `docs/PRODUCTION_AUDIT.md`. No changes needed
for an 800-1,500-candidate Mock JAMB beyond what's already documented there:

- **Gunicorn**: `WEB_CONCURRENCY=4` (gthread) × `GUNICORN_THREADS=4`.
- **Postgres**: `max_connections=200`, `shared_buffers=2GB`,
  `effective_cache_size=5GB`, `work_mem=16MB`, `maintenance_work_mem=256MB`.
- **PgBouncer**: optional at this scale (a single tenant DB) — skip it, point
  straight at `:5432`, unless you're also running several other large tenants
  concurrently.
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
