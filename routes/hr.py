"""
Staff / HR routes — personnel directory, departments, leave management and
monthly payroll (with optional posting of the salary run to Finance expenses).
"""
from datetime import datetime, date
from utils.helpers import get_active_term

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify, Response)
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


# --- SPA helpers (no-reload React shell + JSON-aware action responses) -------

def _wants_json():
    from utils.spa import wants_json
    return wants_json()


def _render(payload):
    from utils.spa import render_or_json
    return render_or_json('hr/app.html', 'hr_json', payload)


def _ok(message, redirect_url=None, **extra):
    if _wants_json():
        return jsonify({'ok': True, 'message': message, 'redirect': redirect_url, **extra})
    flash(message, 'success')
    return redirect(redirect_url or url_for('hr.dashboard'))


def _err(message, redirect_url=None, status=400):
    if _wants_json():
        return jsonify({'ok': False, 'error': message}), status
    flash(message, 'error')
    return redirect(redirect_url or url_for('hr.dashboard'))


def _is_admin():
    from utils.access_control import is_admin
    return is_admin()


def _nav_urls():
    return {'dashboard': url_for('hr.dashboard'), 'staff': url_for('hr.staff_list'),
            'attendance': url_for('hr.attendance'), 'leave': url_for('hr.leave_list'),
            'payroll': url_for('hr.payroll_list'), 'departments': url_for('hr.departments'),
            'settings': url_for('hr.settings')}


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
    return _render({
        'page': 'dashboard', 'nav': _nav_urls(), 'stats': stats,
        'recent': [{'id': s.id, 'full_name': s.full_name, 'designation': s.designation or '—',
                    'department': s.department.name if s.department else '—',
                    'url': url_for('hr.staff_detail', staff_id=s.id)} for s in recent],
        'pending_leaves': [{'staff_name': lv.staff.full_name, 'leave_type': lv.leave_type,
                            'dates': f"{lv.start_date.strftime('%d %b')}–{lv.end_date.strftime('%d %b')}",
                            'days': lv.days} for lv in pending_leaves],
        'urls': {'add_staff': url_for('hr.add_staff'),
                 'leave_pending': url_for('hr.leave_list', status='Pending')},
    })


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
    return _render({
        'page': 'staff', 'nav': _nav_urls(),
        'staff': [{'id': s.id, 'staff_id': s.staff_id, 'full_name': s.full_name,
                   'phone': s.phone or '', 'designation': s.designation or '—',
                   'department': s.department.name if s.department else '—',
                   'staff_type': s.staff_type, 'status': s.status,
                   'url': url_for('hr.staff_detail', staff_id=s.id)} for s in staff],
        'departments': [{'id': d.id, 'name': d.name} for d in departments],
        'applied': {'department_id': dept_id or '', 'staff_type': staff_type or '',
                    'status': status or '', 'q': q},
        'statuses': hr.STATUSES, 'staff_types': hr.STAFF_TYPES,
        'self_url': url_for('hr.staff_list'),
        'urls': {'add': url_for('hr.add_staff'), 'export': url_for('hr.export_staff')},
    })


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


def _staff_form_payload(s, submit_url, cancel_url):
    def g(attr):
        v = getattr(s, attr) if s else None
        return v if v is not None else ''
    return {
        'page': 'staff_form', 'nav': _nav_urls(), 'mode': 'edit' if s else 'add',
        'staff': {
            'id': s.id if s else None,
            'first_name': g('first_name'), 'surname': g('surname'), 'middle_name': g('middle_name'),
            'gender': g('gender'), 'designation': g('designation'),
            'date_of_birth': s.date_of_birth.isoformat() if s and s.date_of_birth else '',
            'phone': g('phone'), 'email': g('email'), 'address': g('address'),
            'department_id': (s.department_id if s and s.department_id else ''),
            'staff_type': g('staff_type') or 'Teaching', 'employment_type': g('employment_type') or 'Full-time',
            'status': g('status') or 'Active',
            'date_employed': s.date_employed.isoformat() if s and s.date_employed else '',
            'salary': (s.salary if s and s.salary else ''), 'qualification': g('qualification'),
            'nok_name': g('nok_name'), 'nok_phone': g('nok_phone'), 'nok_relationship': g('nok_relationship'),
            'bank_name': g('bank_name'), 'account_number': g('account_number'),
            'account_name': g('account_name'), 'notes': g('notes'),
        },
        'departments': [{'id': d.id, 'name': d.name} for d in
                        Department.query.filter_by(is_active=True).order_by(Department.name).all()],
        'statuses': hr.STATUSES, 'staff_types': hr.STAFF_TYPES, 'employment_types': hr.EMPLOYMENT_TYPES,
        'submit_url': submit_url, 'cancel_url': cancel_url,
    }


@hr_bp.route('/staff/add', methods=['GET', 'POST'])
@login_required
def add_staff():
    if request.method == 'POST':
        if not (request.form.get('first_name') and request.form.get('surname')):
            return _err('First name and surname are required.', url_for('hr.add_staff'))
        s = StaffMember(staff_id=StaffMember.generate_staff_id())
        _read_staff_form(s)
        from utils.branch_scope import branch_for_new
        s.branch_id = branch_for_new(request.form.get('branch_id', type=int))
        db.session.add(s)
        db.session.commit()
        from utils.audit import log_action
        log_action('hr.staff_add', target=s)
        return _ok(f'Staff member {s.full_name} added ({s.staff_id}).',
                   url_for('hr.staff_detail', staff_id=s.id))
    return _render(_staff_form_payload(None, url_for('hr.add_staff'), url_for('hr.staff_list')))


@hr_bp.route('/staff/<int:staff_id>')
@login_required
def staff_detail(staff_id):
    s = db.get_or_404(StaffMember, staff_id)
    from utils.branch_scope import can_access_branch
    if not can_access_branch(s.branch_id):
        return _err('That staff member belongs to another branch.', url_for('hr.staff_list'))
    leaves = s.leave_records.order_by(LeaveRecord.start_date.desc()).all()
    payslips = (Payslip.query.filter_by(staff_id=s.id)
                .join(PayrollRun).order_by(PayrollRun.year.desc(), PayrollRun.month.desc()).all())
    salary_history = s.salary_history.order_by(SalaryHistory.created_at.desc()).all()

    def _leave_row(lv):
        return {'id': lv.id, 'leave_type': lv.leave_type,
                'dates': f"{lv.start_date.strftime('%d %b %Y')} – {lv.end_date.strftime('%d %b %Y')}",
                'days': lv.days, 'status': lv.status,
                'approve_url': url_for('hr.leave_status', leave_id=lv.id),
                'delete_url': url_for('hr.delete_leave', leave_id=lv.id)}

    initials = ((s.first_name[0] if s.first_name else '') + (s.surname[0] if s.surname else '')).upper()
    from utils.comms import normalise_phone
    return _render({
        'page': 'staff_detail', 'nav': _nav_urls(), 'is_admin': _is_admin(),
        'today': date.today().isoformat(), 'leave_types': hr.LEAVE_TYPES,
        's': {
            'id': s.id, 'full_name': s.full_name, 'staff_id': s.staff_id, 'initials': initials,
            'designation': s.designation or '', 'department': s.department.name if s.department else '',
            'staff_type': s.staff_type, 'employment_type': s.employment_type, 'status': s.status,
            'phone': s.phone or '', 'wa_intl': (normalise_phone(s.phone) if s.phone else ''),
            'email': s.email or '', 'gender': s.gender or '',
            'date_of_birth': s.date_of_birth.strftime('%d %b %Y') if s.date_of_birth else '',
            'date_employed': s.date_employed.strftime('%d %b %Y') if s.date_employed else '',
            'salary': s.salary or 0, 'qualification': s.qualification or '', 'address': s.address or '',
            'nok_name': s.nok_name or '', 'nok_phone': s.nok_phone or '', 'nok_relationship': s.nok_relationship or '',
            'bank_name': s.bank_name or '', 'account_number': s.account_number or '',
            'account_name': s.account_name or '', 'notes': s.notes or '',
        },
        'salary_history': [{'effective': (h.effective_date or h.created_at).strftime('%d %b %Y'),
                            'previous_salary': h.previous_salary or 0, 'new_salary': h.new_salary or 0,
                            'change': h.change, 'reason': h.reason or '—'} for h in salary_history],
        'leaves': [_leave_row(lv) for lv in leaves],
        'payslips': [{'period': ps.run.period_label, 'basic': ps.basic or 0,
                      'allowances': ps.allowances or 0, 'total_deductions': ps.total_deductions,
                      'net': ps.net or 0,
                      'print_url': url_for('hr.print_payslip', run_id=ps.run_id, slip_id=ps.id)}
                     for ps in payslips],
        'urls': {'edit': url_for('hr.edit_staff', staff_id=s.id),
                 'delete': url_for('hr.delete_staff', staff_id=s.id),
                 'adjust_salary': url_for('hr.adjust_salary', staff_id=s.id),
                 'add_leave': url_for('hr.add_leave'), 'list': url_for('hr.staff_list')},
    })


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
        return _ok('Staff record updated.', url_for('hr.staff_detail', staff_id=s.id))
    return _render(_staff_form_payload(s, url_for('hr.edit_staff', staff_id=s.id),
                                       url_for('hr.staff_detail', staff_id=s.id)))


@hr_bp.route('/staff/<int:staff_id>/salary', methods=['POST'])
@admin_required
def adjust_salary(staff_id):
    """Record a salary increment / adjustment and update the current salary."""
    s = db.get_or_404(StaffMember, staff_id)
    from utils.branch_scope import require_branch_access
    require_branch_access(s.branch_id)   # no cross-branch salary changes
    new_salary = request.form.get('new_salary', type=float)
    if new_salary is None or new_salary < 0:
        return _err('Enter a valid new salary.', url_for('hr.staff_detail', staff_id=staff_id))
    db.session.add(SalaryHistory(
        staff_id=s.id, previous_salary=s.salary or 0, new_salary=new_salary,
        effective_date=_d(request.form.get('effective_date')) or date.today(),
        reason=(request.form.get('reason') or '').strip() or None,
        created_by=_current_user()))
    s.salary = new_salary
    db.session.commit()
    from utils.audit import log_action
    log_action('hr.salary_adjust', detail=f'-> {new_salary:,.2f}', target=s)
    return _ok(f'Salary updated to {new_salary:,.2f}.', url_for('hr.staff_detail', staff_id=staff_id))


@hr_bp.route('/staff/<int:staff_id>/delete', methods=['POST'])
@admin_required
def delete_staff(staff_id):
    s = db.get_or_404(StaffMember, staff_id)
    from utils.branch_scope import require_branch_access
    require_branch_access(s.branch_id)   # no cross-branch staff deletion
    s.is_active = False
    db.session.commit()
    from utils.audit import log_action
    log_action('hr.staff_delete', target=s)
    return _ok(f'{s.full_name} archived.', url_for('hr.staff_list'))


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
    return _render({
        'page': 'departments', 'nav': _nav_urls(), 'is_admin': _is_admin(),
        'departments': [{'id': d.id, 'name': d.name, 'is_active': bool(d.is_active),
                         'count': counts.get(d.id, 0),
                         'edit_url': url_for('hr.edit_department', dept_id=d.id),
                         'delete_url': url_for('hr.delete_department', dept_id=d.id)} for d in depts],
        'add_url': url_for('hr.add_department'),
    })


@hr_bp.route('/departments/add', methods=['POST'])
@admin_required
def add_department():
    name = (request.form.get('name') or '').strip()
    if not name:
        return _err('Enter a department name.', url_for('hr.departments'))
    if Department.query.filter(func.lower(Department.name) == name.lower()).first():
        return _err(f'Department "{name}" already exists.', url_for('hr.departments'))
    db.session.add(Department(name=name))
    db.session.commit()
    return _ok(f'Department "{name}" added.', url_for('hr.departments'))


@hr_bp.route('/departments/<int:dept_id>/edit', methods=['POST'])
@admin_required
def edit_department(dept_id):
    d = db.get_or_404(Department, dept_id)
    d.name = (request.form.get('name') or d.name).strip()
    d.is_active = bool(request.form.get('is_active'))
    db.session.commit()
    return _ok('Department updated.', url_for('hr.departments'))


@hr_bp.route('/departments/<int:dept_id>/delete', methods=['POST'])
@admin_required
def delete_department(dept_id):
    d = db.get_or_404(Department, dept_id)
    if StaffMember.query.filter_by(department_id=dept_id).count():
        d.is_active = False
        db.session.commit()
        return _ok('Department has staff; deactivated instead of deleted.', url_for('hr.departments'))
    db.session.delete(d)
    db.session.commit()
    return _ok('Department deleted.', url_for('hr.departments'))


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
    return _render({
        'page': 'leave', 'nav': _nav_urls(), 'status': status or '',
        'leave_types': hr.LEAVE_TYPES,
        'staff': [{'id': s.id, 'full_name': s.full_name} for s in staff],
        'leaves': [{'id': lv.id, 'staff_name': lv.staff.full_name, 'staff_id': lv.staff_id,
                    'leave_type': lv.leave_type, 'days': lv.days, 'status': lv.status,
                    'dates': f"{lv.start_date.strftime('%d %b %Y')} – {lv.end_date.strftime('%d %b %Y')}",
                    'staff_url': url_for('hr.staff_detail', staff_id=lv.staff_id),
                    'approve_url': url_for('hr.leave_status', leave_id=lv.id),
                    'delete_url': url_for('hr.delete_leave', leave_id=lv.id)} for lv in leaves],
        'add_url': url_for('hr.add_leave'), 'self_url': url_for('hr.leave_list'),
    })


@hr_bp.route('/leave/add', methods=['POST'])
@login_required
def add_leave():
    staff_id = request.form.get('staff_id', type=int)
    start = _d(request.form.get('start_date'))
    end = _d(request.form.get('end_date'))
    if not (staff_id and start and end) or end < start:
        return _err('Select a staff member and a valid date range.', url_for('hr.leave_list'))
    db.session.add(LeaveRecord(
        staff_id=staff_id, leave_type=request.form.get('leave_type') or 'Other',
        start_date=start, end_date=end, days=(end - start).days + 1,
        reason=(request.form.get('reason') or '').strip() or None))
    db.session.commit()
    return _ok('Leave request recorded.', url_for('hr.leave_list'))


@hr_bp.route('/leave/<int:leave_id>/status', methods=['POST'])
@login_required
def leave_status(leave_id):
    lv = db.get_or_404(LeaveRecord, leave_id)
    from utils.branch_scope import require_branch_access
    require_branch_access(lv.staff.branch_id)   # scope by the leave's staff
    new_status = request.form.get('status')
    if new_status in ('Approved', 'Rejected', 'Pending'):
        lv.status = new_status
        # Reflect an approved, currently-active leave on the staff status.
        if new_status == 'Approved' and lv.start_date <= date.today() <= lv.end_date:
            lv.staff.status = 'On Leave'
        db.session.commit()
        return _ok(f'Leave {new_status.lower()}.', url_for('hr.leave_list'))
    return _err('Invalid status.', url_for('hr.leave_list'))


@hr_bp.route('/leave/<int:leave_id>/delete', methods=['POST'])
@login_required
def delete_leave(leave_id):
    lv = db.get_or_404(LeaveRecord, leave_id)
    from utils.branch_scope import require_branch_access
    require_branch_access(lv.staff.branch_id)   # scope by the leave's staff
    db.session.delete(lv)
    db.session.commit()
    return _ok('Leave record removed.', url_for('hr.leave_list'))


# ============================================================================
# PAYROLL
# ============================================================================

@hr_bp.route('/payroll')
@login_required
def payroll_list():
    runs = PayrollRun.query.order_by(PayrollRun.year.desc(), PayrollRun.month.desc()).all()
    today = date.today()
    return _render({
        'page': 'payroll', 'nav': _nav_urls(), 'is_admin': _is_admin(),
        'rows': [{'id': r.id, 'period_label': r.period_label, 'status': r.status,
                  'count': r.payslips.count(), 'total': hr.run_total(r),
                  'url': url_for('hr.payroll_detail', run_id=r.id)} for r in runs],
        'months': [{'value': m, 'name': PayrollRun.MONTHS[m]} for m in range(1, 13)],
        'cur_year': today.year, 'cur_month': today.month,
        'create_url': url_for('hr.create_payroll'),
    })


@hr_bp.route('/payroll/create', methods=['POST'])
@admin_required
def create_payroll():
    year = request.form.get('year', type=int)
    month = request.form.get('month', type=int)
    if not (year and month and 1 <= month <= 12):
        return _err('Choose a valid month and year.', url_for('hr.payroll_list'))
    run = PayrollRun.query.filter_by(year=year, month=month).first()
    if not run:
        run = PayrollRun(year=year, month=month)
        db.session.add(run)
        db.session.flush()
    created = hr.generate_payslips(run)
    db.session.commit()
    return _ok(f'Payroll for {run.period_label} ready ({created} payslip(s) generated).',
               url_for('hr.payroll_detail', run_id=run.id))


@hr_bp.route('/payroll/<int:run_id>')
@login_required
def payroll_detail(run_id):
    run = db.get_or_404(PayrollRun, run_id)
    slips = run.payslips.join(StaffMember).order_by(StaffMember.surname).all()

    def _slip(ps):
        items = [{'name': i.name, 'amount': i.amount or 0} for i in ps.items]
        return {'id': ps.id, 'staff_name': ps.staff_name or (ps.staff.full_name if ps.staff else '—'),
                'basic': ps.basic or 0, 'allowances': ps.allowances or 0,
                'deductions': ps.deductions or 0, 'recurring_deductions': ps.recurring_deductions,
                'attendance_deduction': ps.attendance_deduction or 0,
                'total_deductions': ps.total_deductions, 'net': ps.net or 0, 'items': items,
                'print_url': url_for('hr.print_payslip', run_id=run.id, slip_id=ps.id),
                'edit_url': url_for('hr.edit_payslip', run_id=run.id, slip_id=ps.id)}

    return _render({
        'page': 'payroll_detail', 'nav': _nav_urls(), 'is_admin': _is_admin(),
        'run': {'id': run.id, 'period_label': run.period_label, 'status': run.status,
                'posted_expense_id': run.posted_expense_id},
        'slips': [_slip(ps) for ps in slips], 'total': hr.run_total(run),
        'urls': {'sync_deductions': url_for('hr.sync_deductions', run_id=run.id),
                 'finalize': url_for('hr.finalize_payroll', run_id=run.id),
                 'mark_paid': url_for('hr.mark_paid', run_id=run.id),
                 'delete': url_for('hr.delete_payroll', run_id=run.id),
                 'list': url_for('hr.payroll_list')},
    })


@hr_bp.route('/payroll/<int:run_id>/payslip/<int:slip_id>/edit', methods=['POST'])
@admin_required
def edit_payslip(run_id, slip_id):
    ps = db.get_or_404(Payslip, slip_id)
    if ps.run_id != run_id:
        return ('', 404)
    ps.basic = request.form.get('basic', type=float) or 0
    ps.allowances = request.form.get('allowances', type=float) or 0
    ps.deductions = request.form.get('deductions', type=float) or 0
    hr.apply_recurring_deductions(ps)   # percentage lines follow the new basic
    ps.recompute()
    db.session.commit()
    return _ok('Payslip updated.', url_for('hr.payroll_detail', run_id=run_id))


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
            from utils.branch_scope import branch_for_new
            exp = Expense(
                term_id=term.id if term else None,
                category_id=cat.id if cat else None,
                branch_id=branch_for_new(),
                description=f'Payroll — {run.period_label}',
                amount=hr.run_total(run),
                expense_date=date.today(),
                method='Bank Transfer',
                notes=f'Auto-posted from HR payroll #{run.id}')
            db.session.add(exp)
            db.session.flush()
            run.posted_expense_id = exp.id
            db.session.commit()
            return _ok('Payroll finalized and posted to Finance expenses.',
                       url_for('hr.payroll_detail', run_id=run_id))
        except Exception as e:
            # Posting to Finance failed; still finalize the payroll itself, but
            # log the cause and tell the user it can be re-posted.
            db.session.rollback()
            from flask import current_app
            current_app.logger.exception('Payroll #%s: posting to Finance failed', run.id)
            run.status = 'Finalized'
            db.session.commit()
            return _ok(f'Payroll finalized, but posting to Finance failed ({e}). '
                       'You can post it again later.', url_for('hr.payroll_detail', run_id=run_id))
    db.session.commit()
    return _ok('Payroll finalized.', url_for('hr.payroll_detail', run_id=run_id))


@hr_bp.route('/payroll/<int:run_id>/mark-paid', methods=['POST'])
@admin_required
def mark_paid(run_id):
    run = db.get_or_404(PayrollRun, run_id)
    run.status = 'Paid'
    db.session.commit()
    return _ok('Payroll marked as paid.', url_for('hr.payroll_detail', run_id=run_id))


@hr_bp.route('/payroll/<int:run_id>/delete', methods=['POST'])
@admin_required
def delete_payroll(run_id):
    run = db.get_or_404(PayrollRun, run_id)
    db.session.delete(run)
    db.session.commit()
    return _ok('Payroll run deleted.', url_for('hr.payroll_list'))


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
    return _ok(f'Refreshed deductions from attendance ({n} payslip(s) updated).',
               url_for('hr.payroll_detail', run_id=run_id))


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
    return _render({
        'page': 'attendance', 'nav': _nav_urls(),
        'day': day.isoformat(), 'day_label': day.strftime('%A, %d %b %Y'),
        'dept_id': dept_id or '', 'settings': hr.get_settings(), 'summary': summary,
        'att_statuses': hr.ATT_STATUSES,
        'departments': [{'id': d.id, 'name': d.name} for d in departments],
        'rows': [{'id': r['staff'].id, 'full_name': r['staff'].full_name,
                  'status': r['att'].status if r['att'] else 'Present',
                  'clock_in': (r['att'].clock_in if r['att'] and r['att'].clock_in else ''),
                  'minutes_late': (r['att'].minutes_late if r['att'] else 0) or 0,
                  'deduction': (r['att'].deduction if r['att'] else 0) or 0} for r in rows],
        'save_url': url_for('hr.save_attendance'), 'self_url': url_for('hr.attendance'),
        'settings_url': url_for('hr.settings'),
    })


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
    return _ok(f'Attendance saved for {saved} staff on {day.strftime("%d %b %Y")}.',
               url_for('hr.attendance', date=day.isoformat()))


# ============================================================================
# HR SETTINGS
# ============================================================================

@hr_bp.route('/settings')
@login_required
def settings():
    from models import PayrollDeductionType
    deductions = PayrollDeductionType.query.order_by(PayrollDeductionType.name).all()
    return _render({
        'page': 'settings', 'nav': _nav_urls(), 'is_admin': _is_admin(),
        'settings': hr.get_settings(),
        'deductions': [{'id': d.id, 'name': d.name, 'kind': d.kind, 'value': d.value or 0,
                        'is_active': bool(d.is_active),
                        'toggle_url': url_for('hr.toggle_deduction_type', type_id=d.id),
                        'delete_url': url_for('hr.delete_deduction_type', type_id=d.id)} for d in deductions],
        'urls': {'save': url_for('hr.save_hr_settings'), 'add_deduction': url_for('hr.add_deduction_type')},
    })


@hr_bp.route('/settings/deductions/add', methods=['POST'])
@admin_required
def add_deduction_type():
    from models import PayrollDeductionType
    from utils.branch_scope import branch_for_new
    name = (request.form.get('name') or '').strip()
    kind = request.form.get('kind') if request.form.get('kind') in ('percent', 'fixed') else 'fixed'
    value = request.form.get('value', type=float) or 0
    if not name or value <= 0:
        return _err('A name and a positive value are required.', url_for('hr.settings'))
    if kind == 'percent' and value > 100:
        return _err('A percentage deduction cannot exceed 100%.', url_for('hr.settings'))
    db.session.add(PayrollDeductionType(name=name, kind=kind, value=value,
                                        is_active=True, branch_id=branch_for_new()))
    db.session.commit()
    return _ok(f'Deduction "{name}" added. It applies to payroll generated from now on.',
               url_for('hr.settings'))


@hr_bp.route('/settings/deductions/<int:type_id>/toggle', methods=['POST'])
@admin_required
def toggle_deduction_type(type_id):
    from models import PayrollDeductionType
    t = db.get_or_404(PayrollDeductionType, type_id)
    t.is_active = not t.is_active
    db.session.commit()
    return _ok(f'"{t.name}" is now {"active" if t.is_active else "inactive"}.', url_for('hr.settings'))


@hr_bp.route('/settings/deductions/<int:type_id>/delete', methods=['POST'])
@admin_required
def delete_deduction_type(type_id):
    from models import PayrollDeductionType
    t = db.get_or_404(PayrollDeductionType, type_id)
    db.session.delete(t); db.session.commit()
    return _ok('Deduction removed (existing payslips keep their recorded lines).', url_for('hr.settings'))


@hr_bp.route('/settings/save', methods=['POST'])
@admin_required
def save_hr_settings():
    hr.save_settings(request.form)
    db.session.commit()
    return _ok('HR settings saved.', url_for('hr.settings'))
