"""Extra Mock WAEC broadsheet figures, aimed at readiness before the real
WAEC sitting. All read-only, and best-effort: a lookup that can't be resolved
(no earlier mock, no SSS3 subject teachers set up) just leaves its field
empty rather than breaking the sheet.

``enrich(bs)`` adds to a ``MockWAECAnalytics.get_broadsheet`` result:

* each row: ``readiness`` {key, label, tone}, ``absent`` (subjects missed),
  ``borderline`` (subjects scored 45-49, i.e. a few marks off a credit),
  ``prev`` {credits, average, d_credits, d_average} vs the previous mock
  (None when the student didn't sit it);
* each subject summary: ``borderline``, ``teacher`` (``absent`` comes from
  get_broadsheet itself);
* the sheet: ``prev_exam``, ``borderline_total``, ``readiness_counts``.
"""
from models import db

# A paper scored here is a few marks short of a credit (C6 starts at 50).
BORDERLINE_LOW, CREDIT_LINE = 45, 50

READINESS = {
    'ok': ('Qualifies', 'good'),
    'core': (None, 'mid'),            # label built from the missing subject(s)
    'one': ('1 credit short', 'mid'),
    'two': ('2 credits short', 'bad'),
    'far': ('Not on track', 'bad'),
}


def is_borderline(r):
    """A sat paper whose score sits just under the credit line."""
    return bool(r and not getattr(r, 'is_absent', False) and r.score is not None
                and BORDERLINE_LOW <= r.score < CREDIT_LINE)


def readiness(credits, missing_core):
    """Where a student stands against "5 credits including English and Maths".

    Each missing core credit also counts toward the five, so the credits still
    needed is the larger of (5 - credits) and the number of core subjects not
    yet credited."""
    from models.mock_waec import CORE_SUBJECTS
    need = max(5 - credits, len(missing_core))
    if need <= 0:
        key = 'ok'
    elif missing_core and credits + len(missing_core) >= 5:
        key = 'core'                  # enough credits; only English/Maths stand in the way
    elif need == 1:
        key = 'one'
    elif need == 2:
        key = 'two'
    else:
        key = 'far'
    label, tone = READINESS[key]
    if key == 'core':
        short = {'English Language': 'English', 'Mathematics': 'Maths'}
        names = [short.get(s, s) for s in CORE_SUBJECTS if s in missing_core]
        label = 'Needs ' + ' & '.join(names)
    return {'key': key, 'label': label, 'tone': tone, 'need': need}


def previous_exam(exam):
    """The mock before this one: the latest earlier mock in the same session
    (by mock number), else the latest earlier-dated mock in the same branch."""
    from models.mock_waec import MockWAECExam
    q = MockWAECExam.query.filter(MockWAECExam.id != exam.id)
    if exam.branch_id:
        q = q.filter(MockWAECExam.branch_id == exam.branch_id)
    same = (q.filter(MockWAECExam.session_id == exam.session_id,
                     MockWAECExam.exam_number < exam.exam_number)
            .order_by(MockWAECExam.exam_number.desc()).first())
    if same or not exam.exam_date:
        return same
    return (q.filter(MockWAECExam.exam_date < exam.exam_date)
            .order_by(MockWAECExam.exam_date.desc(), MockWAECExam.exam_number.desc()).first())


def _prev_summaries(prev):
    """{student_id: (credits, average)} for an earlier mock."""
    from models.mock_waec import MockWAECResult, MockWAECAnalytics
    by = {}
    for r in MockWAECResult.query.filter_by(mock_exam_id=prev.id).all():
        by.setdefault(r.student_id, []).append(r)
    out = {}
    for sid, rs in by.items():
        s = MockWAECAnalytics._summarise(rs)
        out[sid] = (s['credits'], s['average_score'])
    return out


def subject_teachers(exam, subjects):
    """{mock subject: 'Teacher A / Teacher B'} from the SSS3 class's subject
    set-up in the exam's session (latest term that has one). Uses the class
    subject's teacher name, else the teacher assigned to that subject."""
    try:
        from models import ClassSubject, Subject, Term, TeacherSubjectAssignment, ClassArmAssignment
        from utils.helpers import get_sss3_class
        from utils.exam_rules import canonical_subject
        sss3 = get_sss3_class()
        if not sss3 or not subjects:
            return {}
        wanted = {canonical_subject(s): s for s in subjects}
        terms = (Term.query.filter_by(session_id=exam.session_id)
                 .order_by(Term.term_number.desc()).all())
        for term in terms:
            names = {}
            rows = (db.session.query(Subject.name, ClassSubject.teacher_name)
                    .join(ClassSubject, ClassSubject.subject_id == Subject.id)
                    .filter(ClassSubject.class_id == sss3.id, ClassSubject.term_id == term.id).all())
            for sname, tname in rows:
                key = wanted.get(canonical_subject(sname))
                if key and (tname or '').strip():
                    names.setdefault(key, [])
                    if tname.strip() not in names[key]:
                        names[key].append(tname.strip())
            assigned = (TeacherSubjectAssignment.query
                        .join(ClassArmAssignment,
                              ClassArmAssignment.id == TeacherSubjectAssignment.class_arm_assignment_id)
                        .filter(ClassArmAssignment.class_id == sss3.id,
                                ClassArmAssignment.term_id == term.id,
                                TeacherSubjectAssignment.is_active == True).all())
            # Teacher accounts assigned to the subject fill in only subjects
            # whose class set-up has no teacher name typed in.
            from_names = set(names)
            for a in assigned:
                key = wanted.get(canonical_subject(a.subject.name if a.subject else ''))
                user = a.teacher.user if a.teacher else None
                full = ((user.full_name if user else '') or '').strip()
                if key and full and key not in from_names:
                    names.setdefault(key, [])
                    if full not in names[key]:
                        names[key].append(full)
            if rows or assigned:
                return {k: ' / '.join(v) for k, v in names.items()}
        return {}
    except Exception:
        db.session.rollback()
        return {}


def enrich(bs):
    """Add readiness, absences, borderline papers, change since the previous
    mock and subject teachers to a broadsheet dict, in place. Returns it."""
    from models.mock_waec import CORE_SUBJECTS, PASS_GRADES
    if not bs or not bs.get('rows'):
        return bs
    exam = bs['exam']
    subjects = bs['subjects']
    prev = previous_exam(exam)
    prev_map = _prev_summaries(prev) if prev else {}
    counts = {k: 0 for k in READINESS}
    border_total = 0
    for row in bs['rows']:
        cells = row['cells']
        credited = {s for s, r in cells.items() if r.grade in PASS_GRADES and not getattr(r, 'is_absent', False)}
        missing = [s for s in CORE_SUBJECTS if s not in credited]
        row['readiness'] = readiness(row['credits'], missing)
        counts[row['readiness']['key']] += 1
        row['absent'] = sorted(s for s, r in cells.items() if getattr(r, 'is_absent', False))
        row['borderline'] = sorted(s for s, r in cells.items() if is_borderline(r))
        border_total += len(row['borderline'])
        p = prev_map.get(row['student'].id)
        if p:
            pc, pa = p
            avg = row['average_score']
            row['prev'] = {'credits': pc, 'average': pa,
                           'd_credits': row['credits'] - pc,
                           'd_average': (round(avg - pa, 1) if avg is not None and pa is not None else None)}
        else:
            row['prev'] = None
    teachers = subject_teachers(exam, subjects)
    for subj in subjects:
        d = bs['subject_summary'][subj]
        rs = [row['cells'][subj] for row in bs['rows'] if subj in row['cells']]
        d['borderline'] = sum(1 for r in rs if is_borderline(r))
        d['teacher'] = teachers.get(subj, '')
    # Only compare when some students actually sat both mocks.
    bs['prev_exam'] = prev if any(row['prev'] for row in bs['rows']) else None
    bs['borderline_total'] = border_total
    bs['readiness_counts'] = counts
    return bs


def change_text(d):
    """'+2', '−1', '0' for a change; '' when there's nothing to compare."""
    if d is None:
        return ''
    if isinstance(d, float):
        d = round(d, 1)
        if d == int(d):
            d = int(d)
    return f'+{d}' if d > 0 else (f'−{abs(d)}' if d < 0 else '0')
