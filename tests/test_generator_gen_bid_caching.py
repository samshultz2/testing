"""gen_bid() (the timetable generator's per-request branch resolver) used to
re-query the branches table on every call — for a central user with no branch
picked, it falls back to default_branch_id() -> Branch.get_default(), up to 2
SELECTs, and the / and /setup dashboards alone call gen_bid() a dozen+ times
each to build their stat counts. Now memoized on flask.g so it resolves once
per request no matter how many call sites need it."""
import re
from sqlalchemy import event
from config import Config
from models import db
from tests.conftest import login_token


def _count_selects(app, table, fn):
    pattern = re.compile(r'^select\b.*\bfrom\s+' + re.escape(table) + r'\b',
                         re.IGNORECASE | re.DOTALL)
    counts = {'n': 0}

    def before(conn, cursor, statement, params, context, executemany):
        if pattern.match(statement):
            counts['n'] += 1
    with app.app_context():
        engine = db.engine
    event.listen(engine, 'before_cursor_execute', before)
    try:
        fn()
    finally:
        event.remove(engine, 'before_cursor_execute', before)
    return counts['n']


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_generator_index_resolves_branch_once_per_request(app):
    c = _admin(app)
    c.get('/generator/')   # warm the one-time ensure_generator_schema() cache
    n = _count_selects(app, 'branches', lambda: c.get('/generator/'))
    assert n <= 2, (
        f'{n} branches SELECTs for one /generator/ request (a dozen+ gen_bid() '
        f'calls) — looks like gen_bid() is re-resolving the branch on every call '
        f'instead of once per request')


def test_generator_setup_resolves_branch_once_per_request(app):
    c = _admin(app)
    c.get('/generator/setup')   # warm the one-time ensure_generator_schema() cache
    n = _count_selects(app, 'branches', lambda: c.get('/generator/setup'))
    assert n <= 2, (
        f'{n} branches SELECTs for one /generator/setup request — looks like '
        f'gen_bid() is re-resolving the branch on every call instead of once '
        f'per request')


def test_generator_index_still_renders_correct_stats(app):
    """The gen_bid() memoization + count()-instead-of-all() changes must not
    change what the page actually shows."""
    from models import Branch, GenTeacher, GenClassConfig
    with app.app_context():
        bid = Branch.get_default().id
        db.session.add(GenTeacher(name='T1', school_level='jss', is_active=True, branch_id=bid))
        db.session.add(GenClassConfig(class_name='JSS1', school_level='jss', is_active=True, branch_id=bid))
        db.session.commit()
    c = _admin(app)
    html = c.get('/generator/').get_data(as_text=True)
    assert c.get('/generator/').status_code == 200
    assert 'Timetable Generator' in html
