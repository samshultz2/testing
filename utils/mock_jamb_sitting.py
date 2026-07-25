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


# Subjects whose papers involve calculation — the on-screen JAMB-style basic
# calculator is offered when a candidate sits any of these.
_CALC_SUBJECTS = {
    'mathematics', 'furthermathematics', 'physics', 'chemistry', 'economics',
    'accounting', 'accounts', 'principlesofaccounts', 'financialaccounting',
    'geography',
}


def is_calculation_subject(name):
    return _norm(name) in _CALC_SUBJECTS


def _exam_owns_questions(exam):
    """True if this mock has its own authored questions (a legacy mock). Such a
    mock serves ONLY its own questions; a mock with none draws from the bank."""
    from models import db, MockJAMBQuestion
    return db.session.query(MockJAMBQuestion.id).filter(
        MockJAMBQuestion.mock_exam_id == exam.id).first() is not None


def _pool_condition(model, exam):
    """Rows visible to this mock: its own authored rows if it is a legacy mock,
    otherwise the shared bank (mock_exam_id NULL). The two are never mixed, so a
    legacy mock is unaffected by the bank and vice-versa."""
    if _exam_owns_questions(exam):
        return model.mock_exam_id == exam.id
    return model.mock_exam_id.is_(None)


def eligible_class_ids(exam):
    """SchoolClass ids allowed to sit this mock online. An empty
    ``exam.eligible_levels`` means the graduating SSS3 class only (the JAMB
    cohort) — the default. Returns an empty set only when the target class(es)
    can't be resolved, in which case the caller should not lock anyone out."""
    from models import SchoolClass
    raw = (getattr(exam, 'eligible_levels', None) or '').strip()
    if raw:
        wanted = {n.strip().lower() for n in raw.split(',') if n.strip()}
        return {c.id for c in SchoolClass.query.all()
                if (c.name or '').strip().lower() in wanted}
    from utils.helpers import get_sss3_class
    c = get_sss3_class()
    return {c.id} if c else set()


def student_eligible(exam, student):
    """True if the student's current class is allowed to sit this mock. Unknown
    placements (no active enrolment) are allowed so a mis-configured term never
    silently locks every student out — the branch guard still applies."""
    if not student:
        return False
    ids = eligible_class_ids(exam)
    if not ids:
        return True
    try:
        from routes.cbt import _student_placement
        from utils.helpers import get_active_term
        class_id, _arm = _student_placement(student.id, get_active_term())
    except Exception:
        return True
    if class_id is None:
        return True
    return class_id in ids


def candidate_subject_ids(exam, student):
    """Ordered subject ids the student sits for this mock (English first, ≤ 4).

    Subjects are those with questions in the pool the mock draws from — the
    shared bank plus any legacy in-exam questions — intersected with the
    student's registered JAMB subjects."""
    from models import db, MockJAMBQuestion, Subject
    subj_ids = [s for (s,) in db.session.query(MockJAMBQuestion.subject_id)
                .filter(_pool_condition(MockJAMBQuestion, exam)).distinct().all()]
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


def _blueprint_override(exam, subject_name):
    """Per-mock section-count override for one subject, parsed from the exam's
    ``blueprint`` JSON ``{subject_key: {section: count}}``; else None."""
    import json
    from utils.jamb_blueprint import norm_subject
    raw = getattr(exam, 'blueprint', None)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    ov = data.get(norm_subject(subject_name))
    return ov if isinstance(ov, dict) else None


def _default_novel(novel_questions):
    """When a mock doesn't name a novel, pick ONE recommended text so a paper never
    mixes novels: the title (question ``topic``) with the most recent ``exam_year``,
    tie-broken by how many questions carry it."""
    agg = {}
    for q in novel_questions:
        title = (q.topic or '').strip()
        if not title:
            continue
        y = str(q.exam_year or '').strip()[:4]
        yr = int(y) if y.isdigit() else 0
        a = agg.setdefault(title, {'max_year': 0, 'count': 0})
        a['max_year'] = max(a['max_year'], yr)
        a['count'] += 1
    if not agg:
        return None
    return max(agg.items(), key=lambda kv: (kv[1]['max_year'], kv[1]['count']))[0]


def _subject_pool(exam, subject_id):
    """(passages, questions) available to this mock for one subject — the shared
    bank plus any legacy in-exam rows — ordered deterministically."""
    from models import MockJAMBPassage, MockJAMBQuestion
    passages = (MockJAMBPassage.query
                .filter(MockJAMBPassage.subject_id == subject_id,
                        _pool_condition(MockJAMBPassage, exam))
                .order_by(MockJAMBPassage.order, MockJAMBPassage.id).all())
    qrows = (MockJAMBQuestion.query
             .filter(MockJAMBQuestion.subject_id == subject_id,
                     _pool_condition(MockJAMBQuestion, exam),
                     MockJAMBQuestion.needs_image.isnot(True))   # hold out figure-less questions
             .order_by(MockJAMBQuestion.order, MockJAMBQuestion.id).all())
    return passages, qrows


def subject_items(exam, subject_id, attempt):
    """Deterministic served paper for one subject: an ordered list of items, each
    a passage-group (passage + its questions) or a stand-alone question.

    Draws a JAMB-shaped, per-candidate random paper from the subject's pool: for
    a subject with a JAMB blueprint whose questions are section-tagged, it samples
    each section to the blueprint counts (comprehension/cloze passages kept
    whole). Untagged pools or non-JAMB subjects fall back to the legacy behaviour
    (optional ``questions_per_subject`` cap + shuffle). Returns (items, served)."""
    from models import db, Subject
    from utils.jamb_blueprint import blueprint_for, draw_paper, JAMB_BLUEPRINT, norm_subject
    passages, qrows = _subject_pool(exam, subject_id)
    if not qrows:
        return [], set()

    by_passage, standalone = {}, []
    for q in qrows:
        if q.passage_id:
            by_passage.setdefault(q.passage_id, []).append(q)
        else:
            standalone.append(q)

    rng = random.Random(_seed(attempt, subject_id, 'order'))

    subject = db.session.get(Subject, subject_id)
    subj_name = subject.name if subject else ''
    has_sections = any((q.section or '').strip() for q in qrows)

    # Structured JAMB draw when the subject has a blueprint AND tagged questions.
    if norm_subject(subj_name) in JAMB_BLUEPRINT and has_sections:
        bp = blueprint_for(subj_name, _blueprint_override(exam, subj_name))
        passages_by_section = {}
        for p in passages:
            qs = by_passage.get(p.id)
            if qs:
                passages_by_section.setdefault(p.section or '', []).append(
                    {'passage': p, 'questions': qs})
        questions_by_section = {}
        for q in standalone:
            questions_by_section.setdefault(q.section or '', []).append(q)
        # Novel section: serve only questions from THIS mock's approved novel, so
        # each year's paper tests the correct JAMB-recommended text. Questions are
        # tagged with the novel in their ``topic``. If the mock names no novel, any
        # novel question is eligible.
        novel = (getattr(exam, 'novel_title', None) or '').strip().lower()
        nq = questions_by_section.get('novel')
        # never mix novels from several years: use the mock's named novel, else
        # default to the most recent recommended text present in the pool.
        if not novel and nq:
            novel = (_default_novel(nq) or '').strip().lower()
        if novel and nq:
            def _novel_match(q):
                # tolerant match: the mock's title and the question's novel tag
                # line up if either contains the other (so "The Life Changer"
                # matches "The Life Changer — Khadija Abubakar Jalli").
                t = (q.topic or '').strip().lower()
                return bool(t) and (novel in t or t in novel)
            questions_by_section['novel'] = [
                q for q in questions_by_section['novel'] if _novel_match(q)]
        items, served = draw_paper(bp, passages_by_section, questions_by_section, rng,
                                   arrange=_is_english(subj_name))
        if served:
            return items, served
        # blueprint drew nothing (mis-tagged) → fall through to legacy

    # Legacy fallback: passages kept whole; optional cap trims stand-alone.
    passage_groups = [{'passage': p, 'questions': by_passage[p.id]}
                      for p in passages if by_passage.get(p.id)]
    cap = exam.questions_per_subject or 0
    if cap:
        passage_q = sum(len(g['questions']) for g in passage_groups)
        rem = max(0, cap - passage_q)
        pool = list(standalone)
        rng.shuffle(pool)
        standalone = pool[:rem]

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


# Server-side grace after the timer before the safety net force-submits, so a
# candidate whose client is mid-flush (or briefly offline at the buzzer) still lands
# their own submission first. The client auto-submits at 0; this only catches the
# "tab was closed and never came back" case.
AUTO_SUBMIT_GRACE_SECONDS = 120


def attempt_expired(attempt, grace_seconds=AUTO_SUBMIT_GRACE_SECONDS):
    """True if this in-progress attempt is past its deadline
    (started_at + duration + grace)."""
    from datetime import datetime, timedelta
    if not attempt or attempt.submitted_at or not attempt.started_at:
        return False
    dur = attempt.duration_minutes or 120
    deadline = attempt.started_at + timedelta(minutes=dur, seconds=grace_seconds)
    return datetime.now() >= deadline


def auto_submit_expired(exam=None, student=None, grace_seconds=AUTO_SUBMIT_GRACE_SECONDS):
    """Server-side safety net: grade any in-progress attempt whose time has fully
    elapsed but that was never submitted (e.g. the student closed the tab so the
    client-side auto-submit never fired). Scoped to one exam and/or one student when
    given. Idempotent — only touches attempts with no ``submitted_at`` that are past
    the deadline. Returns the number graded. Never raises (best-effort)."""
    from models import db, MockJAMBAttempt
    q = MockJAMBAttempt.query.filter(MockJAMBAttempt.submitted_at.is_(None))
    if exam is not None:
        q = q.filter(MockJAMBAttempt.mock_exam_id == exam.id)
    if student is not None:
        q = q.filter(MockJAMBAttempt.student_id == student.id)
    graded = 0
    for att in q.all():
        if not attempt_expired(att, grace_seconds):
            continue
        try:
            grade_attempt(att)          # commits; marks submitted + writes the result
            graded += 1
        except Exception:
            db.session.rollback()
    return graded


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
        qs = (MockJAMBQuestion.query.filter(MockJAMBQuestion.id.in_(served)).all()
              if served else [])
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
