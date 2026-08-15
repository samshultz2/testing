"""Staff-loan business rules.

A loan is advanced to a staff member and repaid by monthly salary deductions,
due in full by **November of the year it was taken**. Each school configures its
own interest method (``flat`` 5% of principal, or ``reducing`` balance) and rate;
those are snapshotted onto the loan at creation. Three staff guarantors must
approve before the loan becomes active. If the requested monthly deduction is too
small to clear the loan by November, it is automatically raised.
"""
from datetime import date
from utils import timeutil

from models import db, SchoolSettings, StaffLoan, LoanGuarantor, LoanRepayment

NOVEMBER = 11


def settings():
    g = SchoolSettings.get
    method = (g('loan_interest_method', 'flat') or 'flat')
    try:
        rate = float(g('loan_interest_rate', '5') or 5)
    except (TypeError, ValueError):
        rate = 5.0
    try:
        req = int(g('loan_guarantors_required', '3') or 3)
    except (TypeError, ValueError):
        req = 3
    return {
        'enabled': g('loans_enabled', '1') in ('1', 'true', 'on', True),
        'method': method if method in ('flat', 'reducing') else 'flat',
        'rate': max(0.0, rate),
        'guarantors_required': max(1, min(req, 5)),
        'deadline_month': NOVEMBER,
    }


def save_settings(*, enabled, method, rate, guarantors_required):
    SchoolSettings.set('loans_enabled', '1' if enabled else '0', 'string')
    SchoolSettings.set('loan_interest_method', method if method in ('flat', 'reducing') else 'flat', 'string')
    try:
        rate = max(0.0, float(rate))
    except (TypeError, ValueError):
        rate = 5.0
    SchoolSettings.set('loan_interest_rate', str(rate), 'string')
    try:
        req = max(1, min(int(guarantors_required), 5))
    except (TypeError, ValueError):
        req = 3
    SchoolSettings.set('loan_guarantors_required', str(req), 'string')
    db.session.commit()


def _deadline_year(taken):
    # Everything must be paid off by November of the year the loan was taken; a
    # loan taken after November naturally rolls to the following November.
    return taken.year if taken.month <= NOVEMBER else taken.year + 1


def months_until_november(taken):
    """Inclusive count of monthly payroll deductions from the month taken through
    the November deadline (always at least 1)."""
    end = _deadline_year(taken)
    n = (end * 12 + NOVEMBER) - (taken.year * 12 + taken.month) + 1
    return max(1, n)


def deadline_for(taken):
    return date(_deadline_year(taken), NOVEMBER, 30)


def compute(principal, rate, method, months):
    """Return (total_repayable, min_monthly) for the given terms.

    ``flat``: interest is a flat percent of the principal, spread evenly.
    ``reducing``: standard amortisation at ``rate`` p.a. on the reducing balance.
    """
    principal = max(0.0, float(principal or 0))
    months = max(1, int(months))
    if method == 'reducing':
        r = (float(rate) / 100.0) / 12.0
        monthly = principal / months if r <= 0 else principal * r / (1 - (1 + r) ** (-months))
        total = monthly * months
    else:
        total = principal * (1 + float(rate) / 100.0)
        monthly = total / months
    return round(total, 2), round(monthly, 2)


def quote(principal, taken=None, *, method=None, rate=None):
    """A preview of a loan's terms without creating it."""
    cfg = settings()
    taken = taken or timeutil.today()
    method = method or cfg['method']
    rate = cfg['rate'] if rate is None else rate
    months = months_until_november(taken)
    total, min_monthly = compute(principal, rate, method, months)
    return {'months': months, 'deadline': deadline_for(taken), 'method': method,
            'rate': rate, 'total_repayable': total, 'min_monthly': min_monthly,
            'total_interest': round(total - float(principal or 0), 2)}


def create_loan(*, staff_id, branch_id, principal, guarantor_ids, taken=None,
                desired_monthly=None, purpose='', created_by=''):
    """Create a pending loan with its guarantors. The monthly deduction is raised
    if needed so the loan clears by November. Returns (loan, error|None)."""
    cfg = settings()
    if not cfg['enabled']:
        return None, 'Staff loans are turned off for this school.'
    try:
        principal = float(principal)
    except (TypeError, ValueError):
        principal = 0
    if principal <= 0:
        return None, 'Enter a valid loan amount.'
    gids = [int(g) for g in guarantor_ids if str(g).isdigit() and int(g) != staff_id]
    gids = list(dict.fromkeys(gids))                         # de-dup, drop the borrower
    if len(gids) < cfg['guarantors_required']:
        return None, f'Select {cfg["guarantors_required"]} different guarantors (staff members).'
    taken = taken or timeutil.today()
    months = months_until_november(taken)
    total, min_monthly = compute(principal, cfg['rate'], cfg['method'], months)
    monthly = min_monthly
    if desired_monthly:
        try:
            monthly = max(float(desired_monthly), min_monthly)   # auto-raise to clear by Nov
        except (TypeError, ValueError):
            monthly = min_monthly

    loan = StaffLoan(
        staff_id=staff_id, branch_id=branch_id, principal=round(principal, 2),
        interest_method=cfg['method'], interest_rate=cfg['rate'],
        total_repayable=total, monthly_amount=round(monthly, 2), months=months,
        date_taken=taken, deadline=deadline_for(taken), status='pending',
        purpose=(purpose or '')[:200], created_by=(created_by or '')[:80])
    db.session.add(loan)
    db.session.flush()
    for gid in gids[:cfg['guarantors_required']]:
        db.session.add(LoanGuarantor(loan_id=loan.id, staff_id=gid, status='pending'))
    db.session.commit()
    return loan, None


def _add_months(d, n):
    """Date ``n`` whole months after ``d`` (clamped to the month's last day)."""
    from calendar import monthrange
    m = d.month - 1 + int(n)
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, monthrange(y, m)[1]))


def create_opening_loan(*, staff_id, branch_id, principal, months, monthly_amount,
                        taken, months_paid=0, total_repayable=None, rate=None,
                        method=None, purpose='', created_by=''):
    """Record a loan that was already running *before* the school adopted the
    platform (an opening balance).

    Unlike a fresh loan, this needs no guarantor approval — it is already
    disbursed — so it is created **active** immediately. The admin says how many
    monthly deductions have already been made (``months_paid``); that seeds the
    amount repaid so the outstanding balance and remaining schedule are correct,
    and it is logged as an 'opening balance' entry in the repayment ledger.
    Payroll then continues the monthly deduction from here. Returns (loan, err)."""
    cfg = settings()
    if not cfg['enabled']:
        return None, 'Staff loans are turned off for this school.'
    try:
        principal = float(principal)
    except (TypeError, ValueError):
        principal = 0
    if principal <= 0:
        return None, 'Enter the original loan amount.'
    try:
        months = int(months)
    except (TypeError, ValueError):
        months = 0
    if months < 1:
        return None, 'Enter the total number of months for the loan.'
    try:
        monthly_amount = float(monthly_amount)
    except (TypeError, ValueError):
        monthly_amount = 0
    if monthly_amount <= 0:
        return None, 'Enter the monthly repayment amount.'
    if not taken:
        return None, 'Enter the date the loan was originally taken.'
    try:
        months_paid = max(0, int(months_paid))
    except (TypeError, ValueError):
        months_paid = 0
    if months_paid > months:
        return None, 'Months already paid cannot exceed the total number of months.'

    method = method or cfg['method']
    rate = cfg['rate'] if rate is None else rate
    # Prefer an explicit agreed total; otherwise derive it from the interest terms.
    if total_repayable:
        try:
            total = round(float(total_repayable), 2)
        except (TypeError, ValueError):
            total, _ = compute(principal, rate, method, months)
    else:
        total, _ = compute(principal, rate, method, months)
    total = max(total, round(principal, 2))

    loan = StaffLoan(
        staff_id=staff_id, branch_id=branch_id, principal=round(principal, 2),
        interest_method=method, interest_rate=rate,
        total_repayable=total, monthly_amount=round(monthly_amount, 2), months=months,
        amount_repaid=0.0, date_taken=taken, deadline=_add_months(taken, months - 1),
        status='active', purpose=(purpose or '')[:200], created_by=(created_by or '')[:80])
    db.session.add(loan)
    db.session.flush()
    already = round(min(months_paid * monthly_amount, total), 2)
    if already > 0:
        record_repayment(loan, already, source='opening', when=taken,
                         note=f'Opening balance — {months_paid} month(s) paid before go-live')
    db.session.commit()
    return loan, None


def act_on_guarantor(loan, guarantor_staff_id, *, approve, by=''):
    """Record a guarantor's approval/decline. Activates the loan once all
    guarantors have approved; a single decline rejects it."""
    from datetime import datetime
    g = next((g for g in loan.guarantors if g.staff_id == int(guarantor_staff_id)), None)
    if g is None:
        return 'That person is not a guarantor for this loan.'
    if loan.status not in ('pending',):
        return 'This loan is no longer awaiting guarantor approval.'
    g.status = 'approved' if approve else 'declined'
    g.acted_at = timeutil.now()
    g.acted_by = (by or '')[:80]
    if not approve:
        loan.status = 'rejected'
    elif loan.is_fully_approved:
        loan.status = 'active'                              # disbursed
    db.session.commit()
    return None


def record_repayment(loan, amount, *, source='manual', payroll_run_id=None, when=None, note=''):
    """Book a repayment, capped at the outstanding balance; marks the loan paid
    when cleared. Returns the amount actually applied."""
    amount = round(min(max(0.0, float(amount or 0)), loan.outstanding), 2)
    if amount <= 0:
        return 0.0
    db.session.add(LoanRepayment(loan_id=loan.id, amount=amount, source=source,
                                 payroll_run_id=payroll_run_id, date=(when or timeutil.today()),
                                 note=(note or '')[:200]))
    loan.amount_repaid = round((loan.amount_repaid or 0) + amount, 2)
    if loan.outstanding <= 0:
        loan.status = 'paid'
    return amount


def active_loan_for(staff_id):
    """The staff member's current active loan with a balance, if any."""
    return (StaffLoan.query.filter_by(staff_id=staff_id, status='active')
            .filter(StaffLoan.amount_repaid < StaffLoan.total_repayable)
            .order_by(StaffLoan.date_taken.asc()).first())


# --- payroll integration ---------------------------------------------------
def payslip_loan_deduction(staff_id):
    """The monthly loan deduction to show on this staff member's payslip (0 if
    none). Used when payroll payslips are generated."""
    loan = active_loan_for(staff_id)
    return loan.monthly_due() if loan else 0.0


def post_run_repayments(run):
    """Book loan repayments for a payroll run as it is finalized — once per
    (loan, run). Idempotent: re-finalizing won't double-charge."""
    posted = 0
    for ps in run.payslips:
        loan = active_loan_for(ps.staff_id)
        if not loan:
            continue
        already = LoanRepayment.query.filter_by(loan_id=loan.id, payroll_run_id=run.id).first()
        if already:
            continue
        applied = record_repayment(loan, loan.monthly_due(), source='payroll',
                                   payroll_run_id=run.id,
                                   note=f'Salary deduction — {run.period_label}')
        if applied:
            posted += 1
    if posted:
        db.session.commit()
    return posted
