# Scaling to ~800 concurrent CBT students

CBT load is bursty writes (answer autosave, heartbeats, login events). The phone
pilot and normal day-to-day use are fine as-is; this is the checklist for a large
simultaneous exam.

## Done

- **DB indexes** on the hot CBT foreign keys: `cbt_answers.attempt_id` (autosave
  lookup), `cbt_attempts.exam_id/student_id`, `cbt_device_sessions.exam_id`,
  `cbt_login_events(exam_id, created_at)`, `cbt_violations.attempt_id`.
- **Connection pool** defaults raised (10 + 20 overflow), env-tunable.
- **Batched answer autosave** — the exam page queues changes and flushes to
  `/exam/<id>/answers` every ~3s (and via `sendBeacon` when hidden) in one commit,
  instead of a DB write per click. The final submit still posts every answer.
- **Coalesced heartbeats** — `ping()` only writes `last_seen` when it's >25s
  stale; client pings every 30s.
- **Bounded monitor query** — the invigilator monitor no longer loads the whole
  login-event history each refresh (this exam + recent logins, capped).
- **Shared rate limiter** — now DB-backed (`rate_limit_hits`), so the limit holds
  across all gunicorn workers instead of being per-process/bypassable.
- **Background SMS** — "Send now" dispatches the campaign in a background thread
  and returns immediately, instead of blocking a worker for ~20s per recipient.
- **Load-test harness** — `loadtest/` (locust + seeder). See `loadtest/README.md`.

## Must do before a real 800-student exam

1. **PostgreSQL, not SQLite.** SQLite serializes writes — it will not survive
   concurrent autosave. Set `DATABASE_URL=postgresql+psycopg://...`.
2. **Raise the pool to match load** and Postgres `max_connections`:
   `DB_POOL_SIZE=30 DB_MAX_OVERFLOW=50`, and Postgres `max_connections` ≥
   (pool+overflow) × number of gunicorn workers + headroom.
3. **Don't run background jobs in every worker.** With >1 gunicorn worker, set
   `RUN_INPROCESS_JOBS=0` and run `scripts/run_jobs.py` as one separate process,
   or the scheduled-SMS/daily-backup jobs fire N times.
4. **Make rate limiting shared.** The in-memory `RateLimiter` is per-process, so
   with multiple workers it's bypassable. Back it with Postgres or Redis.
5. **Load-test first.** Drive the CBT endpoints (login → start → answer autosave
   → heartbeat → submit) with a tool like `locust`/`k6` at target concurrency on
   the actual VPS. The first real exam must not be the first stress test.

## Remaining (lower impact)

- **PDF report / large Excel export generation** is still synchronous (a few
  hundred ms each). Fine at normal load; if invigilators bulk-download during an
  exam, move these to a background queue (RQ/Celery) too. SMS — the worst
  offender (20s/recipient) — is already backgrounded.
- **Login/exam-start event writes** at a synchronized start are still one insert
  each (cheap and indexed); batch only if the load test shows it's a hotspot.
- For multiple workers, run the scheduled-jobs process separately
  (`RUN_INPROCESS_JOBS=0` + `scripts/run_jobs.py`) — see item 3 above.

Validate everything with the load test (`loadtest/`) on the real VPS before the
first big exam.
