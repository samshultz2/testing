"""
Library routes — book catalogue, issue/return with overdue fines, loan history
and a dashboard.
"""
from datetime import datetime, date, timedelta
import csv
import io
from utils.helpers import safe_redirect

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify, Response)
from sqlalchemy import func

from models import db, Book, BookLoan, Student, SchoolSettings
from utils.access_control import login_required, admin_required, is_admin
from utils.branch_scope import (scope_query, scope_by_student, require_branch_access,
                                can_access_branch)
from utils.search import like_term

library_bp = Blueprint('library', __name__, url_prefix='/library')


def _settings():
    return {
        'loan_days': int(SchoolSettings.get('library_loan_days', 14) or 14),
        'fine_per_day': float(SchoolSettings.get('library_fine_per_day', 0) or 0),
    }


def _d(value, default=None):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return default


def _wants_json():
    return request.headers.get('X-Requested-With') == 'fetch' or request.is_json


def _ok(message, redirect_url=None):
    if _wants_json():
        return jsonify({'ok': True, 'message': message, 'redirect': redirect_url})
    flash(message, 'success')
    return redirect(redirect_url or url_for('library.dashboard'))


def _err(message, redirect_url=None, info=False):
    if _wants_json():
        return jsonify({'ok': False, 'error': message}), 400
    flash(message, 'info' if info else 'error')
    return redirect(redirect_url or url_for('library.dashboard'))


def _urls():
    return {k: url_for('library.' + v) for k, v in {
        'dashboard': 'dashboard', 'books': 'books', 'issue': 'issue', 'loans': 'loans',
        'reports': 'reports', 'settings': 'settings', 'add_book': 'add_book', 'export': 'export',
        'book_search': 'book_search', 'student_search': 'student_search',
        'staff_search': 'staff_search', 'barcode_lookup': 'barcode_lookup',
        'remind_overdue': 'remind_overdue'}.items()}


def _render(payload):
    payload['urls'] = {**_urls(), **payload.get('urls', {})}
    payload['is_admin'] = is_admin()
    from utils.spa import render_or_json
    return render_or_json('library/app.html', 'library_json', payload)


# ============================================================================
# DASHBOARD
# ============================================================================

def _scope_loans(query):
    """Scope a BookLoan query to the viewer's branch via the owning book (works for
    both student and staff loans, unlike scoping by the borrowing student)."""
    return scope_query(query.join(Book, BookLoan.book_id == Book.id), Book)


@library_bp.route('/')
@login_required
def dashboard():
    import datetime as _dt
    today = date.today()
    month_start = today.replace(day=1)
    books_q = scope_query(Book.query.filter_by(is_active=True), Book)
    titles = books_q.count()
    copies = scope_query(db.session.query(func.coalesce(func.sum(Book.copies_total), 0)), Book).scalar() or 0
    available = scope_query(db.session.query(func.coalesce(func.sum(Book.copies_available), 0)), Book).scalar() or 0
    lost = scope_query(db.session.query(func.coalesce(func.sum(Book.lost_count), 0)), Book).scalar() or 0
    damaged = scope_query(db.session.query(func.coalesce(func.sum(Book.damaged_count), 0)), Book).scalar() or 0
    on_loan = (copies or 0) - (available or 0)

    def _loans(*filters):
        q = _scope_loans(BookLoan.query)
        for f in filters:
            q = q.filter(f)
        return q
    overdue = _loans(BookLoan.status == 'Borrowed', BookLoan.due_date < today).count()
    issued_today = _loans(BookLoan.borrowed_date == today).count()
    returned_today = _loans(BookLoan.status == 'Returned', BookLoan.returned_date == today).count()
    added_month = books_q.filter(Book.created_at >= _dt.datetime.combine(month_start, _dt.time.min)).count()
    active_borrowers = (_loans(BookLoan.status == 'Borrowed')
                        .with_entities(BookLoan.borrower_type, BookLoan.student_id, BookLoan.staff_id)
                        .distinct().count())

    # Most-borrowed books (all-time, by loan count).
    top_rows = (_scope_loans(db.session.query(Book.title, func.count(BookLoan.id).label('n')))
                .group_by(Book.title).order_by(func.count(BookLoan.id).desc()).limit(6).all())
    most_borrowed = [{'title': t, 'count': int(n)} for t, n in top_rows]

    cat_rows = (scope_query(db.session.query(Book.category, func.count(Book.id))
                .filter(Book.is_active == True), Book).group_by(Book.category).all())
    cat_chart = [{'name': c or 'Uncategorised', 'count': n} for c, n in cat_rows]
    recent = (_scope_loans(BookLoan.query).order_by(BookLoan.created_at.desc()).limit(8).all())
    return _render({
        'page': 'dashboard', 'titles': titles, 'copies': int(copies), 'available': int(available),
        'on_loan': on_loan, 'overdue': overdue, 'lost': int(lost), 'damaged': int(damaged),
        'issued_today': issued_today, 'returned_today': returned_today,
        'added_month': added_month, 'active_borrowers': active_borrowers,
        'most_borrowed': most_borrowed, 'cat_chart': cat_chart,
        'recent': [_loan_row(l, short=True) for l in recent],
    })


def _loan_row(l, short=False):
    bfmt = '%d %b' if short else '%d %b %Y'
    return {
        'id': l.id, 'book': l.book.title if l.book else '—',
        'student': l.borrower_name, 'borrower_type': l.borrower_type or 'student',
        'borrower_ref': l.borrower_ref,
        'borrowed': l.borrowed_date.strftime(bfmt) if l.borrowed_date else '',
        'due': l.due_date.strftime(bfmt) if l.due_date else '',
        'is_overdue': bool(l.is_overdue), 'days_overdue': l.days_overdue,
        'renew_count': l.renew_count or 0,
        'status': l.status, 'fine': l.fine or 0,
        'replacement_cost': l.replacement_cost or 0,
        'returned': l.returned_date.strftime('%d %b %Y') if l.returned_date else '',
        'return_url': url_for('library.return_loan', loan_id=l.id),
        'renew_url': url_for('library.renew_loan', loan_id=l.id),
        'mark_url': url_for('library.mark_loan', loan_id=l.id),
    }


# ============================================================================
# CATALOGUE
# ============================================================================

@library_bp.route('/books')
@login_required
def books():
    q = (request.args.get('q') or '').strip()
    category = request.args.get('category')
    avail = request.args.get('avail')
    from utils.branch_scope import scope_query
    subject = request.args.get('subject')
    query = scope_query(Book.query.filter_by(is_active=True), Book)
    if q:
        like = like_term(q)
        query = query.filter(db.or_(
            Book.title.ilike(like, escape='\\'), Book.author.ilike(like, escape='\\'),
            Book.isbn.ilike(like, escape='\\'), Book.barcode.ilike(like, escape='\\'),
            Book.subject.ilike(like, escape='\\'), Book.keywords.ilike(like, escape='\\'),
            Book.publisher.ilike(like, escape='\\')))
    if category:
        query = query.filter_by(category=category)
    if subject:
        query = query.filter_by(subject=subject)
    if avail == '1':
        query = query.filter(Book.copies_available > 0, Book.reference_only.isnot(True))
    rows = query.order_by(Book.title).all()
    return _render({
        'page': 'books', 'q': q, 'category': category or '', 'subject': subject or '',
        'avail': avail or '', 'categories': _distinct_categories(), 'subjects': _distinct('subject'),
        'books': [{'id': b.id, 'title': b.title, 'subtitle': b.subtitle, 'isbn': b.isbn,
                   'barcode': b.barcode, 'author': b.author, 'category': b.category,
                   'subject': b.subject, 'shelf': b.shelf, 'rack': b.rack,
                   'reference_only': bool(b.reference_only), 'status': b.status or 'Available',
                   'copies_available': b.copies_available, 'copies_total': b.copies_total,
                   'edit_url': url_for('library.edit_book', book_id=b.id),
                   'issue_url': url_for('library.issue') + f'?book_id={b.id}',
                   'delete_url': url_for('library.delete_book', book_id=b.id)} for b in rows],
    })


def _book_dict(b):
    return {
        'id': b.id, 'title': b.title, 'subtitle': b.subtitle or '', 'author': b.author or '',
        'isbn': b.isbn or '', 'barcode': b.barcode or '', 'category': b.category or '',
        'subject': b.subject or '', 'keywords': b.keywords or '', 'publisher': b.publisher or '',
        'edition': b.edition or '', 'publication_year': b.publication_year or '',
        'language': b.language or '', 'description': b.description or '',
        'shelf': b.shelf or '', 'rack': b.rack or '', 'condition': b.condition or 'Good',
        'reference_only': bool(b.reference_only), 'price': b.price or 0,
        'status': b.status or 'Available',
        'copies_total': b.copies_total, 'copies_available': b.copies_available,
        'on_loan': b.on_loan, 'notes': b.notes or '',
    }


def _book_payload(b):
    return {
        'page': 'book_form',
        'book': (_book_dict(b) if b else None),
        'categories': _distinct_categories(),
        'subjects': _distinct('subject'),
        'submit_url': url_for('library.edit_book', book_id=b.id) if b else url_for('library.add_book'),
    }


_STR_FIELDS = ('title', 'subtitle', 'author', 'isbn', 'barcode', 'category', 'subject',
               'keywords', 'publisher', 'edition', 'language', 'shelf', 'rack', 'notes')


def _read_book(b):
    for f in _STR_FIELDS:
        val = (request.form.get(f) or '').strip() or None
        setattr(b, f, val)
    b.title = (request.form.get('title') or '').strip()      # required, keep as ''
    b.description = (request.form.get('description') or '').strip() or None
    b.condition = (request.form.get('condition') or 'Good').strip() or 'Good'
    b.reference_only = bool(request.form.get('reference_only'))
    b.status = (request.form.get('status') or 'Available').strip() or 'Available'
    b.price = request.form.get('price', type=float) or 0
    b.publication_year = request.form.get('publication_year', type=int)


def _distinct(col):
    rows = db.session.query(getattr(Book, col)).filter(
        getattr(Book, col).isnot(None), getattr(Book, col) != '').distinct().all()
    return sorted({r[0] for r in rows if r[0]})


def _distinct_categories():
    return _distinct('category')


@library_bp.route('/books/add', methods=['GET', 'POST'])
@login_required
def add_book():
    if request.method == 'POST':
        if not request.form.get('title'):
            return _err('Title is required.', url_for('library.add_book'))
        total = request.form.get('copies_total', type=int) or 1
        b = Book(copies_total=total, copies_available=total)
        _read_book(b)
        from utils.branch_scope import branch_for_new
        b.branch_id = branch_for_new()
        db.session.add(b)
        db.session.commit()
        return _ok(f'Added "{b.title}".', url_for('library.books'))
    return _render(_book_payload(None))


@library_bp.route('/books/<int:book_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_book(book_id):
    b = db.get_or_404(Book, book_id)
    require_branch_access(b.branch_id)
    if request.method == 'POST':
        new_total = request.form.get('copies_total', type=int)
        _read_book(b)
        if new_total is not None and new_total >= 0:
            # keep availability consistent with the change in total copies
            delta = new_total - (b.copies_total or 0)
            b.copies_total = new_total
            b.copies_available = max((b.copies_available or 0) + delta, 0)
            if b.copies_available > b.copies_total:
                b.copies_available = b.copies_total
        db.session.commit()
        return _ok('Book updated.', url_for('library.books'))
    return _render(_book_payload(b))


@library_bp.route('/books/<int:book_id>/delete', methods=['POST'])
@admin_required
def delete_book(book_id):
    b = db.get_or_404(Book, book_id)
    require_branch_access(b.branch_id)
    if b.loans.filter_by(status='Borrowed').count():
        return _err('Cannot delete: copies are still on loan.', url_for('library.books'))
    b.is_active = False
    db.session.commit()
    from utils.audit import log_action
    log_action('library.book_delete', detail=getattr(b, 'title', None), target=b)
    return _ok('Book removed.', url_for('library.books'))


# ============================================================================
# ISSUE / RETURN
# ============================================================================

@library_bp.route('/issue', methods=['GET', 'POST'])
@login_required
def issue():
    s = _settings()
    if request.method == 'POST':
        book = _resolve_book(request.form)
        borrower_type = 'staff' if (request.form.get('borrower_type') == 'staff') else 'student'
        if not book:
            return _err('Select a book (or scan its barcode).', url_for('library.issue'))
        if borrower_type == 'staff':
            from models import StaffMember
            borrower = db.session.get(StaffMember, request.form.get('staff_id', type=int) or 0)
            branch_ok = borrower and can_access_branch(borrower.branch_id)
        else:
            borrower = db.session.get(Student, request.form.get('student_id', type=int) or 0)
            branch_ok = borrower and can_access_branch(borrower.branch_id)
        if not borrower:
            return _err('Select a borrower.', url_for('library.issue'))
        if not can_access_branch(book.branch_id) or not branch_ok:
            return _err('That book or borrower belongs to another branch.', url_for('library.issue'))
        if book.reference_only:
            return _err(f'"{book.title}" is reference-only and cannot be borrowed.', url_for('library.issue'))
        if not book.borrowable:
            return _err('No copies available for that title.', url_for('library.issue'))
        due = _d(request.form.get('due_date')) or (date.today() + timedelta(days=s['loan_days']))
        loan = BookLoan(book_id=book.id, borrower_type=borrower_type,
                        borrowed_date=date.today(), due_date=due, status='Borrowed')
        if borrower_type == 'staff':
            loan.staff_id = borrower.id
            name = borrower.display_name or borrower.full_name
        else:
            loan.student_id = borrower.id
            name = borrower.full_name
        book.copies_available = (book.copies_available or 0) - 1
        db.session.add(loan)
        db.session.commit()
        from utils.audit import log_action
        log_action('library.issue', detail=f'{book.title} -> {name}', target=loan)
        return _ok(f'Issued "{book.title}" to {name} (due {due.strftime("%d %b %Y")}).',
                   url_for('library.loans'))
    preset = db.session.get(Book, request.args.get('book_id', type=int)) if request.args.get('book_id') else None
    return _render({
        'page': 'issue', 'settings': s,
        'default_due': (date.today() + timedelta(days=s['loan_days'])).isoformat(),
        'preset': ({'id': preset.id, 'title': preset.title, 'available': preset.copies_available,
                    'reference_only': bool(preset.reference_only)} if preset else None),
        'urls': {'staff_search': url_for('library.staff_search'),
                 'barcode_lookup': url_for('library.barcode_lookup')},
        'submit_url': url_for('library.issue'),
    })


def _resolve_book(form):
    """Book from an explicit id, else a scanned barcode/ISBN."""
    book_id = form.get('book_id', type=int)
    if book_id:
        return db.session.get(Book, book_id)
    code = (form.get('barcode') or '').strip()
    if code:
        return (scope_query(Book.query.filter_by(is_active=True), Book)
                .filter(db.or_(Book.barcode == code, Book.isbn == code)).first())
    return None


def _post_library_charge(loan, amount, reason):
    """Add a library fine/replacement cost to a student borrower's term bill via the
    Finance module (idempotent per loan). Staff borrowers have no bill, so skipped."""
    if not amount or amount <= 0 or loan.fine_posted or not loan.is_student or not loan.student_id:
        return False
    try:
        from models import AdditionalCharge
        from utils.helpers import get_active_term
        from utils.access_control import get_current_user
        term = get_active_term()
        if not term:
            return False
        who = getattr(get_current_user(), 'full_name', None) or 'Librarian'
        db.session.add(AdditionalCharge(
            student_id=loan.student_id, term_id=term.id,
            branch_id=loan.book.branch_id if loan.book else None,
            kind='charge', category='Library fine', description=reason,
            amount=round(amount, 2), created_by=who))
        loan.fine_posted = True
        return True
    except Exception:
        return False


def _restock(book):
    if book:
        book.copies_available = min((book.copies_available or 0) + 1, book.copies_total or 0)


@library_bp.route('/loans/<int:loan_id>/return', methods=['POST'])
@login_required
def return_loan(loan_id):
    loan = db.get_or_404(BookLoan, loan_id)
    require_branch_access(loan.book.branch_id if loan.book else None)
    if loan.status != 'Borrowed':
        return _err('This loan is already closed.', url_for('library.loans'), info=True)
    s = _settings()
    loan.returned_date = date.today()
    loan.status = 'Returned'
    if request.form.get('waive'):
        loan.fine_waived = True
        loan.fine = 0
    else:
        loan.fine = round(loan.days_overdue * s['fine_per_day'], 2)
    _restock(loan.book)
    posted = _post_library_charge(loan, loan.fine, 'Overdue library book') if loan.fine else False
    db.session.commit()
    from utils.audit import log_action
    log_action('library.return', detail=f'{loan.book.title if loan.book else "book"} ({loan.borrower_name})',
               target=loan)
    msg = f'Returned "{loan.book.title if loan.book else "book"}".'
    if loan.fine:
        msg += f' Overdue fine ₦{loan.fine:,.2f}' + (' billed to the student.' if posted else '.')
    elif loan.fine_waived and loan.days_overdue:
        msg += ' Fine waived.'
    return _ok(msg, url_for('library.loans'))


@library_bp.route('/loans/<int:loan_id>/renew', methods=['POST'])
@login_required
def renew_loan(loan_id):
    loan = db.get_or_404(BookLoan, loan_id)
    require_branch_access(loan.book.branch_id if loan.book else None)
    if loan.status != 'Borrowed':
        return _err('Only an active loan can be renewed.', url_for('library.loans'), info=True)
    s = _settings()
    base = max(loan.due_date or date.today(), date.today())
    loan.due_date = base + timedelta(days=s['loan_days'])
    loan.renew_count = (loan.renew_count or 0) + 1
    db.session.commit()
    from utils.audit import log_action
    log_action('library.renew', detail=f'{loan.book.title if loan.book else "book"} (#{loan.renew_count})',
               target=loan)
    return _ok(f'Renewed — now due {loan.due_date.strftime("%d %b %Y")}.', url_for('library.loans'))


@library_bp.route('/loans/<int:loan_id>/mark', methods=['POST'])
@login_required
def mark_loan(loan_id):
    """Mark an active loan Lost or Damaged: the copy leaves circulation and an
    optional replacement cost is billed to the borrower (students)."""
    loan = db.get_or_404(BookLoan, loan_id)
    require_branch_access(loan.book.branch_id if loan.book else None)
    kind = request.form.get('kind')
    if kind not in ('Lost', 'Damaged'):
        return _err('Choose Lost or Damaged.', url_for('library.loans'))
    if loan.status != 'Borrowed':
        return _err('Only an active loan can be marked lost or damaged.', url_for('library.loans'), info=True)
    cost = request.form.get('cost', type=float)
    if cost is None:
        cost = (loan.book.price or 0) if loan.book else 0
    loan.status = kind
    loan.returned_date = date.today()
    loan.replacement_cost = round(cost or 0, 2)
    # The copy is gone/out of service — reduce total stock, tally on the book.
    if loan.book:
        if kind == 'Lost':
            loan.book.lost_count = (loan.book.lost_count or 0) + 1
        else:
            loan.book.damaged_count = (loan.book.damaged_count or 0) + 1
        loan.book.copies_total = max((loan.book.copies_total or 1) - 1, 0)
        # availability was already decremented at issue; keep it within bounds
        loan.book.copies_available = min(loan.book.copies_available or 0, loan.book.copies_total)
    posted = _post_library_charge(loan, loan.replacement_cost, f'{kind} library book')
    db.session.commit()
    from utils.audit import log_action
    log_action(f'library.{kind.lower()}', detail=f'{loan.book.title if loan.book else "book"} ({loan.borrower_name})',
               target=loan)
    msg = f'Marked "{loan.book.title if loan.book else "book"}" as {kind.lower()}.'
    if loan.replacement_cost:
        msg += f' Replacement cost ₦{loan.replacement_cost:,.2f}' + (' billed.' if posted else '.')
    return _ok(msg, url_for('library.loans'))


@library_bp.route('/loans')
@login_required
def loans():
    status = request.args.get('status', 'Borrowed')
    q = _scope_loans(BookLoan.query)
    if status == 'Overdue':
        q = q.filter(BookLoan.status == 'Borrowed', BookLoan.due_date < date.today())
    elif status in ('Borrowed', 'Returned', 'Lost', 'Damaged'):
        q = q.filter_by(status=status)
    rows = q.order_by(BookLoan.borrowed_date.desc(), BookLoan.id.desc()).limit(500).all()
    return _render({
        'page': 'loans', 'status': status, 'settings': _settings(),
        'loans': [_loan_row(l) for l in rows],
    })


@library_bp.route('/book-search')
@login_required
def book_search():
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify([])
    like = like_term(q)
    rows = (scope_query(Book.query.filter(Book.is_active == True, Book.copies_available > 0), Book)
            .filter(db.or_(Book.title.ilike(like, escape='\\'), Book.author.ilike(like, escape='\\'),
                           Book.isbn.ilike(like, escape='\\')))
            .order_by(Book.title).limit(15).all())
    return jsonify([{'id': b.id, 'label': f'{b.title}'
                     + (f' — {b.author}' if b.author else '')
                     + f' ({b.copies_available} avail)'} for b in rows])


@library_bp.route('/student-search')
@login_required
def student_search():
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify([])
    like = like_term(q)
    rows = (scope_query(Student.query.filter_by(is_active=True), Student)
            .filter(db.or_(Student.surname.ilike(like, escape='\\'), Student.first_name.ilike(like, escape='\\'),
                           Student.student_id.ilike(like, escape='\\')))
            .order_by(Student.surname).limit(15).all())
    return jsonify([{'id': s.id, 'label': f'{s.full_name} ({s.student_id})'} for s in rows])


@library_bp.route('/staff-search')
@login_required
def staff_search():
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify([])
    from models import StaffMember
    like = like_term(q)
    rows = (scope_query(StaffMember.query.filter_by(is_active=True), StaffMember)
            .filter(db.or_(StaffMember.surname.ilike(like, escape='\\'),
                           StaffMember.first_name.ilike(like, escape='\\'),
                           StaffMember.staff_id.ilike(like, escape='\\')))
            .order_by(StaffMember.surname).limit(15).all())
    return jsonify([{'id': s.id, 'label': f'{s.display_name} ({s.staff_id or "staff"})'} for s in rows])


@library_bp.route('/barcode-lookup')
@login_required
def barcode_lookup():
    """Resolve a scanned barcode / ISBN to a book (for fast issue)."""
    code = (request.args.get('code') or '').strip()
    if not code:
        return jsonify({'ok': False})
    b = (scope_query(Book.query.filter_by(is_active=True), Book)
         .filter(db.or_(Book.barcode == code, Book.isbn == code)).first())
    if not b:
        return jsonify({'ok': False})
    return jsonify({'ok': True, 'book': {'id': b.id, 'title': b.title,
                    'available': b.copies_available, 'reference_only': bool(b.reference_only)}})


def _report_filters():
    return {
        'from': _d(request.args.get('from')),
        'to': _d(request.args.get('to')),
        'category': request.args.get('category') or None,
        'subject': request.args.get('subject') or None,
    }


@library_bp.route('/reports')
@login_required
def reports():
    from utils import library_reports as R
    rtype = request.args.get('type') or 'inventory'
    data = R.build(rtype, _report_filters())
    return _render({
        'page': 'reports', 'report': data, 'report_types': [{'key': k, 'label': v} for k, v in R.REPORTS],
        'sel': {'type': data['type'], 'from': request.args.get('from', ''),
                'to': request.args.get('to', ''), 'category': request.args.get('category', ''),
                'subject': request.args.get('subject', '')},
        'categories': _distinct_categories(), 'subjects': _distinct('subject'),
        'urls': {'self': url_for('library.reports'), 'export': url_for('library.reports_export'),
                 'remind': url_for('library.remind_overdue')},
    })


@library_bp.route('/reports/export')
@login_required
def reports_export():
    from utils import library_reports as R
    rtype = request.args.get('type') or 'inventory'
    data = R.build(rtype, _report_filters())
    headers = [c['label'] for c in data['columns']]
    keys = [c['key'] for c in data['columns']]
    fname = f'library_{data["type"]}'
    from utils.audit import log_action
    log_action('library.report_export', detail=data['type'])
    if request.args.get('format') == 'xlsx':
        from openpyxl import Workbook
        from utils.web_exports import xlsx_response
        wb = Workbook(); ws = wb.active; ws.title = data['title'][:31]
        ws.append(headers)
        for r in data['rows']:
            ws.append([r.get(k, '') for k in keys])
        ws.append([])
        for s in data['summary']:
            ws.append([s['label'], s['value']])
        return xlsx_response(wb, f'{fname}.xlsx')
    out = io.StringIO(); w = csv.writer(out)
    w.writerow(headers)
    for r in data['rows']:
        w.writerow([r.get(k, '') for k in keys])
    w.writerow([])
    for s in data['summary']:
        w.writerow([s['label'], s['value']])
    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={fname}.csv'})


@library_bp.route('/remind-overdue', methods=['POST'])
@login_required
def remind_overdue():
    """Draft an SMS reminder (via Communication) to the parents of students who
    have overdue library books. Staff borrowers have no parent channel, so only
    student borrowers are included. Never auto-sends — a human reviews the draft."""
    q = (_scope_loans(BookLoan.query)
         .filter(BookLoan.status == 'Borrowed', BookLoan.due_date < date.today(),
                 BookLoan.borrower_type != 'staff', BookLoan.student_id.isnot(None)))
    student_ids = sorted({l.student_id for l in q.all() if l.student_id})
    if not student_ids:
        return _err('No students with overdue books.', url_for('library.loans') + '?status=Overdue', info=True)
    from utils import comms
    from utils.helpers import get_active_term
    from utils.access_control import get_current_user
    body = ('Dear {parent}, our records show {student} has an overdue library book. '
            'Please return it to the school library. Thank you — {school}.')
    who = getattr(get_current_user(), 'full_name', None) or 'Librarian'
    msg = comms.build_campaign(
        body, channel='SMS', term=get_active_term(), title='Library overdue reminder',
        spec={'to': 'parents', 'audience': 'students', 'student_ids': student_ids},
        created_by=who)
    if not msg:
        return _err('None of those students have a parent phone number on file.',
                    url_for('library.loans') + '?status=Overdue', info=True)
    return _ok(f'Drafted reminders for {msg.recipient_count} parent(s) — review and send.',
               url_for('comms.message_detail', message_id=msg.id))


@library_bp.route('/export')
@login_required
def export():
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['Title', 'Author', 'ISBN', 'Category', 'Total', 'Available', 'Shelf'])
    for b in scope_query(Book.query.filter_by(is_active=True), Book).order_by(Book.title).all():
        w.writerow([b.title, b.author or '', b.isbn or '', b.category or '',
                    b.copies_total, b.copies_available, b.shelf or ''])
    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=library_catalogue.csv'})


# ============================================================================
# SETTINGS
# ============================================================================

@library_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        if not is_admin():
            return _err('Admins only.', url_for('library.settings'))
        SchoolSettings.set('library_loan_days', request.form.get('loan_days') or '14',
                           'int', 'Library loan period (days)')
        SchoolSettings.set('library_fine_per_day', request.form.get('fine_per_day') or '0',
                           'string', 'Library overdue fine per day')
        return _ok('Library settings saved.', url_for('library.settings'))
    return _render({'page': 'settings', 'settings': _settings(),
                    'submit_url': url_for('library.settings')})
