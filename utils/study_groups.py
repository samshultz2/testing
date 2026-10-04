"""Study/project group allocation (Tools -> Study Groups).

The allocation itself (``allocate_groups``) is a pure function over plain
data -- no Flask, no DB -- so it's cheap to test exhaustively. Everything
else here resolves the DB inputs it needs (candidate students, their
previous-term average) and persists the result.
"""
from __future__ import annotations

import random
from math import ceil


def allocate_groups(students_with_basis, group_size):
    """Split students into groups, balanced by prior performance.

    ``students_with_basis``: list of ``(student_id, basis_average_or_None)``.
    A None basis means no usable prior-term data (new student, or none
    existed at all) -- these are placed randomly, never as leaders unless
    there aren't enough ranked students to lead every group.

    Returns a list of ``{'members': [student_id, ...], 'leader_id': student_id}``,
    one dict per group, in order. The leader is always first in ``members``.
    Group count is ``ceil(total / group_size)``; sizes differ by at most 1.

    Deterministic for the ranked part (same input -> same groups); the
    unranked part is shuffled, so pass a seeded ``random.Random`` via the
    module-level ``random`` state in a test if exact reproducibility of the
    random leftovers is needed (tests instead just assert the invariants that
    must hold regardless of shuffle order).
    """
    total = len(students_with_basis)
    if total == 0 or group_size < 1:
        return []
    num_groups = ceil(total / group_size)

    ranked = sorted((s for s in students_with_basis if s[1] is not None),
                    key=lambda s: -s[1])
    unranked = [s for s in students_with_basis if s[1] is None]
    random.shuffle(unranked)

    groups = [{'members': [], 'leader_id': None} for _ in range(num_groups)]

    leaders, rest_ranked = ranked[:num_groups], ranked[num_groups:]
    for i, (sid, _avg) in enumerate(leaders):
        groups[i]['members'].append(sid)
        groups[i]['leader_id'] = sid

    # Snake draft the remaining ranked students (0,1,..,N-1,N-1,..,1,0,...) so
    # each group ends up with a similar spread of ability, not "the best
    # leftovers all in group 1".
    _snake_fill(groups, rest_ranked, num_groups)

    # Round-robin fill the unranked (random-order) students.
    g = 0
    for sid, _avg in unranked:
        groups[g]['members'].append(sid)
        g = (g + 1) % num_groups

    # A class with fewer ranked students than groups leaves some groups
    # leaderless by the ranking above -- promote whoever ended up in that
    # group (random is fine; the admin can always reassign the leader).
    for grp in groups:
        if grp['leader_id'] is None and grp['members']:
            grp['leader_id'] = grp['members'][0]

    return groups


def _snake_fill(groups, items, num_groups):
    """Deal ``items`` across ``groups`` in snake order: 0..N-1, N-1..0, repeat."""
    order = []
    forward = True
    while len(order) < len(items):
        order.extend(range(num_groups) if forward else range(num_groups - 1, -1, -1))
        forward = not forward
    for (sid, _avg), g in zip(items, order):
        groups[g]['members'].append(sid)


def previous_term_for_grouping(term):
    """The term whose TermSummary.average_score should rank students for a
    group-set targeting ``term``: the prior term in the same session, or --
    when ``term`` is a session's first term -- the last term of the session
    immediately before it. Sessions have no reliable cross-school ordering
    field other than creation order, so "the session before" is simply the
    one with the next-lower id (sessions are always created in chronological
    order). Returns None when neither exists (the school's very first term)."""
    from models import Term, AcademicSession
    if term and term.term_number and term.term_number > 1:
        prior = Term.query.filter_by(session_id=term.session_id,
                                     term_number=term.term_number - 1).first()
        if prior:
            return prior
    if not term:
        return None
    prev_session = (AcademicSession.query
                    .filter(AcademicSession.id < term.session_id)
                    .order_by(AcademicSession.id.desc()).first())
    if prev_session:
        return (Term.query.filter_by(session_id=prev_session.id)
                .order_by(Term.term_number.desc()).first())
    return None


def candidate_students(class_id, arm_ids, term_id):
    """Active students enrolled in ``class_id`` under any of ``arm_ids`` for
    ``term_id`` -- the candidate pool for one grouping run. Merging arms here
    never touches ClassArmAssignment/StudentEnrollment; it only widens which
    rows this query reads."""
    from models import ClassArmAssignment, StudentEnrollment, Student
    caa_ids = [row.id for row in ClassArmAssignment.query.filter(
        ClassArmAssignment.class_id == class_id,
        ClassArmAssignment.arm_id.in_(arm_ids),
        ClassArmAssignment.term_id == term_id).all()]
    if not caa_ids:
        return []
    student_ids = [row.student_id for row in StudentEnrollment.query.filter(
        StudentEnrollment.class_arm_assignment_id.in_(caa_ids),
        StudentEnrollment.is_active.is_(True)).all()]
    if not student_ids:
        return []
    return (Student.query.filter(Student.id.in_(student_ids))
            .order_by(Student.surname, Student.first_name).all())


def basis_averages_for(student_ids, basis_term_id):
    """{student_id: average_score} from TermSummary for ``basis_term_id`` --
    a student missing from the result has no usable prior data (treat as
    None, i.e. random placement)."""
    from models import TermSummary
    if not basis_term_id or not student_ids:
        return {}
    rows = TermSummary.query.filter(
        TermSummary.term_id == basis_term_id,
        TermSummary.student_id.in_(student_ids)).all()
    return {r.student_id: r.average_score for r in rows if r.average_score is not None}


def create_group_set(*, branch_id, class_id, arm_ids, term_id, group_size, title, created_by):
    """Resolve candidates + their basis averages, allocate groups, and
    persist the result as a new GroupSet. Raises ValueError if there are no
    candidate students for that class/arm/term selection."""
    from models import db, Term, GroupSet, StudentGroup, GroupMember
    term = db.session.get(Term, term_id)
    students = candidate_students(class_id, arm_ids, term_id)
    if not students:
        raise ValueError('No active students found for that class/arm selection in this term.')

    basis_term = previous_term_for_grouping(term)
    basis_map = basis_averages_for([s.id for s in students],
                                   basis_term.id if basis_term else None)
    students_with_basis = [(s.id, basis_map.get(s.id)) for s in students]
    groups = allocate_groups(students_with_basis, group_size)

    gs = GroupSet(branch_id=branch_id, class_id=class_id,
                  arm_ids=','.join(str(a) for a in arm_ids), term_id=term_id,
                  basis_term_id=basis_term.id if basis_term else None,
                  group_size=group_size, num_groups=len(groups), title=title,
                  created_by=created_by)
    db.session.add(gs)
    db.session.flush()

    for i, grp in enumerate(groups, start=1):
        sg = StudentGroup(group_set_id=gs.id, position=i, label=f'Group {i}')
        db.session.add(sg)
        db.session.flush()
        for sid in grp['members']:
            db.session.add(GroupMember(group_set_id=gs.id, group_id=sg.id, student_id=sid,
                                       basis_average=basis_map.get(sid)))
        sg.leader_student_id = grp['leader_id']
    db.session.commit()
    return gs


def move_student(group_set_id, student_id, new_group_id):
    """Move a student to a different group within the same set. If they were
    their old group's leader, promote the remaining member with the highest
    basis average (or just the first remaining member) so the group isn't
    left leaderless -- the admin can always reassign it afterward."""
    from models import db, GroupMember, StudentGroup
    member = GroupMember.query.filter_by(group_set_id=group_set_id, student_id=student_id).first()
    if not member:
        raise ValueError('That student is not in this group set.')
    new_group = StudentGroup.query.filter_by(id=new_group_id, group_set_id=group_set_id).first()
    if not new_group:
        raise ValueError('Target group not found in this set.')
    old_group_id = member.group_id
    if old_group_id == new_group_id:
        return
    old_group = db.session.get(StudentGroup, old_group_id)
    member.group_id = new_group_id
    db.session.flush()
    if old_group and old_group.leader_student_id == student_id:
        remaining = (GroupMember.query.filter_by(group_id=old_group.id)
                    .order_by(GroupMember.basis_average.is_(None),
                             GroupMember.basis_average.desc()).first())
        old_group.leader_student_id = remaining.student_id if remaining else None
    db.session.commit()


def set_leader(group_set_id, group_id, student_id):
    """Make ``student_id`` the leader of ``group_id`` -- they must already be
    a member of that group."""
    from models import db, StudentGroup, GroupMember
    group = StudentGroup.query.filter_by(id=group_id, group_set_id=group_set_id).first()
    if not group:
        raise ValueError('Group not found in this set.')
    member = GroupMember.query.filter_by(group_id=group_id, student_id=student_id).first()
    if not member:
        raise ValueError('That student is not a member of this group.')
    group.leader_student_id = student_id
    db.session.commit()
