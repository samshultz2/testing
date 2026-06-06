"""
Library models — book catalogue and borrow/return loans.

Copies are tracked per title (``copies_total`` / ``copies_available``). Issuing a
book decrements availability; returning restores it and computes any overdue
fine from the library settings (loan period + fine/day, stored in SchoolSettings).
"""
from datetime import date

from models.models import db, local_now


class Book(db.Model):
    __tablename__ = 'library_books'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(150))
    isbn = db.Column(db.String(30))
    category = db.Column(db.String(60))
    publisher = db.Column(db.String(120))
    shelf = db.Column(db.String(40))
    copies_total = db.Column(db.Integer, default=1)
    copies_available = db.Column(db.Integer, default=1)
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)

    loans = db.relationship('BookLoan', backref='book',
                            lazy='dynamic', cascade='all, delete-orphan')

    @property
    def on_loan(self):
        return (self.copies_total or 0) - (self.copies_available or 0)

    def __repr__(self):
        return f'<Book {self.title!r}>'


class BookLoan(db.Model):
    __tablename__ = 'library_loans'

    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('library_books.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    borrowed_date = db.Column(db.Date, default=date.today)
    due_date = db.Column(db.Date)
    returned_date = db.Column(db.Date)
    status = db.Column(db.String(15), default='Borrowed')   # Borrowed / Returned
    fine = db.Column(db.Float, default=0)
    note = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=local_now)

    student = db.relationship('Student')

    @property
    def is_overdue(self):
        return (self.status == 'Borrowed' and self.due_date
                and self.due_date < date.today())

    @property
    def days_overdue(self):
        if not self.due_date:
            return 0
        end = self.returned_date or date.today()
        return max((end - self.due_date).days, 0)

    def __repr__(self):
        return f'<BookLoan book{self.book_id} student{self.student_id} {self.status}>'
