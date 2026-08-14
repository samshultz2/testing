# Running exams at scale (CBT)

How EduSyncra's online-test (CBT) runtime is built to carry a whole cohort —
thousands of candidates sitting one exam at once — and how to turn on the
optional Redis / queue tier and load-test it.

Everything here degrades gracefully: with no Redis and a single web process the
app behaves exactly as before. The scale features switch on by configuration,
never by a rewrite.

## The eight properties

| Requirement | How it's met |
|---|---|
| **Exam frontend is CDN-cached** | Static JS/CSS/font bundles are content-versioned (`bundle_url` → `?v=<mtime>`) and served with `Cache-Control: public, max-age=31536000, immutable` (`app.py:_static_cache_headers`), so a CDN/browser caches them for a year and a rebuild busts them. The exam **HTML** itself is per-candidate (answers, CSRF, timer) and intentionally stays uncached — a CDN passes it through. |
| **Questions loaded efficiently** | An exam's questions are rendered once on `GET /exam/<id>/take` (no per-question round trips). `cbt_questions.exam_id` is indexed (`ix_cbt_question_exam`), so loading a whole exam is an index scan. The correct-option map used to grade autosaves is cached per exam (`_exam_answer_key`), removing a full questions re-query on every autosave batch. |
| **Answers batched** | The client debounces changes and flushes `q_<id>=<opt>` batches to `POST /exam/<id>/answers` (one request/commit for many answers). Answers are also persisted on-device (`localStorage`) and flushed via `navigator.sendBeacon` when the tab hides. |
| **Autosave every 30–60 s** | In addition to the event-driven batch flush, a periodic safety net re-pushes the full on-device answer set every ~45 s (idempotent server-side), reconciling any batch lost to a flaky link even without a new change. |
| **Redis handles transient session/cache state** | `utils/cache.py` — Redis-backed when `REDIS_URL` is set, bounded in-process dict otherwise. Backs the per-exam answer-key cache and the heartbeat coalescing gate (`should_run`), so heartbeats and answer-key reads don't hit Postgres on every request. Cookie sessions already scale horizontally (no server state); Redis carries the *transient* cache/heartbeat state. |
| **PostgreSQL properly indexed** | The exam-runtime FKs are all indexed via the central registry in `models/__init__` (`_INDEXES`), created with `CREATE INDEX CONCURRENTLY` on Postgres so a deploy never write-locks a populated table: attempts(exam_id, student_id), answers(attempt_id), **questions(exam_id)**, violations(attempt_id), login_events(exam_id, student_id), device_sessions(exam_id). |
| **Submissions queued** | `utils/jobqueue.py` — a Redis list queue with an inline fallback. With `CBT_ASYNC_GRADING=1` + Redis + the jobs worker, `POST /exam/<id>/submit` records the answers, marks the attempt *Submitting*, enqueues grading, and returns a lightweight "grading…" page; the worker finalises within seconds. If the worker is unreachable the result page self-heals by grading inline after a short grace, so a candidate is never stuck. Default (flag off / no Redis): graded inline, immediately. |
| **Analytics completely asynchronous** | The heavy psychometric item analysis never runs on a student request. After each submission a best-effort `cbt_analytics` job (dropped when there's no worker, never inline on the student path) recomputes and caches the snapshot; the admin analytics page reads the cache and only computes on a cold miss. |

## Turning on the scale tier

```ini
# .env (staging/production)
DATABASE_URL=postgresql+psycopg://…      # always, for real concurrency
WEB_CONCURRENCY=4                         # web workers = ~2–4× vCPU
RUN_INPROCESS_JOBS=0                       # split jobs off the web tier
REDIS_URL=redis://127.0.0.1:6379/0         # optional cache + queue backend
CBT_ASYNC_GRADING=1                        # optional: queue grading at the deadline
```

Run the web tier and the dedicated jobs worker side by side (see
`docs/DEPLOYMENT.md` §4). The jobs worker drains the queue every ~2 s when Redis
is present, so queued grading and analytics complete promptly; on a single box
the in-process worker drains it once a minute (fine for analytics — async grading
wants the dedicated worker).

Install Redis' client library on the server for the Redis path:

```bash
pip install "redis>=5"
```

The `/platform` monitoring page shows Redis memory + job-queue depth alongside
CPU/RAM/PG connections/latency, so you can watch the whole tier during a sitting.

## Load testing

A full 5,000-candidate Locust harness (login → fetch → navigate → autosave →
heartbeat → submit → reconnect) and its runbook live in **`loadtest/`**. It seeds
a throwaway cohort, drives the real endpoints, and maps every measured figure
(rps, p95/p99, submit latency, error/dropped rate, plus the server-side CPU/RAM/
PG/Redis metrics from `/platform`) — see `loadtest/README.md`.
