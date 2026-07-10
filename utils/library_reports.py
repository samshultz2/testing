"""Library reports — server-side builders for the reporting screen and exports.

Each builder returns a uniform shape ({title, columns, rows, summary}) so the UI
and the CSV/Excel exporter can render any report the same way. All queries are
branch-scoped (via the owning book) and honour the shared filters.
"""
from __future__ import annotations

import datetime as _dt


REPORTS = [
    ('inventory', 'Book Inventory'),
    ('valuation', 'Inventory Valuation'),
    ('acquisitions', 'Book Acquisitions'),
    ('issued', 'Books Issued'),
    ('returned', 'Books Returned'),
    ('overdue', 'Overdue Books'),
    ('lost', 'Lost Books'),
    ('damaged', 'Damaged Books'),
    ('popular', 'Popular Books'),
    ('inactive', 'Inactive Books'),
    ('borrowers_class', 'Borrowers by Class'),
    ('borrowers_branch', 'Borrowers by Branch'),
]
_LABELS = dict(REPORTS)


def _books(filters):
    from models import Book
    from utils.branch_scope import scope_query
    q = scope_query(Book.query.filter_by(is_active=True), Book)
    if filters.get('category'):
        q = q.filter(Book.category == filters['category'])
    if filters.get('subject'):
        q = q.filter(Book.subject == filters['subject'])
    return q


def _loans():
    from models import Book, BookLoan
    from utils.branch_scope import scope_query
    return scope_query(BookLoan.query.join(Book, BookLoan.book_id == Book.id), Book)


def _date_between(q, col, filters):
    if filters.get('from'):
        q = q.filter(col >= filters['from'])
    if filters.get('to'):
        q = q.filter(col <= filters['to'])
    return q


def _money(v):
    return round(float(v or 0), 2)


def build(rtype, filters):
    fn = _BUILDERS.get(rtype) or _BUILDERS['inventory']
    out = fn(filters)
    out['type'] = rtype if rtype in _LABELS else 'inventory'
    out.setdefault('title', _LABELS.get(out['type'], 'Report'))
    return out


# --- book-based -------------------------------------------------------------
def _inventory(filters):
    from models import Book
    rows, total_copies, total_val = [], 0, 0.0
    for b in _books(filters).order_by(Book.title).all():
        val = _money((b.price or 0) * (b.copies_total or 0))
        total_copies += b.copies_total or 0
        total_val += val
        rows.append({'title': b.title, 'author': b.author or '', 'category': b.category or '',
                     'subject': b.subject or '', 'shelf': b.shelf or '', 'total': b.copies_total or 0,
                     'available': b.copies_available or 0, 'on_loan': b.on_loan, 'value': val})
    return {
        'columns': [
            {'key': 'title', 'label': 'Title'}, {'key': 'author', 'label': 'Author'},
            {'key': 'category', 'label': 'Category'}, {'key': 'subject', 'label': 'Subject'},
            {'key': 'shelf', 'label': 'Shelf'}, {'key': 'total', 'label': 'Total', 'align': 'right'},
            {'key': 'available', 'label': 'Available', 'align': 'right'},
            {'key': 'on_loan', 'label': 'On loan', 'align': 'right'},
            {'key': 'value', 'label': 'Value (₦)', 'align': 'right', 'money': True}],
        'rows': rows,
        'summary': [{'label': 'Titles', 'value': len(rows)},
                    {'label': 'Copies', 'value': total_copies},
                    {'label': 'Total value', 'value': f'₦{total_val:,.2f}'}],
    }


def _valuation(filters):
    r = _inventory(filters)
    r['title'] = _LABELS['valuation']
    return r


def _acquisitions(filters):
    from models import Book
    q = _books(filters)
    if filters.get('from'):
        q = q.filter(Book.created_at >= _dt.datetime.combine(filters['from'], _dt.time.min))
    if filters.get('to'):
        q = q.filter(Book.created_at <= _dt.datetime.combine(filters['to'], _dt.time.max))
    rows, spend = [], 0.0
    for b in q.order_by(Book.created_at.desc()).all():
        cost = _money((b.price or 0) * (b.copies_total or 0))
        spend += cost
        rows.append({'title': b.title, 'category': b.category or '', 'copies': b.copies_total or 0,
                     'price': _money(b.price), 'cost': cost,
                     'added': b.created_at.strftime('%d %b %Y') if b.created_at else ''})
    return {
        'columns': [{'key': 'added', 'label': 'Added'}, {'key': 'title', 'label': 'Title'},
                    {'key': 'category', 'label': 'Category'},
                    {'key': 'copies', 'label': 'Copies', 'align': 'right'},
                    {'key': 'price', 'label': 'Unit ₦', 'align': 'right', 'money': True},
                    {'key': 'cost', 'label': 'Cost ₦', 'align': 'right', 'money': True}],
        'rows': rows,
        'summary': [{'label': 'Titles added', 'value': len(rows)},
                    {'label': 'Acquisition spend', 'value': f'₦{spend:,.2f}'}],
    }


def _popular(filters):
    from sqlalchemy import func
    from models import Book, BookLoan
    from utils.branch_scope import scope_query
    q = scope_query(db_session().query(Book.title, Book.category, func.count(BookLoan.id).label('n'))
                    .join(BookLoan, BookLoan.book_id == Book.id), Book)
    q = _date_between(q, BookLoan.borrowed_date, filters)
    if filters.get('category'):
        q = q.filter(Book.category == filters['category'])
    rows = [{'title': t, 'category': c or '', 'loans': int(n)}
            for t, c, n in q.group_by(Book.title, Book.category).order_by(func.count(BookLoan.id).desc()).limit(100).all()]
    return {
        'columns': [{'key': 'title', 'label': 'Title'}, {'key': 'category', 'label': 'Category'},
                    {'key': 'loans', 'label': 'Times borrowed', 'align': 'right'}],
        'rows': rows,
        'summary': [{'label': 'Titles borrowed', 'value': len(rows)},
                    {'label': 'Total loans', 'value': sum(r['loans'] for r in rows)}],
    }


def _inactive(filters):
    from models import Book, BookLoan
    borrowed_ids = {r[0] for r in db_session().query(BookLoan.book_id).distinct().all()}
    rows = []
    for b in _books(filters).order_by(Book.title).all():
        if b.id in borrowed_ids:
            continue
        rows.append({'title': b.title, 'category': b.category or '', 'copies': b.copies_total or 0,
                     'added': b.created_at.strftime('%d %b %Y') if b.created_at else ''})
    return {
        'columns': [{'key': 'title', 'label': 'Title'}, {'key': 'category', 'label': 'Category'},
                    {'key': 'copies', 'label': 'Copies', 'align': 'right'}, {'key': 'added', 'label': 'Added'}],
        'rows': rows,
        'summary': [{'label': 'Never-borrowed titles', 'value': len(rows)}],
    }


# --- loan-based -------------------------------------------------------------
def _loan_rows(loans, cols, *, fine_per_day=0):
    from models import BookLoan
    out = []
    for l in loans:
        out.append({
            'book': l.book.title if l.book else '—', 'borrower': l.borrower_name,
            'type': (l.borrower_type or 'student').title(), 'ref': l.borrower_ref,
            'borrowed': l.borrowed_date.strftime('%d %b %Y') if l.borrowed_date else '',
            'due': l.due_date.strftime('%d %b %Y') if l.due_date else '',
            'returned': l.returned_date.strftime('%d %b %Y') if l.returned_date else '',
            'days_late': l.days_overdue, 'status': l.status,
            'fine': _money(l.fine), 'cost': _money(l.replacement_cost),
            'est_fine': _money(l.days_overdue * fine_per_day),
        })
    return out


def _issued(filters):
    from models import BookLoan
    q = _date_between(_loans(), BookLoan.borrowed_date, filters).order_by(BookLoan.borrowed_date.desc())
    rows = _loan_rows(q.limit(2000).all(), None)
    return {
        'columns': [{'key': 'borrowed', 'label': 'Borrowed'}, {'key': 'book', 'label': 'Book'},
                    {'key': 'borrower', 'label': 'Borrower'}, {'key': 'type', 'label': 'Type'},
                    {'key': 'due', 'label': 'Due'}, {'key': 'status', 'label': 'Status'}],
        'rows': rows, 'summary': [{'label': 'Issued', 'value': len(rows)}],
    }


def _returned(filters):
    from models import BookLoan
    q = _loans().filter(BookLoan.status == 'Returned')
    q = _date_between(q, BookLoan.returned_date, filters).order_by(BookLoan.returned_date.desc())
    rows = _loan_rows(q.limit(2000).all(), None)
    fines = sum(r['fine'] for r in rows)
    return {
        'columns': [{'key': 'returned', 'label': 'Returned'}, {'key': 'book', 'label': 'Book'},
                    {'key': 'borrower', 'label': 'Borrower'}, {'key': 'borrowed', 'label': 'Borrowed'},
                    {'key': 'fine', 'label': 'Fine ₦', 'align': 'right', 'money': True}],
        'rows': rows,
        'summary': [{'label': 'Returned', 'value': len(rows)},
                    {'label': 'Fines collected', 'value': f'₦{fines:,.2f}'}],
    }


def _overdue(filters):
    from models import BookLoan, SchoolSettings
    fpd = float(SchoolSettings.get('library_fine_per_day', 0) or 0)
    q = (_loans().filter(BookLoan.status == 'Borrowed', BookLoan.due_date < _dt.date.today())
         .order_by(BookLoan.due_date))
    rows = _loan_rows(q.all(), None, fine_per_day=fpd)
    est = sum(r['est_fine'] for r in rows)
    return {
        'columns': [{'key': 'due', 'label': 'Due'}, {'key': 'book', 'label': 'Book'},
                    {'key': 'borrower', 'label': 'Borrower'}, {'key': 'type', 'label': 'Type'},
                    {'key': 'days_late', 'label': 'Days late', 'align': 'right'},
                    {'key': 'est_fine', 'label': 'Est. fine ₦', 'align': 'right', 'money': True}],
        'rows': rows,
        'summary': [{'label': 'Overdue', 'value': len(rows)},
                    {'label': 'Estimated fines', 'value': f'₦{est:,.2f}'}],
    }


def _lost_or_damaged(status):
    def build_fn(filters):
        from models import BookLoan
        q = _date_between(_loans().filter(BookLoan.status == status),
                          BookLoan.returned_date, filters).order_by(BookLoan.returned_date.desc())
        rows = _loan_rows(q.all(), None)
        cost = sum(r['cost'] for r in rows)
        return {
            'columns': [{'key': 'returned', 'label': 'Date'}, {'key': 'book', 'label': 'Book'},
                        {'key': 'borrower', 'label': 'Borrower'},
                        {'key': 'cost', 'label': 'Cost ₦', 'align': 'right', 'money': True}],
            'rows': rows,
            'summary': [{'label': status, 'value': len(rows)},
                        {'label': 'Replacement cost', 'value': f'₦{cost:,.2f}'}],
        }
    return build_fn


def _borrowers_branch(filters):
    from models import Book, BookLoan, Branch
    from sqlalchemy import func
    from utils.branch_scope import scope_query
    q = scope_query(db_session().query(Book.branch_id,
                    func.count(func.distinct(BookLoan.student_id)),
                    func.count(BookLoan.id)).join(BookLoan, BookLoan.book_id == Book.id), Book)
    q = _date_between(q, BookLoan.borrowed_date, filters)
    names = {b.id: b.name for b in Branch.query.all()}
    rows = [{'branch': names.get(bid, 'Central' if bid is None else f'Branch {bid}'),
             'borrowers': int(nb or 0), 'loans': int(nl or 0)}
            for bid, nb, nl in q.group_by(Book.branch_id).all()]
    return {
        'columns': [{'key': 'branch', 'label': 'Branch'},
                    {'key': 'borrowers', 'label': 'Borrowers', 'align': 'right'},
                    {'key': 'loans', 'label': 'Loans', 'align': 'right'}],
        'rows': sorted(rows, key=lambda r: -r['loans']),
        'summary': [{'label': 'Branches', 'value': len(rows)}],
    }


def _borrowers_class(filters):
    from models import BookLoan
    q = _date_between(_loans().filter(BookLoan.borrower_type != 'staff',
                                      BookLoan.student_id.isnot(None)),
                      BookLoan.borrowed_date, filters)
    loans = q.all()
    labels = _student_class_map({l.student_id for l in loans if l.student_id})
    agg = {}
    for l in loans:
        cls = labels.get(l.student_id, 'Unassigned')
        a = agg.setdefault(cls, {'class': cls, 'students': set(), 'loans': 0})
        a['students'].add(l.student_id)
        a['loans'] += 1
    rows = sorted(({'class': a['class'], 'borrowers': len(a['students']), 'loans': a['loans']}
                   for a in agg.values()), key=lambda r: -r['loans'])
    return {
        'columns': [{'key': 'class', 'label': 'Class'},
                    {'key': 'borrowers', 'label': 'Borrowers', 'align': 'right'},
                    {'key': 'loans', 'label': 'Loans', 'align': 'right'}],
        'rows': rows,
        'summary': [{'label': 'Classes', 'value': len(rows)},
                    {'label': 'Loans', 'value': sum(r['loans'] for r in rows)}],
    }


def _student_class_map(student_ids):
    """{student_id: 'Class Arm'} for the active term (best-effort)."""
    if not student_ids:
        return {}
    from models import StudentEnrollment, ClassArmAssignment
    from utils.helpers import get_active_term
    term = get_active_term()
    if not term:
        return {}
    rows = (StudentEnrollment.query
            .join(ClassArmAssignment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
            .filter(StudentEnrollment.is_active.is_(True),
                    ClassArmAssignment.term_id == term.id,
                    StudentEnrollment.student_id.in_(student_ids)).all())
    out = {}
    for e in rows:
        asg = e.class_arm_assignment
        if asg:
            name = ' '.join(p for p in [asg.school_class.name if asg.school_class else '',
                                        asg.arm_label or ''] if p)
            out[e.student_id] = name or 'Class'
    return out


def db_session():
    from models import db
    return db.session


_BUILDERS = {
    'inventory': _inventory, 'valuation': _valuation, 'acquisitions': _acquisitions,
    'issued': _issued, 'returned': _returned, 'overdue': _overdue,
    'lost': _lost_or_damaged('Lost'), 'damaged': _lost_or_damaged('Damaged'),
    'popular': _popular, 'inactive': _inactive,
    'borrowers_class': _borrowers_class, 'borrowers_branch': _borrowers_branch,
}
