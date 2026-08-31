"""
Gunicorn configuration for PosyHub.

Concurrency model
-----------------
Multiple worker processes are SAFE. The in-process background loop
(scheduled-message dispatch + the daily jobs: backups, stock alerts, analytics
refresh, board packs) elects a single runner per tick with a PostgreSQL advisory
lock and guards each job with a per-day DB marker, so N workers never duplicate
work (see ``app._start_scheduled_messages_worker`` / ``_tick_dispatch``). You can
also set ``RUN_INPROCESS_JOBS=0`` on the web workers and run the loop in a
dedicated process instead.

Scaling for a mass exam sitting (e.g. 1000 students starting at once):
* Raise ``WEB_CONCURRENCY`` to ~ (2 × CPU cores) so the web tier isn't the
  bottleneck. Each worker keeps its own SQLAlchemy pool, so size Postgres
  ``max_connections`` >= workers × (DB_POOL_SIZE + DB_MAX_OVERFLOW), or front the
  DB with PgBouncer.
* The default stays 1 worker so a tiny box (Termux/proot) isn't surprised by the
  memory of extra workers — bump it explicitly in the environment.

Override anything via environment variables (see below).

    WEB_CONCURRENCY=4 gunicorn -c gunicorn.conf.py wsgi:app
"""
import os

# Network
bind = os.environ.get('GUNICORN_BIND', f"0.0.0.0:{os.environ.get('PORT', '5000')}")

# Concurrency — multi-worker is safe (advisory-locked background loop). Default 1
# for small boxes; set WEB_CONCURRENCY to ~2×cores for a mass sitting.
workers = int(os.environ.get('WEB_CONCURRENCY', '1'))
threads = int(os.environ.get('GUNICORN_THREADS', '4'))
worker_class = os.environ.get('GUNICORN_WORKER_CLASS', 'gthread')

# Reliability
timeout = int(os.environ.get('GUNICORN_TIMEOUT', '120'))      # long for OCR/PDF
graceful_timeout = int(os.environ.get('GUNICORN_GRACEFUL', '30'))
keepalive = int(os.environ.get('GUNICORN_KEEPALIVE', '5'))
max_requests = int(os.environ.get('GUNICORN_MAX_REQUESTS', '1000'))
max_requests_jitter = int(os.environ.get('GUNICORN_MAX_REQUESTS_JITTER', '100'))

# preload must stay False: the background thread is started in create_app and
# would not survive the fork if the app were preloaded in the master.
preload_app = False

# Logging to stdout/stderr (captured by the supervisor / systemd / terminal).
accesslog = os.environ.get('GUNICORN_ACCESS_LOG', '-')
errorlog = os.environ.get('GUNICORN_ERROR_LOG', '-')
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')
