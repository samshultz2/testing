"""
Gunicorn configuration for PosyHub.

Defaults are tuned for a single-machine deployment (Termux/proot or a small
VPS): ONE worker process with several threads. This matters because the app
runs an in-process background thread (scheduled-message dispatch + daily
backup); multiple worker processes would each start their own copy and send
duplicates. Scale with threads here, and move background jobs to a separate
process before scaling to multiple workers.

Override anything via environment variables (see below).

    gunicorn -c gunicorn.conf.py wsgi:app
"""
import os

# Network
bind = os.environ.get('GUNICORN_BIND', f"0.0.0.0:{os.environ.get('PORT', '5000')}")

# Concurrency — keep workers=1 unless background jobs are moved out of process.
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
