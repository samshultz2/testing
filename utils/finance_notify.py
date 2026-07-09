"""Finance notifications (Phase 4): fee-due / overdue alerts and failed-payment
warnings, delivered in-app to admins via utils.notify.

Kept small and side-effect free so a route or a scheduled job can drive it. Parent
(email/SMS) reminders go through the Communication module; here we surface what
the bursar/admin needs to see inside the app.
"""
from __future__ import annotations


def overdue_students(term_id, as_of=None, branch_scoped=False):
    """[(student, amount_behind)] for a term plus the total. A student is 'behind'
    by their installment shortfall if the term has a schedule, else by any
    outstanding balance."""
    from models import StudentEnrollment, ClassArmAssignment
    from utils import finance_installments as I
    from utils.finance import student_bill
    if not term_id:
        return [], 0.0
    q = (StudentEnrollment.query
         .join(ClassArmAssignment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
         .filter(StudentEnrollment.is_active.is_(True), ClassArmAssignment.term_id == term_id))
    if branch_scoped:
        from utils.branch_scope import scope_query
        q = scope_query(q, ClassArmAssignment)
    rows, total = [], 0.0
    for e in q.all():
        s = e.student
        if not s or not s.is_active:
            continue
        st = I.student_status(s.id, term_id, as_of=as_of)
        behind = st['behind'] if st['has_plan'] else max(student_bill(s.id, term_id)['balance'], 0.0)
        if behind > 0.005:
            rows.append((s, round(behind, 2)))
            total += behind
    rows.sort(key=lambda r: -r[1])
    return rows, round(total, 2)


def run_fee_reminders(term_id, send=True, url=None):
    """Notify admins of students behind on fees for a term. Returns a summary."""
    rows, total = overdue_students(term_id)
    summary = {'count': len(rows), 'total': total}
    if rows and send:
        from utils.notify import notify_admins
        notify_admins(f'{len(rows)} student(s) behind on fees',
                      f'Outstanding / overdue this term: ₦{total:,.0f}. Review and follow up.',
                      url=url, category='warning')
    return summary


def payment_verification_failed(reference, detail=''):
    """Alert admins that an online payment could not be verified (so a charged
    parent isn't silently left unrecorded)."""
    from utils.notify import notify_admins
    notify_admins('Online payment could not be verified',
                  f'Reference {reference or "?"} failed verification. {detail}'.strip(),
                  category='error')
