# Term / Session Scoping Audit

A review of every PosyHub module to confirm that data which **should** be scoped
to the active term is, and data that **should** cut across terms (historical /
session-level / date-level) does. Conducted across models and routes.

## Scoping model

- **Term-based** — belongs to one term; lists default to the active term.
  (`Term.is_active`)
- **Session-based** — spans the three terms of an academic year.
  (`AcademicSession.is_active`)
- **Date-based** — keyed by calendar date; not constrained by term.
- **Entity-based** — keyed to a person/thing that persists across terms.

## Findings

| Module | Scope | Verdict |
|--------|-------|---------|
| **Finance** — fees, payments, discounts, expenses | Term-based (`term_id`, defaults to active term) | ✅ Correct |
| **Finance** — collections day-book | Date-based, **now** with optional term filter | ✅ Fixed |
| **CBT** — exams & attempts | Term-based (`CBTExam.term_id`; attempts inherit); dashboard has an "all terms" view for history | ✅ Correct |
| **Attendance** — registers, weeks | Term-based (via `Week.term_id` / `ClassArmAssignment.term_id`); past terms browsable | ✅ Correct |
| **Results** — scores, broadsheet, report cards | Term-based (`ClassSubject.term_id`, `TermResult.term_id`, `TermSummary.term_id`) | ✅ Correct |
| **Subjects** — catalogue | Global (linked to a term only at `ClassSubject` level) | ✅ Correct |
| **External Exams** — WAEC / JAMB | Historical, keyed by `exam_year` — **deliberately not** term-bound | ✅ Correct |
| **Mock JAMB** | Session-based (`session_id`); analytics span sessions | ✅ Correct |
| **Exam analytics / predictions** | Cross-term / historical by design | ✅ Correct |
| **Communication** — messages | Flat history log; `Message.term_id` optional; contacts picker can filter by term | ✅ Correct |
| **Communication** — announcements | Date-range driven, global | ✅ Correct |
| **HR** — staff, leave, attendance | Entity / date-based (people persist across terms) | ✅ Correct |
| **HR** — payroll | Month/year-based (`PayrollRun.year/month`) | ✅ Correct |
| **Library** — catalogue & loans | Date-based; a book/loan is not term-bound | ✅ Correct |
| **Admissions** — applicants | Session-based (`Applicant.session_id`); placement resolves to a term on conversion | ✅ Correct |
| **Events / Calendar** | Date-based with an optional `term_id` tag; calendar shows all events in a date range | ✅ Correct |
| **Promotion / graduation** | Session-based (`from_session_id` / `to_session_id`) | ✅ Correct |

## Change made

The **Finance collections day-book** (`/finance/collections`) previously summed
every payment in a date range regardless of term, with nothing in the UI saying
so. A cash day-book *should* span terms by default (you reconcile money taken on
a given day, not per term), but there was no way to narrow it. We added:

- An optional `term_id` filter on the route and CSV export
  (`routes/finance.py:_collections_query`).
- A **Term** dropdown ("All terms" default) plus an "all terms / single term"
  badge so the scope is explicit (`templates/finance/collections.html`).

No other gaps were found — every other module is scoped as it should be.
