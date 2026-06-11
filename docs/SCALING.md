# Scaling to ~800 concurrent CBT students

CBT load is bursty writes (answer autosave, heartbeats, login events). The phone
pilot and normal day-to-day use are fine as-is; this is the checklist for a large
simultaneous exam.

## Done

- **DB indexes** on the hot CBT foreign keys: `cbt_answers.attempt_id` (autosave
  lookup), `cbt_attempts.exam_id/student_id`, `cbt_device_sessions.exam_id`,
  `cbt_login_events(exam_id, created_at)`, `cbt_violations.attempt_id`.
- **Connection pool** defaults raised (10 + 20 overflow), env-tunable.

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

## Strongly recommended (throughput / worker starvation)

6. **Batch the write-heavy CBT paths** (currently one DB commit each):
   - answer autosave (`cbt.py` `POST /exam/<id>/answer`) — accumulate a few
     answers client-side per POST;
   - heartbeat `ping` — send every 60–90s, not every 30s;
   - login/start events at synchronized exam start.
7. **Paginate / cache the live monitor** (`cbt.py monitor_data`) — it currently
   loads all attempts + login events + device sessions into one JSON per refresh.
8. **Move blocking work off the request thread** — PDF report generation, SMS/
   email sending, large Excel exports tie up a worker for hundreds of ms to 20s.
   Queue them (RQ/Celery) and return immediately.

Items 6–8 are app changes that need their own pass + the load test in #5 to
validate; they're deliberately not done blind.
