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
BLOOD_GROUPS = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']


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


# ---- Leave allowances + balances -------------------------------------------

# Sensible Nigerian-school defaults; overridable per school in HR settings.
DEFAULT_LEAVE_ALLOWANCES = {
    'Annual': 20, 'Sick': 12, 'Casual': 6, 'Maternity': 90,
    'Paternity': 7, 'Study': 14, 'Other': 0,
}


def leave_allowances():
    """Per-type annual leave entitlement (days), school-configurable."""
    out = {}
    for t in LEAVE_TYPES:
        raw = SchoolSettings.get(f'hr_leave_allow_{t}', None)
        try:
            out[t] = int(float(raw)) if raw is not None else DEFAULT_LEAVE_ALLOWANCES.get(t, 0)
        except (ValueError, TypeError):
            out[t] = DEFAULT_LEAVE_ALLOWANCES.get(t, 0)
    return out


def save_leave_allowances(form):
    for t in LEAVE_TYPES:
        key = f'leave_allow_{t}'
        if key in form:
            val = form.get(key) or '0'
            SchoolSettings.set(f'hr_leave_allow_{t}', str(val), 'int',
                               f'Annual {t} leave entitlement (days)')


def leave_balances(staff_id, year):
    """Per-type leave balance for a staff member in a year:
    [{'type','allowance','taken','remaining'}] — only types with an allowance or
    some usage are returned, so the list stays meaningful."""
    allow = leave_allowances()
    approved = (LeaveRecord.query.filter(
        LeaveRecord.staff_id == staff_id, LeaveRecord.status == 'Approved',
        extract('year', LeaveRecord.start_date) == year).all())
    taken = {}
    for lv in approved:
        taken[lv.leave_type or 'Other'] = taken.get(lv.leave_type or 'Other', 0) + (lv.days or 0)
    rows = []
    for t in LEAVE_TYPES:
        a, tk = allow.get(t, 0), taken.get(t, 0)
        if a or tk:
            rows.append({'type': t, 'allowance': a, 'taken': tk, 'remaining': a - tk})
    return rows


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


# ---- Cross-module profile hub ----------------------------------------------
# The staff profile pulls together data owned by other modules (teaching
# assignments, attendance, leave) so an administrator sees everything about a
# person in one place — without duplicating those modules' own screens.

def teaching_load(staff):
    """Teaching assignments for a staff member, resolved through their linked
    User → Teacher record. Returns None for staff who don't teach / aren't
    linked to a login. Only the *current* (active) session's assignments count,
    matching how the Academics module scopes a teacher's classes.

    Shape: {'form_classes': [str], 'subjects': [{'class','subject'}],
            'subject_count': int, 'class_count': int}
    """
    if not staff or not staff.user_id:
        return None
    from models import (Teacher, TeacherClassAssignment, TeacherSubjectAssignment,
                        ClassArmAssignment, Term)
    teacher = Teacher.query.filter_by(user_id=staff.user_id).first()
    if not teacher:
        return None
    # Restrict to the active term's assignments so we show the current workload.
    active_term = Term.query.filter_by(is_active=True).first()
    caa_ids = None
    if active_term:
        caa_ids = {r[0] for r in db.session.query(ClassArmAssignment.id)
                   .filter(ClassArmAssignment.term_id == active_term.id).all()}

    def _current(assignments):
        for a in assignments:
            if not a.is_active:
                continue
            if caa_ids is not None and a.class_arm_assignment_id not in caa_ids:
                continue
            yield a

    form_classes = []
    for a in _current(teacher.class_assignments.filter_by(is_form_teacher=True).all()):
        caa = a.class_arm_assignment
        if caa:
            form_classes.append(caa.display_name)

    subjects = []
    for a in _current(teacher.subject_assignments.all()):
        caa = a.class_arm_assignment
        subjects.append({'class': caa.display_name if caa else '—',
                         'subject': a.subject.name if a.subject else '—'})
    subjects.sort(key=lambda x: (x['class'], x['subject']))
    classes = {s['class'] for s in subjects} | set(form_classes)
    return {
        'form_classes': sorted(set(form_classes)),
        'subjects': subjects,
        'subject_count': len(subjects),
        'class_count': len(classes),
        'is_teacher': True,
    }


def attendance_summary(staff_id, year, month):
    """This-month staff-attendance tally (present/late/absent/excused + deduction)."""
    from models import StaffAttendance
    rows = (StaffAttendance.query.filter(
        StaffAttendance.staff_id == staff_id,
        extract('year', StaffAttendance.date) == year,
        extract('month', StaffAttendance.date) == month).all())
    out = {'present': 0, 'late': 0, 'absent': 0, 'excused': 0, 'deduction': 0.0, 'marked': len(rows)}
    for a in rows:
        key = (a.status or 'Present').lower()
        if key in out:
            out[key] += 1
        out['deduction'] += (a.deduction or 0)
    out['deduction'] = round(out['deduction'], 2)
    return out


def leave_summary(staff_id, year):
    """Approved leave days taken this year (by type) plus a pending count."""
    approved = (LeaveRecord.query.filter(
        LeaveRecord.staff_id == staff_id, LeaveRecord.status == 'Approved',
        extract('year', LeaveRecord.start_date) == year).all())
    by_type = {}
    total = 0
    for lv in approved:
        by_type[lv.leave_type or 'Other'] = by_type.get(lv.leave_type or 'Other', 0) + (lv.days or 0)
        total += (lv.days or 0)
    pending = LeaveRecord.query.filter_by(staff_id=staff_id, status='Pending').count()
    return {'total_days': total, 'by_type': by_type, 'pending': pending}


# ---- Lifecycle events + timeline -------------------------------------------

def record_event(staff, kind, title, detail=None, effective_date=None, created_by=None):
    """Append a lifecycle event (promotion / transfer / …) to a staff member."""
    from models import StaffEvent
    from datetime import date
    ev = StaffEvent(staff_id=staff.id, kind=kind, title=title,
                    detail=(detail or None), effective_date=effective_date or date.today(),
                    created_by=created_by)
    db.session.add(ev)
    return ev


# Icon + tone per timeline entry kind (consumed by the React timeline).
_TIMELINE_STYLE = {
    'employment': ('fa-briefcase', 'green'),
    'confirmation': ('fa-user-check', 'green'),
    'promotion': ('fa-arrow-trend-up', 'blue'),
    'transfer': ('fa-arrows-left-right', 'amber'),
    'department': ('fa-sitemap', 'blue'),
    'status': ('fa-flag', 'amber'),
    'salary': ('fa-money-bill-trend-up', 'blue'),
    'leave': ('fa-plane-departure', 'purple'),
    'note': ('fa-note-sticky', 'muted'),
}


def build_timeline(staff):
    """Merge a staff member's lifecycle into one reverse-chronological feed:
    the employment + confirmation dates (from the record itself), StaffEvent rows
    (promotions / transfers / notes), salary changes and approved leave — each
    already owned by its own module, surfaced together here."""
    from models import StaffEvent, SalaryHistory, LeaveRecord
    from datetime import date
    items = []

    def _add(d, kind, title, detail=None):
        if not d:
            return
        icon, tone = _TIMELINE_STYLE.get(kind, ('fa-circle', 'muted'))
        items.append({'date': d, 'kind': kind, 'title': title,
                      'detail': detail or '', 'icon': icon, 'tone': tone})

    if staff.date_employed:
        _add(staff.date_employed, 'employment', 'Joined the school',
             staff.designation or (staff.staff_type or ''))
    if staff.confirmation_date:
        _add(staff.confirmation_date, 'confirmation', 'Confirmed (off probation)')

    for ev in StaffEvent.query.filter_by(staff_id=staff.id).all():
        _add(ev.effective_date or (ev.created_at.date() if ev.created_at else None),
             ev.kind or 'note', ev.title, ev.detail)

    for h in SalaryHistory.query.filter_by(staff_id=staff.id).all():
        d = h.effective_date or (h.created_at.date() if h.created_at else None)
        arrow = 'increase' if h.change >= 0 else 'decrease'
        _add(d, 'salary', f'Salary {arrow}',
             f'{(h.previous_salary or 0):,.0f} → {(h.new_salary or 0):,.0f}'
             + (f' · {h.reason}' if h.reason else ''))

    for lv in (LeaveRecord.query.filter_by(staff_id=staff.id, status='Approved').all()):
        _add(lv.start_date, 'leave', f'{lv.leave_type or "Leave"} ({lv.days or 0} day(s))',
             lv.reason or '')

    items.sort(key=lambda x: (x['date'] or date.min), reverse=True)
    for it in items:
        it['date_label'] = it['date'].strftime('%d %b %Y') if it['date'] else ''
        it.pop('date')
    return items
