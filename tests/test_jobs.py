"""Background job queue (roadmap #1). The feature is flag-gated (ASYNC_JOBS);
these tests exercise the engine directly and the Tasks routes."""
from config import Config


def _admin(app):
    from tests.conftest import login_token
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_async_enabled_reads_flag():
    from utils import jobs

    class _A:
        def __init__(self, v):
            self.config = {'ASYNC_JOBS': v}
    assert jobs.async_enabled(_A(True)) is True
    assert jobs.async_enabled(_A('on')) is True
    assert jobs.async_enabled(_A(False)) is False
    assert jobs.async_enabled(_A(None)) is False   # falls through to env (unset) → False


def test_enqueue_and_drain_runs_handler(app):
    from utils import jobs
    seen = {}

    @jobs.register('unit_echo')
    def _echo(job, value=None):
        seen['value'] = value
        return {'echoed': value}

    with app.app_context():
        job = jobs.enqueue('unit_echo', {'value': 42})
        assert job.status == 'queued' and job.id
        ran = jobs.drain(app, limit=5)
        assert ran >= 1
        from models import db, BackgroundJob
        refreshed = db.session.get(BackgroundJob, job.id)
        assert refreshed.status == 'done'
        assert seen.get('value') == 42
        assert refreshed.as_dict()['result'] == {'echoed': 42}


def test_failing_handler_marks_failed(app):
    from utils import jobs

    @jobs.register('unit_boom')
    def _boom(job):
        raise ValueError('kaboom')

    with app.app_context():
        job = jobs.enqueue('unit_boom')
        jobs.drain(app, limit=5)
        from models import db, BackgroundJob
        refreshed = db.session.get(BackgroundJob, job.id)
        assert refreshed.status == 'failed'
        assert 'kaboom' in (refreshed.message or '')


def test_tasks_page_and_status_route(app):
    from utils import jobs
    with app.app_context():
        job = jobs.enqueue('analytics_recompute', {'branch_id': None})
        jid = job.id
    c = _admin(app)
    r = c.get('/results/tasks')
    assert r.status_code == 200 and 'Background Tasks' in r.get_data(as_text=True)
    j = c.get(f'/results/tasks/{jid}.json').get_json()
    assert j['id'] == jid and j['kind'] == 'analytics_recompute'
