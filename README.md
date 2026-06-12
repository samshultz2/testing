# EduSyncra — School Management System

EduSyncra is a complete, offline‑resilient school management platform for
Nigerian secondary schools, built with Python/Flask. It runs as a Progressive
Web App (installable on any phone), works on poor or no network, and can be
self‑hosted on a phone (Termux) for a pilot or on a small VPS for a whole school.

One system covers the school day end‑to‑end: students, attendance, results &
report cards, computer‑based testing (CBT), external‑exam analytics
(WAEC/JAMB/Mock), fees & finance, HR & payroll, communications, admissions,
library, timetabling, and student welfare — across multiple branches.

---

## Highlights

- **Works on poor / no network.** Pages you've opened stay viewable offline; the
  CBT exam buffers every answer on the device (a reload or outage mid‑exam loses
  nothing); attendance and score entry made offline are queued and **auto‑synced
  when the connection returns**. Responses are gzip‑compressed for slow links.
- **Installable PWA.** Add to Home Screen → own icon, branded splash screen,
  full‑screen, offline‑capable. No app store needed.
- **Computer‑Based Testing (CBT)** with a live invigilator monitor, device/
  concurrent‑login detection, anti‑cheat lockdown, auto‑grading and scaling, and
  network‑outage recovery (auto‑resubmit on reconnect + an "End & grade" tool).
- **Multi‑branch** from the ground up — every record is branch‑scoped, with a
  central/branch permission model.
- **Secure** — role + module + branch access control, CSRF everywhere, scrypt
  password hashing, AES‑256 field encryption at rest, HMAC‑verified payment
  webhooks, shared rate limiting, and security headers.
- **Self‑hostable in one command** — `python app_production.py` serves the app
  and a Cloudflare tunnel on your own domain (HTTPS included).

---

## Modules

### Students & admissions
- Add/edit/view students, parent contacts, photos.
- Soft‑delete with a Trash (restore / permanent‑delete), **bulk delete/restore**.
- **Bulk import** from Excel **or CSV** (header‑matched columns, auto date/phone
  cleanup, duplicate guard, optional class assignment on import).
- Admissions/applicant tracking.

### Academics
- Academic sessions, terms, weeks, classes, arms, and class‑arm assignments.
- **Term Setup wizard** — a guided checklist (session → term → weeks → holidays
  → classes → enrolment) so a term is never half‑configured.
- **Holidays as date ranges** (a one‑week mid‑term break or two‑day Eid in one
  entry), promotion & graduation.

### Attendance
- Daily marking (morning/afternoon), with the specific holiday reason shown on
  non‑school days.
- **Mark‑a‑Week grid** — a students × days grid to clear an attendance backlog,
  with whole‑day or optional AM/PM ticks and one‑tap row/column/all toggles.
- Weekly/termly summaries, alerts, and exports.

### Results & report cards
- Subjects, assessment types, score entry (single & bulk), broadsheets.
- Report cards (PDF), behavioural/affective traits, grade scales.

### External exams (WAEC / JAMB / Mock JAMB)
- Result entry scoped to SSS3 candidates, OCR result scanning, deep analytics,
  university cut‑off/admission guidance.

### Computer‑Based Testing (CBT)
- Exam builder + question bank, per‑exam access passwords, shuffling, timing.
- Student exam portal (separate login), **on‑device answer buffer**, batched
  autosave, anti‑cheat (fullscreen lockdown, leave‑limit auto‑submit).
- **Live monitor** for invigilators: progress, flags, device & concurrent‑login
  detection, and **End & grade** recovery for stranded attempts.
- Scratch‑card result checker (public) and result publishing.

### Finance & operations
- **Fees** (structures, payments, discounts, receipts) with **Paystack** online
  payments (HMAC‑verified webhook) and a read‑only **parent portal**.
- **Expenses**, **HR & payroll** (staff, payslips, salary history, staff
  attendance, payroll → finance posting), **sales/POS**, **contributions**,
  **library** (catalogue, issue/return, fines).

### Communications
- SMS campaigns (Termii/Twilio) with templates, scheduling, and **background
  sending** so large batches don't block the app; announcements; WhatsApp links.

### Welfare
- **Discipline / incident log** and **sick‑bay (clinic) visits** on each student
  profile.

### Timetable
- Constraint‑based timetable generator (OR‑Tools) with printable/image output.

---

## Offline & poor‑network design

| Situation | Behaviour |
|---|---|
| Pages already visited, no network | Viewable (service‑worker cache). |
| CBT exam, network drops mid‑paper | Answers saved on the device + buffered; reload/outage loses nothing; auto‑resubmits when the connection returns. |
| Attendance / scores submitted offline | Queued on the device with a "waiting to sync" badge; replayed automatically on reconnect (survives re‑login). |
| Slow 2G/3G | gzip compression shrinks pages several‑fold. |

> Note: writes are **synced**, not computed offline — summaries/calculations
> refresh on the server once the queued data lands.

---

## Security

- Role + per‑module + per‑branch access control; view‑only accounts.
- CSRF protection on all state‑changing requests; scrypt password hashing.
- **AES‑256‑GCM** field encryption at rest (opt‑in, e.g. portal passwords).
- Shared (DB‑backed) brute‑force rate limiting on all login surfaces.
- Security headers (CSP, HSTS, etc.); HMAC‑verified Paystack webhook.
- See `docs/SECURITY.md` for the full posture and the go‑live checklist.

---

## Tech stack

- **Backend:** Python 3, Flask, SQLAlchemy.
- **Database:** PostgreSQL (production) / SQLite (dev); **Alembic** migrations.
- **Frontend:** server‑rendered templates, vanilla JS, a service worker (PWA);
  all UI assets self‑hosted (no CDN dependency for core UI).
- **Server:** gunicorn / waitress; optional Cloudflare tunnel.

---

## Quick start (development)

```bash
pip install -r requirements.txt
python app.py                 # http://127.0.0.1:5000
```

`create_all` builds the schema on first run. Tests:

```bash
python -m pytest
```

## Run it publicly (phone or VPS)

```bash
python app_production.py      # serves the app + a Cloudflare tunnel on your domain
```

One‑time domain/tunnel setup and go‑live hardening are in `docs/PHONE_PILOT.md`
and `docs/SECURITY.md`.

---

## Deployment & operations docs

| Doc | What it covers |
|---|---|
| `docs/PHONE_PILOT.md` | Serve publicly from a phone via Cloudflare tunnel. |
| `docs/POSTGRES_TERMUX_PROOT.md` / `docs/RUNBOOK_TERMUX.md` | Termux + Postgres setup & runbook. |
| `docs/MIGRATIONS.md` | Alembic schema‑migration workflow. |
| `docs/SECURITY.md` | Security posture + go‑live checklist. |
| `docs/SCALING.md` | Scaling to ~800 concurrent CBT students. |
| `docs/MULTI_BRANCH.md` / `docs/ROLES_AND_PERMISSIONS.md` | Branch scoping & the permission model. |
| `loadtest/` | Locust load‑test harness (seed + run + read results). |

---

## Status

Actively developed; **186 automated tests** passing. Roadmap items under
discussion: native/Play‑Store wrapper (TWA), printable ID cards, and offline
report‑card viewing.
