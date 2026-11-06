"""Find and merge duplicate student records.

Typical cause: the same pupil entered twice, once as "JOHN OKAFOR MARY" and
once as "Okafor John" (maybe with a middle name). Merging keeps one record
(the *keeper*), moves everything that belongs to the duplicate onto it — exam
results (WAEC, JAMB, BECE / Common Entrance, mocks), scores, enrolments,
attendance, fees, CBT, library… every table that points at ``students.id`` —
fills any empty keeper fields from the duplicate (e.g. its middle name), and
then deletes the now-empty duplicate.

Moving rows is done generically from the SQLAlchemy metadata, so new tables
that reference students are covered automatically. Where both records hold
the same unique thing (e.g. a Mathematics WAEC grade for the same year), the
most recently updated row wins (the keeper's when there's no timestamp); the
loser is removed after anything pointing at it has been moved to the winner.
"""
from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy import select, update, delete, and_, func

from models import db, Student

# Student columns never copied from the duplicate onto the keeper.
_NO_COPY = {'id', 'student_id', 'created_at', 'updated_at', 'surname', 'first_name'}


# --------------------------------------------------------------------------- #
# Schema discovery
# --------------------------------------------------------------------------- #
def _students_table():
    return Student.__table__


def student_refs():
    """[(table, column)] for every column that references a student: real
    foreign keys to students.id, plus integer ``student_id`` columns that
    were added without a constraint."""
    out = []
    st = _students_table()
    for t in db.metadata.sorted_tables:
        if t is st:
            continue
        for c in t.columns:
            fk = any(f.column.table is st for f in c.foreign_keys)
            loose = (c.name == 'student_id' and not c.foreign_keys
                     and str(c.type).upper().startswith('INT'))
            if fk or loose:
                out.append((t, c))
    return out


def _unique_sets(table, col):
    """Column-name tuples of every unique constraint / index on ``table`` that
    includes ``col`` (single-column unique included)."""
    sets = []
    for cons in table.constraints:
        if cons.__class__.__name__ == 'UniqueConstraint':
            names = tuple(c.name for c in cons.columns)
            if col.name in names:
                sets.append(names)
    for idx in table.indexes:
        if idx.unique:
            names = tuple(c.name for c in idx.columns)
            if col.name in names:
                sets.append(names)
    if col.unique:
        sets.append((col.name,))
    return list(dict.fromkeys(sets))


def _dependents(table):
    """[(dep_table, dep_col)] — columns elsewhere with a FK to ``table.id``."""
    out = []
    for t in db.metadata.sorted_tables:
        for c in t.columns:
            if any(f.column.table is table and f.column.name == 'id' for f in c.foreign_keys):
                out.append((t, c))
    return out


# --------------------------------------------------------------------------- #
# Row moving with conflict handling
# --------------------------------------------------------------------------- #
def _repoint(table, col, old_id, new_id, depth=0):
    """Point every row of ``table`` whose ``col`` == old_id at new_id. A row
    that would then clash with an existing one (unique constraint) is a
    conflict: resolved by ``_resolve`` (one survives, the other goes)."""
    if old_id == new_id or depth > 6:
        return
    uniq = _unique_sets(table, col)
    pk = table.c.id
    rows = db.session.execute(select(table).where(col == old_id)).mappings().all()
    if not uniq:
        if rows:
            db.session.execute(update(table).where(col == old_id).values({col.name: new_id}))
        return
    for row in rows:
        clash = None
        for names in uniq:
            cond = [col == new_id] + [table.c[n] == row[n] for n in names if n != col.name]
            clash = db.session.execute(select(table).where(and_(*cond))).mappings().first()
            if clash is not None:
                break
        if clash is None:
            db.session.execute(update(table).where(pk == row['id']).values({col.name: new_id}))
            continue
        _resolve(table, col, moving=row, existing=clash, new_id=new_id, depth=depth)


def _newer(a, b):
    """True when row ``a`` was updated more recently than ``b``."""
    for k in ('updated_at', 'created_at'):
        if k in a and a.get(k) and b.get(k):
            return a[k] > b[k]
    return False


def _resolve(table, col, moving, existing, new_id, depth):
    """Two rows clash on a unique key. Keep the more recently updated one
    (the existing/keeper row on a tie); move dependents of the loser to the
    winner, then delete the loser."""
    pk = table.c.id
    if _newer(moving, existing):
        winner, loser = moving, existing
    else:
        winner, loser = existing, moving
    for dt, dc in _dependents(table):
        _repoint(dt, dc, loser['id'], winner['id'], depth + 1)
    db.session.execute(delete(table).where(pk == loser['id']))
    if winner['id'] == moving['id']:
        db.session.execute(update(table).where(pk == moving['id']).values({col.name: new_id}))


def merge_students(keeper_id, dup_ids):
    """Merge each duplicate into ``keeper_id``. Returns a report dict.
    Caller commits (or rolls back)."""
    keeper = db.session.get(Student, keeper_id)
    if keeper is None:
        raise ValueError('The student to keep no longer exists.')
    st = _students_table()
    report = {'keeper': keeper.full_name, 'merged': [], 'filled': []}
    for dup_id in dup_ids:
        if dup_id == keeper_id:
            continue
        dup = db.session.get(Student, dup_id)
        if dup is None:
            continue
        # 1. Fill the keeper's blank fields (middle name, DOB, phone …).
        for c in st.columns:
            if c.name in _NO_COPY:
                continue
            kv, dv = getattr(keeper, c.key, None), getattr(dup, c.key, None)
            if (kv is None or kv == '') and dv not in (None, ''):
                if c.name == 'middle_name' and isinstance(dv, str) and dv.isupper():
                    dv = dv.title()
                setattr(keeper, c.key, dv)
                report['filled'].append(c.name)
        if dup.is_graduated and not keeper.is_graduated:
            keeper.is_graduated = True
        db.session.flush()
        name, code = dup.full_name, dup.student_id
        # 2. Move every referencing row (enrolments first, so attendance /
        #    term summaries hanging off a clashing enrolment follow it).
        refs = sorted(student_refs(), key=lambda tc: tc[0].name != 'student_enrollments')
        for table, col in refs:
            _repoint(table, col, dup_id, keeper_id)
        # 3. Drop the empty duplicate (Core delete: its ORM collections are stale).
        db.session.expunge(dup)
        db.session.execute(delete(st).where(st.c.id == dup_id))
        report['merged'].append({'name': name, 'student_id': code})
    db.session.flush()
    db.session.expire_all()
    return report


# --------------------------------------------------------------------------- #
# Finding duplicates
# --------------------------------------------------------------------------- #
def _tok(s):
    return re.sub(r'[^a-z]', '', (s or '').lower())


def name_key(st):
    """Duplicate key: surname + first name, ignoring case, punctuation and
    their order. The middle name is ignored (one record may lack it)."""
    a, b = _tok(st.surname), _tok(st.first_name)
    if not a or not b:
        return None
    return tuple(sorted((a, b)))


def is_all_caps(st):
    letters = re.sub(r'[^A-Za-z]', '', ' '.join(filter(None, (st.surname, st.first_name, st.middle_name))))
    return bool(letters) and letters.isupper()


def linked_counts(ids):
    """{student_id: {table_name: n}} for the given students."""
    out = defaultdict(dict)
    ids = list(ids)
    if not ids:
        return out
    for table, col in student_refs():
        try:
            rows = db.session.execute(select(col, func.count()).where(col.in_(ids)).group_by(col)).all()
        except Exception:
            db.session.rollback()
            continue
        for sid, n in rows:
            out[sid][table.name] = out[sid].get(table.name, 0) + n
    return out


_SUMMARY = [('waec_results', 'WAEC'), ('jamb_results', 'JAMB'),
            ('school_exam_results', 'BECE / CE'), ('mock_waec_results', 'Mock WAEC'),
            ('mock_jamb_results', 'Mock JAMB'), ('student_scores', 'Scores'),
            ('student_enrollments', 'Enrolments'), ('fee_payments', 'Payments')]


def find_groups(class_id=None, search=None):
    """Groups of 2+ active students that look like the same person, each with
    a suggested keeper (proper case before ALL CAPS, then the one with more
    saved data, then the older record)."""
    from utils.branch_scope import scope_query
    from models import ClassArmAssignment, StudentEnrollment
    students = scope_query(Student.query.filter(Student.is_active == True), Student).all()  # noqa: E712
    buckets = defaultdict(list)
    for s in students:
        k = name_key(s)
        if k:
            buckets[k].append(s)
    groups = [g for g in buckets.values() if len(g) > 1]
    if not groups:
        return []
    ids = [s.id for g in groups for s in g]
    # Current class (latest active enrolment) for display + the class filter.
    cls = {}
    for sid, caa in (db.session.query(StudentEnrollment.student_id, ClassArmAssignment)
                     .join(ClassArmAssignment, ClassArmAssignment.id == StudentEnrollment.class_arm_assignment_id)
                     .filter(StudentEnrollment.student_id.in_(ids), StudentEnrollment.is_active == True)  # noqa: E712
                     .order_by(ClassArmAssignment.term_id).all()):
        cls[sid] = (caa.class_id, caa.display_name)
    counts = linked_counts(ids)
    q = (search or '').strip().lower()
    out = []
    for g in groups:
        if class_id and not any(cls.get(s.id, (None,))[0] == class_id for s in g):
            continue
        if q and not any(q in (s.full_name or '').lower() or q in (s.student_id or '').lower() for s in g):
            continue
        members = []
        for s in g:
            c = counts.get(s.id, {})
            members.append({
                'student': s, 'id': s.id, 'all_caps': is_all_caps(s),
                'class': cls.get(s.id, (None, ''))[1],
                'total': sum(c.values()),
                'summary': [(label, c[t]) for t, label in _SUMMARY if c.get(t)],
            })
        members.sort(key=lambda m: (m['all_caps'], -m['total'], m['id']))
        keeper = members[0]
        # Namesakes / siblings: records currently in different classes, or with
        # different dates of birth, may be two real pupils — flag, never auto-pick.
        classes_now = {cls[s.id][0] for s in g if s.id in cls}
        dobs = {s.date_of_birth for s in g if getattr(s, 'date_of_birth', None)}
        warn = []
        if len(classes_now) > 1:
            warn.append('These records are in different classes right now')
        if len(dobs) > 1:
            warn.append('These records have different dates of birth')
        out.append({'key': '-'.join(sorted(str(m['id']) for m in members)),
                    'members': members, 'keeper_id': keeper['id'], 'warnings': warn,
                    'has_caps_dup': (any(m['all_caps'] for m in members[1:]) and not keeper['all_caps']
                                     and not warn)})
    out.sort(key=lambda g: g['members'][0]['student'].full_name.lower())
    return out
