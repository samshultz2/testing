"""Automated library reminders — overdue + due-soon.

Driven daily by the scheduled worker (see app._tick_one). Gated by the
Communication automation center (``library_overdue`` / ``library_due_soon``), so
schools opt in. Overdue drafts a parent SMS via the Communication module (never
auto-sent) and alerts admins in-app; due-soon alerts admins only. Everything is
best-effort and never raises into the worker loop.
"""
from __future__ import annotations
from utils import timeutil

import datetime as _dt


DUE_SOON_DAYS = 2
_MIN_INTERVAL_DAYS = 1        # don't re-draft an overdue campaign more than daily


def _overdue_student_ids(today):
    from models import Book, BookLoan
    from utils.branch_scope import scope_query
    q = (scope_query(BookLoan.query.join(Book, BookLoan.book_id == Book.id), Book)
         .filter(BookLoan.status == 'Borrowed', BookLoan.due_date < today,
                 BookLoan.borrower_type != 'staff', BookLoan.student_id.isnot(None)))
    return sorted({l.student_id for l in q.all() if l.student_id})


def _overdue_total(today):
    from models import Book, BookLoan
    from utils.branch_scope import scope_query
    return (scope_query(BookLoan.query.join(Book, BookLoan.book_id == Book.id), Book)
            .filter(BookLoan.status == 'Borrowed', BookLoan.due_date < today).count())


def _due_soon_total(today):
    from models import Book, BookLoan
    from utils.branch_scope import scope_query
    horizon = today + _dt.timedelta(days=DUE_SOON_DAYS)
    return (scope_query(BookLoan.query.join(Book, BookLoan.book_id == Book.id), Book)
            .filter(BookLoan.status == 'Borrowed', BookLoan.due_date >= today,
                    BookLoan.due_date <= horizon).count())


def run_library_reminders(app, *, force=False, dry_run=False):
    """Prepare library reminders. Runs inside a central-scope request context so
    audience resolution (which reads the session) sees every branch."""
    from utils import automations
    with app.test_request_context('/'):
        from flask import session, url_for
        session['scope'] = 'central'
        session['role'] = 'super_admin'
        today = _dt.date.today()
        out = {}

        do_overdue = force or automations.is_enabled('library_overdue')
        do_due = force or automations.is_enabled('library_due_soon')

        if do_overdue:
            total = _overdue_total(today)
            out['overdue'] = total
            if total and not dry_run:
                from utils.notify import notify_admins
                notify_admins('Library: overdue books',
                              f'{total} library book(s) are overdue. Review and remind borrowers.',
                              url=url_for('library.loans') + '?status=Overdue', category='warning')
                _maybe_draft_overdue(today)

        if do_due:
            total = _due_soon_total(today)
            out['due_soon'] = total
            if total and not dry_run:
                from utils.notify import notify_admins
                notify_admins('Library: books due soon',
                              f'{total} library book(s) are due within {DUE_SOON_DAYS} day(s).',
                              url=url_for('library.loans') + '?status=Borrowed', category='info')
        return out


def _maybe_draft_overdue(today):
    """Draft a parent SMS for overdue borrowers, at most once per interval."""
    from models import Message
    from datetime import datetime, timedelta
    recent = (Message.query.filter(Message.title == 'Library overdue reminder',
                                   Message.created_at >= timeutil.now() - timedelta(days=_MIN_INTERVAL_DAYS))
              .first())
    if recent:
        return recent
    student_ids = _overdue_student_ids(today)
    if not student_ids:
        return None
    from utils import comms
    from utils.helpers import get_active_term
    body = ('Dear {parent}, our records show {student} has an overdue library book. '
            'Please return it to the school library. Thank you — {school}.')
    return comms.build_campaign(
        body, channel='SMS', term=get_active_term(), title='Library overdue reminder',
        spec={'to': 'parents', 'audience': 'students', 'student_ids': student_ids},
        created_by='auto-reminder')
