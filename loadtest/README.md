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
loops: batched answer autosave, heartbeat, reconnect (a re-fetch of the take page,
as after a network blip), and occasional submit.

### A full cohort (5,000 candidates)

```bash
N=5000 M=40 python loadtest/seed_loadtest.py            # prints EXAM_ID
mkdir -p loadtest/results
EXAM_ID=<id> ACCESS_PASSWORD=<pw> locust -f loadtest/locustfile.py \
    --host https://<staging> --users 5000 --spawn-rate 100 --run-time 45m \
    --headless --csv=loadtest/results/cbt --html=loadtest/results/cbt.html
```

The target should run with `TRUST_PROXY=1` (so each virtual user's unique
`X-Forwarded-For` sidesteps the per-IP login throttle) and on Postgres with a real
multi-worker web tier (`WEB_CONCURRENCY`, `RUN_INPROCESS_JOBS=0` + the jobs
worker). To exercise the Redis/queue tier, set `REDIS_URL` (and optionally
`CBT_ASYNC_GRADING=1`); see `docs/CBT_SCALE.md`. Past one load box's CPU, run
Locust [distributed](https://docs.locust.io/en/stable/running-distributed.html).

## 3. What to watch

Locust reports client-side latency/throughput/errors (UI, `--csv` files, and the
end-of-run summary the harness prints). The server's own `/platform` page reports
host + datastore metrics live (JSON at `/platform/health.json`).

| Metric | Where |
|---|---|
| requests / sec | Locust total RPS (UI, `*_stats.csv`, summary) |
| p95 / p99 response time | Locust percentiles (`*_stats.csv`, summary) |
| submission latency | Locust `/exam/[id]/submit` row (p95/p99 printed in the summary) |
| error rate | Locust failure % (`*_failures.csv`) |
| dropped requests | Locust failures (timeouts/5xx) + gunicorn/nginx logs (worker timeouts, 502/504) |
| CPU / RAM / swap | `/platform` System tiles |
| disk usage / disk I/O | `/platform` Disk + Disk I/O tiles |
| PostgreSQL connections | `/platform` PostgreSQL tile (`pg_stat_activity`) |
| Redis memory / queue depth | `/platform` Redis tiles (when `REDIS_URL` set) |
| concurrent users | `/platform` Concurrent-users tile |
| background-job duration | `/platform` Background jobs panel |
| PostgreSQL CPU | host tool on the DB box (`top`/`pg_top`) or managed-DB dashboard |
| network throughput | host tool (`nload`/`iftop`) or cloud NIC metrics; Locust also reports bytes |

Capture a peak snapshot: `curl -s "$HOST/platform/health.json" > loadtest/results/platform-peak.json`.

- **Failure %** should stay ~0; 5xx/timeout spikes mean you've hit a limit.
- **Response/submit p95** should stay well under ~1–2 s.
- **Levers:** raise `WEB_CONCURRENCY` (until CPU-bound); raise `DB_POOL_SIZE`/
  `DB_MAX_OVERFLOW` and Postgres `max_connections` together; set `REDIS_URL`
  (offloads answer-key reads + heartbeat writes); set `CBT_ASYNC_GRADING=1` so the
  deadline submit spike drains through the worker (see `docs/SCALING.md`,
  `docs/CBT_SCALE.md`).

Ramp up (e.g. 800 → 2,000 → 5,000) and find where it breaks; that's your real headroom.

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

### Prerequisites (the script does NOT start the app)

- The app must already be **running and reachable at `HOST`** (your normal
  gunicorn service) — the script drives it over HTTP and preflight-checks
  `HOST/healthz`, aborting with a clear error if it can't connect.
- **Run the script on the staging box** (or anywhere with the app's env +
  DB access): the seed step imports the app and writes straight to the DB, so it
  needs the same `DATABASE_URL`/`SECRET_KEY`/deps the app uses.
- `pip install locust`.
- **Single-school staging is simplest.** In multi-tenant mode the seed writes to
  the DB the app's default config points at, while locust hits the tenant that
  `HOST`'s subdomain resolves to — they must be the same DB. Use a single-school
  staging copy, or seed the specific tenant DB explicitly.
- Staging only, in a quiet window (it generates heavy load).

## Ephemeral tenant mode (create a throwaway subdomain, then destroy it)

Instead of a fixed HOST, the runner can spin up a **real throwaway tenant** (its
own subdomain + its own database), seed it, test it, and **destroy it afterwards
— even on failure or ctrl-C**. This exercises the true multi-tenant routing path.

```bash
TENANT=loadtest ./loadtest/run_mock_jamb.sh
TENANT=loadtest USERS=1000 SPAWN=40 RUN_TIME=5m ./loadtest/run_mock_jamb.sh
TENANT=loadtest KEEP_TENANT=1 ./loadtest/run_mock_jamb.sh    # keep it for inspection
```

It maps to `https://<TENANT>.<base-domain>` and requires: control-plane DB access
(run it on the server) and wildcard DNS + TLS for `*.<base-domain>` — already how
your tenant subdomains work, so no new DNS is needed.

**Safety guard:** `TENANT` must start with `LOADTEST_TENANT_PREFIX` (default
`loadtest`). `tenant_ctl.py` refuses to provision-over or destroy any subdomain
that doesn't, so it can never touch a real school. You can also drive the
lifecycle by hand:

```bash
N=1000 python loadtest/tenant_ctl.py create  loadtest   # prints TENANT_URL + EXAM_ID
python loadtest/tenant_ctl.py destroy loadtest          # drop DB + registry row
```

## Realistic model + phone-hosted split

The load model is a real cohort, not a stampede: students are **seated gradually**
over `SEAT_WINDOW`, answer for `EXAM_MINUTES`, then each **submits once** near its
deadline. You give real-world inputs; the runner derives locust's spawn-rate
(`USERS/SEAT_WINDOW`) and duration (`SEAT_WINDOW + EXAM_MINUTES + tail`).

```bash
# 100 students seated over 2 min, 10-min exam (defaults)
TENANT=loadtest ./loadtest/run_mock_jamb.sh
# 100 students seated over 3 min, 20-min exam
TENANT=loadtest USERS=100 SEAT_WINDOW=180 EXAM_MINUTES=20 ./loadtest/run_mock_jamb.sh
```

**If the app is hosted on a phone (Termux),** never run the generator on the phone
— it competes for RAM and Android kills the server. Split it: seed on the phone,
generate load from a laptop.

```bash
# 1. PHONE — create + seed the throwaway tenant (writes loadtest/students.csv)
N=100 python loadtest/tenant_ctl.py create loadtest      # note TENANT_URL + EXAM_ID

# 2. copy loadtest/students.csv from the phone to the laptop (same path)

# 3. LAPTOP — drive the realistic load (mode B: HOST + EXAM_ID, no control-plane)
HOST=https://loadtest.edusyncra.site EXAM_ID=<id> \
  USERS=100 SEAT_WINDOW=120 EXAM_MINUTES=10 ./loadtest/run_mock_jamb.sh

# 4. PHONE — tear the tenant down
python loadtest/tenant_ctl.py destroy loadtest
```

### PHONE=1 shortcut (server + generator on one phone)

If you have no separate machine and must run everything in Termux:

```bash
PHONE=1 TENANT=loadtest ./loadtest/run_mock_jamb.sh          # ~15 students, short exam
PHONE=1 TENANT=loadtest USERS=30 ./loadtest/run_mock_jamb.sh # push it up
```

`PHONE=1` sets small conservative defaults (USERS=15, SEAT_WINDOW=90,
EXAM_MINUTES=3, BANK=300). **Read on-device results as a floor, not the true
capacity:** the generator and server fight for the same CPU/RAM, so latencies are
inflated well above what real students (on their own devices) would see. If a
number looks bad here, the server alone is likely faster — confirm from a second
machine when you can.
