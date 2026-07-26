# CBT Load Testing

Validate the app under concurrent exam load **before** a real exam day. Run this
against a **staging** copy on the actual VPS — never production, and not your laptop
(a laptop can't represent the server).

## 1. Seed a runnable exam (on staging)

```bash
N=800 M=50 python loadtest/seed_loadtest.py
```

Creates 800 students (enrolled in a `LOADTEST` class, portal password `pass123`),
one published exam for today with 50 questions and an access password, and writes
`loadtest/students.csv`. It prints the `EXAM_ID` and `ACCESS_PASSWORD`.

## 2. Run locust

```bash
pip install locust
EXAM_ID=<id> ACCESS_PASSWORD=<pw> locust -f loadtest/locustfile.py --host https://<staging-url>
```

Open http://localhost:8089, set the user count (e.g. 800) and a spawn rate
(e.g. 40/s), and start. Each simulated student logs in, starts the exam, then
loops: batched answer autosave, heartbeat, and occasional submit.

## 3. What to watch

- **Failure %** — should stay ~0. 5xx/timeout spikes mean you've hit a limit.
- **Response times (p95)** — answer/ping should stay well under ~1s.
- **On the server**: Postgres connections vs `max_connections`, CPU, and gunicorn
  worker saturation. If connections max out, raise `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`
  and Postgres `max_connections` (see `docs/SCALING.md`).

Ramp up (200 → 400 → 800) and find where it breaks; that's your real headroom.

---

# Mock-JAMB sitting load test

The CBT harness above targets the CBT module. For the **Mock-JAMB** online
sitting (the 4-subjects-in-one paper drawn from the shared bank), use the
dedicated harness:

```bash
# 1. seed staging: N students + a bank + one published mock for today
N=1000 BANK=600 python loadtest/seed_mock_jamb.py       # prints EXAM_ID

# 2. run locust against the real VPS
EXAM_ID=<id> locust -f loadtest/locustfile_mock_jamb.py --host https://<staging-url>
```

Each simulated student logs in, opens the sitting (which draws + caches their
paper), then loops batched autosave + occasional reload/submit. Watch failure %
and p95 for `open`, `save-batch`, and `reload`.

## Quick local sanity benchmark (no VPS)

`bench_mock_jamb.py` times the hardened server-side hot paths on a throwaway
SQLite DB — useful to confirm the paper draw is indexed and the cache is working
before booking VPS time:

```bash
N=500 BANK=500 python loadtest/bench_mock_jamb.py
```

It reports cold-draw vs cached-rebuild vs no-cache cost, the SQLite query plan
(should show the `ix_mock_jamb_questions_subject_pool` index), and full HTTP
page-render timings. NOTE: SQLite serialises writes, so its write numbers are
pessimistic vs Postgres — use the locust run on the VPS for the true ceiling.

## One-command headless run (CI / pre-exam gate)

`run_mock_jamb.sh` seeds (unless `EXAM_ID` is given), runs locust headless for a
fixed user count + duration, writes CSVs to `loadtest/results/`, prints a
summary, and **exits non-zero if the failure ratio exceeds `THRESHOLD`** — so it
can gate CI or a pre-exam smoke check:

```bash
HOST=https://staging.example.com ./loadtest/run_mock_jamb.sh
HOST=... USERS=1000 SPAWN=40 RUN_TIME=5m ./loadtest/run_mock_jamb.sh
HOST=... EXAM_ID=7 USERS=500 RUN_TIME=3m THRESHOLD=0.02 ./loadtest/run_mock_jamb.sh
```

Env: `HOST` (required, staging only), `USERS` (1000), `SPAWN` (40/s),
`RUN_TIME` (5m), `THRESHOLD` (0.01), `EXAM_ID` (skip seeding), `N`/`BANK` (seed
sizes). Results land in `loadtest/results/mockjamb-<timestamp>_stats.csv`.
