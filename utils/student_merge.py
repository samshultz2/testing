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
def _repoint(table, col, old_id, new_id, depth=0, where=None):
    """Point every row of ``table`` whose ``col`` == old_id at new_id (only
    the rows matching ``where``, when given). A row that would then clash with
    an existing one (unique constraint) is a conflict: resolved by
    ``_resolve`` (one survives, the other goes)."""
    if old_id == new_id or depth > 6:
        return 0
    uniq = _unique_sets(table, col)
    pk = table.c.id
    cond = col == old_id if where is None else and_(col == old_id, where)
    rows = db.session.execute(select(table).where(cond)).mappings().all()
    if not uniq:
        if rows:
            db.session.execute(update(table).where(cond).values({col.name: new_id}))
        return len(rows)
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
    return len(rows)


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
# Moving class records between two students (e.g. undoing a wrong merge)
# --------------------------------------------------------------------------- #
def move_class_records(src_id, dst_id, enrollment_ids):
    """Move the chosen class enrolments of student ``src_id`` — with their
    attendance, term summaries, scores, term results and attendance follow-ups
    for that class and term — to student ``dst_id``.

    Used when two different pupils were merged by mistake: the class records
    that belonged to the other pupil go back to their (re-added) record. If
    ``dst_id`` is already enrolled in the same class arm and term, the two
    enrolments are combined (attendance for the same day keeps the most
    recently updated mark). Returns {'classes': [...], 'attendance': n,
    'scores': n}. Caller commits."""
    from models import StudentEnrollment, ClassArmAssignment, Attendance, ClassSubject
    if src_id == dst_id:
        raise ValueError('Choose two different students.')
    src, dst = db.session.get(Student, src_id), db.session.get(Student, dst_id)
    if src is None or dst is None:
        raise ValueError('Student not found.')
    meta = db.metadata.tables
    report = {'classes': [], 'attendance': 0, 'scores': 0}
    enrs = (StudentEnrollment.query.filter(StudentEnrollment.id.in_(list(enrollment_ids) or [-1]),
                                           StudentEnrollment.student_id == src_id).all())
    for e in enrs:
        caa = db.session.get(ClassArmAssignment, e.class_arm_assignment_id)
        term_id = caa.term_id
        report['attendance'] += Attendance.query.filter_by(enrollment_id=e.id).count()
        # Term-keyed records for this class and term.
        cs_ids = [c.id for c in ClassSubject.query.filter(
            ClassSubject.class_id == caa.class_id, ClassSubject.term_id == term_id,
            db.or_(ClassSubject.arm_id == caa.arm_id, ClassSubject.arm_id.is_(None))).all()]
        if 'student_scores' in meta and cs_ids:
            t = meta['student_scores']
            report['scores'] += _repoint(t, t.c.student_id, src_id, dst_id,
                                         where=t.c.class_subject_id.in_(cs_ids)) or 0
        for name in ('term_results', 'term_summaries', 'attendance_interventions'):
            t = meta.get(name)
            if t is not None and 'term_id' in t.c:
                _repoint(t, t.c.student_id, src_id, dst_id, where=t.c.term_id == term_id)
        # The enrolment itself (attendance hangs off it).
        target = StudentEnrollment.query.filter_by(student_id=dst_id,
                                                   class_arm_assignment_id=caa.id).first()
        et = StudentEnrollment.__table__
        if target is None:
            db.session.execute(update(et).where(et.c.id == e.id).values(student_id=dst_id))
        else:
            for dt, dc in _dependents(et):
                _repoint(dt, dc, e.id, target.id)
            if e.is_active and not target.is_active:
                target.is_active = True
            db.session.expunge(e)
            db.session.execute(delete(et).where(et.c.id == e.id))
        report['classes'].append(caa.display_name)
    db.session.flush()
    db.session.expire_all()
    return report


# --------------------------------------------------------------------------- #
# Finding duplicates
# --------------------------------------------------------------------------- #
def _tok(s):
    return re.sub(r'[^a-z]', '', (s or '').lower())


def _tokens(*parts):
    """Lower-case name words; hyphenated / joined names split into words."""
    out = []
    for p in parts:
        out += [w for w in re.split(r'[^a-z]+', (p or '').lower()) if len(w) > 1]
    return out


def _word_match(a, b):
    """Same name word, allowing a small spelling difference ("osargue" ≈
    "osarogue") for words of 4+ letters."""
    if a == b:
        return True
    if min(len(a), len(b)) < 4:
        return False
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.85


def name_similarity(a_words, b_words):
    """Share of the SHORTER list's names found in the longer one (0..1)."""
    if not a_words or not b_words:
        return 0.0
    small, big = (a_words, b_words) if len(a_words) <= len(b_words) else (b_words, a_words)
    hits = sum(1 for w in small if any(_word_match(w, x) for x in big))
    return hits / len(small)


def name_key(st):
    """The surname's first word, normalised — the first test for "same
    person" (so "ABDULWAHAB ILUEDO" typed into the surname box still groups
    with "Abdulwahab")."""
    words = _tokens(st.surname)
    return words[0] if words else None


def _given(st):
    """Every other name word: the rest of the surname box, first and middle."""
    return _tokens(st.surname)[1:] + _tokens(st.first_name, st.middle_name)


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


def find_groups(class_id=None, search=None, min_score=0.5):
    """Groups of 2+ active students that look like the same person:

    * same surname (ignoring capitals / punctuation), and their other names
      (first + middle) overlap — at least ``min_score`` of the shorter list
      matches, small spelling differences allowed. "Abdulwahab Ismail" and
      "ABDULWAHAB ILUEDO AKHTAR-OZOMOYA ISMAIL" match; siblings "Okafor Ada"
      and "Okafor Chidi" don't;
    * or surname and first name swapped ("ADA OKAFOR" vs "Okafor Ada").

    Each group gets a suggested keeper (proper case before ALL CAPS, then the
    one with more saved data, then the older record) and a match score."""
    from utils.branch_scope import scope_query
    from models import ClassArmAssignment, StudentEnrollment
    students = scope_query(Student.query.filter(Student.is_active == True), Student).all()  # noqa: E712
    by_surname = defaultdict(list)
    for s in students:
        k = name_key(s)
        if k:
            by_surname[k].append(s)

    # Union-find over matching pairs; remember the best score per pair.
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    pair_score = {}

    def link(a, b, sc):
        pair_score[(min(a.id, b.id), max(a.id, b.id))] = max(sc, pair_score.get((min(a.id, b.id), max(a.id, b.id)), 0))
        parent[find(a.id)] = find(b.id)

    for bucket in by_surname.values():
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                sc = name_similarity(_given(bucket[i]), _given(bucket[j]))
                if sc >= min_score:
                    link(bucket[i], bucket[j], sc)
    # Surname <-> first name swapped.
    for s in students:
        sur = name_key(s)
        firsts = _tokens(s.first_name)
        for o in by_surname.get(firsts[0] if firsts else '', []):
            if o.id != s.id and sur and sur in _tokens(o.first_name):
                link(s, o, 1.0)

    comps = defaultdict(list)
    by_id = {s.id: s for s in students}
    for sid in list(parent):
        comps[find(sid)].append(by_id[sid])
    groups = [g for g in comps.values() if len(g) > 1]
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
        if len({bool(s.is_graduated) for s in g}) > 1:
            warn.append('One of these records has graduated and the other has not — '
                        'they may be two different pupils')
        ids_g = [s.id for s in g]
        scores = [v for (x, y), v in pair_score.items() if x in ids_g and y in ids_g]
        score = int(round(100 * (min(scores) if scores else 1)))
        out.append({'key': '-'.join(sorted(str(m['id']) for m in members)),
                    'members': members, 'keeper_id': keeper['id'], 'warnings': warn,
                    'score': score,
                    'has_caps_dup': (any(m['all_caps'] for m in members[1:]) and not keeper['all_caps']
                                     and not warn)})
    out.sort(key=lambda g: g['members'][0]['student'].full_name.lower())
    return out
