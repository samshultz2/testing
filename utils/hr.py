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
    def _f(key, default=0):
        v = SchoolSettings.get(key, None)
        try:
            return float(v) if v not in (None, '') else default
        except (ValueError, TypeError):
            return default
    return {
        'late_time': SchoolSettings.get('hr_late_time', '07:30'),
        'late_rate': float(SchoolSettings.get('hr_late_rate', 10) or 0),
        'absence_deduction': float(SchoolSettings.get('hr_absence_deduction', 0) or 0),
        # Self-service attendance (QR / GPS / device)
        'geo_lat': _f('hr_geo_lat', None), 'geo_lng': _f('hr_geo_lng', None),
        'geo_radius': int(_f('hr_geo_radius', 200) or 200),
        'geo_enabled': (SchoolSettings.get('hr_geo_lat', None) not in (None, '')
                        and SchoolSettings.get('hr_geo_lng', None) not in (None, '')),
        'has_device_token': bool(SchoolSettings.get('hr_device_token', None)),
    }


def save_settings(form):
    SchoolSettings.set('hr_late_time', (form.get('late_time') or '07:30').strip(),
                       'string', 'Staff resumption time (HH:MM)')
    SchoolSettings.set('hr_late_rate', form.get('late_rate') or '0',
                       'string', 'Lateness deduction per minute')
    SchoolSettings.set('hr_absence_deduction', form.get('absence_deduction') or '0',
                       'string', 'Deduction per day absent')
    # Geofence for GPS check-in (blank lat/lng disables it).
    for key, field in (('hr_geo_lat', 'geo_lat'), ('hr_geo_lng', 'geo_lng'),
                       ('hr_geo_radius', 'geo_radius')):
        if field in form:
            SchoolSettings.set(key, (form.get(field) or '').strip(), 'string',
                               'Staff GPS check-in geofence')


# ---- Self-service attendance (QR / GPS / biometric device) ------------------

def _checkin_serializer():
    from itsdangerous import URLSafeTimedSerializer
    from flask import current_app
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='hr-checkin')


def day_code():
    """A short-lived signed token valid for today's QR self check-in."""
    import datetime as _dt
    return _checkin_serializer().dumps({'d': _dt.date.today().isoformat()})


def verify_day_code(code):
    """True if ``code`` is a valid, unexpired (≤1 day) token minted for today."""
    import datetime as _dt
    from itsdangerous import BadSignature, SignatureExpired
    try:
        data = _checkin_serializer().loads(code or '', max_age=86400)
    except (BadSignature, SignatureExpired, Exception):
        return False
    return data.get('d') == _dt.date.today().isoformat()


def qr_svg_data_uri(text):
    """A QR code for ``text`` as an inline SVG data URI (no Pillow needed)."""
    import io, base64
    import qrcode
    import qrcode.image.svg as svg
    img = qrcode.make(text, image_factory=svg.SvgPathImage, box_size=10, border=2)
    buf = io.BytesIO(); img.save(buf)
    b64 = base64.b64encode(buf.getvalue()).decode('ascii')
    return 'data:image/svg+xml;base64,' + b64


def haversine_m(lat1, lng1, lat2, lng2):
    """Great-circle distance between two points in metres."""
    import math
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def within_geofence(lat, lng, settings=None):
    s = settings or get_settings()
    if not s.get('geo_enabled') or lat is None or lng is None:
        return None      # geofence not configured / no coords → caller decides
    try:
        dist = haversine_m(float(lat), float(lng), s['geo_lat'], s['geo_lng'])
    except (ValueError, TypeError):
        return False
    return dist <= (s['geo_radius'] or 200)


def mark_attendance_now(staff_id, method='self', when=None, note=None):
    """Upsert today's StaffAttendance for a staff member from a live check-in,
    deriving Present/Late (and any lateness deduction) from the clock-in time."""
    import datetime as _dt
    from models import StaffAttendance
    settings = get_settings()
    now = when or _dt.datetime.now()
    day = now.date()
    clock_in = now.strftime('%H:%M')
    st, mins, ded = compute_attendance('Present', clock_in, settings)
    rec = StaffAttendance.query.filter_by(staff_id=staff_id, date=day).first()
    if not rec:
        rec = StaffAttendance(staff_id=staff_id, date=day)
        db.session.add(rec)
    rec.status = st
    rec.clock_in = clock_in
    rec.minutes_late = mins
    rec.deduction = ded
    rec.note = note or f'{method} check-in'
    return rec, st


def clock_out_now(staff_id, when=None):
    """Stamp today's clock-out time for a staff member. Returns (rec, 'HH:MM')
    or (None, None) when there's no open clock-in to close today."""
    import datetime as _dt
    from models import StaffAttendance
    now = when or _dt.datetime.now()
    rec = StaffAttendance.query.filter_by(staff_id=staff_id, date=now.date()).first()
    if not rec or not rec.clock_in:
        return None, None
    rec.clock_out = now.strftime('%H:%M')
    return rec, rec.clock_out


def hr_self_service(user):
    """Assemble the self-scope HR data a signed-in user may see on their own
    account page. Each section is populated ONLY if the user holds the matching
    self-scope capability, and every query is limited to their own linked staff
    record — never anyone else's. Returns None when the user isn't linked to a
    staff record or holds no self-scope capability."""
    import datetime as _dt
    from models import StaffMember, StaffAttendance, Payslip, PayrollRun
    from utils.access_control import self_scope_level
    from utils.hr_schema import ensure_hr_schema
    ensure_hr_schema()   # make sure the clock_out column exists on this tenant DB
    staff = StaffMember.query.filter_by(user_id=user.id).first() if user else None
    if not staff:
        return None
    att_lvl = self_scope_level('hr.self_attendance')
    pay_lvl = self_scope_level('hr.self_payroll')
    ded_lvl = self_scope_level('hr.self_deductions')
    leave_lv = self_scope_level('hr.self_leave')
    loans_lv = self_scope_level('hr.self_loans')
    docs_lv = self_scope_level('hr.self_documents')
    if not (att_lvl or pay_lvl or ded_lvl or leave_lv or loans_lv or docs_lv):
        return None
    out = {'staff_name': staff.full_name, 'can_clock': att_lvl == 'edit',
           'attendance': None, 'today': None, 'clock_action': None,
           'payslips': None, 'deductions': None,
           'leave': None, 'leave_balances': None, 'loans': None, 'documents': None}
    today = _dt.date.today()
    if att_lvl:
        rows = (StaffAttendance.query.filter_by(staff_id=staff.id)
                .order_by(StaffAttendance.date.desc()).limit(30).all())
        out['attendance'] = [{'date': r.date.strftime('%a %d %b %Y'), 'status': r.status,
                              'clock_in': r.clock_in or '—', 'clock_out': r.clock_out or '—',
                              'minutes_late': r.minutes_late or 0,
                              'deduction': round(r.deduction or 0, 2)} for r in rows]
        trec = next((r for r in rows if r.date == today), None)
        out['today'] = ({'status': trec.status, 'clock_in': trec.clock_in,
                         'clock_out': trec.clock_out} if trec else None)
        # Next self-service action for today's toggle button.
        if not trec or not trec.clock_in:
            out['clock_action'] = 'in'
        elif not trec.clock_out:
            out['clock_action'] = 'out'
        else:
            out['clock_action'] = 'done'
    if pay_lvl or ded_lvl:
        slips = (Payslip.query.join(PayrollRun, Payslip.run_id == PayrollRun.id)
                 .filter(Payslip.staff_id == staff.id,
                         PayrollRun.status.in_(['Finalized', 'Paid']))
                 .order_by(PayrollRun.year.desc(), PayrollRun.month.desc()).all())
        if pay_lvl:
            out['payslips'] = [{'period': s.run.period_label, 'status': s.run.status,
                                'basic': round(s.basic or 0, 2), 'allowances': round(s.allowances or 0, 2),
                                'deductions': round(s.total_deductions, 2),
                                'net': round(s.net or 0, 2)} for s in slips]
        if ded_lvl:
            ded = []
            for s in slips:
                for it in s.items:                       # recurring lines (pension, welfare…)
                    ded.append({'period': s.run.period_label, 'name': it.name or 'Deduction',
                                'amount': round(it.amount or 0, 2)})
                if s.attendance_deduction:
                    ded.append({'period': s.run.period_label, 'name': 'Lateness / absence',
                                'amount': round(s.attendance_deduction, 2)})
                if s.deductions:
                    ded.append({'period': s.run.period_label, 'name': 'Other (loans / PAYE)',
                                'amount': round(s.deductions, 2)})
            out['deductions'] = ded
    if leave_lv:
        from models import LeaveRecord
        recs = (LeaveRecord.query.filter_by(staff_id=staff.id)
                .order_by(LeaveRecord.start_date.desc()).limit(20).all())
        out['leave'] = [{'type': r.leave_type or 'Other',
                         'start': r.start_date.strftime('%d %b %Y') if r.start_date else '—',
                         'end': r.end_date.strftime('%d %b %Y') if r.end_date else '—',
                         'days': r.days or 0, 'status': r.status} for r in recs]
        out['leave_balances'] = leave_balances(staff.id, today.year)
    if loans_lv:
        from models import StaffLoan
        loans = (StaffLoan.query.filter(StaffLoan.staff_id == staff.id,
                 StaffLoan.status.in_(['active', 'paid', 'pending']))
                 .order_by(StaffLoan.date_taken.desc()).all())
        out['loans'] = [{'taken': l.date_taken.strftime('%d %b %Y') if l.date_taken else '—',
                         'status': (l.status or '').title(),
                         'principal': round(l.principal or 0, 2),
                         'repayable': round(l.total_repayable or 0, 2),
                         'repaid': round(l.amount_repaid or 0, 2),
                         'outstanding': l.outstanding,
                         'monthly': round(l.monthly_amount or 0, 2),
                         'deadline': l.deadline.strftime('%d %b %Y') if l.deadline else '—'}
                        for l in loans]
    if docs_lv:
        from models import StaffDocument
        from flask import url_for
        docs = (StaffDocument.query.filter_by(staff_id=staff.id, is_current=True)
                .order_by(StaffDocument.created_at.desc()).all())
        out['documents'] = [{'id': dcm.id, 'title': dcm.title,
                             'type': dcm.doc_type or 'Other', 'version': dcm.version or 1,
                             'expires': dcm.expires_on.strftime('%d %b %Y') if dcm.expires_on else '',
                             'expired': dcm.is_expired,
                             'has_file': bool(dcm.attachment_id),
                             'url': url_for('hr.my_document', doc_id=dcm.id)}
                            for dcm in docs]
    return out


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

    active_status = active.filter_by(status='Active').count()
    import datetime as _dt
    today = _dt.date.today()
    month_start = today.replace(day=1)
    new_hires = active.filter(StaffMember.date_employed >= month_start).count()

    # Contracts expiring within 60 days (and not already past).
    horizon = today + _dt.timedelta(days=60)
    contract_expiring = active.filter(
        StaffMember.contract_end.isnot(None),
        StaffMember.contract_end <= horizon,
        StaffMember.contract_end >= today).count()

    # Qualification breakdown (top few).
    qual_q = (db.session.query(StaffMember.qualification, func.count(StaffMember.id))
              .filter(StaffMember.is_active == True))
    if branch_id is not None:
        qual_q = qual_q.filter(StaffMember.branch_id == branch_id)
    qual_rows = qual_q.group_by(StaffMember.qualification).all()
    qual_chart = sorted([{'name': (q or 'Not recorded'), 'count': c} for q, c in qual_rows if c],
                        key=lambda x: -x['count'])[:8]

    # Branch distribution (only meaningful for a central view).
    branch_chart = []
    if branch_id is None:
        from models import Branch
        bmap = {b.id: b.name for b in Branch.query.all()}
        brows = (db.session.query(StaffMember.branch_id, func.count(StaffMember.id))
                 .filter(StaffMember.is_active == True).group_by(StaffMember.branch_id).all())
        branch_chart = [{'name': bmap.get(bid, 'Unassigned'), 'count': c} for bid, c in brows if c]

    return {
        'total': total, 'teaching': teaching, 'non_teaching': non_teaching,
        'active': active_status, 'on_leave': on_leave, 'male': male, 'female': female,
        'new_hires': new_hires, 'contract_expiring': contract_expiring,
        'monthly_payroll': monthly_payroll, 'pending_leave': pending_leave,
        'dept_chart': dept_chart, 'type_chart': type_chart,
        'qual_chart': qual_chart, 'branch_chart': branch_chart,
    }


def upcoming_birthdays(branch_id=None, days=30, limit=8):
    """Staff with a birthday within the next ``days`` (branch-scoped)."""
    import datetime as _dt
    q = StaffMember.query.filter(StaffMember.is_active == True,
                                 StaffMember.date_of_birth.isnot(None))
    if branch_id is not None:
        q = q.filter(StaffMember.branch_id == branch_id)
    today = _dt.date.today()
    out = []
    for s in q.all():
        dob = s.date_of_birth
        try:
            nxt = dob.replace(year=today.year)
        except ValueError:
            nxt = dob.replace(year=today.year, day=28)
        if nxt < today:
            try:
                nxt = dob.replace(year=today.year + 1)
            except ValueError:
                nxt = dob.replace(year=today.year + 1, day=28)
        delta = (nxt - today).days
        if 0 <= delta <= days:
            out.append((delta, nxt, s))
    out.sort(key=lambda x: x[0])
    return [{'id': s.id, 'name': s.full_name, 'date': nxt.strftime('%d %b'),
             'in_days': delta, 'turning': nxt.year - s.date_of_birth.year} for delta, nxt, s in out[:limit]]


def expiring_contracts(branch_id=None, days=60, limit=8):
    import datetime as _dt
    today = _dt.date.today()
    q = StaffMember.query.filter(
        StaffMember.is_active == True, StaffMember.contract_end.isnot(None),
        StaffMember.contract_end >= today,
        StaffMember.contract_end <= today + _dt.timedelta(days=days))
    if branch_id is not None:
        q = q.filter(StaffMember.branch_id == branch_id)
    rows = q.order_by(StaffMember.contract_end).limit(limit).all()
    return [{'id': s.id, 'name': s.full_name,
             'ends': s.contract_end.strftime('%d %b %Y'),
             'days_left': (s.contract_end - today).days} for s in rows]


def active_deduction_types():
    """Recurring payroll deductions (pension, welfare, …) currently in force."""
    from models import PayrollDeductionType
    return (PayrollDeductionType.query.filter_by(is_active=True)
            .order_by(PayrollDeductionType.name).all())


def apply_recurring_deductions(ps, types=None):
    """(Re)build a payslip's recurring-deduction line items from the active
    definitions, based on its current basic pay. Replaces any existing lines.
    Also appends the staff member's monthly staff-loan repayment, if any."""
    from models import PayslipDeduction
    types = active_deduction_types() if types is None else types
    ps.items[:] = []
    for t in types:
        amt = t.amount_for(ps.basic or 0)
        if amt:
            ps.items.append(PayslipDeduction(name=t.label, amount=amt))
    try:
        from utils.staff_loans import payslip_loan_deduction
        loan_amt = payslip_loan_deduction(ps.staff_id)
        if loan_amt:
            ps.items.append(PayslipDeduction(name='Staff loan repayment', amount=loan_amt))
    except Exception:
        pass


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
