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
    try:
        insp = inspect(engine)
        existing = {c['name'] for c in insp.get_columns('students')}
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
        missing = [(n, d) for n, d in adds.items() if n not in existing]
        if missing:
            with engine.begin() as conn:
                for name, ddl in missing:
                    try:
                        conn.execute(text(f'ALTER TABLE students ADD COLUMN {name} {ddl}'))
                    except Exception:
                        pass   # concurrent add / already exists
    except Exception:
        db.session.rollback()

    if seed:
        try:
            if University.query.first() is None:
                from utils.university_seed import seed_university_data
                seed_university_data()
        except Exception:
            db.session.rollback()

    _ensured.add(key)
