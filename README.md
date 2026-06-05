# PosyHub Student Management System

A comprehensive student management system built with Python/Flask for Nigerian
secondary schools — students, attendance, internal results, and a deep focus on
external exams (WAEC, JAMB, Mock JAMB) with analytics, OCR result scanning, and
admission guidance.

## Features

### Core
- **Students** — add/edit/view, parent contacts, soft-delete with a Trash
  (restore / permanent-delete), bulk actions, Excel import/export.
- **Academics** — sessions, terms, classes, arms, class setup, promotion &
  graduation.
- **Attendance** — daily/weekly/termly tracking with summaries and alerts.
- **Internal results** — subjects, scores, broadsheet, report cards.
- **Timetable generator**, **contributions**, **reports**.

### External exams (WAEC / JAMB / Mock JAMB)
- **Result entry** restricted to SSS3 candidates; current-year defaults;
  English compulsory for JAMB; raw-correct → /100 conversion for Mock JAMB.
- **Student streams** (Science / Arts / Commercial) that drive WAEC subject
  defaults; per-student WAEC/JAMB subject enrolment.
- **Search** by name/ID on the JAMB and WAEC dashboards.
- **Result image/PDF scanning (OCR)** — upload a photo, scan, or PDF of a WAEC
  or JAMB result (including the JAMB **SMS** format); it reads the name,
  subjects and grades/scores, auto-matches the student, and shows an editable
  review before saving. **Batch mode** handles many files at once. Optional
  Claude-vision fallback for tough images.
- **Analytics hub** — WAEC + JAMB stats, grade/score distributions, gender
  comparison, WAEC↔JAMB correlation, year-over-year trends, a JAMB projection,
  class/arm comparison, and an internal-average ↔ JAMB correlation. Export to
  Excel / image / PDF.
- **Exam readiness** dashboard, **subject-enrolment** report with drill-down,
  per-student **Exam Report** (print/PDF), **Mock JAMB targets**.
- **Admission advisor** — course-specific eligibility from JAMB + WAEC against
  a seeded, editable cut-off table.

### Platform
- Mobile-first responsive UI with dark mode; installable **PWA** with offline
  page caching.
- **Security** — CSRF protection, login throttling, role-gated admin actions,
  an **audit log**, persisted secret key, daily DB backups.

## Requirements

- Python 3.11+
- **Tesseract OCR** (for result image scanning):
  - Ubuntu/Debian/proot: `sudo apt-get install tesseract-ocr tesseract-ocr-osd`
  - macOS: `brew install tesseract`
  - Windows: install the UB Mannheim Tesseract build
- Python packages from `requirements.txt` (includes Pillow, pytesseract,
  PyMuPDF, python-dotenv).

## Installation

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # then edit (see Configuration)
python app.py                     # http://127.0.0.1:5000
```

First login uses the legacy admin password (`ADMIN_PASSWORD`, default
`posyhubcomng` — change it in `.env`). Create real user accounts under
Settings → Users, then set `ENABLE_LEGACY_LOGIN=0`.

## Configuration (`.env`)

Copy `.env.example` to `.env` in the project root. Key settings:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Session secret (auto-persists to `instance/.secret_key` if unset) |
| `ADMIN_PASSWORD` | Legacy shared-admin password |
| `ENABLE_LEGACY_LOGIN` | `0` to disable the shared password once users exist |
| `LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCKOUT_MINUTES` | Login throttling |
| `SESSION_COOKIE_SECURE` | `1` when served over HTTPS |
| `BACKUP_RETENTION` | Daily DB backups kept in `instance/backups/` |
| `OCR_VISION_FALLBACK`, `OCR_VISION_MODEL` | Optional Claude-vision OCR (needs `ANTHROPIC_API_KEY` + `anthropic`) |
| `DATABASE_URL` | Override the default SQLite DB |

## Tests

```bash
pip install pytest
POSYHUB_TESTING=1 python -m pytest -q
```

Tests run against a throwaway temporary database and never touch your data. CI
runs them on every push (`.github/workflows/ci.yml`).

## Notes

- Data lives in `instance/school.db` (SQLite). Schema migrations for new columns
  run automatically on startup; daily backups go to `instance/backups/`.
- OCR accuracy depends on image quality — a straight, well-lit, high-resolution
  photo reads best; digital PDFs (with a text layer) read fastest and cleanest.
