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
from utils import jobqueue  # noqa: E402

POLL_SECONDS = int(os.environ.get('JOBS_POLL_SECONDS', '60'))
# When a Redis queue backs the app, drain it on a short cadence so queued exam
# submissions (async grading) and analytics refreshes are processed within
# seconds, while the once-a-minute scheduler tick still runs on its own cadence.
DRAIN_SECONDS = int(os.environ.get('JOBS_DRAIN_SECONDS', '2'))


def main():
    app = create_app()
    has_queue = jobqueue.backend_enabled()
    step = DRAIN_SECONDS if has_queue else POLL_SECONDS
    app.logger.info('Background jobs worker started (tick=%ss, queue=%s, drain=%ss).',
                    POLL_SECONDS, 'redis' if has_queue else 'off', step)
    last_backup = None
    last_tick = 0.0
    while True:
        try:
            # Fast path: drain any queued jobs (no-op when there's no backend).
            jobqueue.drain(app)
            # Slow path: run the scheduler tick + daily backup at most once/minute.
            if time.monotonic() - last_tick >= POLL_SECONDS:
                last_tick = time.monotonic()
                with app.app_context():
                    _tick_dispatch(app)
                    today = time.strftime('%Y%m%d')
                    if today != last_backup:
                        auto_backup(app)
                        last_backup = today
        except Exception as exc:
            app.logger.error('jobs worker error: %s', exc)
        time.sleep(step)


if __name__ == '__main__':
    main()
