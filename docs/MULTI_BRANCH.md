# Multi-branch support

A school may run several branches sharing one structure. Some users are
**central** (see every branch); others are **branch**-scoped.

## Approach

Single database, branch-aware rows (shared-schema multi-tenancy): branch-owned
records carry a `branch_id`; a scoping layer (Stage 2) filters queries for
branch users while central users bypass it.

## Stages

1. **Branch foundation — DONE.** `Branch` model + `branch_id` columns +
   `User.scope`/`branch_id`. Existing data is backfilled to a default branch
   (**Jemila** on this install); existing admins become `central`. No query
   filtering yet — pure groundwork, no behaviour change.
2. **Scoping layer — DONE.** `utils/branch_scope.py` decides the branch(es) in
   view; central users see all by default with a header **branch switcher**
   (`/set-branch`), branch users are locked to their own. Applied to the
   Students and Staff lists + dashboard counts, with a record-access guard on
   student/staff detail pages and auto branch-stamping on create. More modules
   (finance, CBT, results, attendance) adopt `scope_query`/`branch_for_new`
   incrementally.
3. **Role presets — DONE.** The school's hierarchy (Director of Studies, Exams &
   Standards, IT, Principal, Headmaster, HODs, Headteachers, Teachers, Bursar)
   as configurable one-click presets in `utils/role_presets.py`. The user
   add/edit form has a **Quick preset** picker that pre-fills role, branch scope
   and module checkboxes (still fully editable). Presets are plain data — other
   schools edit the dict or ignore it.
4. **Section/stream filters — DONE.** `utils/org_scope.py` narrows a branch user
   to a section group (Principal = secondary, Headmaster = nursery/primary) and/or
   a subject stream (HOD Arts = Arts+Commercial, HOD Sciences = Science).
   `SchoolClass.section` (auto-classified) + `User.section`/`User.stream` drive it;
   applied to the students list (by current enrolment's class section, and by
   `Student.stream`) and the subjects list (`Subject.category`). Also fixed: only
   actual teachers are limited to assigned classes — other staff use these scopes.
5. **Bursar Sales & Inventory — DONE.** A `sales` module (`models/models_sales.py`,
   `routes/sales.py`): products + stock, point-of-sale (multi-item, optional
   student buyer, auto stock decrement, can't oversell), receipts, history and a
   low-stock dashboard — all branch-scoped. Added to the `bursar` preset and the
   sidebar.

## Stage 1 details

- **Model:** `models/models_branch.py::Branch` (name, code, address, phone,
  `is_default`, `is_active`). `Branch.get_default()` returns the default branch.
- **Scoped tables (carry `branch_id`):** `students`, `teachers`,
  `class_arm_assignments`, `staff_members`, `users`. More tables join in Stage 2
  as filtering requires.
- **User scope:** `User.scope` (`central`/`branch`) + `User.branch_id`.
  `User.is_central` is true for `central` scope or admin roles.
- **Migration/seed:** `init_db` → `_seed_branches()` creates the default branch
  once (name from `POSYHUB_DEFAULT_BRANCH`, default `Jemila`), backfills any
  `NULL` `branch_id` to it, and sets existing admins to `central`. Idempotent.
- **Admin UI:** Settings → **Branches** (`/settings/branches`) to add/edit
  branches and set the default. User add/edit forms gained a **Branch scope**
  selector (central vs a specific branch).

Single-branch / other schools: one branch exists and every user is effectively
scoped to it (or central), so the feature is invisible until more branches and
branch-scoped users are added.

## Stage 2 details

- **`utils/branch_scope.py`** — `is_central()`, `viewing_branch_id()`
  (`None` = all branches), `scope_query(query, Model)`, `can_access_branch(id)`,
  `branch_for_new(form_id)`, `set_session_scope(user)`.
- **Session:** login stores `scope` + `branch_id`; central users' picked branch
  lives in `view_branch_id` (set by `/set-branch`, `'all'` clears it).
- **Header switcher:** central users get an "All branches / <branch>" dropdown;
  branch users see their branch name as a static label.
- **Applied so far:** Students list + dashboard counts + detail guard + create
  stamping; Staff list + detail guard + create stamping.
- **To extend a module:** wrap its list query with `scope_query(...)`, stamp new
  records with `branch_for_new(...)`, and guard detail pages with
  `can_access_branch(...)`.
