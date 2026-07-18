"""Online Mock JAMB sitting — which subjects a candidate sits, which questions
(randomised per candidate) they get, and grading into MockJAMBResult (so all the
current Mock JAMB analytics keep working).

Anti-cheat randomisation, stable per attempt (so a resume shows the same paper):
* Each candidate gets the questions in a shuffled order, and the four options of
  every question in a shuffled order — seeded by the attempt id, so no two
  candidates see the same layout, yet a reload is identical.
* If the exam sets ``questions_per_subject``, each candidate is served a random
  subset of that size per subject (comprehension passages are always kept whole),
  so candidates get genuinely different question sets from a larger bank.
* The stored answer is always the ORIGINAL option letter, so grading is unaffected
  by the display shuffle and each subject still scales to /100, total /400.

A candidate sits the subjects they registered for (``Student.jamb_subject_list``)
that have questions; English is placed first and the set is capped at 4.
"""
from __future__ import annotations
import random


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

    chosen.sort(key=lambda sid: (not _is_english(subjects[sid].name), subjects[sid].name.lower()))
    return chosen[:4]


def _seed(attempt, *parts):
    """A stable seed for this attempt (and optional sub-key), so a candidate's
    paper is identical on every reload but differs between candidates."""
    return hash((int(getattr(attempt, 'id', 0) or 0), *parts)) & 0x7fffffff


def subject_items(exam, subject_id, attempt):
    """Deterministic served paper for one subject: an ordered list of items, each
    either a passage-group (passage + its questions) or a stand-alone question.
    Applies the per-subject random subset (if set) and the per-candidate order
    shuffle. Returns (items, served_question_ids)."""
    from models import MockJAMBPassage, MockJAMBQuestion
    passages = (MockJAMBPassage.query.filter_by(mock_exam_id=exam.id, subject_id=subject_id)
                .order_by(MockJAMBPassage.order, MockJAMBPassage.id).all())
    qrows = (MockJAMBQuestion.query.filter_by(mock_exam_id=exam.id, subject_id=subject_id)
             .order_by(MockJAMBQuestion.order, MockJAMBQuestion.id).all())
    by_passage, standalone = {}, []
    for q in qrows:
        if q.passage_id:
            by_passage.setdefault(q.passage_id, []).append(q)
        else:
            standalone.append(q)
    passage_groups = [{'passage': p, 'questions': by_passage[p.id]}
                      for p in passages if by_passage.get(p.id)]

    rng = random.Random(_seed(attempt, subject_id, 'order'))
    # Random subset (comprehension passages kept whole; the cap trims stand-alone).
    cap = exam.questions_per_subject or 0
    if cap:
        passage_q = sum(len(g['questions']) for g in passage_groups)
        rem = max(0, cap - passage_q)
        pool = list(standalone)
        rng.shuffle(pool)
        standalone = pool[:rem]

    # Shuffle order: passages and stand-alone questions interleave as items.
    items = [{'kind': 'passage', **g} for g in passage_groups] + \
            [{'kind': 'question', 'q': q} for q in standalone]
    rng.shuffle(items)

    served = set()
    for it in items:
        if it['kind'] == 'passage':
            for q in it['questions']:
                served.add(q.id)
        else:
            served.add(it['q'].id)
    return items, served


def _shuffled_options(attempt, q):
    """The four non-empty options in a per-candidate shuffled order, each as
    ``(original_letter, text)`` — the radio value stays the original letter so
    grading is unaffected by the display order."""
    opts = [(letter, text) for letter, text in q.options if text]
    random.Random(_seed(attempt, q.id, 'opt')).shuffle(opts)
    return opts


def sitting_payload(exam, subject_ids, attempt):
    """What the student sees, per subject: passages with their questions and
    stand-alone questions, in the candidate's shuffled order, with shuffled
    options. Correct answers are NOT included."""
    from models import db, Subject
    out = []
    for sid in subject_ids:
        subject = db.session.get(Subject, sid)
        items, served = subject_items(exam, sid, attempt)
        groups, standalone = [], []
        for it in items:
            if it['kind'] == 'passage':
                groups.append({'passage': it['passage'],
                               'questions': [{'q': q, 'options': _shuffled_options(attempt, q)}
                                             for q in it['questions']]})
            else:
                standalone.append({'q': it['q'], 'options': _shuffled_options(attempt, it['q'])})
        out.append({'subject': subject, 'groups': groups, 'standalone': standalone,
                    'count': len(served)})
    return out


def grade_attempt(attempt):
    """Grade a submitted attempt over the served subset only (blanks = 0): scale
    each subject to /100, total /400, and upsert the MockJAMBResult so analytics
    see it. Returns a list of ``(subject_name, scaled_score)``."""
    from datetime import datetime
    from models import db, MockJAMBQuestion, MockJAMBResult, Subject
    exam = attempt.exam
    student = attempt.student
    subject_ids = candidate_subject_ids(exam, student)

    ans = {a.question_id: a for a in attempt.answers}
    per = []
    for sid in subject_ids:
        _items, served = subject_items(exam, sid, attempt)
        qs = [q for q in MockJAMBQuestion.query.filter_by(mock_exam_id=exam.id, subject_id=sid).all()
              if q.id in served]
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
