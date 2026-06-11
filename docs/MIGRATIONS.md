# Database Migrations (Alembic / Flask-Migrate)

Schema changes are tracked with Alembic, in `db_migrations/`. This replaces the
old "edit a model and hope the column appears" approach — `create_all()` only
ever creates *missing tables*, it **never adds new columns to an existing
database**, which silently breaks a live DB after a model change.

All commands need the app env set:

```bash
export FLASK_APP=app.py
```

## One-time: adopt migrations on your EXISTING database

Your current database was built by `create_all()`, so its schema already matches
the baseline. Tell Alembic that — **don't** run `upgrade` on it (that would try
to re-create existing tables):

```bash
flask db stamp head -d db_migrations
```

This records the current revision in an `alembic_version` table. Done once.

## Day-to-day: changing the schema

1. Edit the model (add/alter a column) in `models/`.
2. Generate a migration:
   ```bash
   flask db migrate -d db_migrations -m "add students.foo"
   ```
3. **Review** the generated file in `db_migrations/versions/` — autogenerate is
   not perfect (it can miss server defaults, renames, custom types). Edit if needed.
4. Apply it to your database:
   ```bash
   flask db upgrade -d db_migrations
   ```
   Run this on every environment (your phone, the VPS) after pulling new code.

## A caveat about create_all (read this)

For convenience, the app still runs `create_all()` at startup (fresh dev/test
databases and new installs get their schema instantly). The trade-off: in a dev
environment `create_all` may have **already added** a new column you just defined,
so `flask db migrate` sees no diff and generates an empty migration.

Two clean ways to author a column migration:

- **Recommended:** generate against a database at the *previous* schema. Easiest
  is to point at a throwaway DB built from the current migrations only:
  ```bash
  SKIP_CREATE_ALL=1 DATABASE_URL=sqlite:////tmp/mig.db flask db upgrade -d db_migrations
  SKIP_CREATE_ALL=1 DATABASE_URL=sqlite:////tmp/mig.db flask db migrate -d db_migrations -m "..."
  ```
  `SKIP_CREATE_ALL=1` tells the app not to `create_all`/seed, so Alembic owns the
  schema and the diff is real.
- Or hand-write the `op.add_column(...)` in a new revision (`flask db revision -d db_migrations -m "..."`).

## Going fully Alembic-managed (optional, later)

On the VPS you can let Alembic own the schema completely: set `SKIP_CREATE_ALL=1`
in the environment and rely on `flask db upgrade` for all schema setup/changes
(run it on deploy). The baseline migration builds the entire schema from empty.
Keep `create_all` on for the phone pilot / quick demos.

## Note on the old `migrations/` folder

`migrations/*.py` are legacy one-off scripts from before Alembic. They are kept
for history only — new schema changes go through `db_migrations/` as above.
