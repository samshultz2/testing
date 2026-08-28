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


@register('bank_local_tag')
def _handle_bank_local_tag(job, subject_id=None, mode='untagged', year=None, **_):
    """Local (offline, no-key) topic+sub-topic tagging of a subject's Mock-JAMB
    bank via sentence-embeddings. Runs here in the jobs worker so torch never
    loads in a web process; the engine is imported lazily for the same reason."""
    from models import db, Subject
    subject = db.session.get(Subject, subject_id) if subject_id else None
    if not subject:
        job.message = 'Subject not found.'
        return {}
    from utils.mock_bank_local_tag import available, local_tag
    if not available():
        job.message = 'sentence-transformers is not installed on the server.'
        return {'error': 'not_installed'}

    def _progress(done, total):
        job.progress, job.total = done, total
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    return local_tag(subject, mode=mode, year=year, progress_cb=_progress)


_BATCH_MAX_POLLS = 2000     # non-blocking poll re-enqueues, paced by the tick


@register('bank_batch_retag')
def _handle_bank_batch_retag(job, subject_id=None, model='', year=None, exam_body=None,
                             force=False, phase='submit', batch_id=None, attempt=0, **_):
    """AI-retag a subject's bank questions to its coded syllabus via Anthropic's
    Message Batches API (50% cheaper, async). Runs non-blocking: 'submit' sends
    the batch then hands off to 'poll'; each 'poll' checks once and re-enqueues
    until the batch has 'ended', then applies the codes."""
    from models import db, Subject
    from utils.waec_ocr import _vision_config
    from utils.mock_bank_coded_retag import coded_nodes, _syllabus_block
    from utils import mock_bank_batch_retag as batch

    subject = db.session.get(Subject, subject_id) if subject_id else None
    if not subject:
        job.message = 'Subject not found.'
        return {'error': 'no_subject'}

    cfg = _vision_config()
    if not cfg['installed']:
        job.message = 'The "anthropic" package is not installed on the server.'
        return {'error': 'not_installed'}
    if not cfg['has_key']:
        job.message = 'No Anthropic API key is set (Settings → AI Vision OCR).'
        return {'error': 'no_key'}
    by_code, _syll = coded_nodes(subject.id)
    if not by_code:
        job.message = f'No coded syllabus imported for {subject.name}.'
        return {'error': 'no_syllabus'}
    by_id = {n.id: n for n in by_code.values()}
    use_model = (model or '').strip() or cfg['model']

    import anthropic
    client = anthropic.Anthropic(api_key=cfg['key'])

    if phase == 'submit':
        from models import MockJAMBQuestion
        ids = batch.target_ids(subject, year=year, exam_body=exam_body, force=force)[:batch._MAX_REQUESTS]
        job.total = len(ids)
        db.session.commit()
        if not ids:
            job.message = f'No {subject.name} questions to tag.'
            return {'tagged': 0, 'total': 0}
        block = _syllabus_block(by_code)
        rows = MockJAMBQuestion.query.filter(MockJAMBQuestion.id.in_(ids)).all()
        reqs = batch.build_requests(subject.name, block, rows, use_model)
        bid = batch.submit_batch(client, reqs)
        job.message = f'Submitted {len(ids)} {subject.name} question(s) to a Claude batch ({use_model}); awaiting results…'
        db.session.commit()
        enqueue('bank_batch_retag', {'subject_id': subject_id, 'model': model, 'year': year,
                                     'exam_body': exam_body, 'force': force,
                                     'phase': 'poll', 'batch_id': bid, 'attempt': 0},
                branch_id=job.branch_id)
        return {'phase': 'submitted', 'batch_id': bid, 'requests': len(ids)}

    # phase == 'poll'
    status = batch.batch_status(client, batch_id)
    if status == 'ended':
        summary = batch.apply_results(client, batch_id, subject, by_code, by_id)
        job.message = (f"Batch done — tagged {summary['tagged']} of {summary['scanned']} "
                       f"{subject.name} question(s)"
                       + (f"; {summary['outside']} outside the syllabus" if summary['outside'] else '')
                       + '.')
        db.session.commit()
        summary['phase'] = 'ended'
        summary['batch_id'] = batch_id
        return summary
    if status in ('canceling', 'canceled', 'expired'):
        job.message = f'Claude batch {status}.'
        return {'phase': status, 'batch_id': batch_id}
    # still processing — poll again next tick (non-blocking)
    if attempt < _BATCH_MAX_POLLS:
        job.message = f'Claude batch processing… (poll {attempt + 1})'
        db.session.commit()
        enqueue('bank_batch_retag', {'subject_id': subject_id, 'model': model, 'year': year,
                                     'exam_body': exam_body, 'force': force,
                                     'phase': 'poll', 'batch_id': batch_id, 'attempt': attempt + 1},
                branch_id=job.branch_id)
        return {'phase': 'processing', 'batch_id': batch_id, 'attempt': attempt}
    job.message = 'Claude batch still processing after many checks — results can be applied later.'
    return {'phase': 'timeout', 'batch_id': batch_id}
