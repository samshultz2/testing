#!/usr/bin/env python3
"""
One-time data migration: SQLite -> PostgreSQL.

Copies every table defined on the app's SQLAlchemy metadata from the existing
SQLite database into a PostgreSQL database, then fixes up the Postgres
sequences so future inserts don't collide on primary keys.

Because it drives off ``db.metadata`` (the same model definitions the app
uses), it covers all tables automatically and converts column types
(booleans, datetimes, JSON, ...) correctly on the way across.

Usage
-----
    # PostgreSQL must already be running and the target DB/user created.
    export DATABASE_URL="postgresql+psycopg://posyhub:posyhub@localhost:5432/posyhub"

    # default source is instance/school.db
    python scripts/sqlite_to_postgres.py

    # or point at a specific source / target explicitly
    python scripts/sqlite_to_postgres.py \
        --sqlite instance/school.db \
        --postgres "postgresql+psycopg://posyhub:posyhub@localhost:5432/posyhub"

    # preview only (no writes): see row counts that WOULD be copied
    python scripts/sqlite_to_postgres.py --dry-run

Safety
------
* The script refuses to run if the target Postgres database already contains
  data, unless you pass ``--force`` (which TRUNCATEs the target tables first).
* It runs inside a single transaction per table and stops on the first error.
"""
import argparse
import os
import sys

# Make sure we can import the app's models when run from the repo root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine, select, func, text  # noqa: E402

from models import db  # noqa: E402  (registers all tables on db.metadata)


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def _normalize_pg_url(url):
    """Default plain ``postgresql://`` URLs to the psycopg (v3) driver."""
    if url.startswith('postgresql://'):
        return url.replace('postgresql://', 'postgresql+psycopg://', 1)
    return url


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--sqlite',
                   default=os.path.join(BASE_DIR, 'instance', 'school.db'),
                   help='Path to the source SQLite file (default: instance/school.db)')
    p.add_argument('--postgres',
                   default=os.environ.get('DATABASE_URL', ''),
                   help='Target PostgreSQL URL (default: $DATABASE_URL)')
    p.add_argument('--dry-run', action='store_true',
                   help='Report what would be copied without writing anything')
    p.add_argument('--force', action='store_true',
                   help='TRUNCATE target tables first if the target is not empty')
    p.add_argument('--batch', type=int, default=1000,
                   help='Insert batch size (default: 1000)')
    return p.parse_args()


def main():
    args = parse_args()

    if not os.path.exists(args.sqlite):
        sys.exit(f'ERROR: SQLite source not found: {args.sqlite}')

    pg_url = _normalize_pg_url(args.postgres.strip())
    if not args.dry_run and not pg_url:
        sys.exit('ERROR: no PostgreSQL target. Set $DATABASE_URL or pass --postgres.')

    src = create_engine('sqlite:///' + os.path.abspath(args.sqlite))
    metadata = db.metadata
    # Insert parents before children so foreign keys resolve.
    ordered_tables = metadata.sorted_tables

    print(f'Source SQLite : {args.sqlite}')
    print(f'Target Postgres: {pg_url or "(dry-run, none)"}')
    print(f'Tables on model metadata: {len(ordered_tables)}')
    print('-' * 60)

    # --- which tables actually exist in the SQLite source? ---
    from sqlalchemy import inspect as sa_inspect
    src_tables = set(sa_inspect(src).get_table_names())

    if args.dry_run:
        total = 0
        with src.connect() as sc:
            for table in ordered_tables:
                if table.name not in src_tables:
                    print(f'  {table.name:<40} (absent in source, skipped)')
                    continue
                n = sc.execute(select(func.count()).select_from(table)).scalar() or 0
                total += n
                print(f'  {table.name:<40} {n:>8} rows')
        print('-' * 60)
        print(f'Total rows that would be copied: {total}')
        return

    dst = create_engine(pg_url)

    # 1. Create the schema in Postgres (idempotent).
    print('Creating schema in Postgres (create_all)...')
    metadata.create_all(dst)

    # 2. Guard against clobbering an already-populated target.
    nonempty = []
    with dst.connect() as dc:
        for table in ordered_tables:
            try:
                n = dc.execute(select(func.count()).select_from(table)).scalar() or 0
            except Exception:
                n = 0
            if n:
                nonempty.append((table.name, n))
    if nonempty and not args.force:
        print('\nERROR: target already contains data:')
        for name, n in nonempty:
            print(f'  {name}: {n} rows')
        sys.exit('Refusing to overwrite. Re-run with --force to TRUNCATE first.')

    if nonempty and args.force:
        print('--force: truncating target tables...')
        with dst.begin() as dc:
            names = ', '.join(f'"{t.name}"' for t in ordered_tables
                              if t.name in {n for n, _ in nonempty})
            dc.execute(text(f'TRUNCATE {names} RESTART IDENTITY CASCADE'))

    # 3. Copy table by table.
    grand_total = 0
    with src.connect() as sc:
        for table in ordered_tables:
            if table.name not in src_tables:
                print(f'  {table.name:<40} (absent in source, skipped)')
                continue
            rows = [dict(r) for r in sc.execute(table.select()).mappings()]
            if not rows:
                print(f'  {table.name:<40} {0:>8} rows')
                continue
            with dst.begin() as dc:
                for i in range(0, len(rows), args.batch):
                    dc.execute(table.insert(), rows[i:i + args.batch])
            grand_total += len(rows)
            print(f'  {table.name:<40} {len(rows):>8} rows  ✓')

    # 4. Reset sequences so the next INSERT picks up after the max id.
    print('-' * 60)
    print('Resetting Postgres sequences...')
    reset = 0
    with dst.begin() as dc:
        for table in ordered_tables:
            for col in table.primary_key.columns:
                if not (col.type.python_type is int):
                    continue
                seq = dc.execute(
                    text("SELECT pg_get_serial_sequence(:t, :c)"),
                    {'t': table.name, 'c': col.name},
                ).scalar()
                if not seq:
                    continue
                dc.execute(text(
                    f'SELECT setval(:seq, '
                    f'(SELECT COALESCE(MAX("{col.name}"), 0) + 1 FROM "{table.name}"), false)'
                ), {'seq': seq})
                reset += 1
    print(f'Sequences reset: {reset}')
    print('-' * 60)
    print(f'DONE. Copied {grand_total} rows across {len(ordered_tables)} tables.')


if __name__ == '__main__':
    main()
