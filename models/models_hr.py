"""
Staff / HR models — a personnel record for every employee (teaching and
non-teaching), departments, leave tracking and a simple monthly payroll.

This is deliberately separate from the ``Teacher``/``User`` models (which handle
app login, permissions and teaching assignments): not every staff member logs in
or teaches, and HR needs richer bio/employment/payroll data. A StaffMember may
optionally be linked to a User account.
"""
from models.models import db, local_now


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
    address = db.Column(db.String(255))

    # Employment
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    designation = db.Column(db.String(100))                  # job title
    staff_type = db.Column(db.String(20), default='Teaching')  # Teaching / Non-teaching
    employment_type = db.Column(db.String(20), default='Full-time')  # Full-time/Part-time/Contract/NYSC/Volunteer
    date_employed = db.Column(db.Date)
    status = db.Column(db.String(20), default='Active')      # Active/On Leave/Suspended/Resigned/Terminated
    qualification = db.Column(db.String(200))
    salary = db.Column(db.Float, default=0)                  # monthly gross

    # Next of kin
    nok_name = db.Column(db.String(100))
    nok_phone = db.Column(db.String(20))
    nok_relationship = db.Column(db.String(40))

    # Payroll bank details
    bank_name = db.Column(db.String(80))
    account_number = db.Column(db.String(20))
    account_name = db.Column(db.String(100))

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    notes = db.Column(db.Text)
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

    @staticmethod
    def generate_staff_id():
        last = StaffMember.query.order_by(StaffMember.id.desc()).first()
        num = (last.id + 1) if last else 1
        return f'STF{num:04d}'

    def __repr__(self):
        return f'<StaffMember {self.staff_id} {self.full_name}>'


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
    created_at = db.Column(db.DateTime, default=local_now)

    payslips = db.relationship('Payslip', backref='run',
                               lazy='dynamic', cascade='all, delete-orphan')

    __table_args__ = (db.UniqueConstraint('year', 'month', name='uq_payroll_period'),)

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
