#!/usr/bin/env bash
#
# One-command headless Mock-JAMB load test.
#
# Two ways to pick a target (both non-production):
#
#  A) Ephemeral tenant (recommended) — spins up a throwaway subdomain/tenant with
#     its OWN database, seeds it, tests it, and DESTROYS it afterwards (even on
#     failure/ctrl-C). Needs control-plane DB access + wildcard DNS/TLS for the
#     base domain (already how tenant subdomains work).
#
#       TENANT=loadtest ./loadtest/run_mock_jamb.sh
#       TENANT=loadtest USERS=100 SEAT_WINDOW=120 EXAM_MINUTES=10 ./loadtest/run_mock_jamb.sh
#       TENANT=loadtest KEEP_TENANT=1 ./loadtest/run_mock_jamb.sh   # don't tear down
#
#  B) Fixed HOST — you point it at an already-running non-prod app yourself. This
#     is how you drive load from a LAPTOP while the server runs elsewhere (e.g. a
#     phone): seed once with tenant_ctl.py, copy students.csv over, then run this
#     with HOST + EXAM_ID (no control-plane needed, no teardown here).
#
#       HOST=https://loadtest.edusyncra.site EXAM_ID=7 USERS=100 ./loadtest/run_mock_jamb.sh
#
# Realistic model: students are SEATED gradually over SEAT_WINDOW (not all at
# once), answer for EXAM_MINUTES, then each submits once near its deadline. The
# spawn-rate and run duration are DERIVED from those, so you think in real terms
# (how many students, how long to seat them, how long the exam is) — not in locust
# knobs. Override SPAWN / RUN_TIME directly if you must.
#
# Env:
#   TENANT       ephemeral subdomain to create+seed+destroy (mode A). Must start
#                with LOADTEST_TENANT_PREFIX (default "loadtest") — a safety guard.
#   KEEP_TENANT  set to 1 to skip teardown (debug); default tears the tenant down.
#   HOST         base URL of a running non-prod app (mode B; ignored if TENANT set)
#   USERS        number of students             (default 100)
#   SEAT_WINDOW  seconds to seat them all       (default 120) -> sets the spawn rate
#   EXAM_MINUTES per-student exam length        (default 10)  -> sets the duration
#   THRESHOLD    max acceptable failure ratio   (default 0.01 = 1%)
#   EXAM_ID      reuse an existing seeded mock  (mode B only; skips the seed step)
#   N, BANK      seed sizes when seeding        (default N=USERS, BANK=600)
#   SPAWN, RUN_TIME  advanced: override the derived ramp/duration directly
#
# Do NOT 'source' this script. Sourcing applies its `set -e`/`exit` to your
# interactive shell, which closes the terminal on the first exit. Detect a sourced
# invocation and bail out safely (return, not exit) before enabling set -e.
if (return 0 2>/dev/null); then
  echo "Don't source this — run it:  ./loadtest/run_mock_jamb.sh   (or: bash loadtest/run_mock_jamb.sh)" >&2
  return 1 2>/dev/null
fi

set -euo pipefail

cd "$(dirname "$0")/.."                       # repo root

HOST="${HOST:-}"
TENANT="${TENANT:-}"
USERS="${USERS:-100}"
SEAT_WINDOW="${SEAT_WINDOW:-120}"            # seconds to seat the whole cohort
EXAM_MINUTES="${EXAM_MINUTES:-10}"           # per-student exam length
THRESHOLD="${THRESHOLD:-0.01}"
N="${N:-$USERS}"
BANK="${BANK:-600}"

# Derive the realistic ramp + duration from real-world inputs (override by
# exporting SPAWN / RUN_TIME). Spawn rate = students / seating-window; the run
# lasts the seating window + a full exam + a 90s tail so the last submit lands.
SPAWN="${SPAWN:-$(awk "BEGIN{r=$USERS/$SEAT_WINDOW; if(r<0.1)r=0.1; printf \"%.3f\", r}")}"
RUN_TIME="${RUN_TIME:-$(awk "BEGIN{printf \"%ds\", $SEAT_WINDOW + $EXAM_MINUTES*60 + 90}")}"
export EXAM_MINUTES                           # the locustfile reads this

if ! command -v locust >/dev/null 2>&1; then
  echo "ERROR: locust not installed.  pip install locust" >&2
  exit 2
fi

# ---- mode A: create an ephemeral tenant (auto-destroyed on exit) -------------
if [ -n "$TENANT" ]; then
  echo "==> Creating ephemeral tenant \"$TENANT\" ..."
  CREATE_OUT="$(N="$N" BANK="$BANK" python loadtest/tenant_ctl.py create "$TENANT")"
  echo "$CREATE_OUT"
  # tear it down no matter how we exit (success, failure, or ctrl-C)
  if [ "${KEEP_TENANT:-0}" != "1" ]; then
    trap 'echo; echo "==> Tearing down tenant \"$TENANT\" ..."; \
          python loadtest/tenant_ctl.py destroy "$TENANT" || true' EXIT
  else
    echo "==> KEEP_TENANT=1 — the tenant will NOT be destroyed."
  fi
  HOST="$(printf '%s\n' "$CREATE_OUT" | sed -n 's/^TENANT_URL=\(.*\)/\1/p' | head -1)"
  EXAM_ID="$(printf '%s\n' "$CREATE_OUT" | sed -n 's/^EXAM_ID=\([0-9][0-9]*\).*/\1/p' | head -1)"
  if [ -z "$HOST" ] || [ -z "$EXAM_ID" ]; then
    echo "ERROR: tenant create did not return TENANT_URL/EXAM_ID." >&2
    exit 1
  fi
fi

if [ -z "$HOST" ]; then
  echo "ERROR: set TENANT=<name> (mode A) or HOST=<url> (mode B). Never production." >&2
  exit 2
fi

# ---- preflight: the app must already be up and reachable at HOST ------------
# (this script drives the app over HTTP; it does NOT start it for you.)
if command -v curl >/dev/null 2>&1; then
  echo "==> Checking the app is up at $HOST ..."
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "${HOST%/}/healthz" || true)"
  if [ "$code" != "200" ]; then
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$HOST" || true)"
  fi
  if [ "$code" = "000" ] || [ -z "$code" ]; then
    echo "ERROR: cannot reach $HOST — start the app (gunicorn) first, or fix HOST." >&2
    exit 2
  fi
  echo "    reachable (HTTP $code)."
else
  echo "WARN: curl not found — skipping the reachability check. Make sure the app is running at $HOST." >&2
fi

RESULTS_DIR="loadtest/results"
STAMP="$(date +%Y%m%d-%H%M%S)"
PREFIX="${RESULTS_DIR}/mockjamb-${STAMP}"
mkdir -p "$RESULTS_DIR"

# ---- 1. seed (unless an EXAM_ID was supplied) --------------------------------
if [ -z "${EXAM_ID:-}" ]; then
  echo "==> Seeding staging: N=$N students, BANK=$BANK/subject ..."
  SEED_OUT="$(N="$N" BANK="$BANK" python loadtest/seed_mock_jamb.py)"
  echo "$SEED_OUT"
  EXAM_ID="$(printf '%s\n' "$SEED_OUT" | sed -n 's/.*EXAM_ID=\([0-9][0-9]*\).*/\1/p' | head -1)"
  if [ -z "$EXAM_ID" ]; then
    echo "ERROR: could not read EXAM_ID from the seed output." >&2
    exit 1
  fi
else
  echo "==> Reusing EXAM_ID=$EXAM_ID (skipping seed)."
fi

# ---- 2. run locust headless --------------------------------------------------
echo "==> Realistic run: $USERS students seated over ${SEAT_WINDOW}s (~$SPAWN/s),"
echo "    each sits ~${EXAM_MINUTES} min then submits; total $RUN_TIME against $HOST (exam $EXAM_ID)."
set +e
EXAM_ID="$EXAM_ID" locust \
  -f loadtest/locustfile_mock_jamb.py \
  --host "$HOST" \
  --headless \
  --users "$USERS" \
  --spawn-rate "$SPAWN" \
  --run-time "$RUN_TIME" \
  --csv "$PREFIX" \
  --csv-full-history \
  --only-summary
LOCUST_RC=$?
set -e

# ---- 3. summarise + threshold gate ------------------------------------------
echo
echo "==> Results written to ${PREFIX}_stats.csv (+ _failures, _stats_history)"
python - "$PREFIX" "$THRESHOLD" <<'PY'
import csv, sys
prefix, threshold = sys.argv[1], float(sys.argv[2])
rows = list(csv.DictReader(open(prefix + '_stats.csv')))
agg = next((r for r in rows if r.get('Name') == 'Aggregated'), None)
if not agg:
    print('No Aggregated row — did any requests run?'); sys.exit(1)
reqs = int(agg['Request Count']); fails = int(agg['Failure Count'])
ratio = (fails / reqs) if reqs else 1.0
def g(k):
    return agg.get(k) or agg.get(k.replace('%', '%ile')) or '?'
print('=' * 64)
print(f'  requests      {reqs}')
print(f'  failures      {fails}  ({ratio*100:.2f}%)')
print(f'  median (p50)  {g("50%")} ms      p95 {g("95%")} ms      p99 {g("99%")} ms')
print(f'  avg           {float(agg["Average Response Time"]):.0f} ms      '
      f'max {float(agg["Max Response Time"]):.0f} ms      '
      f'rps {float(agg["Requests/s"]):.1f}')
print('=' * 64)
print('\nPer-endpoint p95 (ms):')
for r in rows:
    if r['Name'] != 'Aggregated' and int(r['Request Count']):
        print(f'  {r["Name"]:<40} {r.get("95%", "?"):>7}  ({r["Failure Count"]} fail)')
if ratio > threshold:
    print(f'\nFAIL: failure ratio {ratio*100:.2f}% exceeds threshold {threshold*100:.2f}%')
    sys.exit(1)
print(f'\nPASS: failure ratio {ratio*100:.2f}% within threshold {threshold*100:.2f}%')
PY
GATE_RC=$?

# non-zero if locust hit errors OR the threshold gate failed
[ "$LOCUST_RC" -eq 0 ] && [ "$GATE_RC" -eq 0 ]
