# Security Audit — EduSyncra / PosyHub

**Date:** 2026-06-20 · **Scope:** whole application (auth/z, APIs, injection, data
exposure, infrastructure). **Method:** code review of `config.py`, `routes/*.py`,
`utils/*.py`, `models/*.py`, `templates/`, `static/js/`, `frontend/src/`.

> This supersedes the optimistic ratings in `docs/SECURITY.md` for two items
> (the default admin password and field encryption): that doc says the default
> password is "Mitigated by startup warnings" — but `ProductionConfig.warnings()`
> is **never called anywhere**, so there is no mitigation in effect.

**Pass 4 (2026-06-21) — authorization sweep + permission groups:**
- A full route-by-route authorization audit found **no unauthenticated or
  under-privileged gaps** in the staff app: `@login_required` discipline is
  consistent and the app-level `enforce_write_level`/`enforce_module_access`/
  `enforce_subsection_access` gates cover every blueprint in `BLUEPRINT_MODULE`.
- **Contributions hardened (the one finding):** the hidden contributions module
  was gated by a shared access code only and was reachable anonymously. It now
  requires a logged-in staff session *first* (the code is a second factor), and
  the wholesale `clear-all` op is **admin-only** and audit-logged. The hardcoded
  default access code has been **removed entirely** (a source-visible shared code
  is no protection): until an admin configures one, only admins may enter the
  module to set it; the code check uses constant-time comparison.
- **Permission groups** added: a `PermissionGroup` template provides a user's
  base module permissions; per-user overrides win ('none' revokes a group
  grant). Branch-scoped (central templates + own-branch groups). Full CRUD UI
  under Users → Permission Groups, and a group picker on the user form.
- **Postgres migration fix:** the lightweight column migrations used SQLite-only
  `DATETIME`/`BOOLEAN DEFAULT 0/1`, which crashed app startup on PostgreSQL the
  first time a new `DATETIME` column was added. DDL is now adapted per dialect
  (`DATETIME`→`TIMESTAMP`, boolean integer defaults→`TRUE`/`FALSE`).

## Overall posture

The codebase is **security-conscious and well above average** for its category:
ORM-only data access (no SQL-injection surface), Jinja autoescaping on (no XSS
sinks found), scrypt password hashing, a global timing-safe CSRF gate, HMAC-
verified payment webhooks, wired security headers, sound branch/tenant
isolation, and DoS-hardened OCR. **No SQLi, command injection, SSTI, SSRF, open
redirect, or stored/reflected XSS was found to be exploitable.**

The real risk is concentrated in **a few authentication/configuration defaults
that fail open**, headed by a publicly-known default admin password. Fix the
Critical/High items before any internet-facing deployment.

---

## Remediation log

**Pass 5 (2026-06-30) — data-at-rest + DoS + config hardening (re-audit):**
A fresh full-stack re-audit (3 parallel reviews, every high-stakes claim verified in
code) confirmed the posture above and found the prior Critical/High items still fixed.
It also confirmed several agent claims were **false positives** (parent-portal "session
fixation"/IDOR — `parent_portal.py:118-122` does `session.clear()`+`rotate_csrf_token()`
and `switch_child` is gated on the sibling set; "QR SVG XSS" — the URL is encoded into QR
*geometry*, not echoed as markup, on a `@login_required` page). Genuinely-open items fixed
this pass:
- **Backups encrypted at rest** — `utils/backup.py` now encrypts every `.db`/`.sql`
  artifact with AES-256-GCM (new `crypto.encrypt_bytes`/`decrypt_bytes`, magic-headed)
  when `FIELD_ENCRYPTION_KEY` is set; restore decrypts transparently and **legacy plaintext
  backups still restore**. Strict mode refuses to keep a plaintext backup.
- **`instance/` + backup permissions** locked to owner-only (`0700` dirs, `0600` files) on
  every backup/restore, so the DB, dumps and persisted dev key aren't world-readable.
- **Solver DoS bounded** — `Config.SOLVER_MAX_SECONDS` (default 90s, env-overridable) caps
  the OR-Tools `time_limit` safely below the 120s gunicorn worker timeout
  (`routes/generator/generation.py`), so one solve can't stall the single worker.
- **Debugger no longer on-by-default** — `DevelopmentConfig.DEBUG` is now opt-in via
  `FLASK_DEBUG=1`, so an APP_ENV-unset deploy doesn't expose the Werkzeug RCE console.
- **OCR prompt injection** — admin assessment-type labels are sanitised (printable ASCII,
  length-capped, quoted) before interpolation into the Claude Vision prompt (`utils/waec_ocr.py`).
- **Dependency floors bumped** — Flask 3.0.0→3.0.3, Werkzeug 3.0.1→3.0.6, cryptography
  floor →43.0.1 (install+validate on deploy). Regression tests in `tests/test_security_hardening.py`.
- **Deliberately deferred (risk > value):** a *global* rate limiter — the existing
  `RateLimiter` is DB-row-per-hit, so a global per-request cap would add a DB write to every
  page load (worse than the Medium DoS it mitigates); this needs Redis/flask-limiter. And the
  dead duplicate CSRF helpers in `utils/security.py` are re-exported via `utils/__init__.py`,
  so deleting them risks a boot-time ImportError for a cosmetic gain — left as a tracked cleanup.
- **H3 (recoverable portal passwords)** remains a flagged **product decision** (hash-only
  breaks credential-sheet reprinting) — owner's call, not changed silently.

**Pass 3 (2026-06-28) — H5 (full): nonce-based CSP, inline scripts/handlers removed:**
- `script-src` is now **nonce-based with no `'unsafe-inline'` and no `'unsafe-eval'`**
  (`utils/security.py`): a per-request nonce (`get_csp_nonce`, memoised on `g`, exposed
  to templates as `csp_nonce`) is set on every inline `<script>`, and **all 174 inline
  `on*` handlers were moved to event listeners** — most via a small dependency-free,
  event-delegated shim (`static/js/csp-behaviors.js`) driven by `data-*` attributes
  (`data-call`/`data-args`/`data-on`, `data-autosubmit`, `data-confirm`, `data-print`,
  `data-copy`, `data-remove-*`). An injected `<script>` or inline handler no longer runs.
- `style-src` intentionally keeps `'unsafe-inline'` (pervasive inline `style=""`; nonces
  don't cover style attributes and the XSS value is far lower for CSS).
- Verified with headless Chromium (Playwright) across ~25 pages incl. the React SPAs and
  the dynamic-row timetable designer: **zero CSP violations**, the `data-call` dispatcher
  binds args/`this` correctly, and the React bundles + MathJax 3 (`tex-mml-chtml`) load
  without `'unsafe-eval'`. Regression test in `tests/test_security_hardening.py`.
  (If a future component genuinely needs eval, re-adding `'unsafe-eval'` is a one-line change.)

**Pass 2 (2026-06-28) — audit of recently-added code + follow-ups:**
- Re-verified the whole-project posture (CSRF, before_request gates, headers/HSTS,
  login rate-limiting, session flags, branch scoping) — all still in force. A full
  route sweep found **zero accidentally-unauthenticated routes**.
- **New finding (this period)** — the WAEC grade-forecast engine setting is global
  (cohort-wide), so changing it now requires a **central admin**, not just any admin
  (`routes/results.py::waec_model_config`, `action=save_method`).
- **M7 (closed)** — contributions object routes that load by URL id now branch-check:
  `student_detail`, `delete_payment`, `api_student_info` call `require_branch_access`
  (central users unaffected; single-branch is a no-op). `delete_expense` is left as-is
  — `ContributionExpense` has no student/branch link (session-level data).
- **M3 (extended)** — applied the existing `@rate_limited('export', …)` decorator to the
  heaviest exports/PDFs: Mock-WAEC broadsheet/blank/slip PDFs + Excel export
  (`routes/mock_waec.py`), and the WAEC/JAMB and weekly/termly attendance Excel exports.
- **Tidy** — `routes/main.py::set_theme` now `@login_required` (was anonymously callable).
- Regression tests in `tests/test_security_hardening.py`.
- Still intentionally deferred (product/cost): full nonce-based CSP (H5), bounding the
  OR-Tools solver (M3 solver), moving off recoverable portal passwords (H3).

**Pass 1 (2026-06-20) — fixed:**
- **C1** — removed the hardcoded `ADMIN_PASSWORD` fallback; legacy login now
  requires both `ENABLE_LEGACY_LOGIN=1` **and** a configured `ADMIN_PASSWORD`,
  and defaults **off**. `auth.py` guards on a configured password.
  `ProductionConfig`'s never-invoked `warnings()` was replaced by
  `Config.security_warnings()`, now **called at startup** and logged.
  Regression tests in `tests/test_security_login.py`.
- **H1** — `ProductionConfig.SESSION_COOKIE_SECURE` now defaults **True**
  (opt-out via env for plain-HTTP LAN).
- **L2** — login throttle is cleared only after the `is_active` check.
- **.env** — loader hardened: a present-but-unreadable `.env` (missing
  python-dotenv) now prints a loud warning instead of silently no-op'ing, and
  `ENV_FILE_LOADED` records whether a file was applied. `.env.example` updated to
  the new secure defaults.

**Pass 2 (2026-06-21) — fixed:**
- **H4 / H3 / M1** — production now **fails closed**: `Config.security_errors()`
  (enforced when `ENFORCE_SECURITY`, set on `ProductionConfig`) blocks startup if
  `SECRET_KEY` or `FIELD_ENCRYPTION_KEY` is missing. `get_config()` warns loudly
  when `APP_ENV`/`FLASK_ENV` is unset (silent default to DEBUG). Verified the app
  refuses to boot without the secrets and boots with them.
- **H2** — all four login paths (staff, legacy admin, parent, CBT) now
  `session.clear()` and mint a fresh CSRF token (`rotate_csrf_token()`), so a
  pre-auth session/token can't be reused after privilege elevation.
- **M6** — CBT supervisor PIN compared with `hmac.compare_digest`.
- **M7** — **not applicable**: verified `ContributionExpense` has no student/
  branch and `ContributionPayment` is session/student-scoped; the contributions
  module has no branch dimension at all, so there is no tenant boundary to cross.
  (The original IDOR concern was a false positive.)

**Pass 3 (2026-06-21) — fixed:**
- **M5** — the public result checker now returns one generic "Student ID or card
  PIN is incorrect" for wrong-ID / wrong-PIN / card-bound-to-another (kills the
  enumeration oracle); the internal audit log stays specific.
- **M4** — self-service reset now emails a **single-use, 1-hour reset link**
  (`User.set_reset_token`/`check_reset_token`/`clear_reset_token`, hashed +
  expiry) instead of overwriting the live password. New
  `/reset-password/<uid>/<token>` page. Triggering a reset for someone else no
  longer locks them out.
- **H6** — auto portal PINs are now 8 chars from an unambiguous alphabet
  (~40 bits, up from 24), and parent + CBT logins throttle per **account**
  (Student ID) in addition to per IP, so a distributed brute-force still trips a
  lockout.
- **H7** — DB restore now requires a typed `RESTORE` confirmation (UI + server)
  and writes an audit-log entry on every attempt.
- **M3** — added a DB-backed `@rate_limited` decorator; applied to the OCR
  scan endpoints (30/10min) and DB download/JSON export (12/10min). **The
  OR-Tools timetable solver was intentionally left untouched** per request.
- **H5 (safe parts)** — CSP hardened with `object-src 'none'`, `base-uri 'self'`,
  `frame-ancestors 'self'`, `form-action 'self'`. `'unsafe-inline'`/`'unsafe-eval'`
  retained (removing needs a per-script nonce migration) — flagged, not done.

**Still open (deferred / by design):**
- **H3 (deeper)** — production already *requires* field encryption; switching to
  hash-only storage was declined because it breaks credential-sheet reprinting.
- **H5 (full)** — nonce-based CSP migration across all inline scripts.
- **M3 (solver)** — bounding the OR-Tools solver time, intentionally skipped.

> Note on H3: production now *requires* `FIELD_ENCRYPTION_KEY` (passwords are
> encrypted at rest), but the design still stores a *recoverable* value. Moving
> to hash-only storage with one-time PIN display remains recommended.

## Severity summary

| ID | Sev | Finding |
|----|-----|---------|
| C1 | 🔴 Critical | Default hardcoded admin password + legacy login on by default |
| H1 | 🟠 High | `SESSION_COOKIE_SECURE` defaults off; no HTTPS enforcement |
| H2 | 🟠 High | No session-ID regeneration on login (fixation); CSRF token never rotated |
| H3 | 🟠 High | Recoverable/plaintext portal passwords stored by default |
| H4 | 🟠 High | Missing `SECRET_KEY` is only a warning in prod (not fatal) |
| H5 | 🟠 High | CSP allows `unsafe-inline` + `unsafe-eval` (negates XSS defense) |
| H6 | 🟠 High | Weak portal auth: 24-bit auto-PINs + enumerable IDs + IP-only throttle |
| H7 | 🟠 High | DB restore replaces live DB from an upload with no re-auth/confirmation |
| M1 | 🟡 Med | Config defaults to Development (`DEBUG=True`) if `APP_ENV` unset |
| M2 | 🟡 Med | Public CSRF-exempt `/client-error` → log injection + error-buffer flush |
| M3 | 🟡 Med | No global rate limit; expensive endpoints DoS a single worker |
| M4 | 🟡 Med | Password reset overwrites live password, no TTL, emailed in cleartext |
| M5 | 🟡 Med | Result/portal Student-ID enumeration oracle |
| M6 | 🟡 Med | Non-constant-time CBT supervisor-PIN compare (plaintext-stored) |
| M7 | 🟡 Med | Possible IDOR: contributions payment/expense delete has no scope check |
| L1–L5 | ⚪ Low/Info | SW caches authed pages; throttle-reset ordering; dep bumps; dead CSRF code; clean repo (no committed secrets) |

---

## CRITICAL

### C1 — Default hardcoded admin password, legacy login on by default
`config.py:111-112`, `routes/auth.py:86-99`
```python
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD') or "posyhubcomng"
ENABLE_LEGACY_LOGIN = _as_bool(os.environ.get('ENABLE_LEGACY_LOGIN'), default=True)
```
The legacy branch grants `role='admin'`, central scope (`set_session_scope(None)`)
to anyone who submits the password with **no username**. `ProductionConfig.warnings()`
flags this — but a repo-wide grep shows `warnings()` is **never invoked**, so it
is silent.

- **Severity:** Critical (unauthenticated full central-admin takeover).
- **Attack:** Visit `/login`, leave username blank, enter `posyhubcomng` → full
  cross-branch admin: all student PII, parent phone numbers, finance, exports,
  user management. The 8-attempt throttle is irrelevant — the password is known.
- **Fix:**
  ```python
  ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')           # no fallback
  ENABLE_LEGACY_LOGIN = _as_bool(os.environ.get('ENABLE_LEGACY_LOGIN'), default=False)
  ```
  In `auth.py`, require a configured password before comparing:
  `if Config.ENABLE_LEGACY_LOGIN and Config.ADMIN_PASSWORD and password and hmac.compare_digest(...)`.
  In `ProductionConfig`, make the default-password-with-legacy-on combination a
  **hard startup error**, and actually call the readiness check at boot.

---

## HIGH

### H1 — Insecure session cookie by default; no HTTPS enforcement
`config.py:144` (`SESSION_COOKIE_SECURE` default `False`); `ProductionConfig`
does not override it; HSTS only emitted `if request.is_secure`.
- **Attack:** On any plain-HTTP hop (LAN/Termux deployments are explicitly
  anticipated), the session cookie travels in cleartext → trivial sniff → admin
  session takeover.
- **Fix:** Default `SESSION_COOKIE_SECURE=True` in `ProductionConfig`; add an
  in-app HTTP→HTTPS redirect when `TRUST_PROXY` + `X-Forwarded-Proto: http`; add a
  `return 301 https://…` block in `deploy/nginx-posyhub.conf`. (`HTTPONLY=True`,
  `SAMESITE='Lax'` are already correct.)

### H2 — No session regeneration on login; CSRF token never rotated
`routes/auth.py` login branches, `routes/parent_portal.py`, `routes/cbt.py`,
`utils/csrf.py:24-30`. Login writes auth keys onto the **existing** session and
never rotates the `_csrf_token`.
- **Attack:** Session-fixation — a pre-seeded session/CSRF token survives the
  privilege elevation at login.
- **Fix:** At the top of each successful login: `session.clear()`, then set auth
  keys, then mint a fresh `_csrf_token`. Same on logout.

### H3 — Recoverable/plaintext portal passwords stored by default
`models/models.py:82-83,119-124`, `utils/crypto.py:62-79`, exported at
`routes/cbt.py:875`. `FIELD_ENCRYPTION_KEY` defaults to empty (`config.py:104`),
so `set_portal_password` stores the **cleartext** PIN in
`students.portal_password_plain`.
- **Attack:** Any DB read (leaked backup, the legacy-admin export, the committed-
  DB risk) yields every student's live portal password in cleartext.
- **Fix:** Prefer storing only the hash and showing the generated PIN once. If
  reprint is required, ship `REQUIRE_FIELD_ENCRYPTION=1` in production (the code
  supports fail-closed) and make a missing `FIELD_ENCRYPTION_KEY` a hard prod
  error. (Algorithm itself — AES-256-GCM, random nonce — is sound.)

### H4 — Missing `SECRET_KEY` only warns in production
`config.py:19-46`. Unset key → self-generated/persisted to `instance/.secret_key`
(next to `school.db`); production only warns and boots anyway.
- **Attack:** Anyone who reads the persisted key (path traversal / backup
  exposure / shared volume) can forge session cookies → impersonate admin.
- **Fix:** Make a missing `SECRET_KEY` **fatal** in `ProductionConfig`; keep the
  persisted-key convenience for dev only.

### H5 — CSP permits `unsafe-inline` and `unsafe-eval`
`utils/security.py:348-355`. `script-src 'self' 'unsafe-inline' 'unsafe-eval' …`
provides essentially no defense-in-depth against injected inline scripts.
- **Fix:** Move inline scripts to files, adopt a per-request nonce
  (`script-src 'self' 'nonce-…'`), drop `unsafe-inline`/`unsafe-eval`. (Other
  headers — `X-Frame-Options`, `nosniff`, `Referrer-Policy` — are good; no CORS
  misconfig, no `flask-cors`.)

### H6 — Weak portal/CBT credential strength + IP-only throttling
`routes/cbt.py:823` auto-PIN is `secrets.token_hex(3)` = 6 hex = **~24 bits**;
Student IDs are sequential `STU#####` (enumerable); rate limits key on
`request.remote_addr` only (parent 10/15m, CBT 15/15m, result 20/15m), so there
is **no per-account lockout**.
- **Attack:** Distributed brute force (proxy pool) over enumerable IDs defeats
  the per-IP limit and cracks the 24-bit PIN space for a target student.
- **Fix:** `secrets.token_urlsafe(9)` PINs; add a per-`student_id` failure counter
  and lockout; throttle on (IP **and** account).

### H7 — DB restore swaps the live database from an upload, no re-auth
`routes/settings.py:633-686` → `utils/backup.py:124-180`. A central admin uploads
a `.db`/`.sql` that **replaces** the live DB (`shutil.move` / `psql -f`). Defenses
are decent (central-admin only, magic-byte validation, pre-snapshot,
single-transaction Postgres apply, no path traversal), but it is an admin-
equivalent live-data swap with no confirmation/audit gate.
- **Attack:** A compromised (or default-password, see C1) admin plants arbitrary
  rows — e.g. an attacker-known password hash — wholesale.
- **Fix:** Require typed confirmation + re-authentication for restore; audit-log
  and alert on it; prefer schema-validated data import over raw file swap.

---

## MEDIUM

### M1 — Defaults to Development (`DEBUG=True`) when `APP_ENV` unset
`config.py:203-208` (`get_config` default `development`), `config.py:157`.
A prod deploy that forgets `APP_ENV=production` runs with the Werkzeug debugger
(PIN-protected RCE console) exposed and verbose errors.
- **Fix:** Default to a safe (production) config; refuse to start with `DEBUG=True`
  off-localhost.

### M2 — Public CSRF-exempt `/client-error` → log injection + error eviction
`routes/main.py:1913-1930` (CSRF-exempt at `utils/csrf.py:21`), stored in a
300-entry ring buffer (`utils/error_tracking.py`) and shown to a central admin.
- Stored-XSS is **mitigated** (Jinja autoescape in `templates/errors/recent.html`)
  — add a comment so nobody "fixes" it with `|safe`.
- Residual: **log injection** (newlines in `stack`/`message` forge log lines) and
  **buffer flushing** (push 300 junk entries to evict real errors; 40/5min/IP is
  trivially distributed).
- **Fix:** Strip control chars/newlines before logging; tighten/auth the endpoint.

### M3 — No global rate limit; expensive endpoints DoS the single worker
No `flask-limiter`; `gunicorn.conf.py` runs `workers=1` (required by in-process
jobs). The OR-Tools timetable solver (`routes/generator.py:1349`, `time_limit`
up to 300s vs 120s gunicorn timeout), OCR, and big PDF/Excel exports are reachable
by authenticated low-priv users.
- **Attack:** One user triggering a long solve/OCR stalls the **entire** app.
- **Fix:** Add `flask-limiter` (DB/Redis-backed) with global + per-endpoint caps;
  cap solver `time_limit` below the gunicorn timeout; offload OCR/solver/PDF to a
  background queue.

### M4 — Password reset overwrites the live password (no TTL, emailed cleartext)
`routes/auth.py:120-132`, `routes/users.py:610-615`. The temp password replaces
the real one immediately, never expires, and is emailed in plaintext.
- **Attack:** Triggering "forgot password" for a victim instantly disables their
  real password (DoS); a temp left in an inbox stays valid forever.
- **Fix:** Issue a separate hashed, single-use, time-limited (≈1h) reset token;
  do not invalidate the current password until a new one is set.

### M5 — Student-ID enumeration oracle on the public result checker
`routes/result_portal.py:210-217` returns distinct messages for unknown student
vs invalid PIN, confirming which sequential IDs exist.
- **Fix:** One generic "Student ID or PIN is incorrect" for all mismatches.

### M6 — Non-constant-time CBT supervisor-PIN compare
`routes/cbt.py:1275` uses `pin != real` (timing-observable); PIN stored plaintext.
- **Fix:** `hmac.compare_digest(pin, real)`; store the PIN hashed.

### M7 — Possible IDOR: contributions delete has no scope check
`routes/contributions.py:358-372` (`delete_payment`) and `:471` (`delete_expense`)
do `db.get_or_404(…, id)` then delete **without** a branch/scope check. By
contrast `finance` correctly calls `require_branch_access(payment.branch_id)` on
every payment mutation (`routes/finance.py:650,669,691,731`).
- **Attack (if contributions data spans branches):** a user with the
  contributions capability deletes another branch's payment by guessing its id.
- **Fix:** Add `require_branch_access(payment.student.branch_id)` (or the
  equivalent scope check) before delete, matching the finance pattern. Verify
  whether contributions is genuinely single-cohort/central before downgrading.

---

## LOW / INFORMATIONAL

- **L1 — Service worker caches authenticated GET navigations** device-side
  (`static/js/sw.js:133-144`). Mitigated (single-user install, `clear-runtime`
  handler). Ensure logout posts `clear-runtime`; exclude finance / passwords-
  export / parent-portal routes from runtime caching.
- **L2 — Throttle counter cleared before the `is_active` check** (`auth.py:53`):
  a correct password on a deactivated account resets the brute-force counter.
  Move `_clear_login_failures()` after the `is_active` check.
- **L3 — Dependency bumps:** Werkzeug 3.0.1 / Flask 3.0.0 are behind 3.0.x
  security patches; `cryptography>=41` floor is old. Pin higher floors.
- **L4 — Duplicate/dead CSRF code:** `utils/security.py:305-330` (unused) and an
  inline processor in `app.py:182-186` duplicate `utils/csrf.py`. Delete the dead
  ones to keep one source of truth.
- **L5 — Repo hygiene (good):** `git ls-files` shows no `.db`, `.env`, or
  `.secret_key` tracked; only hardcoded secret is the legacy `ADMIN_PASSWORD`
  (C1). `.gitignore` covers DB/secret/env files.

---

## Verified good (no action)

SQL injection (ORM-only; the few `text()` calls use bind params) · command
injection (list-argv `subprocess`, no `shell=True`, no user input) · SSTI/RCE (no
`eval`/`exec`/`pickle`/`render_template_string`) · XSS (autoescape on; JS/React
sinks use `esc()`; no `dangerouslySetInnerHTML`) · SSRF/open-redirect (fixed
hosts; `_safe_next` validates redirects) · ReDoS (linear, anchored regexes;
16MB cap) · branch/tenant isolation (`require_branch_access`, `scope_query`;
`set_view_branch` gated on `is_central`) · OCR DoS hardening (pixel/time/page
caps) · payment webhook (HMAC-SHA512, `compare_digest`).

---

## Production-grade remediation order

1. **C1** — remove the hardcoded `ADMIN_PASSWORD` fallback, default legacy login
   **off**, make the bad combo a fatal boot error (and actually run the check).
2. **H3 / H4 / M1** — fail-closed in production: require field encryption, require
   `SECRET_KEY`, default to the production config (no accidental `DEBUG`).
3. **H1 / H5** — secure cookies + HTTPS redirect; nonce-based CSP without
   `unsafe-inline`/`unsafe-eval`.
4. **H2 / H6 / M4 / M5 / M6** — rotate session + CSRF on login; stronger PINs +
   per-account lockout; single-use TTL reset tokens; generic auth errors;
   constant-time PIN compare.
5. **H7 / M7** — confirmation + audit on DB restore; add the missing scope check
   to contributions deletes.
6. **M3** — `flask-limiter` + bound/offload the solver, OCR, and exports.
7. **L3 / L4** — bump dependencies; delete dead CSRF code.

### Pre-launch checklist (delta from `docs/SECURITY.md`)
- [ ] `ADMIN_PASSWORD` set **or** `ENABLE_LEGACY_LOGIN=0`; default fallback removed
- [ ] `SECRET_KEY`, `FIELD_ENCRYPTION_KEY` set and enforced (fatal if missing)
- [ ] `APP_ENV=production`; readiness check invoked and blocking
- [ ] `SESSION_COOKIE_SECURE=1`, HTTPS redirect, HSTS, nonce-CSP
- [ ] DB restore gated by confirmation + audit; contributions scope check added
- [ ] `flask-limiter` in place; solver/OCR/export bounded
