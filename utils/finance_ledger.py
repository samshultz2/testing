"""The finance ledger — Phase 0 spine (single source of truth).

Every monetary event in the app is mirrored into ``FinanceTransaction`` so the
Finance module can classify and report on *all* money without owning any other
module's data. Two ways in:

  * Automatically — ORM ``after_insert`` / ``after_delete`` listeners on the
    source models (FeePayment, Expense, Sale) post/reverse a ledger row whenever
    money is recorded or removed, no matter which route created it.
  * Explicitly — ``post()`` / ``reverse()`` for code that wants to record a
    money movement directly (or a manual journal-style entry).

Posting is idempotent: one ledger row per (origin_type, origin_id), enforced by
a unique key, so a replayed sale/payment can never double-count. Registered from
app startup via ``register_ledger_hooks()``.
"""
from __future__ import annotations

import datetime as _dt

from sqlalchemy import event, select

REVENUE = 'in'
EXPENSE = 'out'


def _today():
    return _dt.date.today()


def _session_for_term(connection, term_id):
    """Look up a term's academic session id over the given connection (used inside
    flush listeners, where we can't open a new ORM query)."""
    if not term_id:
        return None
    from models import Term
    row = connection.execute(
        select(Term.__table__.c.session_id).where(Term.__table__.c.id == term_id)
    ).first()
    return row[0] if row else None


def _insert_row(connection, **vals):
    """Insert one ledger row over `connection`, ignoring a duplicate origin (the
    unique key makes re-posting a no-op)."""
    from models import FinanceTransaction
    from sqlalchemy.exc import IntegrityError
    vals.setdefault('occurred_on', _today())
    vals.setdefault('created_at', _dt.datetime.now())
    try:
        connection.execute(FinanceTransaction.__table__.insert().values(**vals))
    except IntegrityError:
        pass                       # already posted for this origin — idempotent


# --- explicit API (ORM session; for direct/manual posting) ------------------
def post(direction, amount, *, source_module, category=None, method=None,
         branch_id=None, term_id=None, session_id=None, student_id=None,
         origin_type='manual', origin_id=None, reference=None, description=None,
         occurred_on=None, created_by=None, created_by_id=None):
    """Record a money movement in the ledger (ORM). Returns the FinanceTransaction,
    or the existing one if this origin was already posted."""
    from models import db, FinanceTransaction, Term
    if origin_id is not None:
        existing = FinanceTransaction.query.filter_by(
            origin_type=origin_type, origin_id=origin_id).first()
        if existing:
            return existing
    if session_id is None and term_id:
        t = db.session.get(Term, term_id)
        session_id = t.session_id if t else None
    txn = FinanceTransaction(
        direction=direction, amount=amount or 0, source_module=source_module,
        category=category, method=method, branch_id=branch_id, term_id=term_id,
        session_id=session_id, student_id=student_id, origin_type=origin_type,
        origin_id=origin_id, reference=reference, description=description,
        occurred_on=occurred_on or _today(), created_by=created_by,
        created_by_id=created_by_id)
    db.session.add(txn)
    db.session.flush()
    return txn


def reverse(txn, *, by=None, reason=None):
    """Post an offsetting entry that cancels ``txn`` (for refunds/reversals), and
    mark the original reversed. Idempotent per original."""
    from models import db, FinanceTransaction
    if txn is None or txn.reversed:
        return None
    rev = FinanceTransaction(
        direction=(EXPENSE if txn.direction == REVENUE else REVENUE),
        amount=txn.amount, source_module=txn.source_module,
        category=txn.category, method=txn.method, branch_id=txn.branch_id,
        term_id=txn.term_id, session_id=txn.session_id, student_id=txn.student_id,
        origin_type='reversal', origin_id=None, reference=txn.reference,
        description=(reason or 'Reversal of #%s' % txn.id),
        occurred_on=_today(), reversal_of_id=txn.id, created_by=by)
    txn.reversed = True
    db.session.add(rev)
    db.session.flush()
    return rev


# --- automatic mirroring from source modules --------------------------------
def _fee_payment_vals(connection, t):
    return dict(direction=REVENUE, source_module='fees', category='School Fees',
                amount=t.amount, method=t.method, branch_id=t.branch_id,
                term_id=t.term_id, session_id=_session_for_term(connection, t.term_id),
                student_id=t.student_id, origin_type='fee_payment', origin_id=t.id,
                reference=(t.receipt_no or t.reference), created_by=t.received_by,
                description='School fee payment', occurred_on=t.payment_date or _today())


def _expense_vals(connection, e):
    cat = None
    if e.category_id:
        from models import ExpenseCategory
        row = connection.execute(
            select(ExpenseCategory.__table__.c.name)
            .where(ExpenseCategory.__table__.c.id == e.category_id)).first()
        cat = row[0] if row else None
    return dict(direction=EXPENSE, source_module='expense', category=(cat or 'Expenses'),
                amount=e.amount, method=e.method, branch_id=e.branch_id,
                term_id=e.term_id, session_id=_session_for_term(connection, e.term_id),
                origin_type='expense', origin_id=e.id, reference=e.reference,
                created_by=e.recorded_by, description=e.description,
                occurred_on=e.expense_date or _today())


def _sale_vals(connection, s):
    return dict(direction=REVENUE, source_module='sales', category='Sales',
                amount=(s.amount_paid if s.amount_paid else s.total), method=s.payment_method,
                branch_id=s.branch_id, student_id=s.student_id,
                origin_type='sale', origin_id=s.id, reference=s.receipt_no,
                created_by=s.sold_by, description='Shop / inventory sale',
                occurred_on=(s.created_at.date() if s.created_at else _today()))


def _reverse_by_origin(connection, origin_type, origin_id):
    """When a source row is deleted, cancel its ledger entry with a reversal row."""
    from models import FinanceTransaction
    tbl = FinanceTransaction.__table__
    row = connection.execute(
        select(tbl.c.id, tbl.c.direction, tbl.c.amount, tbl.c.source_module,
               tbl.c.category, tbl.c.method, tbl.c.branch_id, tbl.c.term_id,
               tbl.c.session_id, tbl.c.student_id, tbl.c.reference, tbl.c.reversed)
        .where(tbl.c.origin_type == origin_type, tbl.c.origin_id == origin_id)).first()
    if not row or row.reversed:
        return
    connection.execute(tbl.update()
                       .where(tbl.c.id == row.id).values(reversed=True))
    _insert_row(connection,
                direction=(EXPENSE if row.direction == REVENUE else REVENUE),
                amount=row.amount, source_module=row.source_module,
                category=row.category, method=row.method, branch_id=row.branch_id,
                term_id=row.term_id, session_id=row.session_id, student_id=row.student_id,
                origin_type='reversal', origin_id=None, reference=row.reference,
                description='Reversal (source deleted)', reversal_of_id=row.id)


_HOOKS_REGISTERED = False


def register_ledger_hooks():
    """Wire the auto-posting listeners onto the source models. Idempotent."""
    global _HOOKS_REGISTERED
    if _HOOKS_REGISTERED:
        return
    from models import FeePayment, Expense
    try:
        from models import Sale
    except Exception:
        Sale = None

    @event.listens_for(FeePayment, 'after_insert')
    def _fee_in(mapper, connection, target):
        _insert_row(connection, **_fee_payment_vals(connection, target))

    @event.listens_for(FeePayment, 'after_delete')
    def _fee_out(mapper, connection, target):
        _reverse_by_origin(connection, 'fee_payment', target.id)

    @event.listens_for(Expense, 'after_insert')
    def _exp_in(mapper, connection, target):
        _insert_row(connection, **_expense_vals(connection, target))

    @event.listens_for(Expense, 'after_delete')
    def _exp_out(mapper, connection, target):
        _reverse_by_origin(connection, 'expense', target.id)

    if Sale is not None:
        @event.listens_for(Sale, 'after_insert')
        def _sale_in(mapper, connection, target):
            _insert_row(connection, **_sale_vals(connection, target))

        @event.listens_for(Sale, 'after_delete')
        def _sale_out(mapper, connection, target):
            _reverse_by_origin(connection, 'sale', target.id)

    _HOOKS_REGISTERED = True


# --- backfill existing data into the ledger (one-off, idempotent) -----------
def backfill():
    """Post any pre-existing FeePayment / Expense / Sale rows that aren't in the
    ledger yet. Safe to run repeatedly. Returns the number of rows added."""
    from models import db, FinanceTransaction, FeePayment, Expense
    try:
        from models import Sale
    except Exception:
        Sale = None
    conn = db.session.connection()
    have = {(r.origin_type, r.origin_id)
            for r in db.session.query(FinanceTransaction.origin_type,
                                      FinanceTransaction.origin_id).all()}
    added = 0
    for p in FeePayment.query.all():
        if ('fee_payment', p.id) not in have:
            _insert_row(conn, **_fee_payment_vals(conn, p)); added += 1
    for e in Expense.query.all():
        if ('expense', e.id) not in have:
            _insert_row(conn, **_expense_vals(conn, e)); added += 1
    if Sale is not None:
        for s in Sale.query.all():
            if ('sale', s.id) not in have:
                _insert_row(conn, **_sale_vals(conn, s)); added += 1
    db.session.commit()
    return added
