"""Lazy, idempotent data self-heal for academics branch tagging.

Class-arm assignments created before branch tagging (or via a path that omitted
it) carry ``branch_id = NULL``; once a specific branch is selected they vanish
from every branch-scoped list (attendance, exam halls, contributions, …). This
backfills those rows to the school's default branch — the branch a record gets
when none is chosen — so they belong to (and show under) that branch.

Runs at most once per tenant engine and never raises.
"""
_healed = set()


def _default_branch_id():
    try:
        from models import Branch
        b = Branch.get_default()
        return b.id if b else None
    except Exception:
        return None


def ensure_class_arm_branch():
    """Backfill ``class_arm_assignments.branch_id`` (NULL -> default branch) once
    per tenant DB engine. Best-effort; safe to call on every request."""
    from models import db
    try:
        engine = db.session.get_bind()
    except Exception:
        try:
            engine = db.engine
        except Exception:
            return
    if engine is None:
        return
    key = str(getattr(engine, 'url', 'default'))
    if key in _healed:
        return

    default_bid = _default_branch_id()
    if default_bid is None:
        return                                   # no branch yet — retry next request

    from sqlalchemy import text
    try:
        with engine.connect() as base:
            conn = base.execution_options(isolation_level='AUTOCOMMIT')
            conn.execute(text(
                'UPDATE class_arm_assignments SET branch_id = :b WHERE branch_id IS NULL'),
                {'b': default_bid})
        _healed.add(key)
    except Exception:
        pass                                     # transient — retry on a later request
