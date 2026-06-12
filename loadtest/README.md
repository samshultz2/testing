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
