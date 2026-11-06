"""Roster placement for external-exam result entry (WAEC / JSS3 / Basic 6).

When results are entered by list (quick entry / CSV), every candidate must end up
in the exam's class — SSS3 for WAEC, JSS3 for BECE, Basic 6 for Common Entrance —
for the academic session the results belong to. This module plans and applies
that, behind a single approval:

* a name that matches a student who is **not** in the class for that session
  → **move** them into it (their other enrolment that term is deactivated);
* a name that matches nobody → **create** the student, splitting the name on
  spaces as ``Surname First Middle…`` (the order the app displays names in),
  then place them in the class.

"That academic session" is the session whose exam year equals the year being
entered (``2026`` → ``2025/2026``), because WAEC / BECE / Common Entrance results
usually arrive after the cohort has been promoted — placing them in the class of
the *current* session would demote students who have already moved up. The
placement term is the session's active term if it is the live session, else its
last term.

Nothing here commits; callers commit once with the saved results.
"""
from __future__ import annotations

import re

from models import db, Student

LEVEL_LABEL = {'sss3': 'SSS3', 'jss3': 'JSS3', 'basic6': 'Basic 6'}
SCHOOL_WIDE_MATCH = 0.92


def level_class(level):
    if level == 'sss3':
        from utils.helpers import get_sss3_class
        return get_sss3_class()
    from utils.school_exams import find_level_class
    return find_level_class(level)


def session_for_year(year):
    """The AcademicSession whose exam year is ``year``; prefers the active one."""
    from models import AcademicSession
    from utils.helpers import session_exam_year, get_active_session
    act = get_active_session()
    if act is not None and session_exam_year(act) == year:
        return act
    for s in AcademicSession.query.order_by(AcademicSession.id.desc()).all():
        if session_exam_year(s) == year:
            return s
    return None


def placement_target(level, year):
    """Where list-entered candidates for ``year`` are placed.

    Returns a dict ``{cls, session, term, arms: [ClassArmAssignment]}`` or
    ``{'error': message}`` when the class / session / term / arms are missing."""
    from models import Term, ClassArmAssignment
    from utils.helpers import get_active_term
    from utils.branch_scope import scope_query
    label = LEVEL_LABEL[level]
    cls = level_class(level)
    if cls is None:
        return {'error': f'There is no {label} class yet — create it under Academics first.'}
    sess = session_for_year(year)
    if sess is None:
        return {'error': f'No academic session matches the exam year {year}, so students '
                         f'cannot be placed in {label} for it.'}
    term = get_active_term()
    if term is None or term.session_id != sess.id:
        term = (Term.query.filter_by(session_id=sess.id)
                .order_by(Term.term_number.desc()).first())
    if term is None:
        return {'error': f'{sess.name} has no terms, so students cannot be placed in {label}.'}
    arms = scope_query(ClassArmAssignment.query.filter_by(class_id=cls.id, term_id=term.id),
                       ClassArmAssignment).all()
    if not arms:
        return {'error': f'{label} has no class arm set up for {term.name} ({sess.name}) — '
                         f'add one under Academics first.'}
    arms.sort(key=lambda a: (a.arm.name if a.arm else ''))
    return {'cls': cls, 'session': sess, 'term': term, 'arms': arms}


def in_class_ids(cls, session_id, student_ids):
    """Of ``student_ids``, those actively enrolled in ``cls`` in any term of the
    session (graduates keep their enrolment, so they count)."""
    from models import ClassArmAssignment, StudentEnrollment, Term
    if not student_ids:
        return set()
    rows = (db.session.query(StudentEnrollment.student_id)
            .join(ClassArmAssignment, ClassArmAssignment.id == StudentEnrollment.class_arm_assignment_id)
            .join(Term, Term.id == ClassArmAssignment.term_id)
            .filter(ClassArmAssignment.class_id == cls.id, Term.session_id == session_id,
                    StudentEnrollment.is_active == True,               # noqa: E712
                    StudentEnrollment.student_id.in_(list(student_ids)))
            .distinct().all())
    return {r[0] for r in rows}


def split_name(name):
    """``"John Okafor Mary"`` → ``('John', 'Okafor', 'Mary')`` as
    (surname, first name, middle name). Needs at least two words."""
    words = [w for w in re.split(r'\s+', (name or '').strip()) if w]
    words = [w[:50].strip('.,') for w in words if w.strip('.,')]
    if len(words) < 2:
        return None
    surname, first = words[0].title(), words[1].title()
    middle = ' '.join(words[2:]).title()[:50] or None
    return surname, first, middle


def can_change_roster():
    """Creating / moving students needs students-module edit rights (admins
    always). SSS3 arm teachers with derived exam access cannot."""
    from utils.access_control import is_admin, can_write_module
    try:
        return is_admin() or can_write_module('students')
    except Exception:
        return False


def plan(rows, level, year, roster):
    """Annotate parsed rows (each with ``name`` and ``student`` — matched against
    ``roster`` or None) with a placement plan, matching unmatched names against
    the rest of the school first.

    Sets on each row: ``placement`` ∈ {None, 'move', 'create'}, ``new_name``
    (surname, first, middle) for creates, ``from_class`` for moves. Returns a
    summary ``{'target', 'moves', 'creates', 'allowed', 'error'}``."""
    from utils.waec_ocr import match_students_unique
    from utils.branch_scope import scope_query
    label = LEVEL_LABEL[level]
    target = placement_target(level, year)
    allowed = can_change_roster()
    no_match = f'No {label}'

    # 1. Unmatched names — and names with only a weak match in the class —
    # are looked up across the rest of the school (branch-scoped), so an exact
    # match outside the class (e.g. the pupil is still in SSS2) beats a loose
    # in-class look-alike instead of becoming a duplicate "new" student.
    for r in rows:
        if r.get('student') is not None and (r.get('score') or 0) < SCHOOL_WIDE_MATCH:
            r['_weak'] = (r['student'], r.get('score') or 0)
            r['student'], r['score'] = None, 0.0
    unmatched = [r for r in rows if r.get('student') is None]
    if unmatched:
        roster_ids = {s.id for s in roster}
        others = [s for s in scope_query(Student.query.filter_by(is_active=True), Student).all()
                  if s.id not in roster_ids]
        # An exact Student ID (CSV imports) beats any fuzzy name match.
        by_code = {(s.student_id or '').strip().lower(): s for s in others}
        for r in list(unmatched):
            st = by_code.get((r.get('code') or '').strip().lower()) if r.get('code') else None
            if st is not None:
                r['student'], r['score'] = st, 1.0
                r['errors'] = [e for e in r['errors'] if 'candidate matches' not in e]
                others.remove(st)
                unmatched.remove(r)
        for row, (st, sc) in zip(unmatched, match_students_unique([r['name'] for r in unmatched], others)):
            # Outside the class a loose match could move the wrong pupil, so only
            # a near-certain name match counts; anything weaker becomes "new".
            if st is not None and sc < SCHOOL_WIDE_MATCH:
                row['suggest'], row['suggest_inside'] = st, False
            if st is not None and sc >= SCHOOL_WIDE_MATCH:
                row['student'], row['score'] = st, sc
                row['errors'] = [e for e in row['errors'] if not e.startswith(no_match)
                                 and 'candidate matches' not in e]

    # No better match outside the class: fall back to the weak in-class one
    # (offered as a suggestion below, never trusted on its own).
    for r in rows:
        weak = r.pop('_weak', None)
        if weak and r.get('student') is None:
            r['student'], r['score'] = weak
            r['errors'] = [e for e in r['errors'] if 'candidate matches' not in e]

    # 2. Matched but not in the class for that session → move.
    matched = [r for r in rows if r.get('student') is not None]
    inside = set()
    if 'error' not in target:
        inside = in_class_ids(target['cls'], target['session'].id, {r['student'].id for r in matched})
    # A move changes someone's class, so it needs a near-certain name match
    # wherever the match came from (the roster can be the whole school before
    # the class is set up). A weaker match to someone outside the class is
    # treated as a new student instead — visible on the approval list.
    # Any weak match (one shared word, a spelling stretch) is not trusted now
    # that unknown names are added: it becomes a new student by default, with
    # the possible match offered on the approval list ("use existing").
    for r in matched:
        if (r.get('score') or 0) < SCHOOL_WIDE_MATCH:
            r['suggest'] = r['student']
            r['suggest_inside'] = r['student'].id in inside
            r['student'], r['score'] = None, 0.0
    matched = [r for r in matched if r.get('student') is not None]
    current = _current_class_names({r['student'].id for r in matched}, target)
    for r in rows:
        r['placement'], r['new_name'], r['from_class'] = None, None, None
        st = r.get('student')
        if st is not None:
            if 'error' not in target and st.id not in inside:
                r['placement'] = 'move'
                r['from_class'] = current.get(st.id)
        else:
            nm = split_name(r['name'])
            if nm:
                r['placement'] = 'create'
                r['new_name'] = nm
                r['errors'] = [e for e in r['errors'] if 'candidate matches' not in e]
            else:
                r['errors'] = [e for e in r['errors'] if 'candidate matches' not in e]
                r['errors'].insert(0, f'"{r["name"]}" matches nobody, and a new student needs at '
                                      f'least a surname and a first name.')
        r['blocked'] = bool(r['placement']) and ('error' in target or not allowed)
        if r['blocked']:
            why = target.get('error') or ('only staff who can edit Students may add or move '
                                          'students — ask an admin.')
            if r['placement'] == 'move':
                # Results still save (as before); the student just isn't moved.
                r['warnings'] = [f'Not in {label} for {year} and can\'t be moved: {why}']
            else:
                r['errors'].insert(0, f'Not on the register and can\'t be added: {why}')
    return {'target': target, 'allowed': allowed, 'label': label, 'year': year,
            'error': target.get('error'),
            'moves': [r for r in rows if r['placement'] == 'move' and not r['blocked']],
            'creates': [r for r in rows if r['placement'] == 'create' and not r['blocked']]}


def _current_class_names(student_ids, target):
    """{student_id: 'JSS2 Gold'} — each student's active class in the placement
    term (or their latest active class), for the approval list."""
    from models import ClassArmAssignment, StudentEnrollment
    if not student_ids:
        return {}
    q = (db.session.query(StudentEnrollment.student_id, ClassArmAssignment)
         .join(ClassArmAssignment, ClassArmAssignment.id == StudentEnrollment.class_arm_assignment_id)
         .filter(StudentEnrollment.student_id.in_(list(student_ids)),
                 StudentEnrollment.is_active == True)                 # noqa: E712
         .order_by(ClassArmAssignment.term_id))
    out = {}
    term_id = target.get('term').id if target.get('term') else None
    for sid, caa in q.all():
        name = getattr(caa, 'display_name', None) or (caa.school_class.name if caa.school_class else '')
        if term_id is None or caa.term_id <= term_id:
            out[sid] = name
    return out


def create_student(surname, first, middle=None, gender=None):
    """Add a student to the register (current branch, generated ID). Flushes."""
    from utils.branch_scope import branch_for_new
    bid = branch_for_new()
    st = Student(surname=(surname or '').strip()[:50].title(), first_name=(first or '').strip()[:50].title(),
                 middle_name=((middle or '').strip()[:50].title() or None),
                 gender=(gender if gender in ('Male', 'Female') else ''), branch_id=bid,
                 is_active=True, student_id=Student.generate_student_id(bid))
    db.session.add(st)
    db.session.flush()
    return st


def place(student, target, arm_id=None):
    """Enrol ``student`` in the target class for the placement term, switching
    off any other active enrolment that term. Returns False when the class has
    no arm in the student's branch."""
    from models import StudentEnrollment, ClassArmAssignment
    cands = [a for a in target['arms'] if a.branch_id in (student.branch_id, None)] or \
            ([] if student.branch_id else target['arms'])
    caa = next((a for a in cands if arm_id and a.arm_id == arm_id), None) or (cands[0] if cands else None)
    if caa is None:
        return False
    for e in (StudentEnrollment.query.join(ClassArmAssignment,
              ClassArmAssignment.id == StudentEnrollment.class_arm_assignment_id)
              .filter(StudentEnrollment.student_id == student.id,
                      StudentEnrollment.is_active == True,             # noqa: E712
                      ClassArmAssignment.term_id == target['term'].id,
                      StudentEnrollment.class_arm_assignment_id != caa.id).all()):
        e.is_active = False
    e = StudentEnrollment.query.filter_by(student_id=student.id, class_arm_assignment_id=caa.id).first()
    if e is None:
        db.session.add(StudentEnrollment(student_id=student.id, class_arm_assignment_id=caa.id,
                                         is_active=True))
    else:
        e.is_active = True
    db.session.flush()
    return True


def apply(plan_summary, include, arm_id=None, genders=None, use_existing=None):
    """Create / move the approved rows. ``include`` is the set of row line
    numbers ticked on the approval list; ``arm_id`` the ClassArm to place them
    in (else the class's first arm); ``genders`` {line: 'Male'|'Female'} for new
    students; ``use_existing`` lines whose possible match the approver chose.
    Returns ``(created, moved, skipped_lines)``; rows that could not be placed
    get ``student`` cleared so their results are not saved."""
    target = plan_summary['target']
    if 'error' in target:
        return 0, 0, []
    genders = genders or {}
    use_existing = use_existing or set()
    created = moved = 0
    skipped = []
    for row in plan_summary['creates'] + plan_summary['moves']:
        if row['line'] not in include:
            row['student'] = None
            skipped.append(row['line'])
            continue
        if row['placement'] == 'create' and row['line'] in use_existing and row.get('suggest'):
            # The approver said the possible match IS this student.
            row['student'], row['placement'] = row['suggest'], 'move'
            if row.get('suggest_inside'):
                continue                      # already in the class — just save results
        elif row['placement'] == 'create':
            row['student'] = create_student(*row['new_name'], gender=genders.get(row['line']))
            created += 1
        if not place(row['student'], target, arm_id):
            row['errors'].append(f'No {plan_summary["label"]} arm in this student\'s branch.')
            row['student'] = None
            skipped.append(row['line'])
            continue
        if row['placement'] == 'move':
            moved += 1
    return created, moved, skipped


def recount(preview):
    """Refresh ``n_ready`` / ``n_results`` after planning: a row is ready when it
    has results and either a student or an approved-to-create name."""
    ready = [r for r in preview['rows'] if r['items'] and (
        r.get('student') is not None or (r.get('placement') == 'create' and not r.get('blocked')))]
    preview['n_ready'] = len(ready)
    preview['n_results'] = sum(len(r['items']) for r in ready)
    return preview


def approval_from_form(form):
    """(approved, include_lines, arm_id, genders) from the approval panel."""
    include = set()
    for v in form.getlist('inc'):
        try:
            include.add(int(v))
        except (TypeError, ValueError):
            pass
    genders = {}
    for k, v in form.items():
        if k.startswith('g_') and v in ('Male', 'Female'):
            try:
                genders[int(k[2:])] = v
            except ValueError:
                pass
    use_existing = set()
    for k, v in form.items():
        if k.startswith('use_') and v == 'existing':
            try:
                use_existing.add(int(k[4:]))
            except ValueError:
                pass
    return (bool(form.get('approve_roster')), include, form.get('arm_id', type=int), genders,
            use_existing)
