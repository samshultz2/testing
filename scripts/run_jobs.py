#!/usr/bin/env python3
"""
Out-of-process background worker.

Run this as a single, separate process when you scale the web app to multiple
gunicorn workers (so scheduled messages and daily backups fire exactly once
instead of once per worker). With it running, start the web app with
``RUN_INPROCESS_JOBS=0``.

    RUN_INPROCESS_JOBS=0 gunicorn -c gunicorn.conf.py wsgi:app   # web (N workers)
    python scripts/run_jobs.py                                   # jobs (1 process)

It loops forever: dispatches due scheduled campaigns every minute and ensures a
daily database backup exists.
"""
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# This process owns the jobs, so don't also start the in-process thread.
os.environ['RUN_INPROCESS_JOBS'] = '0'

from app import create_app, _tick_dispatch  # noqa: E402
from utils.backup import auto_backup  # noqa: E402

POLL_SECONDS = int(os.environ.get('JOBS_POLL_SECONDS', '60'))


def main():
    app = create_app()
    app.logger.info('Background jobs worker started (poll=%ss).', POLL_SECONDS)
    last_backup = None
    while True:
        try:
            with app.app_context():
                # Shared with the in-process worker: dispatch due campaigns + the
                # daily fee reminder (idempotent via the DB-shared marker, guarded
                # by the advisory lock — a no-op for this single process).
                _tick_dispatch(app)
                # Daily DB backup is owned by this out-of-process runner.
                today = time.strftime('%Y%m%d')
                if today != last_backup:
                    auto_backup(app)
                    last_backup = today
        except Exception as exc:
            app.logger.error('jobs worker error: %s', exc)
        time.sleep(POLL_SECONDS)


if __name__ == '__main__':
    main()
