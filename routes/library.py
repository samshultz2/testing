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


# ============================================================================
# DASHBOARD
# ============================================================================

@library_bp.route('/')
@login_required
def dashboard():
    titles = Book.query.filter_by(is_active=True).count()
    copies = db.session.query(func.coalesce(func.sum(Book.copies_total), 0)).scalar() or 0
    available = db.session.query(func.coalesce(func.sum(Book.copies_available), 0)).scalar() or 0
    on_loan = (copies or 0) - (available or 0)
    overdue = BookLoan.query.filter(BookLoan.status == 'Borrowed',
                                    BookLoan.due_date < date.today()).count()
    cat_rows = (db.session.query(Book.category, func.count(Book.id))
                .filter(Book.is_active == True).group_by(Book.category).all())
    cat_chart = [{'name': c or 'Uncategorised', 'count': n} for c, n in cat_rows]
    recent = (BookLoan.query.order_by(BookLoan.created_at.desc()).limit(8).all())
    return render_template('library/dashboard.html', titles=titles, copies=copies,
        available=available, on_loan=on_loan, overdue=overdue,
        cat_chart=cat_chart, recent=recent)


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
        like = f'%{q}%'
        query = query.filter(db.or_(Book.title.ilike(like), Book.author.ilike(like),
                                    Book.isbn.ilike(like)))
    if category:
        query = query.filter_by(category=category)
    if avail == '1':
        query = query.filter(Book.copies_available > 0)
    books = query.order_by(Book.title).all()
    categories = [c[0] for c in db.session.query(Book.category).filter(
        Book.category != None, Book.category != '').distinct().all()]
    return render_template('library/books.html', books=books, q=q,
        category=category, avail=avail, categories=categories)


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
            flash('Title is required.', 'error')
            return redirect(url_for('library.add_book'))
        total = request.form.get('copies_total', type=int) or 1
        b = Book(copies_total=total, copies_available=total)
        _read_book(b)
        from utils.branch_scope import branch_for_new
        b.branch_id = branch_for_new()
        db.session.add(b)
        db.session.commit()
        flash(f'Added "{b.title}".', 'success')
        return redirect(url_for('library.books'))
    return render_template('library/book_form.html', book=None)


@library_bp.route('/books/<int:book_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_book(book_id):
    b = db.get_or_404(Book, book_id)
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
        flash('Book updated.', 'success')
        return redirect(url_for('library.books'))
    return render_template('library/book_form.html', book=b)


@library_bp.route('/books/<int:book_id>/delete', methods=['POST'])
@admin_required
def delete_book(book_id):
    b = db.get_or_404(Book, book_id)
    if b.loans.filter_by(status='Borrowed').count():
        flash('Cannot delete: copies are still on loan.', 'error')
        return redirect(url_for('library.books'))
    b.is_active = False
    db.session.commit()
    flash('Book removed.', 'success')
    return redirect(url_for('library.books'))


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
            flash('Select a book and a student.', 'error')
            return redirect(url_for('library.issue'))
        if (book.copies_available or 0) <= 0:
            flash('No copies available for that title.', 'error')
            return redirect(url_for('library.issue'))
        due = _d(request.form.get('due_date')) or (date.today() + timedelta(days=s['loan_days']))
        loan = BookLoan(book_id=book.id, student_id=student.id,
                        borrowed_date=date.today(), due_date=due, status='Borrowed')
        book.copies_available = (book.copies_available or 0) - 1
        db.session.add(loan)
        db.session.commit()
        flash(f'Issued "{book.title}" to {student.full_name} (due {due.strftime("%d %b %Y")}).', 'success')
        return redirect(url_for('library.loans'))
    preset = db.session.get(Book, request.args.get('book_id', type=int)) if request.args.get('book_id') else None
    return render_template('library/issue.html', settings=s, preset=preset,
        default_due=(date.today() + timedelta(days=s['loan_days'])))


@library_bp.route('/loans/<int:loan_id>/return', methods=['POST'])
@login_required
def return_loan(loan_id):
    loan = db.get_or_404(BookLoan, loan_id)
    if loan.status == 'Returned':
        flash('Already returned.', 'info')
        return safe_redirect(url_for('library.loans'))
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
    flash(msg, 'success')
    return safe_redirect(url_for('library.loans'))


@library_bp.route('/loans')
@login_required
def loans():
    status = request.args.get('status', 'Borrowed')
    q = BookLoan.query
    if status == 'Overdue':
        q = q.filter(BookLoan.status == 'Borrowed', BookLoan.due_date < date.today())
    elif status in ('Borrowed', 'Returned'):
        q = q.filter_by(status=status)
    loans = q.order_by(BookLoan.borrowed_date.desc(), BookLoan.id.desc()).all()
    return render_template('library/loans.html', loans=loans, status=status,
                           today=date.today())


@library_bp.route('/book-search')
@login_required
def book_search():
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify([])
    like = f'%{q}%'
    rows = (Book.query.filter(Book.is_active == True, Book.copies_available > 0)
            .filter(db.or_(Book.title.ilike(like), Book.author.ilike(like),
                           Book.isbn.ilike(like)))
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
    like = f'%{q}%'
    rows = (Student.query.filter_by(is_active=True)
            .filter(db.or_(Student.surname.ilike(like), Student.first_name.ilike(like),
                           Student.student_id.ilike(like)))
            .order_by(Student.surname).limit(15).all())
    return jsonify([{'id': s.id, 'label': f'{s.full_name} ({s.student_id})'} for s in rows])


@library_bp.route('/export')
@login_required
def export():
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['Title', 'Author', 'ISBN', 'Category', 'Total', 'Available', 'Shelf'])
    for b in Book.query.filter_by(is_active=True).order_by(Book.title).all():
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
            flash('Admins only.', 'error')
            return redirect(url_for('library.settings'))
        SchoolSettings.set('library_loan_days', request.form.get('loan_days') or '14',
                           'int', 'Library loan period (days)')
        SchoolSettings.set('library_fine_per_day', request.form.get('fine_per_day') or '0',
                           'string', 'Library overdue fine per day')
        flash('Library settings saved.', 'success')
        return redirect(url_for('library.settings'))
    return render_template('library/settings.html', settings=_settings())
