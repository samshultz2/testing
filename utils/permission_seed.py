"""Seed the built-in role presets as central permission-group templates.

One idempotent helper used by every path that can bring a tenant DB into being
or up to date:
  - models.init_db (single-school / dev boot)
  - provisioning._seed (a brand-new tenant)
  - tenant_runtime._engine_for (self-heal an existing tenant on first use)

Central templates (branch_id NULL). Idempotent per name — a group an admin has
already created/edited under the same name is left untouched. Admin presets are
skipped (admins bypass module gates); the plain 'teacher' role is seeded from
its default module set.
"""


def seed_permission_groups(session):
    """Seed the default groups into the database behind ``session``.

    ``session`` is any SQLAlchemy session/scoped-session (the flask-sqlalchemy
    ``db.session`` or a plain ``Session(engine)`` bound to a tenant DB). Returns
    the number of groups created.
    """
    from models import PermissionGroup
    from utils.role_presets import ROLE_PRESETS
    from utils.access_control import ROLE_DEFAULT_MODULES, MODULES

    created = 0
    for key, p in ROLE_PRESETS.items():
        if p.get('role') == 'admin':
            continue                       # admins bypass module gates
        mods = [m for m in (p.get('modules') or []) if m in MODULES]
        if not mods and p.get('role') == 'teacher':
            mods = sorted(ROLE_DEFAULT_MODULES.get('teacher', ()))
        if not mods:
            continue
        name = p.get('label') or key
        if session.query(PermissionGroup).filter_by(name=name, branch_id=None).first():
            continue
        g = PermissionGroup(name=name, description=p.get('description'),
                            branch_id=None, is_active=True)
        g.set_permissions({m: 'edit' for m in mods})
        session.add(g)
        created += 1
    if created:
        session.commit()
    return created
