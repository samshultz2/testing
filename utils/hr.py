"""HR helpers — settings, lateness/deduction maths, dashboard stats and
attendance-aware payroll generation."""

from sqlalchemy import func, extract

from models import (db, StaffMember, Department, LeaveRecord, Payslip, StaffAttendance,
                    SchoolSettings)

STATUSES = ['Active', 'On Leave', 'Suspended', 'Resigned', 'Terminated']
STAFF_TYPES = ['Teaching', 'Non-teaching']
EMPLOYMENT_TYPES = ['Full-time', 'Part-time', 'Contract', 'NYSC', 'Volunteer']
LEAVE_TYPES = ['Annual', 'Sick', 'Casual', 'Maternity', 'Paternity', 'Study', 'Other']
ATT_STATUSES = ['Present', 'Late', 'Absent', 'Excused']


# ---- Settings (lateness / absence rules) -----------------------------------

def get_settings():
    return {
        'late_time': SchoolSettings.get('hr_late_time', '07:30'),
        'late_rate': float(SchoolSettings.get('hr_late_rate', 10) or 0),
        'absence_deduction': float(SchoolSettings.get('hr_absence_deduction', 0) or 0),
    }


def save_settings(form):
    SchoolSettings.set('hr_late_time', (form.get('late_time') or '07:30').strip(),
                       'string', 'Staff resumption time (HH:MM)')
    SchoolSettings.set('hr_late_rate', form.get('late_rate') or '0',
                       'string', 'Lateness deduction per minute')
    SchoolSettings.set('hr_absence_deduction', form.get('absence_deduction') or '0',
                       'string', 'Deduction per day absent')


def _to_minutes(hhmm):
    try:
        h, m = str(hhmm).split(':')
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def compute_attendance(status, clock_in, settings=None):
    """
    Return (status, minutes_late, deduction) for a marked day.

    Lateness: ₦rate for every minute after the resumption time. Absence: a flat
    configured per-day deduction. ``status`` may be auto-upgraded to 'Late' when
    a clock-in time is after the threshold.
    """
    s = settings or get_settings()
    if status == 'Absent':
        return 'Absent', 0, s['absence_deduction']
    if status == 'Excused':
        return 'Excused', 0, 0
    # Present / Late — derive from clock-in if given.
    late_min = _to_minutes(s['late_time'])
    cin = _to_minutes(clock_in) if clock_in else None
    if cin is not None and late_min is not None and cin > late_min:
        minutes = cin - late_min
        return 'Late', minutes, round(minutes * s['late_rate'], 2)
    # Marked Late but with no (or an on-time) clock-in: keep the Late status but
    # there are no computable minutes to charge for.
    if status == 'Late':
        return 'Late', 0, 0
    return 'Present', 0, 0


def month_attendance_deduction(staff_id, year, month):
    """Total attendance-based deduction for a staff member in a month."""
    return (db.session.query(func.coalesce(func.sum(StaffAttendance.deduction), 0.0))
            .filter(StaffAttendance.staff_id == staff_id,
                    extract('year', StaffAttendance.date) == year,
                    extract('month', StaffAttendance.date) == month).scalar()) or 0.0


def dashboard_stats(branch_id=None):
    """HR dashboard figures. ``branch_id`` scopes every count and the monthly
    payroll total to one branch (None = all branches, for central users), so a
    branch admin never sees other branches' headcount or salary spend."""
    active = StaffMember.query.filter_by(is_active=True)
    if branch_id is not None:
        active = active.filter(StaffMember.branch_id == branch_id)
    total = active.count()
    teaching = active.filter_by(staff_type='Teaching').count()
    non_teaching = total - teaching
    on_leave = active.filter_by(status='On Leave').count()
    male = active.filter_by(gender='Male').count()
    female = active.filter_by(gender='Female').count()
    pay_q = db.session.query(func.coalesce(func.sum(StaffMember.salary), 0.0)).filter(
        StaffMember.is_active == True, StaffMember.status == 'Active')
    if branch_id is not None:
        pay_q = pay_q.filter(StaffMember.branch_id == branch_id)
    monthly_payroll = pay_q.scalar() or 0.0
    pending_leave = LeaveRecord.query.filter_by(status='Pending').count()

    # by department
    dept_join = (StaffMember.department_id == Department.id) & (StaffMember.is_active == True)
    if branch_id is not None:
        dept_join = dept_join & (StaffMember.branch_id == branch_id)
    dept_rows = (db.session.query(Department.name, func.count(StaffMember.id))
                 .outerjoin(StaffMember, dept_join)
                 .group_by(Department.name).all())
    dept_chart = [{'name': n, 'count': c} for n, c in dept_rows if c]

    type_chart = [{'name': 'Teaching', 'count': teaching},
                  {'name': 'Non-teaching', 'count': non_teaching}]

    return {
        'total': total, 'teaching': teaching, 'non_teaching': non_teaching,
        'on_leave': on_leave, 'male': male, 'female': female,
        'monthly_payroll': monthly_payroll, 'pending_leave': pending_leave,
        'dept_chart': dept_chart, 'type_chart': type_chart,
    }


def active_deduction_types():
    """Recurring payroll deductions (pension, welfare, …) currently in force."""
    from models import PayrollDeductionType
    return (PayrollDeductionType.query.filter_by(is_active=True)
            .order_by(PayrollDeductionType.name).all())


def apply_recurring_deductions(ps, types=None):
    """(Re)build a payslip's recurring-deduction line items from the active
    definitions, based on its current basic pay. Replaces any existing lines."""
    from models import PayslipDeduction
    types = active_deduction_types() if types is None else types
    ps.items[:] = []
    for t in types:
        amt = t.amount_for(ps.basic or 0)
        if amt:
            ps.items.append(PayslipDeduction(name=t.label, amount=amt))


def generate_payslips(run):
    """Create a payslip for every active staff member on the run (idempotent).

    Pre-fills attendance (lateness/absence) deductions AND the recurring
    deduction definitions (pension, welfare, …)."""
    existing = {p.staff_id for p in run.payslips}
    q = StaffMember.query.filter_by(is_active=True, status='Active')
    # Per-branch payroll: a branch run only covers that branch's staff. A legacy
    # NULL-branch run (org-wide) still covers everyone.
    if run.branch_id:
        q = q.filter_by(branch_id=run.branch_id)
    staff = q.all()
    types = active_deduction_types()
    created = 0
    for s in staff:
        if s.id in existing:
            continue
        ded = month_attendance_deduction(s.id, run.year, run.month)
        ps = Payslip(run_id=run.id, staff_id=s.id, staff_name=s.full_name,
                     basic=s.salary or 0, allowances=0, deductions=0,
                     attendance_deduction=ded)
        db.session.add(ps)
        db.session.flush()
        apply_recurring_deductions(ps, types)
        ps.recompute()
        created += 1
    return created


def sync_attendance_deductions(run):
    """Refresh each payslip's auto attendance-deduction AND its recurring
    deductions (pension, welfare, …) from the current definitions. Manual
    deductions in ``deductions`` are preserved."""
    types = active_deduction_types()
    n = 0
    for ps in run.payslips:
        ded = month_attendance_deduction(ps.staff_id, run.year, run.month)
        ps.attendance_deduction = ded
        apply_recurring_deductions(ps, types)
        ps.recompute()
        n += 1
    return n


def run_total(run):
    return (db.session.query(func.coalesce(func.sum(Payslip.net), 0.0))
            .filter(Payslip.run_id == run.id).scalar()) or 0.0
