"""HR helpers — stats for the dashboard and payroll generation."""
from datetime import date

from sqlalchemy import func

from models import db, StaffMember, Department, LeaveRecord, PayrollRun, Payslip

STATUSES = ['Active', 'On Leave', 'Suspended', 'Resigned', 'Terminated']
STAFF_TYPES = ['Teaching', 'Non-teaching']
EMPLOYMENT_TYPES = ['Full-time', 'Part-time', 'Contract', 'NYSC', 'Volunteer']
LEAVE_TYPES = ['Annual', 'Sick', 'Casual', 'Maternity', 'Paternity', 'Study', 'Other']


def dashboard_stats():
    active = StaffMember.query.filter_by(is_active=True)
    total = active.count()
    teaching = active.filter_by(staff_type='Teaching').count()
    non_teaching = total - teaching
    on_leave = active.filter_by(status='On Leave').count()
    male = active.filter_by(gender='Male').count()
    female = active.filter_by(gender='Female').count()
    monthly_payroll = (db.session.query(func.coalesce(func.sum(StaffMember.salary), 0.0))
                       .filter(StaffMember.is_active == True,
                               StaffMember.status == 'Active').scalar()) or 0.0
    pending_leave = LeaveRecord.query.filter_by(status='Pending').count()

    # by department
    dept_rows = (db.session.query(Department.name, func.count(StaffMember.id))
                 .outerjoin(StaffMember, (StaffMember.department_id == Department.id) &
                            (StaffMember.is_active == True))
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


def generate_payslips(run):
    """Create a payslip for every active staff member on the run (idempotent)."""
    existing = {p.staff_id for p in run.payslips}
    staff = StaffMember.query.filter_by(is_active=True, status='Active').all()
    created = 0
    for s in staff:
        if s.id in existing:
            continue
        ps = Payslip(run_id=run.id, staff_id=s.id, staff_name=s.full_name,
                     basic=s.salary or 0, allowances=0, deductions=0)
        ps.recompute()
        db.session.add(ps)
        created += 1
    return created


def run_total(run):
    return (db.session.query(func.coalesce(func.sum(Payslip.net), 0.0))
            .filter(Payslip.run_id == run.id).scalar()) or 0.0
