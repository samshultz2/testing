#!/usr/bin/env python3
"""One-shot: add the university-aspiration columns/tables to EVERY database and
report exactly what happened.

This is a database-per-tenant app: the platform DB (DATABASE_URL) plus one
database per school. A background job (e.g. the daily exam-analytics refresh)
binds a school's DB and queries ``students`` — so if that school's table is
missing the aspiration columns you get::

    column students.target_university_id does not exist

Run this once to heal the platform DB and every registered school's DB:

    python scripts/heal_aspiration_columns.py

It adds each missing column in its own transaction and prints a per-database
result, including the real error if an ALTER is refused (e.g. the DB role does
not own the students table). Safe to run repeatedly.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# name -> column type. Kept in sync with utils/university_schema.py.
COLUMNS = [
    ('target_university_id', 'INTEGER'),
    ('target_course_id', 'INTEGER'),
    ('target_department', 'VARCHAR(120)'),
    ('target2_university_id', 'INTEGER'),
    ('target2_course_id', 'INTEGER'),
    ('career_goal', 'VARCHAR(120)'),
    ('admission_status', 'VARCHAR(20)'),
    ('admitted_university_id', 'INTEGER'),
    ('admitted_course_id', 'INTEGER'),
]


def _heal_bound(label):
    """Heal whatever database ``db`` is currently bound to. Returns True on
    success (all columns present)."""
    from models import db
    from sqlalchemy import inspect, text

    engine = db.engine
    try:
        who = db.session.execute(text('SELECT current_user')).scalar()
    except Exception:
        who = '?'
    print(f'\n▶ {label}  [{engine.url.database or engine.url} as {who}]')

    # Make sure the feature's own tables exist first (harmless if present).
    try:
        from models.models_university import University, Course, UniversityCourse, StudentScholarship
        for model in (University, Course, UniversityCourse, StudentScholarship):
            model.__table__.create(bind=engine, checkfirst=True)
    except Exception as exc:
        print(f'  · table create note: {str(exc).splitlines()[0]}')

    try:
        existing = {c['name'] for c in inspect(engine).get_columns('students')}
    except Exception as exc:
        print(f'  ✗ cannot read students table: {str(exc).splitlines()[0]}')
        return False

    added, failed = 0, []
    for name, ddl in COLUMNS:
        if name in existing:
            continue
        try:
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE students ADD COLUMN IF NOT EXISTS {name} {ddl}'))
            added += 1
        except Exception:
            try:
                with engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE students ADD COLUMN {name} {ddl}'))
                added += 1
            except Exception as exc2:
                failed.append((name, str(exc2).splitlines()[0]))

    present = {c['name'] for c in inspect(engine).get_columns('students')}
    missing = [n for n, _ in COLUMNS if n not in present]
    for n, err in failed:
        print(f'  ✗ {n}: {err}')
    print(f'  added {added}, already {len(COLUMNS) - added - len(missing)}, missing {len(missing)}'
          + (f' → {missing}' if missing else '  ✓'))
    return not missing


def main():
    from app import create_app

    ok_all = True
    # 1) the platform / bound database
    app = create_app()
    with app.app_context():
        ok_all &= _heal_bound('platform database')

    # 2) every registered school's database (no-op for a single-tenant deploy)
    try:
        from utils import tenancy, tenant_admin
        tenancy.init_control_plane()
        targets = tenant_admin.active_tenants()
    except Exception as exc:
        print(f'\n(no tenant registry — single-database deploy: {str(exc).splitlines()[0]})')
        targets = []

    for t in targets:
        try:
            tapp = tenant_admin.tenant_app(t.database_url)
            with tapp.app_context():
                ok_all &= _heal_bound(f'school: {t.subdomain}')
        except Exception as exc:
            ok_all = False
            print(f'\n▶ school: {t.subdomain}  ✗ {str(exc).splitlines()[0]}')

    print()
    if ok_all:
        print('SUCCESS — every database has the aspiration columns. The error will stop.')
        return 0
    print('SOME DATABASES STILL MISSING COLUMNS — see the ✗ lines above. If it is a '
          'permissions error, run the ALTER TABLE as that database\'s owner.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
