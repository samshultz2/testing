"""
Staff / HR routes — personnel directory, departments, leave management and
monthly payroll (with optional posting of the salary run to Finance expenses).
"""
from datetime import datetime, date
from utils.helpers import get_active_term

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, Response)
from sqlalchemy import func

from models import (
    db, StaffMember, Department, LeaveRecord, PayrollRun, Payslip,
    SalaryHistory, StaffAttendance,
)
from utils.access_control import login_required, admin_required
from utils import hr

hr_bp = Blueprint('hr', __name__, url_prefix='/hr')


def _d(value, default=None):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return default


def _current_user():
    from flask import session
    return session.get('username') or session.get('user') or 'Admin'


# ============================================================================
# DASHBOARD
# ============================================================================

@hr_bp.route('/')
@login_required
def dashboard():
    from utils.branch_scope import scope_query, scope_by_staff
    stats = hr.dashboard_stats()
    recent = scope_query(StaffMember.query.filter_by(is_active=True), StaffMember).order_by(
        StaffMember.created_at.desc()).limit(6).all()
    pending_leaves = scope_by_staff(LeaveRecord.query.filter_by(status='Pending'),
                                    LeaveRecord).order_by(
        LeaveRecord.created_at.desc()).limit(6).all()
    return render_template('hr/dashboard.html', stats=stats, recent=recent,
                           pending_leaves=pending_leaves)


# ============================================================================
# STAFF DIRECTORY
# ============================================================================

@hr_bp.route('/staff')
@login_required
def staff_list():
    dept_id = request.args.get('department_id', type=int)
    staff_type = request.args.get('staff_type')
    status = request.args.get('status')
    q = (request.args.get('q') or '').strip()

    from utils.branch_scope import scope_query
    query = scope_query(StaffMember.query.filter_by(is_active=True), StaffMember)
    if dept_id:
        query = query.filter_by(department_id=dept_id)
    if staff_type:
        query = query.filter_by(staff_type=staff_type)
    if status:
        query = query.filter_by(status=status)
    if q:
        like = f'%{q}%'
        query = query.filter(db.or_(StaffMember.first_name.ilike(like),
                                    StaffMember.surname.ilike(like),
                                    StaffMember.staff_id.ilike(like),
                                    StaffMember.designation.ilike(like),
                                    StaffMember.phone.ilike(like)))
    staff = query.order_by(StaffMember.surname, StaffMember.first_name).all()
    departments = Department.query.filter_by(is_active=True).order_by(Department.name).all()
    return render_template('hr/staff_list.html', staff=staff, departments=departments,
        dept_id=dept_id, staff_type=staff_type, status=status, q=q,
        statuses=hr.STATUSES, staff_types=hr.STAFF_TYPES)


def _read_staff_form(s):
    s.first_name = (request.form.get('first_name') or '').strip()
    s.surname = (request.form.get('surname') or '').strip()
    s.middle_name = (request.form.get('middle_name') or '').strip() or None
    s.gender = request.form.get('gender') or None
    s.date_of_birth = _d(request.form.get('date_of_birth'))
    s.phone = (request.form.get('phone') or '').strip() or None
    s.email = (request.form.get('email') or '').strip() or None
    s.address = (request.form.get('address') or '').strip() or None
    s.department_id = request.form.get('department_id', type=int) or None
    s.designation = (request.form.get('designation') or '').strip() or None
    s.staff_type = request.form.get('staff_type') or 'Teaching'
    s.employment_type = request.form.get('employment_type') or 'Full-time'
    s.date_employed = _d(request.form.get('date_employed'))
    s.status = request.form.get('status') or 'Active'
    s.qualification = (request.form.get('qualification') or '').strip() or None
    s.salary = request.form.get('salary', type=float) or 0
    s.nok_name = (request.form.get('nok_name') or '').strip() or None
    s.nok_phone = (request.form.get('nok_phone') or '').strip() or None
    s.nok_relationship = (request.form.get('nok_relationship') or '').strip() or None
    s.bank_name = (request.form.get('bank_name') or '').strip() or None
    s.account_number = (request.form.get('account_number') or '').strip() or None
    s.account_name = (request.form.get('account_name') or '').strip() or None
    s.notes = (request.form.get('notes') or '').strip() or None


@hr_bp.route('/staff/add', methods=['GET', 'POST'])
@login_required
def add_staff():
    if request.method == 'POST':
        if not (request.form.get('first_name') and request.form.get('surname')):
            flash('First name and surname are required.', 'error')
            return redirect(url_for('hr.add_staff'))
        s = StaffMember(staff_id=StaffMember.generate_staff_id())
        _read_staff_form(s)
        from utils.branch_scope import branch_for_new
        s.branch_id = branch_for_new(request.form.get('branch_id', type=int))
        db.session.add(s)
        db.session.commit()
        from utils.audit import log_action
        log_action('hr.staff_add', target=s)
        flash(f'Staff member {s.full_name} added ({s.staff_id}).', 'success')
        return redirect(url_for('hr.staff_detail', staff_id=s.id))
    return render_template('hr/staff_form.html', staff=None,
        departments=Department.query.filter_by(is_active=True).order_by(Department.name).all(),
        statuses=hr.STATUSES, staff_types=hr.STAFF_TYPES, employment_types=hr.EMPLOYMENT_TYPES)


@hr_bp.route('/staff/<int:staff_id>')
@login_required
def staff_detail(staff_id):
    s = db.get_or_404(StaffMember, staff_id)
    from utils.branch_scope import can_access_branch
    if not can_access_branch(s.branch_id):
        flash('That staff member belongs to another branch.', 'error')
        return redirect(url_for('hr.staff_list'))
    leaves = s.leave_records.order_by(LeaveRecord.start_date.desc()).all()
    payslips = (Payslip.query.filter_by(staff_id=s.id)
                .join(PayrollRun).order_by(PayrollRun.year.desc(), PayrollRun.month.desc()).all())
    salary_history = s.salary_history.order_by(SalaryHistory.created_at.desc()).all()
    return render_template('hr/staff_detail.html', s=s, leaves=leaves,
                           payslips=payslips, leave_types=hr.LEAVE_TYPES,
                           salary_history=salary_history, today=date.today())


@hr_bp.route('/staff/<int:staff_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_staff(staff_id):
    s = db.get_or_404(StaffMember, staff_id)
    from utils.branch_scope import require_branch_access
    require_branch_access(s.branch_id)
    if request.method == 'POST':
        _read_staff_form(s)
        db.session.commit()
        from utils.audit import log_action
        log_action('hr.staff_edit', target=s)
        flash('Staff record updated.', 'success')
        return redirect(url_for('hr.staff_detail', staff_id=s.id))
    return render_template('hr/staff_form.html', staff=s,
        departments=Department.query.filter_by(is_active=True).order_by(Department.name).all(),
        statuses=hr.STATUSES, staff_types=hr.STAFF_TYPES, employment_types=hr.EMPLOYMENT_TYPES)


@hr_bp.route('/staff/<int:staff_id>/salary', methods=['POST'])
@admin_required
def adjust_salary(staff_id):
    """Record a salary increment / adjustment and update the current salary."""
    s = db.get_or_404(StaffMember, staff_id)
    new_salary = request.form.get('new_salary', type=float)
    if new_salary is None or new_salary < 0:
        flash('Enter a valid new salary.', 'error')
        return redirect(url_for('hr.staff_detail', staff_id=staff_id))
    db.session.add(SalaryHistory(
        staff_id=s.id, previous_salary=s.salary or 0, new_salary=new_salary,
        effective_date=_d(request.form.get('effective_date')) or date.today(),
        reason=(request.form.get('reason') or '').strip() or None,
        created_by=_current_user()))
    s.salary = new_salary
    db.session.commit()
    from utils.audit import log_action
    log_action('hr.salary_adjust', detail=f'-> {new_salary:,.2f}', target=s)
    flash(f'Salary updated to {new_salary:,.2f}.', 'success')
    return redirect(url_for('hr.staff_detail', staff_id=staff_id))


@hr_bp.route('/staff/<int:staff_id>/delete', methods=['POST'])
@admin_required
def delete_staff(staff_id):
    s = db.get_or_404(StaffMember, staff_id)
    s.is_active = False
    db.session.commit()
    from utils.audit import log_action
    log_action('hr.staff_delete', target=s)
    flash(f'{s.full_name} archived.', 'success')
    return redirect(url_for('hr.staff_list'))


@hr_bp.route('/staff/export')
@login_required
def export_staff():
    import csv, io
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['Staff ID', 'Name', 'Gender', 'Department', 'Designation', 'Type',
                'Employment', 'Status', 'Phone', 'Email', 'Date Employed', 'Salary'])
    from utils.branch_scope import scope_query
    for s in scope_query(StaffMember.query.filter_by(is_active=True), StaffMember).order_by(StaffMember.surname).all():
        w.writerow([s.staff_id, s.full_name, s.gender or '',
                    s.department.name if s.department else '', s.designation or '',
                    s.staff_type, s.employment_type, s.status, s.phone or '',
                    s.email or '', s.date_employed or '', s.salary or 0])
    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=staff_directory.csv'})


# ============================================================================
# DEPARTMENTS
# ============================================================================

@hr_bp.route('/departments')
@login_required
def departments():
    depts = Department.query.order_by(Department.is_active.desc(), Department.name).all()
    counts = dict(db.session.query(StaffMember.department_id, func.count(StaffMember.id))
                  .filter(StaffMember.is_active == True).group_by(StaffMember.department_id).all())
    return render_template('hr/departments.html', departments=depts, counts=counts)


@hr_bp.route('/departments/add', methods=['POST'])
@admin_required
def add_department():
    name = (request.form.get('name') or '').strip()
    if name and not Department.query.filter(func.lower(Department.name) == name.lower()).first():
        db.session.add(Department(name=name))
        db.session.commit()
        flash(f'Department "{name}" added.', 'success')
    return redirect(url_for('hr.departments'))


@hr_bp.route('/departments/<int:dept_id>/edit', methods=['POST'])
@admin_required
def edit_department(dept_id):
    d = db.get_or_404(Department, dept_id)
    d.name = (request.form.get('name') or d.name).strip()
    d.is_active = bool(request.form.get('is_active'))
    db.session.commit()
    flash('Department updated.', 'success')
    return redirect(url_for('hr.departments'))


@hr_bp.route('/departments/<int:dept_id>/delete', methods=['POST'])
@admin_required
def delete_department(dept_id):
    d = db.get_or_404(Department, dept_id)
    if StaffMember.query.filter_by(department_id=dept_id).count():
        d.is_active = False
        flash('Department has staff; deactivated instead of deleted.', 'info')
    else:
        db.session.delete(d)
        flash('Department deleted.', 'success')
    db.session.commit()
    return redirect(url_for('hr.departments'))


# ============================================================================
# LEAVE
# ============================================================================

@hr_bp.route('/leave')
@login_required
def leave_list():
    from utils.branch_scope import scope_query, scope_by_staff
    status = request.args.get('status')
    q = scope_by_staff(LeaveRecord.query, LeaveRecord)
    if status:
        q = q.filter_by(status=status)
    leaves = q.order_by(LeaveRecord.created_at.desc()).all()
    staff = scope_query(StaffMember.query.filter_by(is_active=True), StaffMember).order_by(StaffMember.surname).all()
    return render_template('hr/leave.html', leaves=leaves, staff=staff,
                           status=status, leave_types=hr.LEAVE_TYPES)


@hr_bp.route('/leave/add', methods=['POST'])
@login_required
def add_leave():
    staff_id = request.form.get('staff_id', type=int)
    start = _d(request.form.get('start_date'))
    end = _d(request.form.get('end_date'))
    if not (staff_id and start and end) or end < start:
        flash('Select a staff member and a valid date range.', 'error')
        return redirect(url_for('hr.leave_list'))
    db.session.add(LeaveRecord(
        staff_id=staff_id, leave_type=request.form.get('leave_type') or 'Other',
        start_date=start, end_date=end, days=(end - start).days + 1,
        reason=(request.form.get('reason') or '').strip() or None))
    db.session.commit()
    flash('Leave request recorded.', 'success')
    return redirect(request.referrer or url_for('hr.leave_list'))


@hr_bp.route('/leave/<int:leave_id>/status', methods=['POST'])
@login_required
def leave_status(leave_id):
    lv = db.get_or_404(LeaveRecord, leave_id)
    new_status = request.form.get('status')
    if new_status in ('Approved', 'Rejected', 'Pending'):
        lv.status = new_status
        # Reflect an approved, currently-active leave on the staff status.
        if new_status == 'Approved' and lv.start_date <= date.today() <= lv.end_date:
            lv.staff.status = 'On Leave'
        db.session.commit()
        flash(f'Leave {new_status.lower()}.', 'success')
    return redirect(request.referrer or url_for('hr.leave_list'))


@hr_bp.route('/leave/<int:leave_id>/delete', methods=['POST'])
@login_required
def delete_leave(leave_id):
    lv = db.get_or_404(LeaveRecord, leave_id)
    db.session.delete(lv)
    db.session.commit()
    flash('Leave record removed.', 'success')
    return redirect(request.referrer or url_for('hr.leave_list'))


# ============================================================================
# PAYROLL
# ============================================================================

@hr_bp.route('/payroll')
@login_required
def payroll_list():
    runs = PayrollRun.query.order_by(PayrollRun.year.desc(), PayrollRun.month.desc()).all()
    rows = [{'run': r, 'total': hr.run_total(r), 'count': r.payslips.count()} for r in runs]
    today = date.today()
    return render_template('hr/payroll.html', rows=rows, months=PayrollRun.MONTHS,
                           cur_year=today.year, cur_month=today.month)


@hr_bp.route('/payroll/create', methods=['POST'])
@admin_required
def create_payroll():
    year = request.form.get('year', type=int)
    month = request.form.get('month', type=int)
    if not (year and month and 1 <= month <= 12):
        flash('Choose a valid month and year.', 'error')
        return redirect(url_for('hr.payroll_list'))
    run = PayrollRun.query.filter_by(year=year, month=month).first()
    if not run:
        run = PayrollRun(year=year, month=month)
        db.session.add(run)
        db.session.flush()
    created = hr.generate_payslips(run)
    db.session.commit()
    flash(f'Payroll for {run.period_label} ready ({created} payslip(s) generated).', 'success')
    return redirect(url_for('hr.payroll_detail', run_id=run.id))


@hr_bp.route('/payroll/<int:run_id>')
@login_required
def payroll_detail(run_id):
    run = db.get_or_404(PayrollRun, run_id)
    slips = run.payslips.join(StaffMember).order_by(StaffMember.surname).all()
    return render_template('hr/payroll_detail.html', run=run, slips=slips,
                           total=hr.run_total(run))


@hr_bp.route('/payroll/<int:run_id>/payslip/<int:slip_id>/edit', methods=['POST'])
@admin_required
def edit_payslip(run_id, slip_id):
    ps = db.get_or_404(Payslip, slip_id)
    if ps.run_id != run_id:
        return ('', 404)
    ps.basic = request.form.get('basic', type=float) or 0
    ps.allowances = request.form.get('allowances', type=float) or 0
    ps.deductions = request.form.get('deductions', type=float) or 0
    ps.recompute()
    db.session.commit()
    flash('Payslip updated.', 'success')
    return redirect(url_for('hr.payroll_detail', run_id=run_id))


@hr_bp.route('/payroll/<int:run_id>/finalize', methods=['POST'])
@admin_required
def finalize_payroll(run_id):
    run = db.get_or_404(PayrollRun, run_id)
    run.status = 'Finalized'
    # Post the salary run to Finance as a single expense (once).
    if request.form.get('post_expense') and not run.posted_expense_id:
        try:
            from models import Expense, ExpenseCategory
            cat = ExpenseCategory.query.filter(
                ExpenseCategory.name.ilike('%salar%')).first()
            term = get_active_term()
            exp = Expense(
                term_id=term.id if term else None,
                category_id=cat.id if cat else None,
                description=f'Payroll — {run.period_label}',
                amount=hr.run_total(run),
                expense_date=date.today(),
                method='Bank Transfer',
                notes=f'Auto-posted from HR payroll #{run.id}')
            db.session.add(exp)
            db.session.flush()
            run.posted_expense_id = exp.id
            flash('Payroll finalized and posted to Finance expenses.', 'success')
        except Exception:
            db.session.rollback()
            run.status = 'Finalized'
            flash('Payroll finalized (could not post to Finance).', 'warning')
    else:
        flash('Payroll finalized.', 'success')
    db.session.commit()
    return redirect(url_for('hr.payroll_detail', run_id=run_id))


@hr_bp.route('/payroll/<int:run_id>/mark-paid', methods=['POST'])
@admin_required
def mark_paid(run_id):
    run = db.get_or_404(PayrollRun, run_id)
    run.status = 'Paid'
    db.session.commit()
    flash('Payroll marked as paid.', 'success')
    return redirect(url_for('hr.payroll_detail', run_id=run_id))


@hr_bp.route('/payroll/<int:run_id>/delete', methods=['POST'])
@admin_required
def delete_payroll(run_id):
    run = db.get_or_404(PayrollRun, run_id)
    db.session.delete(run)
    db.session.commit()
    flash('Payroll run deleted.', 'success')
    return redirect(url_for('hr.payroll_list'))


@hr_bp.route('/payroll/<int:run_id>/payslip/<int:slip_id>/print')
@login_required
def print_payslip(run_id, slip_id):
    ps = db.get_or_404(Payslip, slip_id)
    if ps.run_id != run_id:
        return ('', 404)
    from models import SchoolSettings
    school = {'name': SchoolSettings.get('school_name', 'My School'),
              'address': SchoolSettings.get('school_address', ''),
              'phone': SchoolSettings.get('school_phone', '')}
    return render_template('hr/payslip_print.html', ps=ps, run=ps.run, school=school)


@hr_bp.route('/payroll/<int:run_id>/sync-deductions', methods=['POST'])
@admin_required
def sync_deductions(run_id):
    run = db.get_or_404(PayrollRun, run_id)
    n = hr.sync_attendance_deductions(run)
    db.session.commit()
    flash(f'Refreshed deductions from attendance ({n} payslip(s) updated).', 'success')
    return redirect(url_for('hr.payroll_detail', run_id=run_id))


# ============================================================================
# STAFF ATTENDANCE (with auto lateness / absence deductions)
# ============================================================================

@hr_bp.route('/attendance')
@login_required
def attendance():
    from utils.branch_scope import scope_query
    day = _d(request.args.get('date')) or date.today()
    dept_id = request.args.get('department_id', type=int)
    query = scope_query(StaffMember.query.filter_by(is_active=True, status='Active'), StaffMember)
    if dept_id:
        query = query.filter_by(department_id=dept_id)
    staff = query.order_by(StaffMember.surname, StaffMember.first_name).all()

    existing = {a.staff_id: a for a in StaffAttendance.query.filter_by(date=day).all()}
    rows = [{'staff': s, 'att': existing.get(s.id)} for s in staff]
    # Daily summary
    todays = list(existing.values())
    summary = {
        'present': sum(1 for a in todays if a.status == 'Present'),
        'late': sum(1 for a in todays if a.status == 'Late'),
        'absent': sum(1 for a in todays if a.status == 'Absent'),
        'deduction': sum(a.deduction or 0 for a in todays),
    }
    departments = Department.query.filter_by(is_active=True).order_by(Department.name).all()
    return render_template('hr/attendance.html', rows=rows, day=day, dept_id=dept_id,
        departments=departments, settings=hr.get_settings(), summary=summary,
        att_statuses=hr.ATT_STATUSES)


@hr_bp.route('/attendance/save', methods=['POST'])
@login_required
def save_attendance():
    day = _d(request.form.get('date')) or date.today()
    settings = hr.get_settings()
    staff_ids = request.form.getlist('staff_id', type=int)
    saved = 0
    for sid in staff_ids:
        status = request.form.get(f'status_{sid}') or 'Present'
        clock_in = (request.form.get(f'clock_{sid}') or '').strip() or None
        st, mins, ded = hr.compute_attendance(status, clock_in, settings)
        rec = StaffAttendance.query.filter_by(staff_id=sid, date=day).first()
        if not rec:
            rec = StaffAttendance(staff_id=sid, date=day)
            db.session.add(rec)
        rec.status = st
        rec.clock_in = clock_in
        rec.minutes_late = mins
        rec.deduction = ded
        saved += 1
    db.session.commit()
    flash(f'Attendance saved for {saved} staff on {day.strftime("%d %b %Y")}.', 'success')
    return redirect(url_for('hr.attendance', date=day.isoformat()))


# ============================================================================
# HR SETTINGS
# ============================================================================

@hr_bp.route('/settings')
@login_required
def settings():
    return render_template('hr/settings.html', settings=hr.get_settings())


@hr_bp.route('/settings/save', methods=['POST'])
@admin_required
def save_hr_settings():
    hr.save_settings(request.form)
    db.session.commit()
    flash('HR settings saved.', 'success')
    return redirect(url_for('hr.settings'))
