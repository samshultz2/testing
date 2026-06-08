"""
Finance / Fees Models — school fee management.

A school sets up a catalogue of fee items (Tuition, Development levy, PTA, etc.),
then defines a *fee structure* per class for a given term (how much each item
costs). Each enrolled student therefore has an expected bill for the term; the
school records payments against that bill and can grant per-student discounts or
waivers. Balances and collection figures are computed from these tables.
"""
from models.models import db, local_now


class FeeItem(db.Model):
    """A type of fee a school can charge (catalogue entry)."""
    __tablename__ = 'fee_items'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)

    def __repr__(self):
        return f'<FeeItem {self.name}>'


class FeeStructure(db.Model):
    """The amount charged for one fee item, for a class (optionally an arm) in a term."""
    __tablename__ = 'fee_structures'

    id = db.Column(db.Integer, primary_key=True)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'), nullable=False)
    arm_id = db.Column(db.Integer, db.ForeignKey('class_arms.id'), nullable=True)  # null = all arms
    fee_item_id = db.Column(db.Integer, db.ForeignKey('fee_items.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)

    term = db.relationship('Term')
    school_class = db.relationship('SchoolClass')
    arm = db.relationship('ClassArm')
    fee_item = db.relationship('FeeItem')

    __table_args__ = (
        db.UniqueConstraint('term_id', 'class_id', 'arm_id', 'fee_item_id',
                            name='uq_fee_structure'),
    )

    def __repr__(self):
        return f'<FeeStructure t{self.term_id} c{self.class_id} item{self.fee_item_id}: {self.amount}>'


class FeePayment(db.Model):
    """A payment a student makes toward their term fees."""
    __tablename__ = 'fee_payments'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, nullable=False, default=local_now)
    method = db.Column(db.String(30), default='Cash')  # Cash, Transfer, POS, Cheque, Online
    reference = db.Column(db.String(60))               # bank ref / teller no (optional)
    receipt_no = db.Column(db.String(30))              # generated, e.g. RCP-000123
    received_by = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=local_now)

    student = db.relationship('Student', backref=db.backref('fee_payments', lazy='dynamic'))
    term = db.relationship('Term')

    def __repr__(self):
        return f'<FeePayment {self.student_id} t{self.term_id}: {self.amount}>'


class FeeDiscount(db.Model):
    """A discount / waiver / scholarship applied to a student's term bill."""
    __tablename__ = 'fee_discounts'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0)
    reason = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=local_now)

    student = db.relationship('Student', backref=db.backref('fee_discounts', lazy='dynamic'))
    term = db.relationship('Term')

    def __repr__(self):
        return f'<FeeDiscount {self.student_id} t{self.term_id}: {self.amount}>'


class ExpenseCategory(db.Model):
    """A category for school expenditure (Salaries, Utilities, Supplies, …)."""
    __tablename__ = 'expense_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)

    def __repr__(self):
        return f'<ExpenseCategory {self.name}>'


class Expense(db.Model):
    """A recorded expense / money paid out by the school."""
    __tablename__ = 'expenses'

    id = db.Column(db.Integer, primary_key=True)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'), nullable=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    category_id = db.Column(db.Integer, db.ForeignKey('expense_categories.id'), nullable=True)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0)
    expense_date = db.Column(db.Date, nullable=False, default=local_now)
    payee = db.Column(db.String(120))
    method = db.Column(db.String(30), default='Cash')
    reference = db.Column(db.String(60))
    recorded_by = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=local_now)

    term = db.relationship('Term')
    category = db.relationship('ExpenseCategory')

    def __repr__(self):
        return f'<Expense {self.description}: {self.amount}>'
