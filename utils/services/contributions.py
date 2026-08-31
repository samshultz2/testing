"""Contribution-fund aggregates (the SSS3 graduation fund).

Replaces per-student ``SUM`` loops in the routes with single GROUP BY queries.
"""
from sqlalchemy import func

from models import db, ContributionPayment


def paid_by_student(session_id, student_ids=None):
    """``{student_id: total_paid}`` for a session in ONE query.

    Students with no payments simply aren't in the map — callers use
    ``.get(id, 0)``. Pass ``student_ids`` to bound the scan to a class roster.
    """
    q = db.session.query(
        ContributionPayment.student_id,
        func.coalesce(func.sum(ContributionPayment.amount), 0.0))
    if session_id is not None:
        q = q.filter(ContributionPayment.session_id == session_id)
    else:
        q = q.filter(ContributionPayment.session_id.is_(None))
    if student_ids is not None:
        if not student_ids:
            return {}
        q = q.filter(ContributionPayment.student_id.in_(list(student_ids)))
    return {sid: float(total) for sid, total in q.group_by(ContributionPayment.student_id).all()}
