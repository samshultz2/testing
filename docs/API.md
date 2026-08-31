# Internal JSON API — inventory & contract

EduSyncra/PosyHub is a server-rendered Flask app with a **private, first-party
JSON API** consumed by its own React islands and soft-navigation shell. It is
**not** a public/partner API. This document is the maintained inventory called
for by OWASP API Security Top 10 **API9: Improper Inventory Management** — keep
it current when adding or removing endpoints.

## Authentication & authorization

Every JSON endpoint runs behind the **same session + access-control stack** as
the HTML routes — there is no separate API auth surface, token, or key:

- **Session**: signed-cookie session (HttpOnly, `SameSite=Strict` in prod,
  `Secure` in prod), with server-side revocation via `users.token_version`
  (see `enforce_session_version`). Idle + absolute timeouts apply.
- **CSRF**: unsafe methods (POST/PUT/PATCH/DELETE) require a valid `_csrf_token`
  (global `before_request` check). Safe reads (GET) are exempt. The only
  CSRF-exempt endpoints are the Paystack webhook and the client-error beacon.
- **Function-level authz** (API5/BFLA): `enforce_module_access`,
  `enforce_subsection_access`, `enforce_read_only`, `enforce_write_level`.
- **Object-level authz** (API1/BOLA): per-route ownership checks
  (`require_branch_access`, `assert_student_access`, `can_manage`,
  `can_access_class`). New by-id endpoints **must** add the matching check.
- **Rate limiting** (API4): a global per-IP ceiling plus per-bucket limiters;
  `MAX_CONTENT_LENGTH` caps upload size.

A JSON caller signals itself with `X-Requested-With: fetch` (or an `/api/`
path / `Accept: application/json`); error handlers then return JSON
(`{"error": ...}`) with the right status (400/401/403/404/413/429/500).

## Versioning

Endpoints are **unversioned by design**: the client and server ship together
from one repo and deploy atomically, so there is no external consumer to break.
If a third party is ever granted access, introduce a `/api/v1/` prefix and a
deprecation policy at that point — do not retrofit versioning before it buys
anything.

## Endpoint inventory

Paths are grouped by module. All require an authenticated session and the
listed module permission; mutating routes additionally require CSRF + write
level. Paths are shown **as declared on their blueprint** — the live URL may
carry that blueprint's `url_prefix`, so treat `git grep -nE "route\('/api/"`
(and the blueprint registrations in `app.py`) as the source of truth. This
table is a representative map, not an exhaustive generated spec.

### Shell / cross-cutting
| Method | Path | Purpose | Gate |
|---|---|---|---|
| GET | `/api/context` | Current user + nav context | any session |
| GET | `/api/session/ping` | Session keepalive (204/401) | any session |
| GET | `/api/notifications` | Unread notifications | any session |
| POST | `/api/notifications/<id>/read`, `/api/notifications/read-all` | Mark read | any session |
| GET | `/api/dashboard/stats`, `/api/dashboard/data`, `/api/dashboard/widgets` | Dashboard tiles | any session |

### Students & academics
| Method | Path | Purpose | Gate |
|---|---|---|---|
| GET | `/api/students`, `/api/students/<id>` | Student search / detail | `students` |
| GET | `/api/student/<id>/info`, `/api/student/<id>/progress` | Student panels | `students` (branch-scoped) |
| GET | `/api/assignments/<term_id>`, `/api/class/<id>/arms`, `/api/class-subjects/<term_id>/<class_id>`, `/api/stream/<id>/subjects` | Class/subject selectors | `academics`/`results` |
| GET | `/api/student-scores/<id>/<term_id>` | Score sheet | `results` (branch-scoped) |

### Attendance
| Method | Path | Purpose | Gate |
|---|---|---|---|
| GET | `/api/check-attendance`, `/api/roster`, `/api/daily-summary`, `/api/school-days/<week_id>` | Registers/summaries | `attendance` (class-scoped) |
| POST | `/api/mark` | Mark attendance | `attendance` + form-teacher of class |

### Analytics, exams & predictions
| Method | Path | Purpose | Gate |
|---|---|---|---|
| GET | `/api/charts/*` (attendance-trend, enrollment-by-class, gender/religion-distribution, waec-grade/jamb-score-distribution) | Dashboard charts | relevant module |
| GET | `/api/exam/<id>/stats`, `/api/jamb/score-distribution/<year>` | Exam stats | `external_exams` |
| GET | `/api/predict-jamb/<id>`, `/api/predictions/<id>`, `/api/student-risk/<id>`, `/api/at-risk` | Predictions | `external_exams` (branch-scoped) |
| GET | `/api/report/{weekly,termly,week-totals,alerts}` | Report data | `reports` |

### Finance / comms / other modules
Finance, communication, HR, CBT and admissions expose their own JSON actions
under their blueprints (e.g. `/finance/payments/...`, `/comms/...`) using the
`X-Requested-With: fetch` convention rather than an `/api/` prefix; they are
gated by the `finance` / `communication` / `hr` / `cbt` / `admissions` modules
and their sub-sections, with object-level branch checks on every by-id route.

### External (not session-authed)
| Method | Path | Purpose | Gate |
|---|---|---|---|
| POST | `/parent/pay/webhook` | Paystack webhook | HMAC-SHA512 signature, idempotent, CSRF-exempt |
| POST | `/check-result` | Public result checker | rate-limited + scratch-card PIN, card-to-student binding |

## Checklist when adding a JSON endpoint
1. Put it behind the correct module/sub-section (so the `before_request` gates cover it).
2. For any by-id resource, add the object-level ownership check.
3. Mutating? It already requires CSRF via the global gate — don't exempt it.
4. Return JSON errors via `abort(...)`/the shared handlers, not ad-hoc HTML.
5. Add it to this inventory.
