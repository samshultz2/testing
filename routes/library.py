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
        'settings': 'settings', 'add_book': 'add_book', 'export': 'export',
        'book_search': 'book_search', 'student_search': 'student_search'}.items()}


def _render(payload):
    payload['urls'] = {**_urls(), **payload.get('urls', {})}
    payload['is_admin'] = is_admin()
    from utils.spa import render_or_json
    return render_or_json('library/app.html', 'library_json', payload)


# ============================================================================
# DASHBOARD
# ============================================================================

@library_bp.route('/')
@login_required
def dashboard():
    titles = scope_query(Book.query.filter_by(is_active=True), Book).count()
    copies = scope_query(db.session.query(func.coalesce(func.sum(Book.copies_total), 0)), Book).scalar() or 0
    available = scope_query(db.session.query(func.coalesce(func.sum(Book.copies_available), 0)), Book).scalar() or 0
    on_loan = (copies or 0) - (available or 0)
    overdue = scope_by_student(BookLoan.query.filter(BookLoan.status == 'Borrowed',
                                    BookLoan.due_date < date.today()), BookLoan).count()
    cat_rows = (scope_query(db.session.query(Book.category, func.count(Book.id))
                .filter(Book.is_active == True), Book).group_by(Book.category).all())
    cat_chart = [{'name': c or 'Uncategorised', 'count': n} for c, n in cat_rows]
    recent = (scope_by_student(BookLoan.query, BookLoan).order_by(BookLoan.created_at.desc()).limit(8).all())
    return _render({
        'page': 'dashboard', 'titles': titles, 'copies': copies, 'available': available,
        'on_loan': on_loan, 'overdue': overdue, 'cat_chart': cat_chart,
        'recent': [_loan_row(l, short=True) for l in recent],
    })


def _loan_row(l, short=False):
    bfmt = '%d %b' if short else '%d %b %Y'
    return {
        'id': l.id, 'book': l.book.title if l.book else '—',
        'student': l.student.full_name if l.student else '—',
        'borrowed': l.borrowed_date.strftime(bfmt) if l.borrowed_date else '',
        'due': l.due_date.strftime(bfmt) if l.due_date else '',
        'is_overdue': bool(l.is_overdue), 'days_overdue': l.days_overdue,
        'status': l.status, 'fine': l.fine or 0,
        'returned': l.returned_date.strftime('%d %b %Y') if l.returned_date else '',
        'return_url': url_for('library.return_loan', loan_id=l.id),
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
    query = scope_query(Book.query.filter_by(is_active=True), Book)
    if q:
        like = like_term(q)
        query = query.filter(db.or_(Book.title.ilike(like, escape='\\'), Book.author.ilike(like, escape='\\'),
                                    Book.isbn.ilike(like, escape='\\')))
    if category:
        query = query.filter_by(category=category)
    if avail == '1':
        query = query.filter(Book.copies_available > 0)
    rows = query.order_by(Book.title).all()
    categories = [c[0] for c in db.session.query(Book.category).filter(
        Book.category != None, Book.category != '').distinct().all()]
    return _render({
        'page': 'books', 'q': q, 'category': category or '', 'avail': avail or '',
        'categories': categories,
        'books': [{'id': b.id, 'title': b.title, 'isbn': b.isbn, 'author': b.author,
                   'category': b.category, 'shelf': b.shelf,
                   'copies_available': b.copies_available, 'copies_total': b.copies_total,
                   'edit_url': url_for('library.edit_book', book_id=b.id),
                   'issue_url': url_for('library.issue') + f'?book_id={b.id}',
                   'delete_url': url_for('library.delete_book', book_id=b.id)} for b in rows],
    })


def _book_payload(b):
    return {
        'page': 'book_form',
        'book': ({'id': b.id, 'title': b.title, 'author': b.author or '', 'isbn': b.isbn or '',
                  'category': b.category or '', 'publisher': b.publisher or '', 'shelf': b.shelf or '',
                  'copies_total': b.copies_total, 'copies_available': b.copies_available,
                  'on_loan': b.on_loan, 'notes': b.notes or ''} if b else None),
        'submit_url': url_for('library.edit_book', book_id=b.id) if b else url_for('library.add_book'),
    }


def _read_book(b):
    b.title = (request.form.get('title') or '').strip()
    b.author = (request.form.get('author') or '').strip() or None
    b.isbn = (request.form.get('isbn') or '').strip() or None
    b.category = (request.form.get('category') or '').strip() or None
    b.publisher = (request.form.get('publisher') or '').strip() or None
    b.shelf = (request.form.get('shelf') or '').strip() or None
    b.notes = (request.form.get('notes') or '').strip() or None


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
    return _ok('Book removed.', url_for('library.books'))


# ============================================================================
# ISSUE / RETURN
# ============================================================================

@library_bp.route('/issue', methods=['GET', 'POST'])
@login_required
def issue():
    s = _settings()
    if request.method == 'POST':
        book_id = request.form.get('book_id', type=int)
        student_id = request.form.get('student_id', type=int)
        book = db.session.get(Book, book_id) if book_id else None
        student = db.session.get(Student, student_id) if student_id else None
        if not (book and student):
            return _err('Select a book and a student.', url_for('library.issue'))
        if not can_access_branch(book.branch_id) or not can_access_branch(student.branch_id):
            return _err('That book or student belongs to another branch.', url_for('library.issue'))
        if (book.copies_available or 0) <= 0:
            return _err('No copies available for that title.', url_for('library.issue'))
        due = _d(request.form.get('due_date')) or (date.today() + timedelta(days=s['loan_days']))
        loan = BookLoan(book_id=book.id, student_id=student.id,
                        borrowed_date=date.today(), due_date=due, status='Borrowed')
        book.copies_available = (book.copies_available or 0) - 1
        db.session.add(loan)
        db.session.commit()
        return _ok(f'Issued "{book.title}" to {student.full_name} (due {due.strftime("%d %b %Y")}).',
                   url_for('library.loans'))
    preset = db.session.get(Book, request.args.get('book_id', type=int)) if request.args.get('book_id') else None
    return _render({
        'page': 'issue', 'settings': s,
        'default_due': (date.today() + timedelta(days=s['loan_days'])).isoformat(),
        'preset': ({'id': preset.id, 'title': preset.title} if preset else None),
        'submit_url': url_for('library.issue'),
    })


@library_bp.route('/loans/<int:loan_id>/return', methods=['POST'])
@login_required
def return_loan(loan_id):
    loan = db.get_or_404(BookLoan, loan_id)
    require_branch_access(loan.book.branch_id if loan.book else None)
    if loan.status == 'Returned':
        return _err('Already returned.', url_for('library.loans'), info=True)
    s = _settings()
    loan.returned_date = date.today()
    loan.status = 'Returned'
    loan.fine = round(loan.days_overdue * s['fine_per_day'], 2)
    if loan.book:
        loan.book.copies_available = min((loan.book.copies_available or 0) + 1,
                                         loan.book.copies_total or 0)
    db.session.commit()
    msg = f'Returned "{loan.book.title if loan.book else "book"}".'
    if loan.fine:
        msg += f' Overdue fine: ₦{loan.fine:,.2f}.'
    return _ok(msg, url_for('library.loans'))


@library_bp.route('/loans')
@login_required
def loans():
    status = request.args.get('status', 'Borrowed')
    q = scope_by_student(BookLoan.query, BookLoan)
    if status == 'Overdue':
        q = q.filter(BookLoan.status == 'Borrowed', BookLoan.due_date < date.today())
    elif status in ('Borrowed', 'Returned'):
        q = q.filter_by(status=status)
    rows = q.order_by(BookLoan.borrowed_date.desc(), BookLoan.id.desc()).all()
    return _render({
        'page': 'loans', 'status': status,
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
