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

# The expense category a sale's cost of goods is booked under. Recognising cost
# at the point of sale (the matching principle) is what makes the ledger's
# net = revenue − expense a true gross-profit figure for the shop. Inventory
# purchases themselves are *not* expensed — they move cash into stock (an asset)
# and only become an expense, as COGS, when the stock is sold. Booking both would
# double-count the same inventory cost.
COGS_CATEGORY = 'Cost of Goods Sold'


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


# Product categories → the revenue bucket a sale of them is booked under, so the
# ledger/accounting splits shop income into meaningful lines (Bookshop, Uniform…)
# instead of one opaque "Sales". Anything unmapped falls back to "Other sales".
_SALE_BUCKETS = {
    # Legacy category names (kept so existing products still bucket correctly).
    'Textbook': 'Bookshop', 'Workbook': 'Bookshop', 'Notebook': 'Bookshop',
    'Stationery': 'Bookshop', 'Uniform': 'Uniform',
    # Current catalogue categories.
    'Academic Materials': 'Bookshop', 'Textbooks': 'Bookshop',
    'Exercise Books': 'Bookshop', 'School Bags': 'Bookshop',
    'Uniforms': 'Uniform', 'Sports Wear': 'Uniform',
}


def sale_category(product_categories):
    """Revenue category for a sale, from the product categories of its line items.
    One bucket → that bucket ('Bookshop'/'Uniform'); several → 'Mixed sales';
    none/unknown → 'Other sales'."""
    buckets = {_SALE_BUCKETS.get((c or '').strip(), 'Other sales')
               for c in (product_categories or []) if c is not None}
    buckets.discard(None)
    if not buckets:
        return 'Sales'
    if len(buckets) == 1:
        return next(iter(buckets))
    return 'Mixed sales'


def _sale_vals(connection, s):
    # The sales route stamps the computed bucket on the object before flush (the
    # line items don't exist in the DB yet at after_insert time); fall back to a
    # generic label for any sale created without one.
    category = getattr(s, '_ledger_category', None) or 'Sales'
    return dict(direction=REVENUE, source_module='sales', category=category,
                amount=(s.amount_paid if s.amount_paid else s.total), method=s.payment_method,
                branch_id=s.branch_id, student_id=s.student_id,
                origin_type='sale', origin_id=s.id, reference=s.receipt_no,
                created_by=s.sold_by, description='Shop / inventory sale',
                occurred_on=(s.created_at.date() if s.created_at else _today()))


def cogs_amount(lines):
    """Total cost of goods for a set of sale lines. ``lines`` is any iterable of
    (product, quantity, …) tuples — only the first two positions are read."""
    total = 0.0
    for line in lines:
        product, qty = line[0], line[1]
        total += (getattr(product, 'cost_price', 0) or 0) * (qty or 0)
    return round(total, 2)


def post_sale_cogs(sale, lines):
    """Book a sale's cost of goods sold as an EXPENSE (ORM), idempotent per sale.
    Called from the sales route right after the sale + its items are flushed, so
    the whole sale (revenue, stock, COGS) commits atomically. No-op when the cost
    is zero (e.g. products without a recorded cost)."""
    cogs = cogs_amount(lines)
    if cogs <= 0:
        return None
    return post(EXPENSE, cogs, source_module='cogs', category=COGS_CATEGORY,
                method=sale.payment_method, branch_id=sale.branch_id,
                student_id=sale.student_id, origin_type='sale_cogs', origin_id=sale.id,
                reference=sale.receipt_no, description='Cost of goods sold',
                created_by=sale.sold_by,
                occurred_on=(sale.created_at.date() if sale.created_at else _today()))


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


# Nullable columns added after the schema baseline. ``create_all`` never adds a
# column to an existing table, so bring older tenant DBs up to date in place with
# a tiny, dialect-portable ADD COLUMN (no defaults/constraints beyond the type).
_ADDED_COLUMNS = {
    'staff_signups': {'gender': 'VARCHAR(10)', 'staff_type': 'VARCHAR(20)',
                      'department_id': 'INTEGER', 'qualification': 'VARCHAR(200)'},
    # Cache of each candidate's drawn paper so the expensive pool draw runs once.
    'mock_jamb_attempts': {'paper': 'TEXT'},
    # Graduate lifecycle status on the student.
    'students': {'graduate_status': 'VARCHAR(40)'},
    'site_media': {'storage': "VARCHAR(10) DEFAULT 'db'", 'storage_key': 'VARCHAR(300)'},
    'gen_teachers': {'user_id': 'INTEGER'},   # link a generator-teacher to a login account
    'parent_contacts': {'email': 'VARCHAR(120)'},
    'message_recipients': {'email': 'VARCHAR(120)', 'read_at': 'TIMESTAMP'},
    'message_templates': {'is_favorite': 'BOOLEAN'},
    'announcements': {'needs_ack': 'BOOLEAN', 'attachment_id': 'INTEGER'},
    'messages': {'attachment_id': 'INTEGER'},
    'notifications': {'origin_recipient_id': 'INTEGER'},
    'library_books': {
        'subtitle': 'VARCHAR(200)', 'barcode': 'VARCHAR(40)', 'subject': 'VARCHAR(80)',
        'keywords': 'VARCHAR(255)', 'edition': 'VARCHAR(40)', 'publication_year': 'INTEGER',
        'language': 'VARCHAR(40)', 'description': 'TEXT', 'rack': 'VARCHAR(40)',
        'condition': 'VARCHAR(20)', 'reference_only': 'BOOLEAN', 'price': 'FLOAT',
        'status': 'VARCHAR(15)', 'lost_count': 'INTEGER', 'damaged_count': 'INTEGER',
        'supplier': 'VARCHAR(120)', 'source': 'VARCHAR(20)', 'donated_by': 'VARCHAR(120)',
    },
    'library_loans': {
        'borrower_type': 'VARCHAR(10)', 'staff_id': 'INTEGER', 'renew_count': 'INTEGER',
        'fine_waived': 'BOOLEAN', 'fine_posted': 'BOOLEAN', 'replacement_cost': 'FLOAT',
    },
    'staff_members': {
        'confirmation_date': 'DATE', 'contract_start': 'DATE', 'contract_end': 'DATE',
        'certifications': 'VARCHAR(255)', 'prior_experience_years': 'INTEGER',
        'emergency_name': 'TEXT', 'emergency_phone': 'TEXT',
        'tax_id': 'TEXT', 'pension_pin': 'TEXT', 'pension_provider': 'VARCHAR(120)',
        'blood_group': 'VARCHAR(6)', 'medical_notes': 'TEXT',
    },
    'staff_documents': {
        'version': 'INTEGER', 'replaces_id': 'INTEGER', 'is_current': 'BOOLEAN',
    },
    'students': {
        'house': 'VARCHAR(40)', 'boarding_status': 'VARCHAR(10)',
        'nin': 'VARCHAR(20)', 'jamb_reg_number': 'VARCHAR(30)', 'jamb_profile_code': 'VARCHAR(30)',
        'blood_group': 'VARCHAR(6)', 'genotype': 'VARCHAR(6)', 'allergies': 'TEXT',
        'medical_conditions': 'TEXT', 'disabilities': 'TEXT', 'medications': 'TEXT',
        'medical_notes': 'TEXT', 'emergency_medical': 'TEXT',
    },
    'sales_products': {
        'barcode': 'VARCHAR(60)', 'brand': 'VARCHAR(80)', 'description': 'TEXT',
        'image_url': 'VARCHAR(255)', 'discount_price': 'FLOAT', 'wholesale_price': 'FLOAT',
        'staff_price': 'FLOAT', 'student_price': 'FLOAT', 'parent_price': 'FLOAT',
        'opening_stock': 'INTEGER', 'max_stock': 'INTEGER', 'reorder_qty': 'INTEGER',
        'unit': 'VARCHAR(20)', 'pack_size': 'VARCHAR(30)', 'taxable': 'BOOLEAN',
        'vat_rate': 'FLOAT', 'preferred_supplier': 'VARCHAR(120)',
        'storage_location': 'VARCHAR(80)', 'expiry_date': 'DATE', 'warranty_period': 'VARCHAR(40)',
        'batch_tracked': 'BOOLEAN',
    },
    'sales': {'customer_type': 'VARCHAR(20)', 'subtotal': 'FLOAT',
              'discount': 'FLOAT', 'discount_code': 'VARCHAR(30)'},
}

# Columns whose NOT NULL constraint must be relaxed on existing databases (a
# borrower can now be a staff member, so a loan's student_id may be NULL).
_DROP_NOT_NULL = {'library_loans': ['student_id'],
                  'site_media': ['data']}          # bytes are NULL for non-DB backends


# Indexes that post-date the schema baseline and must be added to existing main
# and tenant databases (SKIP_CREATE_ALL means model-level index=True only affects
# freshly-created DBs). CREATE INDEX IF NOT EXISTS is supported by SQLite and
# Postgres and is a no-op once present.
_ADDED_INDEXES = {
    'ix_parent_contacts_student_id': ('parent_contacts', 'student_id'),
    # Mock-JAMB sitting draws the pool by (subject_id, mock_exam_id) on every paper
    # render; index it so a mass start does index scans, not full-table scans.
    'ix_mock_jamb_questions_subject_pool': ('mock_jamb_questions', 'subject_id, mock_exam_id'),
    'ix_mock_jamb_passages_subject_pool': ('mock_jamb_passages', 'subject_id, mock_exam_id'),
}


def _ensure_indexes(engine):
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    for name, (table, column) in _ADDED_INDEXES.items():
        try:
            existing_tables = insp.get_table_names()
        except Exception:
            return
        if table not in existing_tables:
            continue
        try:
            with engine.begin() as conn:
                conn.execute(text(
                    f'CREATE INDEX IF NOT EXISTS {name} ON {table} ({column})'))
        except Exception:
            pass                               # racy/duplicate — safe to ignore


def _ensure_columns(engine):
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    for table, cols in _ADDED_COLUMNS.items():
        try:
            existing = {c['name'] for c in insp.get_columns(table)}
        except Exception:
            continue                       # table not present on this DB — skip
        for name, ddl in cols.items():
            if name not in existing:
                try:
                    with engine.begin() as conn:
                        conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))
                except Exception:
                    pass                   # racy/duplicate add — safe to ignore
    # Relax NOT NULL where a column became optional (Postgres only; SQLite can't
    # ALTER a constraint but fresh SQLite DBs already match the model).
    if engine.dialect.name == 'postgresql':
        for table, columns in _DROP_NOT_NULL.items():
            for col in columns:
                try:
                    with engine.begin() as conn:
                        conn.execute(text(f'ALTER TABLE {table} ALTER COLUMN {col} DROP NOT NULL'))
                except Exception:
                    pass


def ensure_tables(bind=None):
    """Create newer tables that post-date the schema baseline (the finance ledger,
    additional charges, installment plans, and saved recipient groups) if they
    don't exist yet, and add any post-baseline nullable columns. Idempotent
    (checkfirst). Needed because production runs with SKIP_CREATE_ALL=1 — Alembic
    owns the schema and never auto-creates these newer tables/columns — and because
    existing tenant databases predate them."""
    from models import (db, FinanceTransaction, AdditionalCharge, InstallmentPlan,
                        RecipientGroup, AnnouncementAck, CommAttachment,
                        Conversation, ConversationMember, ChatMessage,
                        BookReservation, ReadingListItem, StaffEvent,
                        StaffDocument, TrainingRecord, PerformanceReview,
                        JobVacancy, JobApplication, Interview,
                        AttendanceIntervention, InterventionNote, StockMovement,
                        Supplier, PurchaseOrder, PurchaseOrderItem, SupplierPayment,
                        PromoCode, StockAudit, StockAuditItem, FixedAsset, StockBatch,
                        UserSession, SiteSettings, SitePage, SiteMedia,
                        SiteViewDaily, SiteReferrerDaily, SiteVisitorDaily,
                        HolidayAssignment, NewsPost,
                        StaffLoan, LoanGuarantor, LoanRepayment)
    from models import TermAssessmentSetting, StaffInvite, StaffSignup, GraduateAudit
    tables = [FinanceTransaction.__table__, AdditionalCharge.__table__,
              InstallmentPlan.__table__, RecipientGroup.__table__,
              AnnouncementAck.__table__, CommAttachment.__table__,
              Conversation.__table__, ConversationMember.__table__,
              ChatMessage.__table__, BookReservation.__table__,
              ReadingListItem.__table__, StaffEvent.__table__,
              StaffDocument.__table__, TrainingRecord.__table__,
              PerformanceReview.__table__, JobVacancy.__table__,
              JobApplication.__table__, Interview.__table__,
              AttendanceIntervention.__table__, InterventionNote.__table__,
              StockMovement.__table__, Supplier.__table__, PurchaseOrder.__table__,
              PurchaseOrderItem.__table__, SupplierPayment.__table__, PromoCode.__table__,
              StockAudit.__table__, StockAuditItem.__table__, FixedAsset.__table__,
              StockBatch.__table__, UserSession.__table__,
              SiteSettings.__table__, SitePage.__table__, SiteMedia.__table__,
              SiteViewDaily.__table__, SiteReferrerDaily.__table__,
              SiteVisitorDaily.__table__, HolidayAssignment.__table__,
              NewsPost.__table__, StaffLoan.__table__, LoanGuarantor.__table__,
              LoanRepayment.__table__, TermAssessmentSetting.__table__,
              StaffInvite.__table__, StaffSignup.__table__, GraduateAudit.__table__]
    engine = bind if bind is not None else db.engine
    # Never let a failure creating one newer TABLE stop the column/index self-heal
    # that follows — the added COLUMNS (e.g. students.graduate_status) sit on hot,
    # always-queried tables, so skipping them would 500 the dashboard.
    try:
        db.metadata.create_all(bind=engine, tables=tables, checkfirst=True)
    except Exception:
        try:
            from flask import current_app
            current_app.logger.exception('ensure_tables: create_all failed; continuing to column/index heal')
        except Exception:
            pass
    _ensure_columns(engine)
    _ensure_indexes(engine)


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
            _reverse_by_origin(connection, 'sale_cogs', target.id)

    _HOOKS_REGISTERED = True


# --- reporting: read the ledger (Phase 1) -----------------------------------
def _effective_query(filters):
    """Base query over 'live' ledger rows (excludes reversed originals and the
    reversal entries themselves) matching the given filters."""
    from models import db, FinanceTransaction as F
    q = db.session.query(F).filter(F.reversed.is_(False), F.origin_type != 'reversal')
    branch_ids = filters.get('branch_ids')
    if branch_ids:
        q = q.filter(F.branch_id.in_(branch_ids))
    if filters.get('session_id'):
        q = q.filter(F.session_id == filters['session_id'])
    if filters.get('term_id'):
        q = q.filter(F.term_id == filters['term_id'])
    if filters.get('date_from'):
        q = q.filter(F.occurred_on >= filters['date_from'])
    if filters.get('date_to'):
        q = q.filter(F.occurred_on <= filters['date_to'])
    if filters.get('source_module'):
        q = q.filter(F.source_module == filters['source_module'])
    if filters.get('category'):
        q = q.filter(F.category == filters['category'])
    if filters.get('method'):
        q = q.filter(F.method == filters['method'])
    if filters.get('direction'):
        q = q.filter(F.direction == filters['direction'])
    if filters.get('student_id'):
        q = q.filter(F.student_id == filters['student_id'])
    return q


def _branch_names():
    from models import Branch
    return {b.id: b.name for b in Branch.query.all()}


def _sum(q, direction):
    from sqlalchemy import func
    from models import FinanceTransaction as F
    v = q.filter(F.direction == direction).with_entities(func.coalesce(func.sum(F.amount), 0)).scalar()
    return round(float(v or 0), 2)


def _group(q, col, direction=None):
    from sqlalchemy import func
    from models import FinanceTransaction as F
    qq = q
    if direction:
        qq = qq.filter(F.direction == direction)
    rows = qq.with_entities(col, func.coalesce(func.sum(F.amount), 0), func.count(F.id)).group_by(col).all()
    return [{'key': r[0], 'total': round(float(r[1] or 0), 2), 'count': int(r[2])} for r in rows]


def summary(filters):
    """Everything the finance overview needs, computed from the ledger."""
    import datetime as dt
    from models import FinanceTransaction as F
    base = _effective_query(filters)
    revenue, expense = _sum(base, REVENUE), _sum(base, EXPENSE)
    names = _branch_names()

    def label_branch(rows):
        for r in rows:
            r['label'] = names.get(r['key'], 'Central / unbranched' if r['key'] is None else f'Branch {r["key"]}')
        return rows

    # collections for standard windows (revenue only)
    today = dt.date.today()
    def collected(since):
        f = dict(filters); f['date_from'] = since; f['date_to'] = today; f['direction'] = REVENUE
        return _sum(_effective_query(f), REVENUE)
    week_start = today - dt.timedelta(days=today.weekday())
    year_start = today.replace(month=1, day=1)
    month_start = today.replace(day=1)

    recent = (base.order_by(F.occurred_on.desc(), F.id.desc()).limit(15).all())
    return {
        'revenue': revenue, 'expense': expense, 'net': round(revenue - expense, 2),
        'count': base.count(),
        'today': collected(today), 'week': collected(week_start),
        'month': collected(month_start), 'year': collected(year_start),
        'by_source': sorted(_group(base, F.category, REVENUE), key=lambda r: -r['total']),
        'by_expense': sorted(_group(base, F.category, EXPENSE), key=lambda r: -r['total']),
        'by_method': sorted(_group(base, F.method, REVENUE), key=lambda r: -r['total']),
        'by_branch': label_branch(_group(base, F.branch_id)),
        'by_module': _group(base, F.source_module),
        'recent': [{
            'date': (t.occurred_on.strftime('%d %b %Y') if t.occurred_on else ''),
            'direction': t.direction, 'source': t.source_module, 'category': t.category,
            'amount': round(float(t.amount or 0), 2), 'method': t.method or '',
            'branch': names.get(t.branch_id, '—' if t.branch_id is None else ''),
            'description': t.description or '', 'reference': t.reference or '',
        } for t in recent],
    }


def filter_options():
    """Distinct values for the overview filter dropdowns."""
    from models import db, FinanceTransaction as F, Branch, AcademicSession, Term
    def distinct(col):
        return [r[0] for r in db.session.query(col).filter(col.isnot(None)).distinct().all() if r[0] != '']
    return {
        'branches': [{'id': b.id, 'name': b.name} for b in Branch.query.order_by(Branch.name).all()],
        'sessions': [{'id': s.id, 'name': s.name} for s in AcademicSession.query.order_by(AcademicSession.id.desc()).all()],
        'terms': [{'id': t.id, 'name': t.full_name} for t in Term.query.order_by(Term.id.desc()).all()],
        'sources': sorted(distinct(F.source_module)),
        'methods': sorted(distinct(F.method)),
        'categories': sorted(distinct(F.category)),
    }


def export_rows(filters):
    """Flat rows for CSV/Excel export of the filtered ledger."""
    from models import FinanceTransaction as F
    names = _branch_names()
    q = _effective_query(filters).order_by(F.occurred_on.desc(), F.id.desc())
    out = []
    for t in q.all():
        out.append([
            t.occurred_on.strftime('%Y-%m-%d') if t.occurred_on else '',
            'Revenue' if t.direction == REVENUE else 'Expense',
            t.source_module, t.category or '', t.method or '',
            names.get(t.branch_id, '') if t.branch_id else 'Central',
            round(float(t.amount or 0), 2), t.reference or '', t.description or '',
        ])
    return out


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
                if not getattr(s, '_ledger_category', None):
                    s._ledger_category = sale_category(
                        [(it.product.category if it.product else None) for it in s.items])
                _insert_row(conn, **_sale_vals(conn, s)); added += 1
            if ('sale_cogs', s.id) not in have:
                cost = cogs_amount([(it.product, it.quantity) for it in s.items if it.product])
                if cost > 0:
                    _insert_row(conn, direction=EXPENSE, source_module='cogs',
                                category=COGS_CATEGORY, amount=cost, method=s.payment_method,
                                branch_id=s.branch_id, student_id=s.student_id,
                                origin_type='sale_cogs', origin_id=s.id,
                                reference=s.receipt_no, description='Cost of goods sold',
                                occurred_on=(s.created_at.date() if s.created_at else _today()))
                    added += 1
    db.session.commit()
    return added
