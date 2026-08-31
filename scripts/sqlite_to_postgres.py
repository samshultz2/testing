#!/usr/bin/env python3
"""
One-time data migration: SQLite -> PostgreSQL.

Copies every table defined on the app's SQLAlchemy metadata from the existing
SQLite database into a PostgreSQL database, then fixes up the Postgres
sequences so future inserts don't collide on primary keys.

Because it drives off ``db.metadata`` (the same model definitions the app
uses), it covers all tables automatically and converts column types
(booleans, datetimes, JSON, ...) correctly on the way across.

Referential integrity
----------------------
SQLite does not enforce foreign keys by default, so an existing SQLite file can
contain rows that reference parents which no longer exist (e.g. timetable
config pointing at deleted subjects). PostgreSQL *does* enforce foreign keys, so
those dangling rows cannot be inserted. To land a **consistent** database, this
script transitively prunes orphaned rows before loading and reports exactly
what it dropped. Use ``--strict`` to abort instead of pruning, so you can
inspect first.

Usage
-----
    export DATABASE_URL="postgresql+psycopg://posyhub:posyhub@localhost:5432/posyhub"

    python scripts/sqlite_to_postgres.py              # migrate (prunes orphans)
    python scripts/sqlite_to_postgres.py --dry-run    # preview counts + orphans
    python scripts/sqlite_to_postgres.py --if-empty   # no-op if target has data
    python scripts/sqlite_to_postgres.py --strict     # abort if orphans found
    python scripts/sqlite_to_postgres.py --force      # TRUNCATE target first

Safety
------
* Refuses to overwrite a populated target unless ``--force`` (TRUNCATE) or
  ``--if-empty`` (skip) is given.
* Never modifies the source SQLite file; pruning happens in memory only.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load DATABASE_URL (and friends) from a .env in the repo root if present, so
# this script "just works" the same way the app does. Real env vars win.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except Exception:
    pass

from sqlalchemy import create_engine, select, func, text, inspect as sa_inspect  # noqa: E402

from models import db  # noqa: E402  (registers all tables on db.metadata)


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def _normalize_pg_url(url):
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
                   help='Report what would be copied (and pruned) without writing')
    p.add_argument('--force', action='store_true',
                   help='TRUNCATE target tables first if the target is not empty')
    p.add_argument('--if-empty', action='store_true',
                   help='Exit successfully without copying if the target already '
                        'has data (use for automated/idempotent startup).')
    p.add_argument('--strict', action='store_true',
                   help='Abort if any orphaned (dangling-FK) rows are found, '
                        'instead of pruning them.')
    p.add_argument('--batch', type=int, default=1000,
                   help='Insert batch size (default: 1000)')
    return p.parse_args()


def load_source(src, ordered_tables, src_tables):
    """Read every present table fully into memory: {table_name: [rowdict, ...]}."""
    data = {}
    with src.connect() as sc:
        for table in ordered_tables:
            if table.name not in src_tables:
                continue
            data[table.name] = [dict(r) for r in sc.execute(table.select()).mappings()]
    return data


def prune_orphans(data, ordered_tables):
    """
    Transitively drop rows whose non-null foreign keys reference a parent row
    that isn't present. Loops until stable so cascades are handled. Mutates
    ``data`` in place and returns a list of (table, constraint_desc, dropped).
    """
    # Constraints to check: (child_table, [local_cols], parent_table, [referred_cols])
    constraints = []
    for table in ordered_tables:
        for fkc in table.foreign_key_constraints:
            local_cols = [el.parent.name for el in fkc.elements]
            parent_table = fkc.elements[0].column.table.name
            referred_cols = [el.column.name for el in fkc.elements]
            constraints.append((table.name, local_cols, parent_table, referred_cols))

    removed = {}
    while True:
        changed = False
        # Build current value sets for each (parent_table, tuple(referred_cols)).
        parent_keys = {}
        for child, local_cols, parent, referred_cols in constraints:
            key = (parent, tuple(referred_cols))
            if key not in parent_keys:
                rows = data.get(parent, [])
                parent_keys[key] = {tuple(r[c] for c in referred_cols) for r in rows}

        for child, local_cols, parent, referred_cols in constraints:
            rows = data.get(child)
            if not rows:
                continue
            valid_keys = parent_keys[(parent, tuple(referred_cols))]
            kept = []
            dropped = 0
            for r in rows:
                vals = tuple(r[c] for c in local_cols)
                # NULL in any FK column => not enforced (MATCH SIMPLE).
                if any(v is None for v in vals):
                    kept.append(r)
                elif vals in valid_keys:
                    kept.append(r)
                else:
                    dropped += 1
            if dropped:
                data[child] = kept
                desc = f"{','.join(local_cols)} -> {parent}"
                removed[(child, desc)] = removed.get((child, desc), 0) + dropped
                changed = True
        if not changed:
            break
    return sorted([(t, d, n) for (t, d), n in removed.items()])


def main():
    args = parse_args()

    if not os.path.exists(args.sqlite):
        sys.exit(f'ERROR: SQLite source not found: {args.sqlite}')

    pg_url = _normalize_pg_url(args.postgres.strip())
    if not args.dry_run and not pg_url:
        sys.exit('ERROR: no PostgreSQL target. Set $DATABASE_URL or pass --postgres.')

    src = create_engine('sqlite:///' + os.path.abspath(args.sqlite))
    metadata = db.metadata
    ordered_tables = metadata.sorted_tables  # parents before children
    src_tables = set(sa_inspect(src).get_table_names())

    print(f'Source SQLite : {args.sqlite}')
    print(f'Target Postgres: {pg_url or "(dry-run, none)"}')
    print(f'Tables on model metadata: {len(ordered_tables)}')
    print('-' * 60)

    # Read everything, then prune dangling-FK rows transitively.
    data = load_source(src, ordered_tables, src_tables)
    orphans = prune_orphans(data, ordered_tables)

    if orphans:
        print('Orphaned (dangling foreign key) rows detected:')
        for t, desc, n in orphans:
            print(f'  {t} [{desc}]: {n} rows')
        total_orphans = sum(n for _, _, n in orphans)
        if args.strict:
            sys.exit(f'\n--strict: aborting. {total_orphans} orphan rows would be '
                     f'dropped. Inspect/clean the source, or re-run without --strict.')
        print(f'  -> these {total_orphans} rows will be DROPPED for consistency.')
        print('-' * 60)

    if args.dry_run:
        total = 0
        for table in ordered_tables:
            rows = data.get(table.name)
            if rows is None:
                print(f'  {table.name:<40} (absent in source, skipped)')
                continue
            total += len(rows)
            print(f'  {table.name:<40} {len(rows):>8} rows')
        print('-' * 60)
        print(f'Total rows that would be copied: {total}')
        return

    dst = create_engine(pg_url)

    print('Creating schema in Postgres (create_all)...')
    metadata.create_all(dst)

    # Guard against clobbering a populated target.
    nonempty = []
    with dst.connect() as dc:
        for table in ordered_tables:
            try:
                n = dc.execute(select(func.count()).select_from(table)).scalar() or 0
            except Exception:
                n = 0
            if n:
                nonempty.append((table.name, n))

    if nonempty and args.if_empty:
        print('Target already contains data — nothing to do (--if-empty).')
        return
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

    # Copy (parents first; data is already referentially consistent).
    grand_total = 0
    for table in ordered_tables:
        rows = data.get(table.name)
        if rows is None:
            print(f'  {table.name:<40} (absent in source, skipped)')
            continue
        if not rows:
            print(f'  {table.name:<40} {0:>8} rows')
            continue
        with dst.begin() as dc:
            for i in range(0, len(rows), args.batch):
                dc.execute(table.insert(), rows[i:i + args.batch])
        grand_total += len(rows)
        print(f'  {table.name:<40} {len(rows):>8} rows  ✓')

    # Reset sequences so the next INSERT picks up after the max id.
    print('-' * 60)
    print('Resetting Postgres sequences...')
    reset = 0
    with dst.begin() as dc:
        for table in ordered_tables:
            for col in table.primary_key.columns:
                if col.type.python_type is not int:
                    continue
                seq = dc.execute(text("SELECT pg_get_serial_sequence(:t, :c)"),
                                 {'t': table.name, 'c': col.name}).scalar()
                if not seq:
                    continue
                dc.execute(text(
                    f'SELECT setval(:seq, '
                    f'(SELECT COALESCE(MAX("{col.name}"), 0) + 1 FROM "{table.name}"), false)'
                ), {'seq': seq})
                reset += 1
    print(f'Sequences reset: {reset}')
    print('-' * 60)
    dropped_note = f' (dropped {sum(n for _,_,n in orphans)} orphan rows)' if orphans else ''
    print(f'DONE. Copied {grand_total} rows across {len(ordered_tables)} tables{dropped_note}.')


if __name__ == '__main__':
    main()
