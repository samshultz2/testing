"""Live system + application metrics for the platform monitoring page.

System figures (CPU, memory, swap, disk, disk I/O) come from ``psutil`` and are
process-independent, so they're correct no matter how many gunicorn workers run.
PostgreSQL connections come from ``pg_stat_activity``.

Request latency and concurrent users are collected in-process by lightweight
request hooks. That state is per-worker: at the default single worker (this app's
default on a small box) it's exact; if you scale WEB_CONCURRENCY, the monitoring
request is served by one worker and shows that worker's sample. Background-job
durations are recorded whenever the scheduled tick runs.

Everything here is best-effort — a metric that can't be read returns ``None`` (or
is omitted) rather than raising, so the monitoring page never errors.
"""
from __future__ import annotations

import threading
import time
from collections import deque

# ── in-process collectors ────────────────────────────────────────────────────
_LOCK = threading.Lock()
_LATENCIES = deque(maxlen=1000)          # recent (monotonic_ts, duration_ms)
_ACTIVE = {}                             # user/ip key -> last-seen epoch
_JOBS = {}                               # job name -> {'ms': int, 'at': epoch}
_IO_LAST = {'t': None, 'read': 0, 'write': 0}
_STARTED = time.time()


def record_request(duration_ms: float):
    with _LOCK:
        _LATENCIES.append((time.monotonic(), duration_ms))


def touch_user(key: str):
    if not key:
        return
    with _LOCK:
        _ACTIVE[key] = time.time()
        if len(_ACTIVE) > 5000:          # bound memory on a busy box
            cutoff = time.time() - 3600
            for k in [k for k, v in _ACTIVE.items() if v < cutoff]:
                _ACTIVE.pop(k, None)


def record_job(name: str, duration_ms: float):
    with _LOCK:
        _JOBS[name] = {'ms': round(duration_ms), 'at': time.time()}


def _percentile(values, pct):
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((pct / 100.0) * (len(s) - 1)))))
    return s[k]


def request_metrics(window_seconds: int = 300):
    now = time.monotonic()
    with _LOCK:
        recent = [d for (t, d) in _LATENCIES if now - t <= window_seconds]
        active_cut = time.time() - window_seconds
        concurrent = sum(1 for v in _ACTIVE.values() if v >= active_cut)
        jobs = {k: dict(v) for k, v in _JOBS.items()}
    return {
        'window_seconds': window_seconds,
        'count': len(recent),
        'avg_ms': round(sum(recent) / len(recent), 1) if recent else None,
        'p50_ms': round(_percentile(recent, 50), 1) if recent else None,
        'p95_ms': round(_percentile(recent, 95), 1) if recent else None,
        'concurrent_users': concurrent,
        'jobs': jobs,
    }


# ── system metrics (psutil) ───────────────────────────────────────────────────
def system_metrics():
    try:
        import psutil
    except Exception:
        return {'available': False}
    out = {'available': True}
    try:
        out['cpu_percent'] = psutil.cpu_percent(interval=0.0)
        out['cpu_count'] = psutil.cpu_count()
        try:
            out['load_avg'] = [round(x, 2) for x in psutil.getloadavg()]
        except Exception:
            out['load_avg'] = None
    except Exception:
        pass
    try:
        vm = psutil.virtual_memory()
        out['mem'] = {'total': vm.total, 'used': vm.used, 'percent': vm.percent}
    except Exception:
        pass
    try:
        sw = psutil.swap_memory()
        out['swap'] = {'total': sw.total, 'used': sw.used, 'percent': sw.percent}
    except Exception:
        pass
    try:
        du = psutil.disk_usage('/')
        out['disk'] = {'total': du.total, 'used': du.used, 'percent': du.percent}
    except Exception:
        pass
    # Disk I/O as a rate: bytes since the previous sample.
    try:
        io = psutil.disk_io_counters()
        now = time.time()
        prev_t = _IO_LAST['t']
        if prev_t and now > prev_t:
            dt = now - prev_t
            out['disk_io'] = {
                'read_bps': max(0, (io.read_bytes - _IO_LAST['read']) / dt),
                'write_bps': max(0, (io.write_bytes - _IO_LAST['write']) / dt),
            }
        _IO_LAST.update({'t': now, 'read': io.read_bytes, 'write': io.write_bytes})
    except Exception:
        pass
    out['uptime_seconds'] = int(time.time() - _STARTED)
    return out


# ── PostgreSQL connections ────────────────────────────────────────────────────
def pg_metrics():
    from models import db
    from sqlalchemy import text
    try:
        bind = db.session.get_bind()
        if bind.dialect.name != 'postgresql':
            return {'available': False, 'reason': 'not PostgreSQL'}
        total = db.session.execute(text('SELECT count(*) FROM pg_stat_activity')).scalar()
        active = db.session.execute(
            text("SELECT count(*) FROM pg_stat_activity WHERE state = 'active'")).scalar()
        maxc = db.session.execute(text("SELECT current_setting('max_connections')")).scalar()
        return {'available': True, 'total': int(total or 0),
                'active': int(active or 0), 'max': int(maxc) if maxc else None}
    except Exception:
        db.session.rollback()
        return {'available': False, 'reason': 'unreadable'}


def all_metrics():
    """Assemble the full snapshot for the monitoring page / JSON endpoint."""
    return {
        'system': system_metrics(),
        'postgres': pg_metrics(),
        'requests': request_metrics(),
        'at': int(time.time()),
    }
