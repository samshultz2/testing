"""Lazy, idempotent schema self-heal for the university-aspiration feature.

Creates the universities / courses / university_courses tables and the three
target_* columns on students on whatever tenant DB is currently bound, once per
engine, best-effort. Seeds the starter reference data the first time the tables
are empty (the admin can edit it afterwards). Mirrors utils/hr_schema.py.
"""
from __future__ import annotations

_ensured = set()   # engine URLs already healed this process


def ensure_university_schema(seed=True):
    """Ensure the aspiration tables + student columns exist on the bound DB, and
    seed the starter data if empty. No-op after the first call per engine."""
    from models import db
    try:
        engine = db.engine
    except Exception:
        return
    key = str(getattr(engine, 'url', 'default'))
    if key in _ensured:
        return

    from sqlalchemy import inspect, text
    from models.models_university import University, Course, UniversityCourse, StudentScholarship
    try:
        for model in (University, Course, UniversityCourse, StudentScholarship):
            model.__table__.create(bind=engine, checkfirst=True)
    except Exception:
        db.session.rollback()

    # Student columns (create_all won't add columns to the existing table).
    adds = {
        'target_university_id': 'INTEGER',
        'target_course_id': 'INTEGER',
        'target_department': 'VARCHAR(120)',
        'target2_university_id': 'INTEGER',
        'target2_course_id': 'INTEGER',
        'career_goal': 'VARCHAR(120)',
        'admission_status': 'VARCHAR(20)',
        'admitted_university_id': 'INTEGER',
        'admitted_course_id': 'INTEGER',
    }
    columns_ok = False
    errors = {}
    try:
        existing = {c['name'] for c in inspect(engine).get_columns('students')}
        # Each ALTER in its OWN transaction: on Postgres one failed statement
        # aborts the whole transaction, so a batched loop would silently skip the
        # rest after the first "already exists". Per-column keeps them independent.
        for name, ddl in adds.items():
            if name in existing:
                continue
            try:
                with engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE students ADD COLUMN IF NOT EXISTS {name} {ddl}'))
            except Exception as exc:
                # Fall back to plain ADD COLUMN for engines without IF NOT EXISTS.
                try:
                    with engine.begin() as conn:
                        conn.execute(text(f'ALTER TABLE students ADD COLUMN {name} {ddl}'))
                except Exception as exc2:
                    errors[name] = str(exc2 or exc)
        # Verify before caching: only mark this engine "done" when every column is
        # really present, so a transient failure retries on the next call instead
        # of being permanently skipped.
        present = {c['name'] for c in inspect(engine).get_columns('students')}
        columns_ok = all(n in present for n in adds)
    except Exception:
        db.session.rollback()

    # Surface WHY a heal failed instead of swallowing it — a persistent failure
    # here (e.g. the app's DB role does not own the students table, so it cannot
    # ALTER it) needs a human to run the migration as the table owner.
    if not columns_ok and errors:
        try:
            from flask import current_app
            current_app.logger.error(
                'university aspiration self-heal could NOT add student columns %s — '
                'run the ALTER TABLE statements manually as the DB owner. First error: %s',
                sorted(errors), next(iter(errors.values())))
        except Exception:
            pass

    if seed:
        try:
            if University.query.first() is None:
                from utils.university_seed import seed_university_data
                seed_university_data()
        except Exception:
            db.session.rollback()

    if columns_ok:
        _ensured.add(key)
