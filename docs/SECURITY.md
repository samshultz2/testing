# PosyHub — Security Review & Posture

Last reviewed: 2026-06. Scope: application code, auth/z, data handling, crypto,
public endpoints. This is a living document — update it as findings are resolved.

## Summary

PosyHub is in **good shape** for an app of its kind. Strong foundations are in
place: one-way password hashing (scrypt), CSRF on all state-changing requests,
role + branch + module + capability authorization, security response headers,
ORM-only data access (no SQL injection surface), Jinja auto-escaping, and
HMAC-validated payment webhooks. The main gaps are **operational** (TLS, secrets,
disk encryption) and a **missing brute-force throttle on public endpoints**.

## What was fixed in the recent hardening pass

| Issue | Resolution |
|-------|-----------|
| Branch-scoped users could manage accounts in other branches | `current_manage_scope()` clamps non-central users to their branch |
| Security headers (`add_security_headers`) defined but never sent | Wired into `after_request` (CSP, X-Frame-Options, nosniff, Referrer-Policy; HSTS over TLS) |
| Result-card / timetable generation open to anyone with module access | Explicit capability grants; result-cards is central-admin-grant-only |
| Student portal passwords stored as **cleartext** | **AES-256-GCM at rest** (opt-in via `FIELD_ENCRYPTION_KEY`) |
| Dashboards exposed stats beyond a user's permission | Per-permission widget gating + teacher class-scoping |
| No WSGI server / debug server in prod | gunicorn, `DEBUG=False`, env-driven config |

## Findings

| # | Severity | Finding | Status / Recommendation |
|---|----------|---------|--------------------------|
| 1 | **High** | **No rate limiting on public endpoints** — `/check-result` (scratch-card PIN) and `/parent` login can be brute-forced. Attempts are logged but not throttled. | **Open.** Apply the existing `RateLimiter` (utils/security.py) keyed by IP (+ student id) to both. |
| 2 | ~~Critical~~ **Fixed** | **Default shared admin password** `posyhubcomng` + legacy login on by default (the "mitigated by warnings" note was wrong — `warnings()` was never called). | **Resolved 2026-06:** hardcoded password removed; legacy login is off by default and inert unless `ENABLE_LEGACY_LOGIN=1` **and** a strong `ADMIN_PASSWORD` are set. Advisories are now logged at startup. See `docs/SECURITY_AUDIT_2026-06.md`. |
| 3 | Medium | **No TLS in transit** (LAN/Termux is plain HTTP). | Closes on server deploy — HTTPS via nginx+certbot. "AES-256 in transit" = TLS. |
| 4 | Medium | **Backups & uploads stored unencrypted** on disk. | Enable **disk/volume encryption** on the server (covers DB files, daily backups, uploads). Manual backups can also be AES-256 encrypted via `BACKUP_ENCRYPTION_KEY`. |
| 5 | Low | `SECRET_KEY` auto-generated/persisted if unset. | Set `SECRET_KEY` explicitly in production (warned at startup). |
| 6 | Low | `next_url` stored from `request.url` for post-login redirect. | Low risk (server-set, same-origin). Optionally validate it is a local/relative path before redirecting. |
| 7 | Info | CSRF exemption on `parent.pay_webhook`. | **Correct** — the webhook is authenticated by Paystack HMAC-SHA512 (`hmac.compare_digest`), which is the right mechanism. |

### Verified good (no action)

- **SQL injection:** all access via SQLAlchemy ORM; no string-built SQL.
- **XSS:** Jinja auto-escaping on; the only `|safe` uses are `|tojson|safe` for
  embedding numeric/stat data in scripts (safe pattern).
- **RCE/SSTI:** no `eval`/`exec`/`pickle`/`shell=True`/`render_template_string`.
- **Outbound HTTP:** Paystack/Termii/Twilio calls all set `timeout`.
- **Passwords:** scrypt hashing (one-way, salted) — do **not** switch to
  reversible encryption.
- **Webhook:** Paystack signature verified before recording payment.

## Encryption (AES-256)

AES-256 applies in three distinct places — set them all for defence in depth:

1. **In transit → HTTPS.** TLS already uses AES-256-GCM. Put nginx + certbot in
   front on the server. *Biggest single win.*
2. **At rest, whole disk → encrypted volume** (LUKS / cloud "encrypted disk").
   Covers the database, daily backups, and uploads in one step.
3. **At rest, sensitive fields → app-level AES-256-GCM** (implemented):
   - Set `FIELD_ENCRYPTION_KEY` (see `.env.example`).
   - Run `python scripts/encrypt_portal_passwords.py` once.
   - `Student.portal_password_plain` is then encrypted in the DB; the app
     decrypts transparently for the credentials sheet.
   - Losing the key makes those fields unrecoverable, but portal passwords can
     be regenerated, so the blast radius is small. Keep the key in secrets, not
     in source control.

## Pre-launch security checklist

- [ ] `APP_ENV=production`, zero `PRODUCTION:` warnings in logs
- [ ] `SECRET_KEY` set; `ADMIN_PASSWORD` strong (or `ENABLE_LEGACY_LOGIN=0`)
- [ ] HTTPS on; `SESSION_COOKIE_SECURE=1`, `ENABLE_HSTS=1`, `TRUST_PROXY=1`
- [ ] `FIELD_ENCRYPTION_KEY` set + portal passwords migration run
- [ ] Disk/volume encryption enabled on the server
- [ ] **Rate limiting added to `/check-result` and `/parent` login (finding #1)**
- [ ] Backups verified (restore tested) and stored off-box (encrypted)
- [ ] `.env` permissions `600`, never committed
