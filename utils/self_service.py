"""Self-scope self-service assemblers.

Each function returns the data a signed-in user is entitled to see about their
OWN record for one module, gated by that module's self-scope capability and
scoped strictly to the caller's linked staff record — never anyone else's. The
/account page renders whatever these return.

HR self-service lives in utils.hr.hr_self_service (kept there with the rest of
the HR helpers); this module adds the others and a single aggregate entry point.
"""
from __future__ import annotations


def _linked_staff(user):
    from models import StaffMember
    return StaffMember.query.filter_by(user_id=user.id).first() if user else None


def library_self_loans(user):
    """A staff borrower's own current library loans (read-only). Populated only
    if the user holds 'library.self_loans' and is linked to a staff record;
    every row belongs to the caller. None otherwise."""
    from models import BookLoan
    from utils.access_control import self_scope_level
    if not user or not self_scope_level('library.self_loans'):
        return None
    staff = _linked_staff(user)
    if not staff:
        return None
    loans = (BookLoan.query
             .filter(BookLoan.borrower_type == 'staff',
                     BookLoan.staff_id == staff.id,
                     BookLoan.status == 'Borrowed')
             .order_by(BookLoan.due_date.asc().nullslast()).all())
    rows = [{'title': (l.book.title if l.book else '—'),
             'borrowed': l.borrowed_date.strftime('%d %b %Y') if l.borrowed_date else '—',
             'due': l.due_date.strftime('%d %b %Y') if l.due_date else '—',
             'overdue': bool(l.is_overdue), 'days_overdue': l.days_overdue,
             'renewals': l.renew_count or 0} for l in loans]
    return {'loans': rows, 'overdue': sum(1 for r in rows if r['overdue'])}


def profile_self_service(user):
    """All self-service blocks for the /account page, keyed by module. Each value
    is that module's assembler output (or None when not entitled/applicable)."""
    from utils.hr import hr_self_service
    return {'hr': hr_self_service(user), 'library': library_self_loans(user)}
