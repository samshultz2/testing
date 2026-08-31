"""Background job queue (feature-flagged via ASYNC_JOBS).

Enqueue long-running admin work as a row in ``background_jobs``; the in-process
scheduler tick drains queued rows on the bound (tenant) DB. When ASYNC_JOBS is
off, callers run their work synchronously as before and nothing is written here,
so production behaviour is unchanged until the flag is turned on.
"""
import json
import os

_HANDLERS = {}


def register(kind):
    """Register a handler ``fn(job, **params) -> result_dict|None`` for a kind."""
    def deco(fn):
        _HANDLERS[kind] = fn
        return fn
    return deco


def _truthy(val):
    return str(val).strip().lower() in ('1', 'true', 'yes', 'on')


def async_enabled(app=None):
    """True when the ASYNC_JOBS flag is set (app config first, then env)."""
    try:
        from flask import current_app
        a = app or current_app
        val = a.config.get('ASYNC_JOBS')
    except Exception:
        val = None
    if val is None:
        val = os.environ.get('ASYNC_JOBS')
    return _truthy(val) if val is not None else False


def _ensure_table():
    """Create the background_jobs table on the bound DB if missing (covers
    existing tenants provisioned before this feature)."""
    from models import db, BackgroundJob
    try:
        BackgroundJob.__table__.create(bind=db.engine, checkfirst=True)
    except Exception:
        db.session.rollback()


def enqueue(kind, params=None, created_by=None, branch_id=None):
    """Insert a queued job row and return it. Caller decides (via async_enabled)
    whether to enqueue or run inline."""
    from models import db, BackgroundJob
    _ensure_table()
    who = created_by
    if who is None:
        try:
            from flask import session
            who = session.get('user') or session.get('username')
        except Exception:
            who = None
    job = BackgroundJob(kind=kind, status='queued', params=json.dumps(params or {}),
                        created_by=who, branch_id=branch_id)
    db.session.add(job)
    db.session.commit()
    return job


def _run(job):
    from models import db, local_now
    fn = _HANDLERS.get(job.kind)
    if fn is None:
        job.status = 'failed'
        job.message = f'No handler registered for "{job.kind}"'
        job.finished_at = local_now()
        db.session.commit()
        return
    job.status = 'running'
    job.started_at = local_now()
    db.session.commit()
    try:
        params = json.loads(job.params or '{}')
        result = fn(job, **params)
        job.result = json.dumps(result) if result is not None else None
        job.status = 'done'
        job.finished_at = local_now()
        db.session.commit()
    except Exception as e:              # a bad job must never break the tick
        db.session.rollback()
        job.status = 'failed'
        job.message = str(e)[:500]
        job.finished_at = local_now()
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()


def run_job(job_id):
    """Run a single job by id (used by the drain and by tests)."""
    from models import db, BackgroundJob
    job = db.session.get(BackgroundJob, job_id)
    if job and job.status == 'queued':
        _run(job)
    return job


def drain(app=None, limit=3):
    """Run up to ``limit`` queued jobs on the bound DB. Called from the scheduler
    tick when ASYNC_JOBS is on. Best-effort — never raises."""
    from models import db, BackgroundJob
    try:
        _ensure_table()
        jobs = (BackgroundJob.query.filter_by(status='queued')
                .order_by(BackgroundJob.id).limit(limit).all())
    except Exception:
        db.session.rollback()
        return 0
    ran = 0
    for job in jobs:
        _run(job)
        ran += 1
    return ran


# --- built-in handlers ------------------------------------------------------
@register('analytics_recompute')
def _handle_analytics_recompute(job, branch_id=None, **_):
    """Bulk exam-analytics recompute (the async form of the Recompute button)."""
    from flask import current_app
    from utils.exam_refresh import run_exam_analytics_refresh
    summary = run_exam_analytics_refresh(current_app, warm=True, branch_id=branch_id)
    return {'students': summary.get('students'), 'at': summary.get('at')}
