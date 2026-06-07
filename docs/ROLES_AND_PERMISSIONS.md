# Roles & Permissions

PosyHub controls access on three independent layers. Together they decide
*who can sign in*, *which sections they see*, and *whether they may change
anything*.

## 1. Roles (coarse)

Every `User` has a `role` (stored on `users.role`):

| Role | Meaning |
|------|---------|
| `super_admin` | Full access; can manage other super admins. |
| `admin` | Full access to every module. Bypasses all module gates. |
| `teacher` | Class/subject-scoped access (see "Teacher scoping"). |
| `staff` | Restricted user — **no** modules by default; grant them explicitly. |
| `readonly` | May browse but never create/edit/delete (see "View-only"). |

Legacy password login (when enabled) signs in as `admin`.

`is_admin()` ⇒ role in (`super_admin`, `admin`). Admins skip every gate below.

## 2. Module access (fine-grained)

The grantable sections are defined once in `utils/access_control.py::MODULES`
(students, admissions, academics, events, attendance, results, external_exams,
cbt, timetable, promotion, finance, communication, hr, library, reports).

Each blueprint is mapped to a module in `BLUEPRINT_MODULE`. A `before_request`
gate (`enforce_module_access`) resolves the request's blueprint → module and:

- **Admins** → always allowed.
- **Non-admins** → allowed only if the module is in `user_modules()`:
  - the user's explicit `allowed_modules` (JSON list on the user), **or**
  - if none set, the role default from `ROLE_DEFAULT_MODULES`
    (`teacher` and `readonly` get sensible defaults; `staff` gets nothing).
- Denied requests get a `403` for fetch/JSON, otherwise a flash + redirect to
  the dashboard.

The sidebar mirrors this: each section is wrapped in
`{% if can_access_module('<key>') %}`, so users only see what they can open.
Admin-only areas (Tools, Settings, Users, Audit) are gated on the role directly.

**Granting modules**

- Per user: the *Module Access* checkbox grid on the user add/edit pages.
- In bulk: the **Permission Matrix** (`/users/matrix`) — a users × modules grid
  editable in one place.

Leaving every box unticked falls back to the role default. Admins ignore the
list entirely.

## 3. View-only (write protection)

Independent of modules, a user can be made **view-only**:

- the `readonly` role implies it, **or**
- any user with the `view_only` flag set (checkbox on add/edit, or the matrix).

`enforce_read_only` (a `before_request` gate) blocks every unsafe HTTP method
(`POST`/`PUT`/`PATCH`/`DELETE`) for these users — they can read every page they
have module access to but cannot change anything. Their own account actions
(login, logout, change password) remain allowed.

## Teacher scoping (orthogonal)

For `teacher` users the `Teacher` profile additionally limits access to the
specific classes/subjects assigned to them (`can_mark_attendance`,
`can_enter_results`, class/subject assignments). This is enforced by the
`*_access_required` decorators and `get_accessible_class_ids()` and is unrelated
to the module gate above.

## Auditing

Every permission change is recorded in the audit log via `log_action`:

- `user.create` — new user (role, modules, view-only).
- `user.permissions` — any change to role / modules / view-only (old → new),
  whether made on the edit page or the matrix.

## Where it lives

| Concern | File |
|---------|------|
| Modules, gates, role defaults, decorators | `utils/access_control.py` |
| Gate registration | `app.py` (`before_request`) |
| User CRUD + matrix + audit | `routes/users.py` |
| Sidebar gating | `templates/base.html` |
| User forms / matrix UI | `templates/users/*.html` |
| Tests | `tests/test_permissions.py` |

## Extending

To add a new gated section: add its key to `MODULES`, map its blueprint in
`BLUEPRINT_MODULE`, and wrap its sidebar section in `can_access_module('<key>')`.
Nothing else is required — the matrix and user forms read `MODULES` directly.
