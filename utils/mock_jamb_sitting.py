"""Online Mock JAMB sitting — which subjects a candidate sits, and grading a
submitted attempt into the existing MockJAMBResult (so all the current Mock JAMB
analytics keep working).

JAMB is a 4-subject sitting scored out of 400 (each subject scaled to 100). A
candidate sits the subjects they registered for (``Student.jamb_subject_list``)
that have questions in the exam; if they registered none, they get every subject
the exam has questions for. English (the compulsory subject) is placed first and
the set is capped at 4, matching JAMB and the four MockJAMBResult slots.
"""
from __future__ import annotations


def _norm(name):
    import re
    return re.sub(r'[^a-z0-9]', '', (name or '').lower())


def _is_english(name):
    return 'english' in (name or '').lower()


def candidate_subject_ids(exam, student):
    """Ordered subject ids the student sits for this mock (English first, ≤ 4)."""
    from models import db, MockJAMBQuestion, Subject
    subj_ids = [s for (s,) in db.session.query(MockJAMBQuestion.subject_id)
                .filter(MockJAMBQuestion.mock_exam_id == exam.id).distinct().all()]
    if not subj_ids:
        return []
    subjects = {s.id: s for s in Subject.query.filter(Subject.id.in_(subj_ids)).all()}

    registered = {_norm(n) for n in (student.jamb_subject_list or [])} if student else set()
    if registered:
        chosen = [sid for sid in subj_ids if _norm(subjects[sid].name) in registered]
        if not chosen:
            chosen = list(subj_ids)
    else:
        chosen = list(subj_ids)

    # English first, then alphabetical; cap at 4 (a JAMB sitting).
    chosen.sort(key=lambda sid: (not _is_english(subjects[sid].name), subjects[sid].name.lower()))
    return chosen[:4]


def sitting_payload(exam, subject_ids):
    """The questions to render, grouped by subject then passage. Correct answers
    are NOT included — this is what the student sees."""
    from models import db, Subject, MockJAMBPassage, MockJAMBQuestion
    out = []
    for sid in subject_ids:
        subject = db.session.get(Subject, sid)
        passages = (MockJAMBPassage.query.filter_by(mock_exam_id=exam.id, subject_id=sid)
                    .order_by(MockJAMBPassage.order, MockJAMBPassage.id).all())
        qrows = (MockJAMBQuestion.query.filter_by(mock_exam_id=exam.id, subject_id=sid)
                 .order_by(MockJAMBQuestion.order, MockJAMBQuestion.id).all())
        by_passage = {}
        standalone = []
        for q in qrows:
            if q.passage_id:
                by_passage.setdefault(q.passage_id, []).append(q)
            else:
                standalone.append(q)
        groups = []
        for p in passages:
            if by_passage.get(p.id):
                groups.append({'passage': p, 'questions': by_passage[p.id]})
        out.append({'subject': subject, 'groups': groups, 'standalone': standalone,
                    'count': len(qrows)})
    return out


def grade_attempt(attempt):
    """Grade a submitted attempt: scale each subject to /100 (blanks count as 0),
    total out of 400, and upsert the MockJAMBResult so analytics see it. Returns
    a list of ``(subject_name, scaled_score)`` for the subjects sat."""
    from datetime import datetime
    from models import (db, MockJAMBQuestion, MockJAMBAnswer, MockJAMBResult,
                        Subject)
    exam = attempt.exam
    student = attempt.student
    subject_ids = candidate_subject_ids(exam, student)

    # correct/earned marks per subject from saved answers
    ans = {a.question_id: a for a in attempt.answers}
    per = []
    for sid in subject_ids:
        qs = MockJAMBQuestion.query.filter_by(mock_exam_id=exam.id, subject_id=sid).all()
        total_marks = sum((q.marks or 1) for q in qs)
        earned = sum((q.marks or 1) for q in qs
                     if ans.get(q.id) and ans[q.id].is_correct)
        scaled = round(earned / total_marks * 100) if total_marks else 0
        per.append((db.session.get(Subject, sid).name, scaled))

    total = min(400, sum(s for _n, s in per))

    result = MockJAMBResult.query.filter_by(
        student_id=student.id, mock_exam_id=exam.id).first()
    if not result:
        result = MockJAMBResult(student_id=student.id, mock_exam_id=exam.id, total_score=0)
        db.session.add(result)
    result.total_score = total
    for i in range(4):
        name, score = (per[i] if i < len(per) else (None, None))
        setattr(result, f'subject{i + 1}', name)
        setattr(result, f'subject{i + 1}_score', score)

    attempt.total_score = total
    attempt.status = 'Submitted'
    attempt.submitted_at = datetime.now()
    db.session.commit()
    return per
