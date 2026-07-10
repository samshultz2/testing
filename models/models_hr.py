"""
Staff / HR models — a personnel record for every employee (teaching and
non-teaching), departments, leave tracking and a simple monthly payroll.

This is deliberately separate from the ``Teacher``/``User`` models (which handle
app login, permissions and teaching assignments): not every staff member logs in
or teaches, and HR needs richer bio/employment/payroll data. A StaffMember may
optionally be linked to a User account.
"""
from models.models import db, local_now, EncryptedString


class Department(db.Model):
    __tablename__ = 'departments'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)

    def __repr__(self):
        return f'<Department {self.name}>'


class StaffMember(db.Model):
    __tablename__ = 'staff_members'

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.String(20), unique=True)         # e.g. STF0001
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))

    # Bio
    first_name = db.Column(db.String(60), nullable=False)
    surname = db.Column(db.String(60), nullable=False)
    middle_name = db.Column(db.String(60))
    gender = db.Column(db.String(10))
    date_of_birth = db.Column(db.Date)
    photo_url = db.Column(db.String(255))

    # Contact
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    address = db.Column(EncryptedString())        # encrypted at rest (never searched)

    # Employment
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    designation = db.Column(db.String(100))                  # job title
    staff_type = db.Column(db.String(20), default='Teaching')  # Teaching / Non-teaching
    employment_type = db.Column(db.String(20), default='Full-time')  # Full-time/Part-time/Contract/NYSC/Volunteer
    date_employed = db.Column(db.Date)
    confirmation_date = db.Column(db.Date)                   # date confirmed off probation
    contract_start = db.Column(db.Date)                     # for Contract staff
    contract_end = db.Column(db.Date)                      # contract expiry (dashboard alert)
    status = db.Column(db.String(20), default='Active')      # Active/On Leave/Suspended/Resigned/Terminated
    qualification = db.Column(db.String(200))
    certifications = db.Column(db.String(255))              # professional certifications
    prior_experience_years = db.Column(db.Integer)          # experience before joining
    salary = db.Column(db.Float, default=0)                  # monthly gross

    # Next of kin — encrypted at rest (never searched)
    nok_name = db.Column(EncryptedString())
    nok_phone = db.Column(EncryptedString())
    nok_relationship = db.Column(EncryptedString())

    # Emergency contact — encrypted at rest (never searched)
    emergency_name = db.Column(EncryptedString())
    emergency_phone = db.Column(EncryptedString())

    # Statutory / payroll identity — encrypted at rest (never searched)
    tax_id = db.Column(EncryptedString())                   # TIN
    pension_pin = db.Column(EncryptedString())
    pension_provider = db.Column(db.String(120))

    # Medical — encrypted at rest (never searched)
    blood_group = db.Column(db.String(6))
    medical_notes = db.Column(EncryptedString())

    # Payroll bank details — encrypted at rest (never searched)
    bank_name = db.Column(EncryptedString())
    account_number = db.Column(EncryptedString())
    account_name = db.Column(EncryptedString())

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    notes = db.Column(EncryptedString())          # encrypted at rest (never searched)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

    department = db.relationship('Department')
    leave_records = db.relationship('LeaveRecord', backref='staff',
                                    lazy='dynamic', cascade='all, delete-orphan')

    @property
    def full_name(self):
        parts = [self.surname, self.first_name, self.middle_name]
        return ' '.join(p for p in parts if p)

    @property
    def display_name(self):
        return ' '.join(p for p in [self.first_name, self.surname] if p)

    @property
    def years_of_service(self):
        """Whole years since date_employed (0 if unknown)."""
        if not self.date_employed:
            return 0
        from datetime import date
        today = date.today()
        yrs = today.year - self.date_employed.year - (
            (today.month, today.day) < (self.date_employed.month, self.date_employed.day))
        return max(yrs, 0)

    @property
    def total_experience_years(self):
        """Service here plus any experience gained before joining."""
        return self.years_of_service + (self.prior_experience_years or 0)

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        from datetime import date
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))

    @property
    def contract_days_left(self):
        """Days until the contract expires (None if no end date). Negative = expired."""
        if not self.contract_end:
            return None
        from datetime import date
        return (self.contract_end - date.today()).days

    @staticmethod
    def generate_staff_id():
        last = StaffMember.query.order_by(StaffMember.id.desc()).first()
        num = (last.id + 1) if last else 1
        return f'STF{num:04d}'

    def __repr__(self):
        return f'<StaffMember {self.staff_id} {self.full_name}>'


class StaffEvent(db.Model):
    """A dated milestone in a staff member's employment lifecycle — promotions,
    branch transfers, department moves, status changes and free-form notes.

    Salary changes (SalaryHistory), leave (LeaveRecord) and employment/confirmation
    dates (on StaffMember) are their own records; the timeline *merges* all of
    them, so this table only stores events that have no home elsewhere."""
    __tablename__ = 'staff_events'

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff_members.id'), nullable=False, index=True)
    kind = db.Column(db.String(20), default='note')   # promotion/transfer/department/status/confirmation/note
    title = db.Column(db.String(120), nullable=False)
    detail = db.Column(db.String(255))
    effective_date = db.Column(db.Date)
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)

    staff = db.relationship('StaffMember', backref=db.backref(
        'events', lazy='dynamic', cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<StaffEvent staff{self.staff_id} {self.kind} {self.title!r}>'


class LeaveRecord(db.Model):
    __tablename__ = 'leave_records'

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff_members.id'), nullable=False)
    leave_type = db.Column(db.String(40))      # Annual/Sick/Casual/Maternity/Study/Other
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    days = db.Column(db.Integer, default=0)
    reason = db.Column(db.Text)
    status = db.Column(db.String(15), default='Pending')   # Pending/Approved/Rejected
    created_at = db.Column(db.DateTime, default=local_now)

    def __repr__(self):
        return f'<LeaveRecord {self.staff_id} {self.leave_type} {self.status}>'


class PayrollRun(db.Model):
    __tablename__ = 'payroll_runs'

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)            # 1-12
    status = db.Column(db.String(15), default='Draft')       # Draft/Finalized/Paid
    note = db.Column(db.String(200))
    posted_expense_id = db.Column(db.Integer)                # finance Expense id if posted
    # Payroll is per-branch: each branch runs its own payroll for a period, and a
    # central admin manages every branch's. NULL = a legacy org-wide run created
    # before per-branch payroll (central-only access).
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    created_at = db.Column(db.DateTime, default=local_now)

    branch = db.relationship('Branch')
    payslips = db.relationship('Payslip', backref='run',
                               lazy='dynamic', cascade='all, delete-orphan')

    # One run per (period, branch) — two branches can each have their own June run.
    __table_args__ = (db.UniqueConstraint('year', 'month', 'branch_id',
                                          name='uq_payroll_period_branch'),)

    MONTHS = ['', 'January', 'February', 'March', 'April', 'May', 'June',
              'July', 'August', 'September', 'October', 'November', 'December']

    @property
    def period_label(self):
        return f'{self.MONTHS[self.month]} {self.year}'

    def __repr__(self):
        return f'<PayrollRun {self.period_label} {self.status}>'


class Payslip(db.Model):
    __tablename__ = 'payslips'

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey('payroll_runs.id'), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff_members.id'), nullable=False)
    staff_name = db.Column(db.String(120))      # snapshot
    basic = db.Column(db.Float, default=0)
    allowances = db.Column(db.Float, default=0)
    deductions = db.Column(db.Float, default=0)              # manual (loans, PAYE…)
    attendance_deduction = db.Column(db.Float, default=0)    # auto from attendance
    net = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=local_now)

    staff = db.relationship('StaffMember')
    items = db.relationship('PayslipDeduction', backref='payslip',
                            lazy='selectin', cascade='all, delete-orphan')

    @property
    def recurring_deductions(self):
        """Sum of the itemised recurring deductions (pension, welfare, …)."""
        return sum((i.amount or 0) for i in self.items)

    @property
    def total_deductions(self):
        return ((self.deductions or 0) + (self.attendance_deduction or 0)
                + self.recurring_deductions)

    def recompute(self):
        self.net = ((self.basic or 0) + (self.allowances or 0)
                    - self.total_deductions)
        return self.net


class PayrollDeductionType(db.Model):
    """A recurring payroll deduction definition (applied to every payslip).

    ``kind='percent'`` deducts ``value``% of the staff member's basic pay;
    ``kind='fixed'`` deducts a flat ``value`` amount each month.
    """
    __tablename__ = 'payroll_deduction_types'

    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    name = db.Column(db.String(80), nullable=False)
    kind = db.Column(db.String(10), nullable=False, default='fixed')  # 'percent' | 'fixed'
    value = db.Column(db.Float, nullable=False, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)

    def amount_for(self, basic):
        if self.kind == 'percent':
            return round((basic or 0) * (self.value or 0) / 100.0, 2)
        return self.value or 0

    @property
    def label(self):
        return (f'{self.name} ({self.value:g}%)' if self.kind == 'percent'
                else self.name)


class PayslipDeduction(db.Model):
    """A single recurring deduction line snapshotted onto a payslip."""
    __tablename__ = 'payslip_deductions'

    id = db.Column(db.Integer, primary_key=True)
    payslip_id = db.Column(db.Integer, db.ForeignKey('payslips.id'), nullable=False)
    name = db.Column(db.String(100))
    amount = db.Column(db.Float, default=0)

    def __repr__(self):
        return f'<Payslip run{self.run_id} staff{self.staff_id} net{self.net}>'


class SalaryHistory(db.Model):
    """Audit trail of salary changes (increments / adjustments)."""
    __tablename__ = 'salary_history'

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff_members.id'), nullable=False)
    previous_salary = db.Column(db.Float, default=0)
    new_salary = db.Column(db.Float, default=0)
    effective_date = db.Column(db.Date)
    reason = db.Column(db.String(200))
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)

    staff = db.relationship('StaffMember', backref=db.backref(
        'salary_history', lazy='dynamic', cascade='all, delete-orphan'))

    @property
    def change(self):
        return (self.new_salary or 0) - (self.previous_salary or 0)

    def __repr__(self):
        return f'<SalaryHistory staff{self.staff_id} {self.previous_salary}->{self.new_salary}>'


class StaffDocument(db.Model):
    """A file in a staff member's HR file — appointment letter, contract,
    certificate, ID, promotion letter, etc. The bytes live as a CommAttachment
    (shared upload storage); this row adds the HR-specific metadata."""
    __tablename__ = 'staff_documents'

    DOC_TYPES = ['Appointment letter', 'Employment contract', 'Certificate',
                 'Identification', 'Promotion letter', 'Query/Warning', 'Other']

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff_members.id'), nullable=False, index=True)
    attachment_id = db.Column(db.Integer, db.ForeignKey('comm_attachments.id'))
    title = db.Column(db.String(150), nullable=False)
    doc_type = db.Column(db.String(30), default='Other')
    expires_on = db.Column(db.Date)              # optional (e.g. licence, permit)
    uploaded_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)

    staff = db.relationship('StaffMember', backref=db.backref(
        'documents', lazy='dynamic', cascade='all, delete-orphan'))
    attachment = db.relationship('CommAttachment')

    @property
    def is_expired(self):
        from datetime import date
        return bool(self.expires_on and self.expires_on < date.today())


class TrainingRecord(db.Model):
    """A professional-development activity a staff member attended — training,
    workshop, seminar or certification — with an optional certificate file."""
    __tablename__ = 'staff_training'

    KINDS = ['Training', 'Workshop', 'Seminar', 'Certification', 'Conference']

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff_members.id'), nullable=False, index=True)
    title = db.Column(db.String(150), nullable=False)
    kind = db.Column(db.String(20), default='Training')
    provider = db.Column(db.String(120))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    hours = db.Column(db.Float, default=0)
    certificate_id = db.Column(db.Integer, db.ForeignKey('comm_attachments.id'))
    note = db.Column(db.String(255))
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)

    staff = db.relationship('StaffMember', backref=db.backref(
        'training', lazy='dynamic', cascade='all, delete-orphan'))
    certificate = db.relationship('CommAttachment')


class PerformanceReview(db.Model):
    """A periodic appraisal / evaluation of a staff member."""
    __tablename__ = 'staff_reviews'

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff_members.id'), nullable=False, index=True)
    period = db.Column(db.String(40))             # e.g. '2024/2025', 'Term 1 2025'
    review_date = db.Column(db.Date)
    reviewer = db.Column(db.String(120))
    score = db.Column(db.Float)                   # 0–100 (or any school scale)
    rating = db.Column(db.String(30))             # Excellent/Good/Fair/Poor …
    strengths = db.Column(db.Text)
    improvements = db.Column(db.Text)
    comments = db.Column(db.Text)
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)

    staff = db.relationship('StaffMember', backref=db.backref(
        'reviews', lazy='dynamic', cascade='all, delete-orphan'))


class StaffAttendance(db.Model):
    """Daily staff attendance with auto lateness / absence deductions."""
    __tablename__ = 'staff_attendance'

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff_members.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(15), default='Present')  # Present/Late/Absent/Excused
    clock_in = db.Column(db.String(5))                    # 'HH:MM'
    minutes_late = db.Column(db.Integer, default=0)
    deduction = db.Column(db.Float, default=0)
    note = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=local_now)

    staff = db.relationship('StaffMember', backref=db.backref(
        'attendance', lazy='dynamic', cascade='all, delete-orphan'))

    __table_args__ = (db.UniqueConstraint('staff_id', 'date', name='uq_staff_attendance_day'),)

    def __repr__(self):
        return f'<StaffAttendance {self.staff_id} {self.date} {self.status}>'
