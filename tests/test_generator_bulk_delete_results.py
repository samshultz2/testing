"""Bulk-delete for the Generated Timetables list (/generator/results):
select several batches at once and remove them all in one request, the
same effect as the existing single-batch delete just for however many are
checked."""
from config import Config
from models import db, Branch, GenTimetableResult
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return c


def _post(c, url, **data):
    data.setdefault('_csrf_token', 'a' * 64)
    return c.post(url, data=data)


def _scoped_to_branch(c, branch_id):
    with c.session_transaction() as s:
        s['view_branch_id'] = branch_id
    return c


def _seed_batch(app, branch_id, batch_id, tag):
    with app.app_context():
        for d in range(2):
            db.session.add(GenTimetableResult(
                branch_id=branch_id, batch_id=batch_id, school_level='sss',
                class_name=f'ZzBD{tag}', arm_name='Main', day_of_week=d, period_number=1))
        db.session.commit()


def _fresh_branch(app, tag):
    with app.app_context():
        b = Branch(name=f'ZzBulkDeleteBranch{tag}', code=None)
        db.session.add(b); db.session.commit()
        return b.id


def _count(app, batch_id):
    with app.app_context():
        return GenTimetableResult.query.filter_by(batch_id=batch_id).count()


def test_bulk_delete_removes_selected_batches_only(app):
    bid = _fresh_branch(app, 'A')
    _seed_batch(app, bid, 'zzbdA-1', 'A1')
    _seed_batch(app, bid, 'zzbdA-2', 'A2')
    _seed_batch(app, bid, 'zzbdA-3', 'A3')
    c = _scoped_to_branch(_admin(app), bid)

    r = _post(c, '/generator/results/bulk-delete', **{'batch_ids[]': ['zzbdA-1', 'zzbdA-2']})
    assert r.status_code == 302

    assert _count(app, 'zzbdA-1') == 0
    assert _count(app, 'zzbdA-2') == 0
    assert _count(app, 'zzbdA-3') == 2   # untouched


def test_bulk_delete_scoped_to_branch(app):
    """A batch living in a DIFFERENT branch, even with the same name pattern,
    must survive a bulk-delete issued while viewing another branch."""
    bid1 = _fresh_branch(app, 'B1')
    bid2 = _fresh_branch(app, 'B2')
    _seed_batch(app, bid1, 'zzbdB-shared', 'B1')
    with app.app_context():
        db.session.add(GenTimetableResult(
            branch_id=bid2, batch_id='zzbdB-shared', school_level='sss',
            class_name='ZzBDB2', arm_name='Main', day_of_week=0, period_number=1))
        db.session.commit()

    c = _scoped_to_branch(_admin(app), bid1)
    r = _post(c, '/generator/results/bulk-delete', **{'batch_ids[]': ['zzbdB-shared']})
    assert r.status_code == 302

    with app.app_context():
        remaining = GenTimetableResult.query.filter_by(batch_id='zzbdB-shared').all()
        assert len(remaining) == 1
        assert remaining[0].branch_id == bid2


def test_bulk_delete_with_no_selection_flashes_error(app):
    bid = _fresh_branch(app, 'C')
    c = _scoped_to_branch(_admin(app), bid)
    r = c.post('/generator/results/bulk-delete', data={'_csrf_token': 'a' * 64}, follow_redirects=True)
    assert r.status_code == 200
    assert b'Select at least one' in r.data


def test_results_list_page_renders_bulk_controls(app):
    bid = _fresh_branch(app, 'D')
    _seed_batch(app, bid, 'zzbdD-1', 'D1')
    c = _scoped_to_branch(_admin(app), bid)
    body = c.get('/generator/results').get_data(as_text=True)
    assert 'batch-checkbox' in body
    assert 'bulkDeleteForm' in body
    assert 'zzbdD-1' in body
