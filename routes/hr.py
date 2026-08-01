"""
Staff / HR routes — personnel directory, departments, leave management and
monthly payroll (with optional posting of the salary run to Finance expenses).
"""
from datetime import datetime, date
from utils.helpers import get_active_term

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify, Response, abort, session)
from utils.web_exports import csv_response
from sqlalchemy import func

from models import (
    db, StaffMember, Department, LeaveRecord, PayrollRun, Payslip,
    SalaryHistory, StaffAttendance, StaffLoan,
)
from utils.audit import log_action
from utils.access_control import login_required, admin_required
from utils.branch_scope import require_branch_access
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


# --- SPA helpers (no-reload React shell + JSON-aware action responses) ---
from utils.spa import section_responders
from utils.search import like_term
_wants_json, _render, _ok, _err = section_responders(
    'hr/app.html', 'hr_json', 'hr.dashboard')


def _is_admin():
    from utils.access_control import is_admin
    return is_admin()


def _require_payroll_run_access(run):
    """Payroll is per-branch: a branch admin manages only their own branch's
    runs, a central admin manages every branch's. A legacy NULL-branch run is
    org-wide (pre per-branch payroll) and is therefore central-only. Guards
    every by-id payroll route against a branch admin reaching another branch's
    run/payslip via a guessed id."""
    from utils.branch_scope import is_central, require_branch_access
    if run is None:
        abort(404)
    if run.branch_id is None:
        if not is_central():
            abort(403)          # legacy org-wide run: central only
        return
    require_branch_access(run.branch_id)


def _branches_for_transfer(s):
    """Destination branches a central admin may transfer this staff member to
    (all active branches except their current one). Empty for branch admins, who
    cannot move staff across branches."""
    from utils.branch_scope import is_central
    if not is_central():
        return []
    from models import Branch
    return [{'id': b.id, 'name': b.name} for b in
            Branch.query.filter_by(is_active=True).order_by(Branch.name).all()
            if b.id != s.branch_id]


def _nav_urls():
    return {'dashboard': url_for('hr.dashboard'), 'staff': url_for('hr.staff_list'),
            'attendance': url_for('hr.attendance'), 'leave': url_for('hr.leave_list'),
            'payroll': url_for('hr.payroll_list'), 'departments': url_for('hr.departments'),
            'recruitment': url_for('hr.recruitment'),
            'reports': url_for('hr.reports'), 'settings': url_for('hr.settings')}


# ============================================================================
# DASHBOARD
# ============================================================================

@hr_bp.route('/')
@login_required
def dashboard():
    from utils.branch_scope import scope_query, scope_by_staff, viewing_branch_id
    stats = hr.dashboard_stats(viewing_branch_id())
    recent = scope_query(StaffMember.query.filter_by(is_active=True), StaffMember).order_by(
        StaffMember.created_at.desc()).limit(6).all()
    pending_leaves = scope_by_staff(LeaveRecord.query.filter_by(status='Pending'),
                                    LeaveRecord).order_by(
        LeaveRecord.created_at.desc()).limit(6).all()
    bid = viewing_branch_id()
    return _render({
        'page': 'dashboard', 'nav': _nav_urls(), 'stats': stats,
        'recent': [{'id': s.id, 'full_name': s.full_name, 'designation': s.designation or '—',
                    'department': s.department.name if s.department else '—',
                    'url': url_for('hr.staff_detail', staff_id=s.id)} for s in recent],
        'pending_leaves': [{'id': lv.id, 'staff_name': lv.staff.full_name, 'leave_type': lv.leave_type,
                            'dates': f"{lv.start_date.strftime('%d %b')}–{lv.end_date.strftime('%d %b')}",
                            'days': lv.days,
                            'staff_url': url_for('hr.staff_detail', staff_id=lv.staff_id)} for lv in pending_leaves],
        'birthdays': [{**b, 'url': url_for('hr.staff_detail', staff_id=b['id'])}
                      for b in hr.upcoming_birthdays(bid)],
        'contracts': [{**c, 'url': url_for('hr.staff_detail', staff_id=c['id'])}
                      for c in hr.expiring_contracts(bid)],
        'urls': {'add_staff': url_for('hr.add_staff'),
                 'attendance': url_for('hr.attendance'), 'reports': url_for('hr.reports'),
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
        like = like_term(q)
        query = query.filter(db.or_(StaffMember.first_name.ilike(like, escape='\\'),
                                    StaffMember.surname.ilike(like, escape='\\'),
                                    StaffMember.staff_id.ilike(like, escape='\\'),
                                    StaffMember.designation.ilike(like, escape='\\'),
                                    StaffMember.phone.ilike(like, escape='\\')))
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
        'urls': {'add': url_for('hr.add_staff'), 'export': url_for('hr.export_staff'),
                 'import': url_for('hr.import_staff'), 'notify': url_for('hr.notify_staff'),
                 'search': url_for('hr.staff_search')},
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
    s.confirmation_date = _d(request.form.get('confirmation_date'))
    s.contract_start = _d(request.form.get('contract_start'))
    s.contract_end = _d(request.form.get('contract_end'))
    s.status = request.form.get('status') or 'Active'
    s.qualification = (request.form.get('qualification') or '').strip() or None
    s.certifications = (request.form.get('certifications') or '').strip() or None
    s.prior_experience_years = request.form.get('prior_experience_years', type=int)
    s.salary = request.form.get('salary', type=float) or 0
    s.nok_name = (request.form.get('nok_name') or '').strip() or None
    s.nok_phone = (request.form.get('nok_phone') or '').strip() or None
    s.nok_relationship = (request.form.get('nok_relationship') or '').strip() or None
    s.emergency_name = (request.form.get('emergency_name') or '').strip() or None
    s.emergency_phone = (request.form.get('emergency_phone') or '').strip() or None
    s.tax_id = (request.form.get('tax_id') or '').strip() or None
    s.pension_pin = (request.form.get('pension_pin') or '').strip() or None
    s.pension_provider = (request.form.get('pension_provider') or '').strip() or None
    s.blood_group = (request.form.get('blood_group') or '').strip() or None
    s.medical_notes = (request.form.get('medical_notes') or '').strip() or None
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
            'confirmation_date': s.confirmation_date.isoformat() if s and s.confirmation_date else '',
            'contract_start': s.contract_start.isoformat() if s and s.contract_start else '',
            'contract_end': s.contract_end.isoformat() if s and s.contract_end else '',
            'salary': (s.salary if s and s.salary else ''), 'qualification': g('qualification'),
            'certifications': g('certifications'),
            'prior_experience_years': (s.prior_experience_years if s and s.prior_experience_years is not None else ''),
            'nok_name': g('nok_name'), 'nok_phone': g('nok_phone'), 'nok_relationship': g('nok_relationship'),
            'emergency_name': g('emergency_name'), 'emergency_phone': g('emergency_phone'),
            'tax_id': g('tax_id'), 'pension_pin': g('pension_pin'), 'pension_provider': g('pension_provider'),
            'blood_group': g('blood_group'), 'medical_notes': g('medical_notes'),
            'bank_name': g('bank_name'), 'account_number': g('account_number'),
            'account_name': g('account_name'), 'notes': g('notes'),
        },
        'blood_groups': hr.BLOOD_GROUPS,
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
        db.session.flush()
        # Optionally also create a linked login account so this person can sign in.
        user_note = ''
        if (request.form.get('create_user') or '').lower() in ('on', 'true', '1', 'yes'):
            from utils.staff_user_link import create_user_for_staff
            u, temp = create_user_for_staff(s, created_by_id=session.get('user_id'))
            if temp:
                user_note = (f' A login account was created — username "{u.username}", '
                             f'temporary password "{temp}" (they must change it at first sign-in).')
        db.session.commit()
        from utils.audit import log_action
        log_action('hr.staff_add', target=s, detail='+user' if user_note else None)
        return _ok(f'Staff member {s.full_name} added ({s.staff_id}).{user_note}',
                   url_for('hr.staff_detail', staff_id=s.id))
    return _render(_staff_form_payload(None, url_for('hr.add_staff'), url_for('hr.staff_list')))


@hr_bp.route('/staff/<int:staff_id>')
@login_required
def staff_detail(staff_id):
    s = db.get_or_404(StaffMember, staff_id)
    from utils.branch_scope import can_access_branch
    from models import StaffDocument, TrainingRecord, PerformanceReview
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
    today = date.today()
    contract_left = s.contract_days_left
    return _render({
        'page': 'staff_detail', 'nav': _nav_urls(), 'is_admin': _is_admin(),
        'today': today.isoformat(), 'leave_types': hr.LEAVE_TYPES,
        's': {
            'id': s.id, 'full_name': s.full_name, 'staff_id': s.staff_id, 'initials': initials,
            'photo_url': s.photo_url or '',
            'designation': s.designation or '', 'department': s.department.name if s.department else '',
            'staff_type': s.staff_type, 'employment_type': s.employment_type, 'status': s.status,
            'phone': s.phone or '', 'wa_intl': (normalise_phone(s.phone) if s.phone else ''),
            'email': s.email or '', 'gender': s.gender or '',
            'date_of_birth': s.date_of_birth.strftime('%d %b %Y') if s.date_of_birth else '',
            'age': s.age,
            'date_employed': s.date_employed.strftime('%d %b %Y') if s.date_employed else '',
            'confirmation_date': s.confirmation_date.strftime('%d %b %Y') if s.confirmation_date else '',
            'contract_start': s.contract_start.strftime('%d %b %Y') if s.contract_start else '',
            'contract_end': s.contract_end.strftime('%d %b %Y') if s.contract_end else '',
            'contract_days_left': contract_left,
            'contract_expiring': (contract_left is not None and contract_left <= 60),
            'years_of_service': s.years_of_service, 'total_experience_years': s.total_experience_years,
            'salary': s.salary or 0, 'qualification': s.qualification or '',
            'certifications': s.certifications or '', 'address': s.address or '',
            'nok_name': s.nok_name or '', 'nok_phone': s.nok_phone or '', 'nok_relationship': s.nok_relationship or '',
            'emergency_name': s.emergency_name or '', 'emergency_phone': s.emergency_phone or '',
            'tax_id': s.tax_id or '', 'pension_pin': s.pension_pin or '', 'pension_provider': s.pension_provider or '',
            'blood_group': s.blood_group or '', 'medical_notes': s.medical_notes or '',
            'bank_name': s.bank_name or '', 'account_number': s.account_number or '',
            'account_name': s.account_name or '', 'notes': s.notes or '',
        },
        'teaching_load': hr.teaching_load(s),
        'attendance_summary': hr.attendance_summary(s.id, today.year, today.month),
        'attendance_month': today.strftime('%B %Y'),
        'leave_summary': hr.leave_summary(s.id, today.year),
        'leave_balances': hr.leave_balances(s.id, today.year),
        'timeline': hr.build_timeline(s),
        'can_transfer': _branches_for_transfer(s),
        'doc_types': StaffDocument.DOC_TYPES, 'training_kinds': TrainingRecord.KINDS,
        'documents': [_doc_row(x) for x in
                      s.documents.filter(StaffDocument.is_current.isnot(False))
                      .order_by(StaffDocument.created_at.desc()).all()],
        'training': [_training_row(x) for x in
                     s.training.order_by(TrainingRecord.created_at.desc()).all()],
        'reviews': [_review_row(x) for x in
                    s.reviews.order_by(PerformanceReview.created_at.desc()).all()],
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
                 'promote': url_for('hr.promote_staff', staff_id=s.id),
                 'transfer': url_for('hr.transfer_staff', staff_id=s.id),
                 'confirm': url_for('hr.confirm_staff', staff_id=s.id),
                 'add_note': url_for('hr.add_staff_note', staff_id=s.id),
                 'upload_document': url_for('hr.upload_document', staff_id=s.id),
                 'add_training': url_for('hr.add_training', staff_id=s.id),
                 'add_review': url_for('hr.add_review', staff_id=s.id),
                 'self': url_for('hr.staff_detail', staff_id=s.id),
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
    old_salary = s.salary or 0          # capture before overwriting for the audit
    db.session.add(SalaryHistory(
        staff_id=s.id, previous_salary=old_salary, new_salary=new_salary,
        effective_date=_d(request.form.get('effective_date')) or date.today(),
        reason=(request.form.get('reason') or '').strip() or None,
        created_by=_current_user()))
    s.salary = new_salary
    db.session.commit()
    from utils.audit import log_action
    log_action('hr.salary_adjust',
               detail=f'{old_salary:,.2f}→{new_salary:,.2f}', target=s)
    return _ok(f'Salary updated to {new_salary:,.2f}.', url_for('hr.staff_detail', staff_id=staff_id))


@hr_bp.route('/staff/<int:staff_id>/promote', methods=['POST'])
@admin_required
def promote_staff(staff_id):
    """Record a promotion: update the job title (and optionally the salary, which
    also lands in salary history) and log a lifecycle event."""
    s = db.get_or_404(StaffMember, staff_id)
    from utils.branch_scope import require_branch_access
    require_branch_access(s.branch_id)
    new_title = (request.form.get('designation') or '').strip()
    if not new_title:
        return _err('Enter the new position/title.', url_for('hr.staff_detail', staff_id=staff_id))
    old_title = s.designation or '—'
    eff = _d(request.form.get('effective_date')) or date.today()
    detail = f'{old_title} → {new_title}'
    # Optional salary change rides along with the promotion.
    new_salary = request.form.get('new_salary', type=float)
    if new_salary is not None and new_salary >= 0 and new_salary != (s.salary or 0):
        db.session.add(SalaryHistory(
            staff_id=s.id, previous_salary=s.salary or 0, new_salary=new_salary,
            effective_date=eff, reason=f'Promotion: {new_title}', created_by=_current_user()))
        s.salary = new_salary
        detail += f' · salary {new_salary:,.0f}'
    s.designation = new_title
    hr.record_event(s, 'promotion', f'Promoted to {new_title}', detail=detail,
                    effective_date=eff, created_by=_current_user())
    db.session.commit()
    from utils.audit import log_action
    log_action('hr.promote', detail=detail, target=s)
    return _ok(f'{s.full_name} promoted to {new_title}.', url_for('hr.staff_detail', staff_id=staff_id))


@hr_bp.route('/staff/<int:staff_id>/transfer', methods=['POST'])
@admin_required
def transfer_staff(staff_id):
    """Transfer a staff member to another branch (central admins only) and log it."""
    s = db.get_or_404(StaffMember, staff_id)
    from utils.branch_scope import require_branch_access, is_central
    require_branch_access(s.branch_id)
    if not is_central():
        return _err('Only a central administrator can transfer staff between branches.',
                    url_for('hr.staff_detail', staff_id=staff_id))
    from models import Branch
    target_id = request.form.get('branch_id', type=int)
    target = db.session.get(Branch, target_id) if target_id else None
    if not target:
        return _err('Choose a destination branch.', url_for('hr.staff_detail', staff_id=staff_id))
    if target.id == s.branch_id:
        return _err('The staff member is already at that branch.',
                    url_for('hr.staff_detail', staff_id=staff_id))
    old_branch = db.session.get(Branch, s.branch_id) if s.branch_id else None
    old = old_branch.name if old_branch else 'Unassigned'
    eff = _d(request.form.get('effective_date')) or date.today()
    s.branch_id = target.id
    hr.record_event(s, 'transfer', f'Transferred to {target.name}',
                    detail=f'{old} → {target.name}', effective_date=eff, created_by=_current_user())
    db.session.commit()
    from utils.audit import log_action
    log_action('hr.transfer', detail=f'{old} -> {target.name}', target=s)
    return _ok(f'{s.full_name} transferred to {target.name}.',
               url_for('hr.staff_detail', staff_id=staff_id))


@hr_bp.route('/staff/<int:staff_id>/confirm', methods=['POST'])
@admin_required
def confirm_staff(staff_id):
    """Confirm a staff member off probation (sets the confirmation date)."""
    s = db.get_or_404(StaffMember, staff_id)
    from utils.branch_scope import require_branch_access
    require_branch_access(s.branch_id)
    eff = _d(request.form.get('effective_date')) or date.today()
    s.confirmation_date = eff
    db.session.commit()
    from utils.audit import log_action
    log_action('hr.confirm', detail=eff.isoformat(), target=s)
    return _ok(f'{s.full_name} confirmed as of {eff.strftime("%d %b %Y")}.',
               url_for('hr.staff_detail', staff_id=staff_id))


@hr_bp.route('/staff/<int:staff_id>/note', methods=['POST'])
@login_required
def add_staff_note(staff_id):
    """Attach a dated note to the staff timeline."""
    s = db.get_or_404(StaffMember, staff_id)
    from utils.branch_scope import require_branch_access
    require_branch_access(s.branch_id)
    title = (request.form.get('title') or '').strip()
    if not title:
        return _err('Enter a note.', url_for('hr.staff_detail', staff_id=staff_id))
    hr.record_event(s, 'note', title, detail=(request.form.get('detail') or '').strip() or None,
                    effective_date=_d(request.form.get('effective_date')) or date.today(),
                    created_by=_current_user())
    db.session.commit()
    return _ok('Note added to the timeline.', url_for('hr.staff_detail', staff_id=staff_id))


# ---- Documents / training / performance (attached to a profile) -----------

def _doc_row(doc):
    # Walk the supersession chain to list prior versions (newest-first).
    prior, p, seen = [], doc.replaces, {doc.id}
    while p and p.id not in seen:
        seen.add(p.id)
        prior.append({'version': p.version or 1,
                      'created': p.created_at.strftime('%d %b %Y') if p.created_at else '',
                      'download_url': (url_for('comms.download_attachment', att_id=p.attachment_id)
                                       if p.attachment_id else None)})
        p = p.replaces
    return {'id': doc.id, 'title': doc.title, 'doc_type': doc.doc_type or 'Other',
            'name': doc.attachment.original_name if doc.attachment else '',
            'size': doc.attachment.human_size if doc.attachment else '',
            'expires_on': doc.expires_on.strftime('%d %b %Y') if doc.expires_on else '',
            'is_expired': doc.is_expired, 'version': doc.version or 1, 'prior': prior,
            'download_url': (url_for('comms.download_attachment', att_id=doc.attachment_id)
                             if doc.attachment_id else None),
            'replace_url': url_for('hr.upload_document', staff_id=doc.staff_id) + f'?replace_id={doc.id}',
            'delete_url': url_for('hr.delete_document', staff_id=doc.staff_id, doc_id=doc.id)}


def _training_row(t):
    span = ' – '.join(x.strftime('%d %b %Y') for x in [t.start_date, t.end_date] if x)
    return {'id': t.id, 'title': t.title, 'kind': t.kind or 'Training', 'provider': t.provider or '',
            'dates': span, 'hours': t.hours or 0, 'note': t.note or '',
            'certificate_url': (url_for('comms.download_attachment', att_id=t.certificate_id)
                                if t.certificate_id else None),
            'delete_url': url_for('hr.delete_training', staff_id=t.staff_id, train_id=t.id)}


def _review_row(r):
    return {'id': r.id, 'period': r.period or '', 'reviewer': r.reviewer or '',
            'review_date': r.review_date.strftime('%d %b %Y') if r.review_date else '',
            'score': r.score, 'rating': r.rating or '', 'strengths': r.strengths or '',
            'improvements': r.improvements or '', 'comments': r.comments or '',
            'delete_url': url_for('hr.delete_review', staff_id=r.staff_id, review_id=r.id)}


@hr_bp.route('/staff/<int:staff_id>/documents', methods=['POST'])
@login_required
def upload_document(staff_id):
    s = db.get_or_404(StaffMember, staff_id)
    from utils.branch_scope import require_branch_access
    require_branch_access(s.branch_id)
    title = (request.form.get('title') or '').strip()
    if not title:
        return _err('Give the document a title.', url_for('hr.staff_detail', staff_id=staff_id))
    from utils import comm_attachments as CA
    from models import StaffDocument
    # Replacing an existing document keeps the old one as a prior version.
    replace_id = request.form.get('replace_id', type=int) or request.args.get('replace_id', type=int)
    old = None
    if replace_id:
        old = db.session.get(StaffDocument, replace_id)
        if not old or old.staff_id != s.id:
            return _err('Cannot find the document to replace.', url_for('hr.staff_detail', staff_id=staff_id))
    try:
        att = CA.save(request.files.get('file'), created_by=_current_user())
    except ValueError as e:
        return _err(str(e), url_for('hr.staff_detail', staff_id=staff_id))
    doc = StaffDocument(staff_id=s.id, attachment_id=att.id,
                        title=title or (old.title if old else title),
                        doc_type=request.form.get('doc_type') or (old.doc_type if old else 'Other'),
                        expires_on=_d(request.form.get('expires_on')),
                        uploaded_by=_current_user(), is_current=True)
    if old:
        doc.version = (old.version or 1) + 1
        doc.replaces_id = old.id
        old.is_current = False
    db.session.add(doc)
    db.session.commit()
    from utils.audit import log_action
    log_action('hr.document_add', detail=f'{title} v{doc.version}', target=s)
    return _ok('New version uploaded.' if old else 'Document uploaded.',
               url_for('hr.staff_detail', staff_id=staff_id))


@hr_bp.route('/staff/<int:staff_id>/documents/<int:doc_id>/delete', methods=['POST'])
@login_required
def delete_document(staff_id, doc_id):
    from models import StaffDocument, CommAttachment
    doc = db.get_or_404(StaffDocument, doc_id)
    if doc.staff_id != staff_id:
        return ('', 404)
    from utils.branch_scope import require_branch_access
    require_branch_access(doc.staff.branch_id)
    from utils import comm_attachments as CA
    att = db.session.get(CommAttachment, doc.attachment_id) if doc.attachment_id else None
    db.session.delete(doc)
    db.session.commit()
    if att:
        CA.delete(att)      # removes file + row
    return _ok('Document removed.', url_for('hr.staff_detail', staff_id=staff_id))


@hr_bp.route('/staff/<int:staff_id>/training', methods=['POST'])
@login_required
def add_training(staff_id):
    s = db.get_or_404(StaffMember, staff_id)
    from utils.branch_scope import require_branch_access
    require_branch_access(s.branch_id)
    title = (request.form.get('title') or '').strip()
    if not title:
        return _err('Enter the programme title.', url_for('hr.staff_detail', staff_id=staff_id))
    from models import TrainingRecord
    cert_id = None
    if request.files.get('file') and request.files['file'].filename:
        from utils import comm_attachments as CA
        try:
            cert_id = CA.save(request.files['file'], created_by=_current_user()).id
        except ValueError as e:
            return _err(str(e), url_for('hr.staff_detail', staff_id=staff_id))
    db.session.add(TrainingRecord(
        staff_id=s.id, title=title, kind=request.form.get('kind') or 'Training',
        provider=(request.form.get('provider') or '').strip() or None,
        start_date=_d(request.form.get('start_date')), end_date=_d(request.form.get('end_date')),
        hours=request.form.get('hours', type=float) or 0, certificate_id=cert_id,
        note=(request.form.get('note') or '').strip() or None, created_by=_current_user()))
    db.session.commit()
    from utils.audit import log_action
    log_action('hr.training_add', detail=title, target=s)
    return _ok('Training record added.', url_for('hr.staff_detail', staff_id=staff_id))


@hr_bp.route('/staff/<int:staff_id>/training/<int:train_id>/delete', methods=['POST'])
@login_required
def delete_training(staff_id, train_id):
    from models import TrainingRecord
    t = db.get_or_404(TrainingRecord, train_id)
    if t.staff_id != staff_id:
        return ('', 404)
    from utils.branch_scope import require_branch_access
    require_branch_access(t.staff.branch_id)
    db.session.delete(t)
    db.session.commit()
    return _ok('Training record removed.', url_for('hr.staff_detail', staff_id=staff_id))


@hr_bp.route('/staff/<int:staff_id>/reviews', methods=['POST'])
@admin_required
def add_review(staff_id):
    s = db.get_or_404(StaffMember, staff_id)
    from utils.branch_scope import require_branch_access
    require_branch_access(s.branch_id)
    period = (request.form.get('period') or '').strip()
    if not period:
        return _err('Enter the review period.', url_for('hr.staff_detail', staff_id=staff_id))
    from models import PerformanceReview
    db.session.add(PerformanceReview(
        staff_id=s.id, period=period, review_date=_d(request.form.get('review_date')) or date.today(),
        reviewer=(request.form.get('reviewer') or _current_user()).strip() or None,
        score=request.form.get('score', type=float), rating=request.form.get('rating') or None,
        strengths=(request.form.get('strengths') or '').strip() or None,
        improvements=(request.form.get('improvements') or '').strip() or None,
        comments=(request.form.get('comments') or '').strip() or None, created_by=_current_user()))
    db.session.commit()
    from utils.audit import log_action
    log_action('hr.review_add', detail=period, target=s)
    return _ok('Performance review saved.', url_for('hr.staff_detail', staff_id=staff_id))


@hr_bp.route('/staff/<int:staff_id>/reviews/<int:review_id>/delete', methods=['POST'])
@admin_required
def delete_review(staff_id, review_id):
    from models import PerformanceReview
    r = db.get_or_404(PerformanceReview, review_id)
    if r.staff_id != staff_id:
        return ('', 404)
    from utils.branch_scope import require_branch_access
    require_branch_access(r.staff.branch_id)
    db.session.delete(r)
    db.session.commit()
    return _ok('Review removed.', url_for('hr.staff_detail', staff_id=staff_id))


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


@hr_bp.route('/staff/search')
@login_required
def staff_search():
    """Type-ahead staff search for the directory's quick jump-to-profile box."""
    from utils.branch_scope import scope_query
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify([])
    like = like_term(q)
    rows = (scope_query(StaffMember.query.filter_by(is_active=True), StaffMember)
            .filter(db.or_(StaffMember.first_name.ilike(like, escape='\\'),
                           StaffMember.surname.ilike(like, escape='\\'),
                           StaffMember.staff_id.ilike(like, escape='\\'),
                           StaffMember.designation.ilike(like, escape='\\'),
                           StaffMember.phone.ilike(like, escape='\\')))
            .order_by(StaffMember.surname).limit(15).all())
    return jsonify([{'id': s.id, 'label': f'{s.full_name} ({s.staff_id})'
                     + (f' · {s.designation}' if s.designation else ''),
                     'url': url_for('hr.staff_detail', staff_id=s.id)} for s in rows])


@hr_bp.route('/staff/export')
@login_required
def export_staff():
    import csv, io
    from utils.audit import log_action
    log_action('data.export_staff', detail='staff directory (incl. salary/bank fields)')
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['Staff ID', 'Name', 'Gender', 'Department', 'Designation', 'Type',
                'Employment', 'Status', 'Phone', 'Email', 'Date Employed', 'Salary'])
    from utils.branch_scope import scope_query
    from utils.web_exports import formula_guard as _fg
    for s in scope_query(StaffMember.query.filter_by(is_active=True), StaffMember).order_by(StaffMember.surname).all():
        w.writerow([_fg(s.staff_id), _fg(s.full_name), s.gender or '',
                    _fg(s.department.name if s.department else ''), _fg(s.designation or ''),
                    s.staff_type, s.employment_type, s.status, _fg(s.phone or ''),
                    _fg(s.email or ''), s.date_employed or '', s.salary or 0])
    return csv_response(out.getvalue(), 'staff_directory.csv')


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
        'leave_types': hr.LEAVE_TYPES, 'today': date.today().isoformat(),
        'staff': [{'id': s.id, 'full_name': s.full_name} for s in staff],
        'leaves': [{'id': lv.id, 'staff_name': lv.staff.full_name, 'staff_id': lv.staff_id,
                    'leave_type': lv.leave_type, 'days': lv.days, 'status': lv.status,
                    'start': lv.start_date.isoformat(), 'end': lv.end_date.isoformat(),
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
        # Tell the staff member (if they have a login) that their request moved.
        if new_status in ('Approved', 'Rejected') and lv.staff and lv.staff.user_id:
            try:
                from utils.notify import notify
                span = f"{lv.start_date.strftime('%d %b')}–{lv.end_date.strftime('%d %b %Y')}"
                notify(f'Leave {new_status.lower()}',
                       body=f'Your {lv.leave_type or "leave"} request ({span}) was {new_status.lower()}.',
                       url=url_for('hr.staff_detail', staff_id=lv.staff_id),
                       user_id=lv.staff.user_id,
                       category='success' if new_status == 'Approved' else 'warning')
            except Exception:
                pass
        from utils.audit import log_action
        log_action('hr.leave_status', detail=new_status, target=lv.staff)
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
    from utils.branch_scope import scope_query, is_central
    # Branch admins see only their branch's runs; central admins see all (or the
    # branch they've picked). Legacy NULL-branch runs surface only to central.
    q = scope_query(PayrollRun.query, PayrollRun)
    if not is_central():
        q = q.filter(PayrollRun.branch_id.isnot(None))
    runs = q.order_by(PayrollRun.year.desc(), PayrollRun.month.desc()).all()
    today = date.today()
    show_branch = is_central()
    return _render({
        'page': 'payroll', 'nav': _nav_urls(), 'is_admin': _is_admin(),
        'rows': [{'id': r.id,
                  'period_label': (f'{r.period_label} · {r.branch.name}'
                                   if show_branch and r.branch else r.period_label),
                  'status': r.status,
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
    # Which branch's payroll this is: a branch admin is forced to their own
    # branch; a central admin gets the branch they're viewing (or may pass one).
    from utils.branch_scope import branch_for_new
    branch_id = branch_for_new(request.form.get('branch_id', type=int))
    if not branch_id:
        return _err('No branch is configured to run payroll for.',
                    url_for('hr.payroll_list'))
    run = PayrollRun.query.filter_by(year=year, month=month, branch_id=branch_id).first()
    if not run:
        run = PayrollRun(year=year, month=month, branch_id=branch_id)
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
    _require_payroll_run_access(run)
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
                'branch_name': run.branch.name if run.branch else None,
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
    _require_payroll_run_access(ps.run)   # no cross-branch pay edits
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
    _require_payroll_run_access(run)
    run.status = 'Finalized'
    # Book staff-loan salary deductions for this run (idempotent per loan+run).
    try:
        from utils.staff_loans import post_run_repayments
        post_run_repayments(run)
    except Exception:
        db.session.rollback()
    # Post the salary run to Finance as a single expense (once).
    if request.form.get('post_expense') and not run.posted_expense_id:
        try:
            from models import Expense, ExpenseCategory
            cat = ExpenseCategory.query.filter(
                ExpenseCategory.name.ilike('%salar%')).first()
            if not cat:
                # Give payroll its own ledger line rather than the generic
                # "Expenses" fallback the first time a run is posted.
                cat = ExpenseCategory(name='Salaries', is_active=True)
                db.session.add(cat)
                db.session.flush()
            term = get_active_term()
            from utils.branch_scope import branch_for_new
            exp = Expense(
                term_id=term.id if term else None,
                category_id=cat.id if cat else None,
                branch_id=run.branch_id or branch_for_new(),
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
    _require_payroll_run_access(run)
    run.status = 'Paid'
    db.session.commit()
    return _ok('Payroll marked as paid.', url_for('hr.payroll_detail', run_id=run_id))


@hr_bp.route('/payroll/<int:run_id>/delete', methods=['POST'])
@admin_required
def delete_payroll(run_id):
    run = db.get_or_404(PayrollRun, run_id)
    _require_payroll_run_access(run)
    db.session.delete(run)
    db.session.commit()
    return _ok('Payroll run deleted.', url_for('hr.payroll_list'))


@hr_bp.route('/payroll/<int:run_id>/payslip/<int:slip_id>/print')
@login_required
def print_payslip(run_id, slip_id):
    ps = db.get_or_404(Payslip, slip_id)
    if ps.run_id != run_id:
        return ('', 404)
    _require_payroll_run_access(ps.run)   # no cross-branch salary disclosure
    from models import SchoolSettings
    school = {'name': SchoolSettings.get('school_name', 'My School'),
              'address': SchoolSettings.get('school_address', ''),
              'phone': SchoolSettings.get('school_phone', '')}
    return render_template('hr/payslip_print.html', ps=ps, run=ps.run, school=school)


@hr_bp.route('/payroll/<int:run_id>/sync-deductions', methods=['POST'])
@admin_required
def sync_deductions(run_id):
    run = db.get_or_404(PayrollRun, run_id)
    _require_payroll_run_access(run)
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
        'qr_url': url_for('hr.checkin_qr'), 'checkin_url': url_for('hr.checkin'),
    })


def _current_staff():
    """The StaffMember linked to the logged-in user (or None)."""
    from utils.access_control import get_current_user
    u = get_current_user()
    if not u:
        return None
    return StaffMember.query.filter_by(user_id=u.id, is_active=True).first()


def _today_att_dict(staff_id):
    a = StaffAttendance.query.filter_by(staff_id=staff_id, date=date.today()).first()
    if not a:
        return None
    return {'status': a.status, 'clock_in': a.clock_in or '', 'note': a.note or '',
            'minutes_late': a.minutes_late or 0, 'deduction': a.deduction or 0}


@hr_bp.route('/checkin')
@login_required
def checkin():
    """Self-service check-in screen for the logged-in staff member. A ?c= code
    (from the QR) is validated client-side by posting to checkin_self."""
    staff = _current_staff()
    s = hr.get_settings()
    return _render({
        'page': 'checkin', 'nav': _nav_urls(),
        'staff': ({'id': staff.id, 'name': staff.full_name, 'staff_id': staff.staff_id}
                  if staff else None),
        'today_label': date.today().strftime('%A, %d %b %Y'),
        'today': _today_att_dict(staff.id) if staff else None,
        'geo': {'enabled': bool(s['geo_enabled']), 'radius': s['geo_radius']},
        'prefill_code': request.args.get('c') or '',
        'settings': {'late_time': s['late_time']},
        'urls': {'self': url_for('hr.checkin_self'), 'qr': url_for('hr.checkin_qr')},
    })


@hr_bp.route('/checkin/self', methods=['POST'])
@login_required
def checkin_self():
    """Record the logged-in staff member's attendance via QR code or GPS."""
    staff = _current_staff()
    if not staff:
        return _err('Your login is not linked to a staff record. Ask an administrator.',
                    url_for('hr.checkin'))
    from utils.branch_scope import require_branch_access
    require_branch_access(staff.branch_id)
    method = request.form.get('method') or 'qr'
    if method == 'qr':
        if not hr.verify_day_code(request.form.get('code')):
            return _err('That QR code is invalid or has expired. Scan today\'s code.',
                        url_for('hr.checkin'))
    elif method == 'gps':
        lat = request.form.get('lat', type=float)
        lng = request.form.get('lng', type=float)
        inside = hr.within_geofence(lat, lng)
        if inside is None:
            return _err('GPS check-in is not configured. Ask an administrator to set the campus location.',
                        url_for('hr.checkin'))
        if not inside:
            return _err('You appear to be outside the school premises.', url_for('hr.checkin'))
    else:
        return _err('Unknown check-in method.', url_for('hr.checkin'))
    rec, status = hr.mark_attendance_now(staff.id, method=method)
    db.session.commit()
    from utils.audit import log_action
    log_action('hr.checkin', detail=f'{method} · {status}', target=staff)
    msg = f'Checked in at {rec.clock_in} — marked {status}.'
    if status == 'Late' and rec.deduction:
        msg += f' ({rec.minutes_late} min late)'
    return _ok(msg, url_for('hr.checkin'))


@hr_bp.route('/clock', methods=['POST'])
@login_required
def clock():
    """One-tap self clock-in for staff granted the 'hr.self_attendance'
    capability at edit level. Records the caller's OWN attendance for today with
    the current time — never anyone else's. Read-only holders (view level) and
    users without the capability are refused; the button isn't shown to them.
    Distinct from the QR/GPS checkin flow: no code needed, just the server clock."""
    from utils.access_control import self_scope_level
    staff = _current_staff()
    if not staff:
        return _err('Your login is not linked to a staff record. Ask an administrator.',
                    url_for('auth.profile'))
    if self_scope_level('hr.self_attendance') != 'edit':
        # View-only self-attendance (or none): may see their record, not mark it.
        if _wants_json():
            abort(403)
        return _err('You can view your attendance but not clock in. Ask an administrator.',
                    url_for('auth.profile'))
    require_branch_access(staff.branch_id)
    rec, status = hr.mark_attendance_now(staff.id, method='self')
    db.session.commit()
    log_action('hr.clock', detail=f'self · {status}', target=staff)
    msg = f'Clocked in at {rec.clock_in} — marked {status}.'
    if status == 'Late' and rec.minutes_late:
        msg += f' ({rec.minutes_late} min late)'
    return _ok(msg, url_for('auth.profile'))


@hr_bp.route('/attendance/qr')
@admin_required
def checkin_qr():
    """Admin display of today's rotating QR code for staff to scan and check in."""
    from flask import request as _rq
    code = hr.day_code()
    checkin_url = url_for('hr.checkin', c=code, _external=True)
    return _render({
        'page': 'checkin_qr', 'nav': _nav_urls(),
        'qr': hr.qr_svg_data_uri(checkin_url), 'url': checkin_url,
        'today_label': date.today().strftime('%A, %d %b %Y'),
        'urls': {'attendance': url_for('hr.attendance')},
    })


@hr_bp.route('/api/attendance/punch', methods=['POST'])
def device_punch():
    """Biometric / access-control device endpoint. Authenticated by a shared token
    (HR settings), not a user session. Accepts JSON or form:
    {token, staff_id | staff_code, time?(ISO)}. Records attendance for the day."""
    from models import SchoolSettings
    token = SchoolSettings.get('hr_device_token', None)
    data = request.get_json(silent=True) or request.form
    if not token or (data.get('token') or '') != token:
        return jsonify({'ok': False, 'error': 'Unauthorised device.'}), 401
    staff = None
    if data.get('staff_id'):
        staff = db.session.get(StaffMember, _int(data.get('staff_id')))
    if not staff and data.get('staff_code'):
        staff = StaffMember.query.filter_by(staff_id=str(data.get('staff_code')).strip()).first()
    if not staff or not staff.is_active:
        return jsonify({'ok': False, 'error': 'Staff not found.'}), 404
    when = None
    if data.get('time'):
        try:
            when = datetime.fromisoformat(str(data.get('time')))
        except (ValueError, TypeError):
            when = None
    rec, status = hr.mark_attendance_now(staff.id, method='device', when=when)
    db.session.commit()
    return jsonify({'ok': True, 'staff': staff.full_name, 'status': status, 'clock_in': rec.clock_in})


@hr_bp.route('/settings/device-token', methods=['POST'])
@admin_required
def regenerate_device_token():
    import secrets
    from models import SchoolSettings
    if request.form.get('action') == 'clear':
        SchoolSettings.set('hr_device_token', '', 'string', 'Biometric device API token')
        db.session.commit()
        return _ok('Device token cleared. Devices can no longer post attendance.',
                   url_for('hr.settings'))
    token = secrets.token_urlsafe(24)
    SchoolSettings.set('hr_device_token', token, 'string', 'Biometric device API token')
    db.session.commit()
    if _wants_json():
        return jsonify({'ok': True, 'token': token,
                        'punch_url': url_for('hr.device_punch', _external=True)})
    return _ok('New device token generated.', url_for('hr.settings'))


def _int(v):
    try:
        return int(v)
    except (ValueError, TypeError):
        return 0


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
# REPORTS
# ============================================================================

def _report_filters():
    return {
        'department_id': request.args.get('department_id', type=int),
        'staff_type': request.args.get('staff_type') or None,
        'status': request.args.get('status') or None,
        'from': _d(request.args.get('from')),
        'to': _d(request.args.get('to')),
    }


@hr_bp.route('/reports')
@login_required
def reports():
    from utils import hr_reports as R
    rtype = request.args.get('type') or 'directory'
    data = R.build(rtype, _report_filters())
    depts = Department.query.filter_by(is_active=True).order_by(Department.name).all()
    return _render({
        'page': 'reports', 'nav': _nav_urls(), 'report': data,
        'report_types': [{'key': k, 'label': v} for k, v in R.REPORTS],
        'departments': [{'id': d.id, 'name': d.name} for d in depts],
        'statuses': hr.STATUSES, 'staff_types': hr.STAFF_TYPES,
        'sel': {'type': data['type'], 'department_id': request.args.get('department_id', ''),
                'staff_type': request.args.get('staff_type', ''), 'status': request.args.get('status', ''),
                'from': request.args.get('from', ''), 'to': request.args.get('to', '')},
        'urls': {'self': url_for('hr.reports'), 'export': url_for('hr.reports_export')},
    })


@hr_bp.route('/reports/export')
@login_required
def reports_export():
    import csv, io
    from utils import hr_reports as R
    rtype = request.args.get('type') or 'directory'
    data = R.build(rtype, _report_filters())
    headers = [c['label'] for c in data['columns']]
    keys = [c['key'] for c in data['columns']]
    fname = f'hr_{data["type"]}'
    from utils.audit import log_action
    log_action('hr.report_export', detail=data['type'])
    if request.args.get('format') == 'xlsx':
        from openpyxl import Workbook
        from utils.web_exports import xlsx_response
        wb = Workbook(); ws = wb.active; ws.title = data['title'][:31]
        ws.append(headers)
        for r in data['rows']:
            ws.append([r.get(k, '') for k in keys])
        ws.append([])
        for sm in data['summary']:
            ws.append([sm['label'], sm['value']])
        return xlsx_response(wb, f'{fname}.xlsx')
    out = io.StringIO(); w = csv.writer(out)
    from utils.web_exports import formula_guard as _fg
    w.writerow(headers)
    for r in data['rows']:
        w.writerow([_fg(r.get(k, '')) for k in keys])
    w.writerow([])
    for sm in data['summary']:
        w.writerow([sm['label'], sm['value']])
    return csv_response(out.getvalue(), f'{fname}.csv')


# ============================================================================
# BULK IMPORT + BULK NOTIFY
# ============================================================================

_IMPORT_ALIASES = {
    'first name': 'first_name', 'firstname': 'first_name', 'first_name': 'first_name',
    'surname': 'surname', 'last name': 'surname', 'lastname': 'surname',
    'middle name': 'middle_name', 'middle_name': 'middle_name',
    'gender': 'gender', 'phone': 'phone', 'email': 'email',
    'department': 'department', 'designation': 'designation', 'title': 'designation',
    'staff type': 'staff_type', 'staff_type': 'staff_type', 'type': 'staff_type',
    'employment': 'employment_type', 'employment type': 'employment_type',
    'employment_type': 'employment_type',
    'qualification': 'qualification', 'salary': 'salary',
    'date employed': 'date_employed', 'date_employed': 'date_employed', 'employed': 'date_employed',
}


@hr_bp.route('/staff/import', methods=['POST'])
@admin_required
def import_staff():
    """Bulk-create staff from a CSV. Header row maps common column names; first
    name + surname required. Departments are matched (case-insensitive) or created."""
    import csv, io
    f = request.files.get('file')
    if not f or not f.filename:
        return _err('Choose a CSV file to import.', url_for('hr.staff_list'))
    try:
        text = f.read().decode('utf-8-sig', errors='replace')
    except Exception:
        return _err('Could not read that file.', url_for('hr.staff_list'))
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return _err('The CSV has no header row.', url_for('hr.staff_list'))
    colmap = {}
    for col in reader.fieldnames:
        key = _IMPORT_ALIASES.get((col or '').strip().lower())
        if key:
            colmap[col] = key
    have = set(colmap.values())
    if 'first_name' not in have or 'surname' not in have:
        return _err('The CSV needs at least "First name" and "Surname" columns.',
                    url_for('hr.staff_list'))
    from utils.branch_scope import branch_for_new
    branch_id = branch_for_new()
    # cache departments for case-insensitive match / create
    dept_by_name = {d.name.lower(): d for d in Department.query.all()}
    created = skipped = 0
    for row in reader:
        vals = {key: (row.get(col) or '').strip() for col, key in colmap.items()}
        if not (vals.get('first_name') and vals.get('surname')):
            skipped += 1
            continue
        s = StaffMember(staff_id=StaffMember.generate_staff_id(), branch_id=branch_id,
                        first_name=vals['first_name'][:60], surname=vals['surname'][:60],
                        middle_name=vals.get('middle_name') or None,
                        gender=vals.get('gender') or None, phone=vals.get('phone') or None,
                        email=vals.get('email') or None, designation=vals.get('designation') or None,
                        staff_type=vals.get('staff_type') or 'Teaching',
                        employment_type=vals.get('employment_type') or 'Full-time',
                        qualification=vals.get('qualification') or None,
                        date_employed=_d(vals.get('date_employed')))
        try:
            s.salary = float(vals.get('salary') or 0)
        except (ValueError, TypeError):
            s.salary = 0
        dname = (vals.get('department') or '').strip()
        if dname:
            dep = dept_by_name.get(dname.lower())
            if not dep:
                dep = Department(name=dname)
                db.session.add(dep)
                db.session.flush()
                dept_by_name[dname.lower()] = dep
            s.department_id = dep.id
        db.session.add(s)
        # flush so generate_staff_id increments correctly across rows
        db.session.flush()
        created += 1
    db.session.commit()
    from utils.audit import log_action
    log_action('hr.staff_import', detail=f'{created} staff')
    return _ok(f'Imported {created} staff.' + (f' {skipped} row(s) skipped.' if skipped else ''),
               url_for('hr.staff_list'))


@hr_bp.route('/staff/notify', methods=['POST'])
@login_required
def notify_staff():
    """Draft a Communication campaign (SMS or email) to the staff matching the
    current directory filters. Never auto-sends — a human reviews the draft."""
    from utils.branch_scope import scope_query
    channel = 'Email' if request.form.get('channel') == 'Email' else 'SMS'
    query = scope_query(StaffMember.query.filter_by(is_active=True), StaffMember)
    if request.form.get('department_id', type=int):
        query = query.filter_by(department_id=request.form.get('department_id', type=int))
    if request.form.get('staff_type'):
        query = query.filter_by(staff_type=request.form.get('staff_type'))
    if request.form.get('status'):
        query = query.filter_by(status=request.form.get('status'))
    staff_ids = [s.id for s in query.all()]
    if not staff_ids:
        return _err('No staff match the current filter.', url_for('hr.staff_list'))
    body = (request.form.get('body') or '').strip()
    if not body:
        return _err('Enter a message to send.', url_for('hr.staff_list'))
    from utils import comms
    from utils.helpers import get_active_term
    msg = comms.build_campaign(
        body, channel=channel, term=get_active_term(),
        title=(request.form.get('title') or 'Staff notice').strip(),
        spec={'to': 'staff', 'audience': 'staff', 'staff_ids': staff_ids},
        created_by=_current_user())
    if not msg:
        return _err(f'None of those staff have {"an email" if channel == "Email" else "a phone number"} on file.',
                    url_for('hr.staff_list'))
    return _ok(f'Drafted a {channel} to {msg.recipient_count} staff — review and send.',
               url_for('comms.message_detail', message_id=msg.id))


# ============================================================================
# RECRUITMENT / ATS
# ============================================================================

from models import JobVacancy as JobVacancy_, JobApplication as JobApplication_, Interview as Interview_


def _vacancy_row(v, dept_map):
    counts = dict(db.session.query(JobApplication_.status, func.count(JobApplication_.id))
                  .filter(JobApplication_.vacancy_id == v.id)
                  .group_by(JobApplication_.status).all())
    return {'id': v.id, 'title': v.title, 'department': dept_map.get(v.department_id, ''),
            'staff_type': v.staff_type, 'employment_type': v.employment_type,
            'positions': v.positions or 1, 'status': v.status,
            'applicants': sum(counts.values()), 'hired': counts.get('Hired', 0),
            'shortlisted': counts.get('Shortlisted', 0) + counts.get('Interview', 0),
            'closing': v.closing_date.strftime('%d %b %Y') if v.closing_date else '',
            'url': url_for('hr.vacancy_detail', vac_id=v.id)}


@hr_bp.route('/recruitment')
@login_required
def recruitment():
    from utils.branch_scope import scope_query
    status = request.args.get('status') or ''
    q = scope_query(JobVacancy_.query, JobVacancy_)
    if status:
        q = q.filter(JobVacancy_.status == status)
    vacs = q.order_by(JobVacancy_.created_at.desc()).all()
    dept_map = {d.id: d.name for d in Department.query.all()}
    depts = Department.query.filter_by(is_active=True).order_by(Department.name).all()
    return _render({
        'page': 'recruitment', 'nav': _nav_urls(), 'is_admin': _is_admin(),
        'status': status, 'statuses': JobVacancy_.STATUSES,
        'vacancies': [_vacancy_row(v, dept_map) for v in vacs],
        'departments': [{'id': d.id, 'name': d.name} for d in depts],
        'staff_types': hr.STAFF_TYPES, 'employment_types': hr.EMPLOYMENT_TYPES,
        'self_url': url_for('hr.recruitment'), 'add_url': url_for('hr.vacancy_add'),
    })


def _read_vacancy(v):
    v.title = (request.form.get('title') or '').strip()
    v.department_id = request.form.get('department_id', type=int) or None
    v.staff_type = request.form.get('staff_type') or 'Teaching'
    v.employment_type = request.form.get('employment_type') or 'Full-time'
    v.positions = request.form.get('positions', type=int) or 1
    v.description = (request.form.get('description') or '').strip() or None
    v.requirements = (request.form.get('requirements') or '').strip() or None
    v.closing_date = _d(request.form.get('closing_date'))
    if request.form.get('status') in JobVacancy_.STATUSES:
        v.status = request.form.get('status')


@hr_bp.route('/recruitment/add', methods=['POST'])
@admin_required
def vacancy_add():
    if not (request.form.get('title') or '').strip():
        return _err('Enter a job title.', url_for('hr.recruitment'))
    v = JobVacancy_(status='Open', created_by=_current_user())
    _read_vacancy(v)
    from utils.branch_scope import branch_for_new
    v.branch_id = branch_for_new(request.form.get('branch_id', type=int))
    db.session.add(v)
    db.session.commit()
    from utils.audit import log_action
    log_action('hr.vacancy_add', detail=v.title, target=v)
    return _ok(f'Vacancy "{v.title}" posted.', url_for('hr.vacancy_detail', vac_id=v.id))


def _application_row(a):
    return {'id': a.id, 'name': a.full_name, 'email': a.email or '', 'phone': a.phone or '',
            'qualification': a.qualification or '', 'experience_years': a.experience_years,
            'status': a.status, 'rating': a.rating, 'cover_note': a.cover_note or '',
            'applied': a.applied_date.strftime('%d %b %Y') if a.applied_date else '',
            'hired_staff_id': a.hired_staff_id,
            'resume_url': (url_for('comms.download_attachment', att_id=a.resume_id)
                           if a.resume_id else None),
            'staff_url': (url_for('hr.staff_detail', staff_id=a.hired_staff_id)
                          if a.hired_staff_id else None),
            'interviews': [{'id': i.id,
                            'when': i.scheduled_at.strftime('%d %b %Y %H:%M') if i.scheduled_at else '',
                            'mode': i.mode, 'location': i.location or '', 'interviewer': i.interviewer or '',
                            'outcome': i.outcome, 'notes': i.notes or '',
                            'outcome_url': url_for('hr.interview_outcome', intv_id=i.id)}
                           for i in a.interviews.order_by(Interview_.scheduled_at).all()],
            'status_url': url_for('hr.application_status', app_id=a.id),
            'interview_url': url_for('hr.interview_schedule', app_id=a.id),
            'hire_url': url_for('hr.hire_applicant', app_id=a.id),
            'delete_url': url_for('hr.application_delete', app_id=a.id)}


@hr_bp.route('/recruitment/<int:vac_id>')
@login_required
def vacancy_detail(vac_id):
    v = db.get_or_404(JobVacancy_, vac_id)
    require_branch_access(v.branch_id)
    apps = v.applications.order_by(JobApplication_.created_at.desc()).all()
    dept_map = {d.id: d.name for d in Department.query.all()}
    depts = Department.query.filter_by(is_active=True).order_by(Department.name).all()
    return _render({
        'page': 'vacancy', 'nav': _nav_urls(), 'is_admin': _is_admin(),
        'vacancy': {'id': v.id, 'title': v.title, 'department': dept_map.get(v.department_id, ''),
                    'department_id': v.department_id or '', 'staff_type': v.staff_type,
                    'employment_type': v.employment_type, 'positions': v.positions or 1,
                    'description': v.description or '', 'requirements': v.requirements or '',
                    'status': v.status, 'posted': v.posted_date.strftime('%d %b %Y') if v.posted_date else '',
                    'closing_date': v.closing_date.isoformat() if v.closing_date else '',
                    'hired': sum(1 for a in apps if a.status == 'Hired')},
        'applications': [_application_row(a) for a in apps],
        'app_statuses': JobApplication_.STATUSES, 'interview_modes': Interview_.MODES,
        'interview_outcomes': Interview_.OUTCOMES,
        'departments': [{'id': d.id, 'name': d.name} for d in depts],
        'staff_types': hr.STAFF_TYPES, 'employment_types': hr.EMPLOYMENT_TYPES, 'statuses': JobVacancy_.STATUSES,
        'urls': {'edit': url_for('hr.vacancy_edit', vac_id=v.id),
                 'delete': url_for('hr.vacancy_delete', vac_id=v.id),
                 'add_application': url_for('hr.application_add', vac_id=v.id),
                 'back': url_for('hr.recruitment')},
    })


@hr_bp.route('/recruitment/<int:vac_id>/edit', methods=['POST'])
@admin_required
def vacancy_edit(vac_id):
    v = db.get_or_404(JobVacancy_, vac_id)
    require_branch_access(v.branch_id)
    _read_vacancy(v)
    db.session.commit()
    return _ok('Vacancy updated.', url_for('hr.vacancy_detail', vac_id=v.id))


@hr_bp.route('/recruitment/<int:vac_id>/delete', methods=['POST'])
@admin_required
def vacancy_delete(vac_id):
    v = db.get_or_404(JobVacancy_, vac_id)
    require_branch_access(v.branch_id)
    db.session.delete(v)
    db.session.commit()
    return _ok('Vacancy removed.', url_for('hr.recruitment'))


@hr_bp.route('/recruitment/<int:vac_id>/applications/add', methods=['POST'])
@login_required
def application_add(vac_id):
    v = db.get_or_404(JobVacancy_, vac_id)
    require_branch_access(v.branch_id)
    if not (request.form.get('first_name') and request.form.get('surname')):
        return _err('Enter the candidate\'s first name and surname.',
                    url_for('hr.vacancy_detail', vac_id=vac_id))
    resume_id = None
    if request.files.get('file') and request.files['file'].filename:
        from utils import comm_attachments as CA
        try:
            resume_id = CA.save(request.files['file'], created_by=_current_user()).id
        except ValueError as e:
            return _err(str(e), url_for('hr.vacancy_detail', vac_id=vac_id))
    a = JobApplication_(
        vacancy_id=v.id, first_name=(request.form.get('first_name') or '').strip(),
        surname=(request.form.get('surname') or '').strip(),
        email=(request.form.get('email') or '').strip() or None,
        phone=(request.form.get('phone') or '').strip() or None,
        gender=request.form.get('gender') or None,
        qualification=(request.form.get('qualification') or '').strip() or None,
        experience_years=request.form.get('experience_years', type=int),
        cover_note=(request.form.get('cover_note') or '').strip() or None,
        resume_id=resume_id, status='Applied')
    db.session.add(a)
    db.session.commit()
    return _ok(f'Application from {a.full_name} recorded.', url_for('hr.vacancy_detail', vac_id=vac_id))


@hr_bp.route('/applications/<int:app_id>/status', methods=['POST'])
@login_required
def application_status(app_id):
    a = db.get_or_404(JobApplication_, app_id)
    require_branch_access(a.vacancy.branch_id)
    new = request.form.get('status')
    if new not in JobApplication_.STATUSES:
        return _err('Invalid status.', url_for('hr.vacancy_detail', vac_id=a.vacancy_id))
    a.status = new
    if request.form.get('rating', type=int):
        a.rating = request.form.get('rating', type=int)
    db.session.commit()
    return _ok(f'Moved {a.full_name} to {new}.', url_for('hr.vacancy_detail', vac_id=a.vacancy_id))


@hr_bp.route('/applications/<int:app_id>/delete', methods=['POST'])
@admin_required
def application_delete(app_id):
    a = db.get_or_404(JobApplication_, app_id)
    require_branch_access(a.vacancy.branch_id)
    vid = a.vacancy_id
    db.session.delete(a)
    db.session.commit()
    return _ok('Application removed.', url_for('hr.vacancy_detail', vac_id=vid))


@hr_bp.route('/applications/<int:app_id>/interview', methods=['POST'])
@login_required
def interview_schedule(app_id):
    a = db.get_or_404(JobApplication_, app_id)
    require_branch_access(a.vacancy.branch_id)
    when = None
    raw = request.form.get('scheduled_at')
    if raw:
        for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M'):
            try:
                when = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
    db.session.add(Interview_(
        application_id=a.id, scheduled_at=when,
        mode=request.form.get('mode') or 'In-person',
        location=(request.form.get('location') or '').strip() or None,
        interviewer=(request.form.get('interviewer') or _current_user()).strip() or None,
        notes=(request.form.get('notes') or '').strip() or None,
        outcome='Pending', created_by=_current_user()))
    # Advance the pipeline to the Interview stage.
    if a.status in ('Applied', 'Shortlisted'):
        a.status = 'Interview'
    db.session.commit()
    return _ok('Interview scheduled.', url_for('hr.vacancy_detail', vac_id=a.vacancy_id))


@hr_bp.route('/interviews/<int:intv_id>/outcome', methods=['POST'])
@login_required
def interview_outcome(intv_id):
    i = db.get_or_404(Interview_, intv_id)
    require_branch_access(i.application.vacancy.branch_id)
    outcome = request.form.get('outcome')
    if outcome not in Interview_.OUTCOMES:
        return _err('Invalid outcome.', url_for('hr.vacancy_detail', vac_id=i.application.vacancy_id))
    i.outcome = outcome
    if request.form.get('notes'):
        i.notes = (request.form.get('notes') or '').strip() or i.notes
    db.session.commit()
    return _ok(f'Interview marked {outcome}.', url_for('hr.vacancy_detail', vac_id=i.application.vacancy_id))


@hr_bp.route('/applications/<int:app_id>/hire', methods=['POST'])
@admin_required
def hire_applicant(app_id):
    """Convert a candidate into a StaffMember (the HR record of truth) and close
    out the pipeline. Idempotent — a candidate already hired isn't re-created."""
    a = db.get_or_404(JobApplication_, app_id)
    v = a.vacancy
    require_branch_access(v.branch_id)
    if a.hired_staff_id:
        return _err('This candidate has already been hired.',
                    url_for('hr.vacancy_detail', vac_id=v.id))
    s = StaffMember(staff_id=StaffMember.generate_staff_id(), branch_id=v.branch_id,
                    first_name=a.first_name, surname=a.surname, gender=a.gender,
                    phone=a.phone, email=a.email, qualification=a.qualification,
                    prior_experience_years=a.experience_years,
                    department_id=v.department_id, staff_type=v.staff_type,
                    employment_type=v.employment_type, designation=v.title,
                    date_employed=date.today(), status='Active')
    db.session.add(s)
    db.session.flush()
    a.status = 'Hired'
    a.hired_staff_id = s.id
    hr.record_event(s, 'employment', 'Hired', detail=f'Recruited for "{v.title}"',
                    effective_date=date.today(), created_by=_current_user())
    # Mark the vacancy Filled once every opening is taken.
    hired = v.applications.filter_by(status='Hired').count()
    if hired >= (v.positions or 1):
        v.status = 'Filled'
    db.session.commit()
    from utils.audit import log_action
    log_action('hr.hire', detail=f'{s.full_name} <- {v.title}', target=s)
    return _ok(f'{s.full_name} hired and added to staff ({s.staff_id}).',
               url_for('hr.staff_detail', staff_id=s.id))


# ============================================================================
# HR SETTINGS
# ============================================================================

@hr_bp.route('/settings')
@login_required
def settings():
    from models import PayrollDeductionType
    deductions = PayrollDeductionType.query.order_by(PayrollDeductionType.name).all()
    from models import SchoolSettings as _SS
    return _render({
        'page': 'settings', 'nav': _nav_urls(), 'is_admin': _is_admin(),
        'settings': hr.get_settings(),
        'device_token': (_SS.get('hr_device_token', '') or '') if _is_admin() else '',
        'punch_url': url_for('hr.device_punch', _external=True),
        'device_token_url': url_for('hr.regenerate_device_token'),
        'leave_types': hr.LEAVE_TYPES, 'leave_allowances': hr.leave_allowances(),
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
    hr.save_leave_allowances(request.form)
    db.session.commit()
    return _ok('HR settings saved.', url_for('hr.settings'))


# ============================================================================
# STAFF LOANS
# ============================================================================
def _loan_staff():
    from utils.branch_scope import scope_query
    return scope_query(StaffMember.query.filter_by(is_active=True), StaffMember).order_by(
        StaffMember.surname, StaffMember.first_name).all()


@hr_bp.route('/loans')
@login_required
@admin_required
def loans_list():
    from utils.branch_scope import scope_query
    from utils import staff_loans
    loans = scope_query(StaffLoan.query, StaffLoan).order_by(StaffLoan.created_at.desc()).all()
    return render_template('hr/loans.html', loans=loans, cfg=staff_loans.settings())


@hr_bp.route('/loans/settings', methods=['POST'])
@login_required
@admin_required
def loans_settings():
    from utils import staff_loans
    staff_loans.save_settings(
        enabled=(request.form.get('enabled') == 'on'),
        method=request.form.get('method'),
        rate=request.form.get('rate'),
        guarantors_required=request.form.get('guarantors_required'))
    log_action('hr.loan_settings')
    return _ok('Loan settings saved.', url_for('hr.loans_list'))


@hr_bp.route('/loans/new', methods=['GET', 'POST'])
@login_required
@admin_required
def loan_new():
    from utils import staff_loans
    from utils.branch_scope import branch_for_new, require_branch_access
    cfg = staff_loans.settings()
    staff = _loan_staff()
    if request.method == 'POST':
        staff_id = request.form.get('staff_id', type=int)
        st = db.session.get(StaffMember, staff_id) if staff_id else None
        if not st:
            flash('Choose the staff member taking the loan.', 'error')
            return render_template('hr/loan_new.html', staff=staff, cfg=cfg)
        require_branch_access(st.branch_id)
        loan, err = staff_loans.create_loan(
            staff_id=st.id, branch_id=st.branch_id or branch_for_new(),
            principal=request.form.get('principal'),
            guarantor_ids=request.form.getlist('guarantor_ids'),
            desired_monthly=request.form.get('monthly_amount'),
            purpose=request.form.get('purpose'), created_by=_current_user())
        if err:
            flash(err, 'error')
            return render_template('hr/loan_new.html', staff=staff, cfg=cfg)
        log_action('hr.loan_create', target=loan)
        flash('Loan created — awaiting guarantor approval before disbursement.', 'success')
        return redirect(url_for('hr.loan_detail', loan_id=loan.id))
    return render_template('hr/loan_new.html', staff=staff, cfg=cfg)


@hr_bp.route('/loans/<int:loan_id>')
@login_required
@admin_required
def loan_detail(loan_id):
    from utils.branch_scope import require_branch_access
    loan = db.get_or_404(StaffLoan, loan_id)
    require_branch_access(loan.branch_id)
    return render_template('hr/loan_detail.html', loan=loan)


@hr_bp.route('/loans/<int:loan_id>/guarantor/<int:staff_id>/act', methods=['POST'])
@login_required
@admin_required
def loan_guarantor_act(loan_id, staff_id):
    from utils import staff_loans
    from utils.branch_scope import require_branch_access
    loan = db.get_or_404(StaffLoan, loan_id)
    require_branch_access(loan.branch_id)
    err = staff_loans.act_on_guarantor(
        loan, staff_id, approve=(request.form.get('action') == 'approve'), by=_current_user())
    log_action('hr.loan_guarantor', detail=request.form.get('action'), target=loan)
    flash(err or 'Guarantor decision recorded.', 'error' if err else 'success')
    return redirect(url_for('hr.loan_detail', loan_id=loan.id))


@hr_bp.route('/loans/<int:loan_id>/repay', methods=['POST'])
@login_required
@admin_required
def loan_repay(loan_id):
    from utils import staff_loans
    from utils.branch_scope import require_branch_access
    loan = db.get_or_404(StaffLoan, loan_id)
    require_branch_access(loan.branch_id)
    if loan.status not in ('active',):
        flash('Only an active (disbursed) loan can take repayments.', 'error')
        return redirect(url_for('hr.loan_detail', loan_id=loan.id))
    applied = staff_loans.record_repayment(
        loan, request.form.get('amount', type=float) or 0, source='manual',
        note=(request.form.get('note') or 'Manual repayment'))
    db.session.commit()
    log_action('hr.loan_repay', detail=str(applied), target=loan)
    flash(f'Recorded a repayment of {applied:,.2f}.' if applied else 'Nothing to repay.',
          'success' if applied else 'warning')
    return redirect(url_for('hr.loan_detail', loan_id=loan.id))


@hr_bp.route('/loans/<int:loan_id>/cancel', methods=['POST'])
@login_required
@admin_required
def loan_cancel(loan_id):
    from utils.branch_scope import require_branch_access
    loan = db.get_or_404(StaffLoan, loan_id)
    require_branch_access(loan.branch_id)
    if loan.status in ('pending', 'active') and not loan.amount_repaid:
        loan.status = 'cancelled'
        db.session.commit()
        log_action('hr.loan_cancel', target=loan)
        flash('Loan cancelled.', 'success')
    else:
        flash('This loan cannot be cancelled (it has repayments or is closed).', 'error')
    return redirect(url_for('hr.loan_detail', loan_id=loan.id))
