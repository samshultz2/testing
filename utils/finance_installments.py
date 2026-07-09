"""Installment plans (Phase 3) — a term's payment schedule.

A schedule is a set of installments for a (term, class): each a percentage of the
student's *payable* due by a date. Percent-based, so one schedule scales to every
student's own bill with no per-student setup. A class-specific schedule overrides
the term-wide (class = None) one.

From a schedule we derive, per student: how much should have been paid by now
(expected-to-date), whether they're on track or behind, the shortfall, and the
next installment due — which the penalty tool and reminders can act on.
"""
from __future__ import annotations

import datetime as _dt


def get_plan(term_id, class_id=None):
    """The installment rows for a (term, class): the class-specific schedule if
    one exists, else the term-wide (class=None) schedule. Ordered."""
    from models import InstallmentPlan
    if term_id is None:
        return []
    rows = (InstallmentPlan.query.filter_by(term_id=term_id, class_id=class_id)
            .order_by(InstallmentPlan.sort_order, InstallmentPlan.due_date).all())
    if not rows and class_id is not None:
        rows = (InstallmentPlan.query.filter_by(term_id=term_id, class_id=None)
                .order_by(InstallmentPlan.sort_order, InstallmentPlan.due_date).all())
    return rows


def has_plan(term_id, class_id=None):
    return bool(get_plan(term_id, class_id))


def save_plan(term_id, class_id, rows, branch_id=None):
    """Replace the schedule for a (term, class) with the given rows.
    Each row: {label, due_date (date|None), percent (float)}."""
    from models import db, InstallmentPlan
    InstallmentPlan.query.filter_by(term_id=term_id, class_id=class_id).delete()
    for i, r in enumerate(rows):
        pct = float(r.get('percent') or 0)
        if pct <= 0 or not (r.get('label') or '').strip():
            continue
        db.session.add(InstallmentPlan(
            term_id=term_id, class_id=class_id, branch_id=branch_id,
            label=r['label'].strip()[:60], due_date=r.get('due_date'),
            percent=pct, sort_order=i))
    db.session.commit()


def clear_plan(term_id, class_id):
    from models import db, InstallmentPlan
    InstallmentPlan.query.filter_by(term_id=term_id, class_id=class_id).delete()
    db.session.commit()


def student_status(student_id, term_id, as_of=None, bill=None):
    """Installment progress for one student. Returns a dict with the schedule (each
    line's amount + cumulative due), expected-to-date, paid, behind, next due, and
    an on_track flag. Empty schedule -> has_plan False."""
    from utils.finance import student_bill, student_placement
    as_of = as_of or _dt.date.today()
    class_id, _arm = student_placement(student_id, term_id)
    plan = get_plan(term_id, class_id)
    bill = bill or student_bill(student_id, term_id)
    payable, paid = bill['payable'], bill['paid']

    schedule, cum_pct, cum_amt, expected = [], 0.0, 0.0, 0.0
    next_due = None
    for r in plan:
        cum_pct += r.percent
        amt = round(payable * r.percent / 100.0, 2)
        cum_amt = round(cum_amt + amt, 2)
        due_passed = bool(r.due_date and r.due_date <= as_of)
        if due_passed:
            expected = cum_amt
        if next_due is None and r.due_date and r.due_date > as_of:
            next_due = {'label': r.label, 'due_date': r.due_date, 'amount': amt}
        schedule.append({'label': r.label, 'due_date': r.due_date, 'percent': r.percent,
                         'amount': amt, 'cumulative': cum_amt, 'due_passed': due_passed})
    behind = round(max(expected - paid, 0.0), 2)
    return {
        'has_plan': bool(plan),
        'schedule': schedule,
        'payable': payable, 'paid': paid,
        'expected_to_date': round(expected, 2),
        'behind': behind,
        'on_track': behind <= 0.005,
        'next_due': next_due,
        'total_percent': round(cum_pct, 2),
    }


def roster(term_id, students, as_of=None):
    """[{student, status}] installment status for a set of (student, caa) pairs."""
    as_of = as_of or _dt.date.today()
    out = []
    for student, caa in students:
        st = student_status(student.id, term_id, as_of=as_of)
        if st['has_plan']:
            out.append({'student': student, 'status': st})
    out.sort(key=lambda r: -r['status']['behind'])
    return out
