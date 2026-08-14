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

import json
import os
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


# ── cross-process job metrics ─────────────────────────────────────────────────
# Background jobs run in the web process (in-process mode) OR in a dedicated
# worker (RUN_INPROCESS_JOBS=0). The /platform page is served by a web worker,
# so job durations recorded elsewhere are mirrored through a tiny JSON sidecar
# that any process on the host can read. Best-effort throughout: a missing app
# context or unwritable disk simply falls back to the in-memory dict.
def _jobs_file():
    try:
        from flask import current_app
        base = current_app.config.get('BASE_DIR')
        if not base:
            return None
        d = os.path.join(base, 'instance', 'metrics')
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, 'jobs.json')
    except Exception:
        return None


def _write_jobs_file(jobs: dict):
    path = _jobs_file()
    if not path:
        return
    try:
        tmp = path + '.tmp'
        with open(tmp, 'w') as fh:
            json.dump(jobs, fh)
        os.replace(tmp, path)
    except Exception:
        pass


def _read_jobs_file() -> dict:
    path = _jobs_file()
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path) as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def record_job(name: str, duration_ms: float):
    entry = {'ms': round(duration_ms), 'at': time.time()}
    with _LOCK:
        _JOBS[name] = entry
        snapshot = dict(_JOBS)
    # Merge onto whatever the sidecar already holds so a job recorded in another
    # process (e.g. the dedicated worker) isn't clobbered, then persist.
    merged = _read_jobs_file()
    merged.update(snapshot)
    _write_jobs_file(merged)


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
    # Fold in job timings recorded by other processes (the dedicated jobs worker
    # under RUN_INPROCESS_JOBS=0), preferring whichever run is more recent.
    for name, entry in _read_jobs_file().items():
        if not isinstance(entry, dict):
            continue
        cur = jobs.get(name)
        if cur is None or entry.get('at', 0) > cur.get('at', 0):
            jobs[name] = dict(entry)
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


# ── Redis (cache/queue) ───────────────────────────────────────────────────────
def redis_metrics():
    """Redis memory + queue depth when the optional cache/queue backend is live."""
    try:
        from utils import cache, jobqueue
    except Exception:
        return {'available': False}
    client = cache._client()
    if client is None:
        return {'available': False}
    out = {'available': True}
    try:
        info = client.info('memory')
        out['used_memory'] = int(info.get('used_memory', 0))
        peak = info.get('used_memory_peak')
        if peak is not None:
            out['used_memory_peak'] = int(peak)
        maxmem = info.get('maxmemory')
        if maxmem:
            out['maxmemory'] = int(maxmem)
    except Exception:
        pass
    try:
        out['queue_length'] = jobqueue.queue_length()
    except Exception:
        pass
    return out


def all_metrics():
    """Assemble the full snapshot for the monitoring page / JSON endpoint."""
    return {
        'system': system_metrics(),
        'postgres': pg_metrics(),
        'redis': redis_metrics(),
        'requests': request_metrics(),
        'at': int(time.time()),
    }
