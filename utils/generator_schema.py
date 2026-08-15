"""Lazy, idempotent schema self-heal for the per-branch timetable generator.

The generator was originally school-global; branch_id was added to its 12 root
tables so each branch keeps its own teachers/classes/subjects/rules/results.
Existing tenant DBs (created before the split) won't get the column from
``create_all``, so this adds it once per engine, backfills every existing row to
the default (HQ) branch, and swaps the three formerly-global unique constraints
(gen_subjects, gen_streams, gen_settings) for their per-branch equivalents.

Mirrors utils/hr_schema.py: best-effort, guarded, cached per engine URL. Safe to
call at the top of any generator request.
"""
from __future__ import annotations

_ensured = set()   # engine URLs already healed this process

# Root generator tables that gained a branch_id (children scope via their parent).
_TABLES = (
    'gen_teachers', 'gen_subjects', 'gen_subject_configs', 'gen_rooms',
    'gen_streams', 'gen_class_configs', 'gen_teacher_assignments',
    'gen_timetable_rules', 'gen_timetable_results', 'gen_settings',
    'gen_subject_clash_rules', 'gen_combined_class_rules',
)

# Formerly-global uniques → their new per-branch form. Only applied on Postgres;
# fresh SQLite (dev/test) DBs get the right constraint from create_all.
_UNIQUE_SWAPS = {
    'gen_subjects': ('uq_gen_subject_branch_name_level', ['branch_id', 'name', 'school_level']),
    'gen_streams': ('uq_gen_stream_branch_name', ['branch_id', 'name']),
    'gen_settings': ('uq_gen_setting_branch_key', ['branch_id', 'setting_key']),
}


def _cols(inspector, table):
    try:
        return {c['name'] for c in inspector.get_columns(table)}
    except Exception:
        return None


def _default_branch_id():
    try:
        from models import Branch
        b = Branch.get_default()
        return b.id if b else None
    except Exception:
        return None


def _swap_uniques_postgres(conn):
    """Drop any unique constraint on the three tables that does NOT include
    branch_id, then add the per-branch composite. Names are looked up so we
    don't depend on Postgres' auto-generated constraint names."""
    from sqlalchemy import text
    for table, (new_name, cols) in _UNIQUE_SWAPS.items():
        try:
            rows = conn.execute(text("""
                SELECT con.conname,
                       ARRAY(SELECT a.attname FROM unnest(con.conkey) k
                             JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k) AS cols
                FROM pg_constraint con
                WHERE con.conrelid = :t::regclass AND con.contype = 'u'
            """), {'t': table}).fetchall()
        except Exception:
            continue
        have_new = False
        for conname, concols in rows:
            concols = list(concols or [])
            if 'branch_id' not in concols:
                try:
                    conn.execute(text(f'ALTER TABLE {table} DROP CONSTRAINT "{conname}"'))
                except Exception:
                    pass
            elif set(concols) == set(cols):
                have_new = True
        if not have_new:
            try:
                conn.execute(text(
                    f'ALTER TABLE {table} ADD CONSTRAINT {new_name} '
                    f'UNIQUE ({", ".join(cols)})'))
            except Exception:
                pass


def ensure_generator_schema():
    """Add branch_id to the generator tables on the current tenant DB, backfill
    it to the default branch, and fix the per-branch uniques. No-op after the
    first call per engine; never raises."""
    from models import db
    try:
        engine = db.engine
    except Exception:
        return
    key = str(getattr(engine, 'url', 'default'))
    if key in _ensured:
        return

    from sqlalchemy import inspect, text
    try:
        insp = inspect(engine)
        is_pg = engine.dialect.name == 'postgresql'
    except Exception:
        _ensured.add(key)
        return

    default_bid = _default_branch_id()

    try:
        with engine.begin() as conn:
            for table in _TABLES:
                cols = _cols(insp, table)
                if cols is None:
                    continue                     # table absent on this DB — skip
                if 'branch_id' not in cols:
                    try:
                        conn.execute(text(f'ALTER TABLE {table} ADD COLUMN branch_id INTEGER'))
                    except Exception:
                        pass
                # Backfill existing (pre-split) rows to the default/HQ branch.
                if default_bid is not None:
                    try:
                        conn.execute(text(
                            f'UPDATE {table} SET branch_id = :b WHERE branch_id IS NULL'),
                            {'b': default_bid})
                    except Exception:
                        pass
            if is_pg:
                _swap_uniques_postgres(conn)
    except Exception:
        pass
    _ensured.add(key)
