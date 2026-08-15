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
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    title = db.Column(db.String(200), nullable=False)
    subtitle = db.Column(db.String(200))
    author = db.Column(db.String(150))
    isbn = db.Column(db.String(30))
    barcode = db.Column(db.String(40), index=True)     # scannable copy/accession code
    category = db.Column(db.String(60))
    subject = db.Column(db.String(80))                 # e.g. Mathematics, English
    keywords = db.Column(db.String(255))               # comma-separated, searchable
    publisher = db.Column(db.String(120))
    edition = db.Column(db.String(40))
    publication_year = db.Column(db.Integer)
    language = db.Column(db.String(40))
    description = db.Column(db.Text)
    shelf = db.Column(db.String(40))
    rack = db.Column(db.String(40))
    condition = db.Column(db.String(20), default='Good')   # Good/Fair/Poor
    reference_only = db.Column(db.Boolean, default=False)  # can't be borrowed
    price = db.Column(db.Float, default=0)                 # unit value (valuation / replacement)
    status = db.Column(db.String(15), default='Available')  # Available / Withdrawn
    supplier = db.Column(db.String(120))                   # acquisition source / vendor
    source = db.Column(db.String(20), default='Purchase')  # Purchase / Donation
    donated_by = db.Column(db.String(120))                 # donor (when a donation)
    copies_total = db.Column(db.Integer, default=1)
    copies_available = db.Column(db.Integer, default=1)
    lost_count = db.Column(db.Integer, default=0)
    damaged_count = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)

    loans = db.relationship('BookLoan', backref='book',
                            lazy='dynamic', cascade='all, delete-orphan')

    @property
    def on_loan(self):
        return (self.copies_total or 0) - (self.copies_available or 0)

    @property
    def borrowable(self):
        """True if a copy can currently be issued."""
        return (self.is_active and not self.reference_only
                and (self.status or 'Available') == 'Available'
                and (self.copies_available or 0) > 0)

    def __repr__(self):
        return f'<Book {self.title!r}>'


class BookLoan(db.Model):
    __tablename__ = 'library_loans'

    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('library_books.id'), nullable=False)
    # Borrower is a student OR a staff member. student_id stays for backwards
    # compatibility (all legacy loans are students); staff loans set staff_id.
    borrower_type = db.Column(db.String(10), default='student')   # 'student' | 'staff'
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff_members.id'), nullable=True)
    borrowed_date = db.Column(db.Date, default=date.today)
    due_date = db.Column(db.Date)
    returned_date = db.Column(db.Date)
    status = db.Column(db.String(15), default='Borrowed')   # Borrowed/Returned/Lost/Damaged
    renew_count = db.Column(db.Integer, default=0)
    fine = db.Column(db.Float, default=0)
    fine_waived = db.Column(db.Boolean, default=False)
    fine_posted = db.Column(db.Boolean, default=False)      # posted to Finance ledger
    replacement_cost = db.Column(db.Float, default=0)       # charged on lost/damaged
    note = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=local_now)

    student = db.relationship('Student')
    staff = db.relationship('StaffMember')

    @property
    def is_student(self):
        return (self.borrower_type or 'student') == 'student'

    @property
    def borrower_name(self):
        if not self.is_student and self.staff:
            return self.staff.display_name or self.staff.full_name
        return self.student.full_name if self.student else '—'

    @property
    def borrower_ref(self):
        if not self.is_student and self.staff:
            return self.staff.staff_id or ''
        return self.student.student_id if self.student else ''

    @property
    def is_overdue(self):
        return (self.status == 'Borrowed' and self.due_date
                and self.due_date < local_now().date())

    @property
    def days_overdue(self):
        if not self.due_date:
            return 0
        end = self.returned_date or local_now().date()
        return max((end - self.due_date).days, 0)

    def __repr__(self):
        return f'<BookLoan book{self.book_id} student{self.student_id} {self.status}>'


class BookReservation(db.Model):
    """A hold on a title. When no copy is free a borrower joins the queue; the
    earliest queued hold becomes Ready when a copy is returned."""
    __tablename__ = 'library_reservations'

    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('library_books.id'), nullable=False, index=True)
    borrower_type = db.Column(db.String(10), default='student')
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))
    staff_id = db.Column(db.Integer, db.ForeignKey('staff_members.id'))
    status = db.Column(db.String(12), default='Queued')   # Queued/Ready/Fulfilled/Cancelled/Expired
    created_at = db.Column(db.DateTime, default=local_now)
    ready_at = db.Column(db.DateTime)
    expires_on = db.Column(db.Date)
    note = db.Column(db.String(200))

    book = db.relationship('Book')
    student = db.relationship('Student')
    staff = db.relationship('StaffMember')

    @property
    def is_student(self):
        return (self.borrower_type or 'student') == 'student'

    @property
    def borrower_name(self):
        if not self.is_student and self.staff:
            return self.staff.display_name or self.staff.full_name
        return self.student.full_name if self.student else '—'


class ReadingListItem(db.Model):
    """A book recommended to a class (class-recommended reading list)."""
    __tablename__ = 'library_reading_list'

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'), nullable=False, index=True)
    book_id = db.Column(db.Integer, db.ForeignKey('library_books.id'), nullable=False)
    note = db.Column(db.String(200))
    added_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)

    book = db.relationship('Book')
    school_class = db.relationship('SchoolClass')

    __table_args__ = (db.UniqueConstraint('class_id', 'book_id', name='uq_reading_item'),)
