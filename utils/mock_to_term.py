"""Copy Mock WAEC scores into the normal term results (CBT + Theory).

A Mock WAEC paper is marked out of 100. In the school's term results the same
paper stands for the exam part of the subject: CBT + Theory, which is 70 for a
subject that also has a mid-term / practical (CBT 30 + Theory 40) and 80 for one
without (CBT 30 + Theory 50). Which one applies comes from the subject's own
"Midterm / practical" setting on the Subjects page; CBT's maximum is read from
the score sheet. If the score sheet's Theory column is smaller than the rule
needs, that subject is flagged instead of written (the sheet would reject it).

    mock 64/100 in a subject worth CBT 30 + Theory 40 → 45/70 → CBT 19 + Theory 26

Whole numbers only, never above either column's maximum. Nothing is written
until ``apply`` is called, which goes through the same ``persist_scores`` path as
the score sheet (published-term lock, edit permission, audit log).
"""
from collections import OrderedDict, defaultdict


def _round(x):
    """Round half up (Python's round() is banker's rounding)."""
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


def split(score, maxes):
    """Scale a /100 ``score`` onto the columns in ``maxes`` (list of ints) and
    share it out in proportion to each column's maximum.

    Returns (scaled_total, [part per column]); every part is a whole number in
    0..max and the parts add up to the scaled total."""
    maxes = [int(m) for m in maxes]
    total = sum(maxes)
    if total <= 0 or score is None:
        return 0, [0] * len(maxes)
    score = max(0.0, min(100.0, float(score)))
    scaled = min(total, _round(score * total / 100.0))
    parts, used = [], 0
    for i, mx in enumerate(maxes):
        if i == len(maxes) - 1:
            part = scaled - used
        else:
            part = _round(scaled * mx / total)
        parts.append(part)
        used += part
    # Keep every part within its column (rounding can push one over by 1).
    for _ in range(len(maxes) * 2):
        over = [i for i, (p, m) in enumerate(zip(parts, maxes)) if p > m]
        under = [i for i, (p, m) in enumerate(zip(parts, maxes)) if p < 0]
        if not over and not under:
            break
        for i in over:
            extra = parts[i] - maxes[i]; parts[i] = maxes[i]
            j = next((k for k in range(len(parts)) if k != i and parts[k] < maxes[k]), None)
            if j is not None:
                parts[j] += extra
        for i in under:
            short = -parts[i]; parts[i] = 0
            j = next((k for k in range(len(parts)) if k != i and parts[k] > 0), None)
            if j is not None:
                parts[j] -= short
    return scaled, parts


def _norm(name):
    from utils.subject_match import canonical_subject
    c = canonical_subject(name or '')
    return (c or name or '').strip().lower()


def _enrolments(term_id, student_ids):
    """{student_id: ClassArmAssignment} for the term."""
    from models import StudentEnrollment, ClassArmAssignment
    if not student_ids:
        return {}
    rows = (StudentEnrollment.query.join(ClassArmAssignment,
                                         ClassArmAssignment.id == StudentEnrollment.class_arm_assignment_id)
            .filter(ClassArmAssignment.term_id == term_id,
                    StudentEnrollment.student_id.in_(list(student_ids)),
                    StudentEnrollment.is_active == True)  # noqa: E712
            .all())
    return {r.student_id: r.class_arm_assignment for r in rows}


def _exam_columns(subject, term_id):
    """[(assessment_type, rule_max, sheet_max)] for the CBT and Theory columns.

    rule_max follows the subject's Midterm / practical setting: Theory is worth
    40 with a mid-term / practical (CBT 30 + 40 = 70) and 50 without (= 80).
    sheet_max is what the term's score sheet allows for that column."""
    from models import AssessmentType
    from utils.assessments import (subject_columns, effective_max, is_cbt, is_theory,
                                   THEORY_WITH_PRACTICAL, THEORY_WITHOUT_PRACTICAL)
    cols = subject_columns(subject, term=term_id)
    cbt = next(((at, mx) for at, mx in cols if is_cbt(at)), None)
    theory = next(((at, mx) for at, mx in cols if is_theory(at)), None)
    if theory is None:
        # The sheet may have dropped Theory (max 0) — still identify the type.
        at = next((t for t in AssessmentType.query.filter_by(is_active=True)
                   .order_by(AssessmentType.order, AssessmentType.id).all() if is_theory(t)), None)
        if at is not None:
            theory = (at, effective_max(subject, at, term=term_id))
    rule_theory = THEORY_WITH_PRACTICAL if getattr(subject, 'has_practical', True) else THEORY_WITHOUT_PRACTICAL
    out = []
    if cbt:
        out.append((cbt[0], cbt[1], cbt[1]))
    if theory:
        out.append((theory[0], rule_theory, theory[1]))
    return out


def plan(exam, term_id):
    """Work out every score that would be written. Returns a dict:

    rows: [{student, subject, mock, class_subject, assignment, columns:
            [{at, max, new, old}], target, scaled, status}]
    status is one of: new, replace, same, partial (some columns already
    filled), absent, no_score, no_class, no_subject, no_columns, sheet_small
    (the score sheet's column is smaller than the 70 / 80 rule needs).
    """
    from models import MockWAECResult, ClassSubject, StudentScore, Student
    from utils.assessments import is_cbt
    from models import db
    results = (MockWAECResult.query.filter_by(mock_exam_id=exam.id)
               .order_by(MockWAECResult.student_id, MockWAECResult.subject).all())
    sids = {r.student_id for r in results}
    students = {s.id: s for s in Student.query.filter(Student.id.in_(list(sids) or [-1])).all()}
    enrol = _enrolments(term_id, sids)

    # Class-subjects per (class, arm), indexed by normalised subject name.
    cs_cache = {}

    def class_subjects(asg):
        key = (asg.class_id, asg.arm_id)
        if key not in cs_cache:
            rows = ClassSubject.query.filter_by(term_id=term_id, class_id=asg.class_id, is_active=True).filter(
                (ClassSubject.arm_id == None) | (ClassSubject.arm_id == asg.arm_id)).all()  # noqa: E711
            exact, canon = {}, {}
            for cs in rows:
                exact.setdefault((cs.subject.name or '').strip().lower(), cs)
                canon.setdefault(_norm(cs.subject.name), cs)
            cs_cache[key] = (exact, canon)
        return cs_cache[key]

    col_cache = {}
    cs_ids = set()
    out = []
    for r in results:
        st = students.get(r.student_id)
        row = {'student': st, 'subject': r.subject, 'mock': r.score, 'class_subject': None,
               'assignment': enrol.get(r.student_id), 'columns': [], 'target': None,
               'scaled': None, 'status': None}
        out.append(row)
        if r.is_absent:
            row['status'] = 'absent'; continue
        if r.score is None:
            row['status'] = 'no_score'; continue
        asg = row['assignment']
        if not asg:
            row['status'] = 'no_class'; continue
        exact, canon = class_subjects(asg)
        # Same name first; otherwise the WAEC-standard name ("Maths" ↔ "Mathematics").
        cs = exact.get((r.subject or '').strip().lower()) or canon.get(_norm(r.subject))
        if not cs:
            row['status'] = 'no_subject'; continue
        row['class_subject'] = cs
        cs_ids.add(cs.id)
        if cs.subject_id not in col_cache:
            col_cache[cs.subject_id] = _exam_columns(cs.subject, term_id)
        cols = col_cache[cs.subject_id]
        if not cols:
            row['status'] = 'no_columns'; continue
        scaled, parts = split(r.score, [mx for _, mx, _ in cols])
        row['target'] = sum(mx for _, mx, _ in cols)
        row['scaled'] = scaled
        row['practical'] = bool(getattr(cs.subject, 'has_practical', True))
        row['columns'] = [{'at': at, 'label': 'CBT' if is_cbt(at) else 'Theory', 'max': mx, 'sheet_max': sm,
                           'new': p, 'old': None} for (at, mx, sm), p in zip(cols, parts)]
        if any(c['max'] > c['sheet_max'] for c in row['columns']):
            row['status'] = 'sheet_small'

    # Existing CBT / Theory scores, one query.
    if cs_ids:
        existing = {(s.student_id, s.class_subject_id, s.assessment_type_id): s.score
                    for s in StudentScore.query.filter(StudentScore.class_subject_id.in_(list(cs_ids))).all()}
        for row in out:
            if not row['columns']:
                continue
            for c in row['columns']:
                c['old'] = existing.get((row['student'].id, row['class_subject'].id, c['at'].id))
            if row['status'] == 'sheet_small':
                continue
            olds = [c['old'] for c in row['columns']]
            if all(o is None for o in olds):
                row['status'] = 'new'
            elif all(o is not None and float(o) == c['new'] for o, c in zip(olds, row['columns'])):
                row['status'] = 'same'
            elif all(o is not None for o in olds):
                row['status'] = 'replace'
            else:
                row['status'] = 'partial'

    counts = defaultdict(int)
    for row in out:
        counts[row['status']] += 1
    by_subject = OrderedDict()
    for row in sorted(out, key=lambda x: (x['subject'], (x['student'].full_name if x['student'] else ''))):
        by_subject.setdefault(row['subject'], []).append(row)
    return {'rows': out, 'by_subject': by_subject, 'counts': dict(counts)}


def apply(p, term_id, replace=False):
    """Write the planned CBT / Theory scores. With ``replace=False`` only empty
    cells are filled; with ``replace=True`` existing CBT / Theory scores are
    overwritten too. Returns {'saved', 'skipped', 'blocked', 'locked', 'classes'}."""
    from models import db
    from routes.subjects import persist_scores
    groups = defaultdict(list)          # class_subject_id -> items
    meta = {}
    skipped = 0
    for row in p['rows']:
        if row['status'] not in ('new', 'replace', 'partial'):
            continue
        cs, asg = row['class_subject'], row['assignment']
        meta[cs.id] = (cs, asg)
        for c in row['columns']:
            if c['old'] is not None and not replace:
                skipped += 1
                continue
            groups[cs.id].append((row['student'].id, c['at'].id, str(c['new']), c['max']))
    total = {'saved': 0, 'skipped': skipped, 'blocked': 0, 'rejected': 0, 'locked': False, 'classes': set()}
    for cs_id, items in groups.items():
        cs, asg = meta[cs_id]
        counts = persist_scores(term_id, asg.id, cs_id, cs.subject_id, items, allow_delete=False)
        if counts is None:
            total['locked'] = True
            continue
        for k in ('saved', 'blocked', 'rejected'):
            total[k] += counts[k]
        total['classes'].add(asg.class_id)
    db.session.commit()
    # Keep term totals / positions and the analytics caches fresh.
    if total['classes']:
        from utils.report_card import compute_term_summaries
        for class_id in total['classes']:
            try:
                compute_term_summaries(term_id, class_id)
            except Exception:
                pass
        try:
            from utils.results_analytics_org import bust_all
            bust_all()
        except Exception:
            pass
    total['classes'] = len(total['classes'])
    return total
