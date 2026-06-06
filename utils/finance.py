"""
Finance helpers — turn the fee structure + payments + discounts into the
numbers the UI shows (expected bill, paid, outstanding balance).
"""
from sqlalchemy import func

from models import (
    db, FeeItem, FeeStructure, FeePayment, FeeDiscount,
    StudentEnrollment, ClassArmAssignment,
)


def student_placement(student_id, term_id):
    """(class_id, arm_id) for a student's active enrolment in a term, or (None, None)."""
    enr = (StudentEnrollment.query
           .join(ClassArmAssignment,
                 StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
           .filter(StudentEnrollment.student_id == student_id,
                   StudentEnrollment.is_active == True,
                   ClassArmAssignment.term_id == term_id)
           .first())
    if not enr:
        return None, None
    asg = enr.class_arm_assignment
    return asg.class_id, asg.arm_id


def structure_items(term_id, class_id, arm_id=None):
    """
    Applicable fee items for a class/arm in a term as [(FeeItem, amount), ...].

    Arm-specific rows override the all-arms (arm_id is NULL) row for the same item.
    """
    if not (term_id and class_id):
        return []
    rows = (FeeStructure.query
            .filter(FeeStructure.term_id == term_id,
                    FeeStructure.class_id == class_id,
                    FeeStructure.is_active == True)
            .filter((FeeStructure.arm_id == None) | (FeeStructure.arm_id == arm_id))
            .all())
    # item_id -> (amount, arm_specific?) so arm rows win over all-arm rows.
    chosen = {}
    for r in rows:
        specific = r.arm_id is not None
        cur = chosen.get(r.fee_item_id)
        if cur is None or (specific and not cur[1]):
            chosen[r.fee_item_id] = (r.amount, specific)
    if not chosen:
        return []
    items = {i.id: i for i in FeeItem.query.filter(FeeItem.id.in_(chosen.keys())).all()}
    out = [(items[iid], amt) for iid, (amt, _) in chosen.items() if iid in items]
    out.sort(key=lambda t: t[0].name.lower())
    return out


def class_fee_total(term_id, class_id, arm_id=None):
    """Total expected fee for a single student in this class/arm/term."""
    return sum(amt for _, amt in structure_items(term_id, class_id, arm_id))


def student_bill(student_id, term_id):
    """
    Full fee picture for a student in a term.

    Returns dict: lines [(FeeItem, amount)], billed, discount, paid, balance.
    """
    class_id, arm_id = student_placement(student_id, term_id)
    lines = structure_items(term_id, class_id, arm_id) if class_id else []
    billed = sum(amt for _, amt in lines)

    discount = (db.session.query(func.coalesce(func.sum(FeeDiscount.amount), 0.0))
                .filter(FeeDiscount.student_id == student_id,
                        FeeDiscount.term_id == term_id).scalar()) or 0.0
    paid = (db.session.query(func.coalesce(func.sum(FeePayment.amount), 0.0))
            .filter(FeePayment.student_id == student_id,
                    FeePayment.term_id == term_id).scalar()) or 0.0

    payable = max(billed - discount, 0)
    return {
        'class_id': class_id,
        'arm_id': arm_id,
        'lines': lines,
        'billed': billed,
        'discount': discount,
        'paid': paid,
        'payable': payable,
        'balance': payable - paid,
    }


def next_receipt_no():
    """
    Monotonic receipt number like RCP-000123.

    Uses a persistent high-water counter in SchoolSettings so numbers are never
    reused after a payment is deleted (deriving from the latest row id alone
    would re-issue a just-freed id). Seeded from existing rows for legacy data.
    """
    from models import SchoolSettings
    last = FeePayment.query.order_by(FeePayment.id.desc()).first()
    by_id = last.id if last else 0
    seq = int(SchoolSettings.get('fee_receipt_seq', 0) or 0)
    n = max(by_id, seq) + 1
    SchoolSettings.set('fee_receipt_seq', n, 'int', 'Fee receipt counter')
    return f'RCP-{n:06d}'


def collection_trend(term_id, weeks=12):
    """Total collected per ISO week for a term — [{label, amount}, ...]."""
    if not term_id:
        return []
    rows = (db.session.query(FeePayment.payment_date, FeePayment.amount)
            .filter(FeePayment.term_id == term_id).all())
    if not rows:
        return []
    buckets = {}
    for d, amt in rows:
        key = d.isocalendar()[:2] if d else (0, 0)  # (year, week)
        buckets[key] = buckets.get(key, 0.0) + (amt or 0)
    ordered = sorted(buckets.items())[-weeks:]
    out = []
    for (yr, wk), amt in ordered:
        out.append({'label': f'W{wk}', 'amount': round(amt, 2)})
    return out


def fee_item_breakdown(term_id):
    """
    Expected revenue per fee item across all enrolled students in a term:
    [{name, amount}, ...] sorted high→low. Used for the income-mix chart.
    """
    if not term_id:
        return []
    enrollments = (StudentEnrollment.query
                   .join(ClassArmAssignment,
                         StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
                   .filter(StudentEnrollment.is_active == True,
                           ClassArmAssignment.term_id == term_id).all())
    # count students per (class, arm)
    counts = {}
    for e in enrollments:
        asg = e.class_arm_assignment
        counts[(asg.class_id, asg.arm_id)] = counts.get((asg.class_id, asg.arm_id), 0) + 1
    totals = {}  # fee_item_id -> amount
    for (class_id, arm_id), n in counts.items():
        for item, amt in structure_items(term_id, class_id, arm_id):
            totals[item.id] = totals.get(item.id, 0.0) + amt * n
    if not totals:
        return []
    items = {i.id: i for i in FeeItem.query.filter(FeeItem.id.in_(totals.keys())).all()}
    out = [{'name': items[iid].name, 'amount': round(amt, 2)}
           for iid, amt in totals.items() if iid in items]
    out.sort(key=lambda x: x['amount'], reverse=True)
    return out
