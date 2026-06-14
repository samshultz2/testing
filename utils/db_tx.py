"""``safe_transaction`` — the commit/rollback+flash pattern in one place.

The routes repeat this ~100 times::

    try:
        ...                      # build/add/update ORM objects
        db.session.commit()
        flash('Saved!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {e}', 'error')

``safe_transaction`` captures exactly that. It commits on a clean exit and, on
any exception, rolls back and flashes — never re-raising, so control continues
after the ``with`` block (matching the original try/except that fell through to
a redirect). The yielded status object exposes ``.ok`` so a caller whose
success and error paths differ can still branch::

    with safe_transaction('User created!', 'Error creating user: {error}') as tx:
        db.session.add(user)
    return redirect(url_for('users.index') if tx.ok
                    else url_for('users.add_user'))

Only migrate handlers whose try-body is purely ORM work + commit and whose
except is purely rollback + flash (+ redirect); anything with extra branching,
early returns, or specific exception handling should be left as-is.
"""
from contextlib import contextmanager


class _Txn:
    __slots__ = ('ok', 'error')

    def __init__(self):
        self.ok = False
        self.error = None


@contextmanager
def safe_transaction(success=None, error='Something went wrong: {error}',
                     ok_category='success', err_category='error'):
    """Commit on success (flashing ``success``); rollback + flash ``error`` on
    failure. ``error`` may contain ``{error}`` which is filled with the
    exception text (matching the common ``f'...: {str(e)}'`` messages)."""
    from flask import flash
    from models import db
    tx = _Txn()
    try:
        yield tx
        db.session.commit()
        tx.ok = True
        if success is not None:
            flash(success, ok_category)
    except Exception as e:  # noqa: BLE001 — same broad catch the routes already use
        db.session.rollback()
        tx.ok = False
        tx.error = e
        if error:
            msg = error.format(error=e) if '{error}' in error else error
            flash(msg, err_category)
