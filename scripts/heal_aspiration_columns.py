#!/usr/bin/env python3
"""One-shot: add the university-aspiration columns to the students table and
report exactly what happened.

Run this once if the exam-analytics refresh (or any page) fails with
``column students.target_university_id does not exist``. It uses the app's own
DATABASE_URL, adds each missing column in its own transaction, and prints a
clear per-column result — including the real database error if an ALTER is
refused (e.g. the app's role does not own the students table).

    python scripts/heal_aspiration_columns.py

Safe to run repeatedly: columns that already exist are left untouched.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app  # noqa: E402

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


def main():
    app = create_app()
    with app.app_context():
        from models import db
        from sqlalchemy import inspect, text

        engine = db.engine
        print(f'Database: {engine.url}')
        print(f'Connected as: ', end='')
        try:
            with engine.connect() as c:
                who = c.execute(text('SELECT current_user')).scalar()
            print(who)
        except Exception:
            print('(unknown — non-Postgres?)')

        existing = {c['name'] for c in inspect(engine).get_columns('students')}
        added, already, failed = [], [], []
        for name, ddl in COLUMNS:
            if name in existing:
                already.append(name)
                continue
            try:
                with engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE students ADD COLUMN {name} {ddl}'))
                added.append(name)
                print(f'  ✓ added   {name}')
            except Exception as exc:
                failed.append((name, str(exc).strip().splitlines()[0]))
                print(f'  ✗ FAILED  {name}: {str(exc).strip().splitlines()[0]}')

        present = {c['name'] for c in inspect(engine).get_columns('students')}
        missing = [n for n, _ in COLUMNS if n not in present]

        print()
        print(f'Added now : {len(added)}   Already present: {len(already)}   Failed: {len(failed)}')
        if not missing:
            print('SUCCESS — all aspiration columns are present. The error will stop.')
            return 0

        print(f'STILL MISSING: {missing}')
        print()
        print('The app cannot add these columns itself. Run the following as the DATABASE'
              ' OWNER / a superuser (in Termux: `psql <your_db_name>`), then restart the app:')
        print()
        print('  ALTER TABLE students')
        print(',\n'.join(f'    ADD COLUMN IF NOT EXISTS {n} {d}' for n, d in COLUMNS) + ';')
        return 1


if __name__ == '__main__':
    sys.exit(main())
