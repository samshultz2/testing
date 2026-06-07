# Code Quality Pass

A project-wide review (pyflakes + a structured audit of `routes/`, `models/`,
`utils/`) was run before the next major change. This records what was fixed and
what is intentionally deferred.

## Fixed (behaviour-preserving, tests green)

- **Unused imports** — ~95 removed across `routes/`, `models/`, `utils/`
  (via `autoflake --ignore-init-module-imports`, so model-registration
  side-effect imports in `__init__.py` are preserved).
- **Dead duplicate models** — deleted `models/user_models.py`, a stale second
  copy of `User`/`Teacher` that lacked `allowed_modules`/`view_only`. The live
  models are in `models/models.py`.
- **Dead merge script** — deleted `fix_conflict.py` (one-off, unused).
- **Shadowed class** — removed the dead first `WAECAnalytics` in
  `utils/exam_analytics.py` (~160 lines); the live second definition holds the
  methods actually called by `routes/results.py`.
- **Exception handling** — every bare `except:` replaced with
  `except Exception:` so `KeyboardInterrupt`/`SystemExit` are no longer
  swallowed.
- **Docstrings / `__repr__`** — added `__repr__` to the newer models
  (scratch-card, CBT login/device/answer/violation); documented the access model
  (`docs/ROLES_AND_PERMISSIONS.md`).

## Deferred (needs care / tests first)

These were identified but **not** changed, because the affected code is not
covered by the test suite and the changes could alter behaviour. Recommended to
tackle deliberately, each behind a test:

1. **N+1 queries in attendance summaries** — `utils/calculations.py`
   (`get_weekly_attendance_summary`, `get_termly_attendance_summary`) query
   `Attendance` per student per day. Should batch with a single
   `join`/`in_` query. Performance only; correctness is fine.
2. **N+1 in the dashboard** — `routes/main.py::dashboard` counts enrolments per
   class in a loop. Could be one grouped query.
3. **Long, multi-responsibility functions** — e.g. `routes/main.py::dashboard`
   (~290 lines), several Excel/PDF export routes in `routes/results.py`,
   `routes/subjects.py`, `routes/attendance.py` mix data aggregation with
   file formatting. Splitting data-building from rendering would help, but the
   export formats are fragile and untested.
4. **Shared helpers** — `Term.query.filter_by(is_active=True).first()` and the
   student class/arm placement lookup recur in many files; a shared
   `get_active_term()` / `student_placement()` would reduce duplication.
5. **Excel import transaction safety** — `utils/excel_utils.py` commits a batch
   without a surrounding transaction; a mid-batch failure leaves partial data.

## How to verify after any change

```
POSYHUB_TESTING=1 python3 -m pytest        # 64 tests
POSYHUB_TESTING=1 python3 -c "import app"  # app + all blueprints import
```
