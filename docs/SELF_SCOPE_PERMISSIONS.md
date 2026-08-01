# Self-scope permissions

The finest tier of the permission model. A **self-scope capability** lets a user
act on **their own record only** — never anyone else's — without granting access
to the surrounding module.

This sits on top of the existing tiers:

```
module            e.g.  hr                     (all HR)
  └─ subsection   e.g.  hr.payroll             (all staff's payroll)
       └─ capability  hr.self_payroll          (MY payslip only)
```

## How it works

- **Storage & levels.** Self-scope keys are ordinary `module.sub` permission
  entries carrying a `view` / `edit` level, stored on the user (and grantable via
  permission groups) exactly like any other grant. `view` = read own; `edit` =
  act on own (e.g. clock in).
- **Never unlocks the module.** Every key is listed in `CAPABILITY_SUBSECTIONS`,
  so `module_level()` ignores it — a user whose only HR grant is
  `hr.self_payroll` has **no** HR-module access and cannot browse other staff.
- **Reachability.** Because the module gate (`enforce_module_access`) would
  otherwise block a capability-only user from the blueprint, self-service
  endpoints are either listed in `_ALWAYS_ALLOWED_ENDPOINTS` (and enforce the
  capability in-view) or live on a non-gated blueprint such as `auth` (the
  `/account` page).
- **The "own record" boundary is enforced by the route.** The capability says
  *whether*; the query says *whose* — every self-service query filters to the
  caller's linked `StaffMember` (`user_id == current user`). This is the line
  that must never be dropped when adding a new one.
- **UI.** Keys are registered in `MODULE_SUBSECTIONS`, so they surface
  automatically in the user **and** group permission editors (rendered as
  "Special capabilities" with a View / View&edit selector). The `/account`
  self-service page shows each block only if the caller holds its capability.

Registry lives in `utils/access_control.py`:
`SELF_SCOPE_SUBSECTIONS`, `CAPABILITY_SUBSECTIONS`, `MODULE_SUBSECTIONS`, and the
`self_scope_level(key)` helper. Read-side assemblers live in
`utils/self_service.py` (`profile_self_service`) and `utils/hr.py`
(`hr_self_service`).

## Current capabilities

| Key | Level meaning | Surface |
| --- | --- | --- |
| `hr.self_attendance` | view = see own attendance · edit = clock in/out | /account → My attendance (+ toggle button → `hr.clock`) |
| `hr.self_payroll` | view own payslips | /account → My payslips |
| `hr.self_deductions` | view own salary deductions (read-only) | /account → My deductions |
| `hr.self_leave` | view own leave records + balances | /account → My leave |
| `library.self_loans` | view own borrowed books | /account → My library loans |

## Adding a self-scope capability to another module

1. **Register** `('<module>.self_<thing>')` in `CAPABILITY_SUBSECTIONS` and
   `SELF_SCOPE_SUBSECTIONS`, and add a labelled entry under
   `MODULE_SUBSECTIONS['<module>']` (label it "… (self)").
2. **Assemble** the read data in `utils/self_service.py` (or the module's util),
   gating on `self_scope_level('<module>.self_<thing>')` and filtering strictly
   to the caller's own record. Add it to `profile_self_service`.
3. **Render** a card on `templates/auth/profile.html`, shown only when the
   assembler returned data.
4. **Writes** (if any) get a dedicated endpoint that re-checks the capability at
   `edit` level and only ever mutates the caller's own row; add the endpoint to
   `_ALWAYS_ALLOWED_ENDPOINTS` if it lives on a module-gated blueprint.
5. **Test** registration, own-only scoping (a second user's data must not leak),
   module access denied, and the write path's level check. See
   `tests/test_hr_self_service.py` and `tests/test_library_self_loans.py`.

Modules whose "own record" view is already served by a dedicated portal
(students/parents, alumni, CBT candidates) don't need a staff self-scope grant —
those audiences don't sign in to the staff app.
