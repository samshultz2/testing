"""Per-student (and cohort) topic / sub-topic mastery for Mock JAMB, built from
the ONLINE sitting answers (``MockJAMBAnswer.is_correct`` joined to the answered
question's subject/topic/subtopic).

This is the microscope the subject-level ``MockJAMBResult`` analytics can't
provide: for a given student it says exactly which topics and sub-topics they
excel at and which they keep getting wrong, and whether they are improving or
declining across successive mocks; for a cohort it surfaces the topics *most*
students miss, so teaching can target them.

Everything is derived on the fly from answered questions — no schema changes —
and every query is scoped to ``allowed_ids`` (branch scoping) when given.
"""
from __future__ import annotations


def _rate(correct, total):
    return round(100 * correct / total, 1) if total else None


def _band(rate):
    if rate is None:
        return 'none'
    if rate >= 75:
        return 'strong'
    if rate >= 50:
        return 'fair'
    return 'weak'


def _submitted_attempts(student_id=None, allowed_ids=None, exam_id=None):
    from models import MockJAMBAttempt
    q = MockJAMBAttempt.query.filter(MockJAMBAttempt.status == 'Submitted')
    if student_id is not None:
        q = q.filter(MockJAMBAttempt.student_id == student_id)
    if exam_id is not None:
        q = q.filter(MockJAMBAttempt.mock_exam_id == exam_id)
    if allowed_ids is not None:
        if not allowed_ids:
            return []
        q = q.filter(MockJAMBAttempt.student_id.in_(list(allowed_ids)))
    return q.all()


def _answer_rows(attempt_ids):
    """(subject_name, topic, subtopic, is_correct) for every answered question in
    the given attempts — one round-trip, joined to the question and its subject."""
    if not attempt_ids:
        return []
    from models import db, MockJAMBAnswer, MockJAMBQuestion, Subject
    rows = (db.session.query(
                Subject.name, MockJAMBQuestion.topic, MockJAMBQuestion.subtopic,
                MockJAMBAnswer.is_correct, MockJAMBAnswer.attempt_id)
            .join(MockJAMBQuestion, MockJAMBAnswer.question_id == MockJAMBQuestion.id)
            .outerjoin(Subject, MockJAMBQuestion.subject_id == Subject.id)
            .filter(MockJAMBAnswer.attempt_id.in_(list(attempt_ids)))
            .all())
    return rows


def _aggregate(rows, key):
    """Aggregate (correct, total) by a key function over answer rows."""
    agg = {}
    for r in rows:
        k = key(r)
        if k is None:
            continue
        c, t = agg.get(k, (0, 0))
        agg[k] = (c + (1 if r.is_correct else 0), t + 1)
    return agg


def student_mastery(student_id, allowed_ids=None, min_attempts=2):
    """Full topic/sub-topic mastery for one student across every submitted mock.

    Returns strengths, weaknesses, per-subject topic tables, sub-topic detail and
    a per-mock trend (overall + per weakest-topic), so a teacher can see at a
    glance what to drill and whether the student is climbing or sliding."""
    from models import db, Student, MockJAMBExam
    student = db.session.get(Student, student_id)
    attempts = _submitted_attempts(student_id=student_id, allowed_ids=allowed_ids)
    meta = {'student_id': student_id,
            'student_name': (student.full_name if student else f'#{student_id}'),
            'mocks': len(attempts)}
    if not attempts:
        return {'meta': meta, 'subjects': [], 'strengths': [], 'weaknesses': [],
                'subtopics': [], 'trend': [], 'has_data': False}

    rows = _answer_rows([a.id for a in attempts])

    # ---- by subject → topic --------------------------------------------------
    subj_topic = _aggregate(rows, lambda r: ((r[0] or 'Unknown'), (r.topic or None)))
    subjects = {}
    for (subj, topic), (c, t) in subj_topic.items():
        subjects.setdefault(subj, []).append(
            {'topic': topic or '(untagged)', 'correct': c, 'total': t,
             'rate': _rate(c, t), 'band': _band(_rate(c, t))})
    subjects_view = []
    for subj in sorted(subjects):
        topics = sorted(subjects[subj], key=lambda x: (x['rate'] if x['rate'] is not None else 999, -x['total']))
        tot_c = sum(x['correct'] for x in topics)
        tot_t = sum(x['total'] for x in topics)
        subjects_view.append({'subject': subj, 'topics': topics,
                              'correct': tot_c, 'total': tot_t,
                              'rate': _rate(tot_c, tot_t)})

    # ---- strengths / weaknesses (topic level, enough evidence) ----------------
    topic_agg = _aggregate(rows, lambda r: (r.topic or None))
    ranked = [{'topic': tp, 'correct': c, 'total': t, 'rate': _rate(c, t),
               'band': _band(_rate(c, t))}
              for tp, (c, t) in topic_agg.items() if t >= min_attempts]
    strengths = sorted([r for r in ranked if r['rate'] is not None and r['rate'] >= 70],
                       key=lambda x: (-x['rate'], -x['total']))[:8]
    weaknesses = sorted([r for r in ranked if r['rate'] is not None and r['rate'] < 50],
                        key=lambda x: (x['rate'], -x['total']))[:8]

    # ---- sub-topic detail (weakest first) ------------------------------------
    sub_agg = _aggregate(rows, lambda r: ((r.topic or '(untagged)'), r.subtopic) if r.subtopic else None)
    subtopics = sorted(
        [{'topic': tp, 'subtopic': st, 'correct': c, 'total': t,
          'rate': _rate(c, t), 'band': _band(_rate(c, t))}
         for (tp, st), (c, t) in sub_agg.items() if t >= min_attempts],
        key=lambda x: (x['rate'] if x['rate'] is not None else 999, -x['total']))

    # ---- per-mock trend (overall + focus on the weakest topic) ----------------
    attempts_sorted = sorted(attempts, key=lambda a: (
        a.exam.exam_date or a.submitted_at or a.created_at, a.id) if a.exam else (a.id,))
    focus_topic = weaknesses[0]['topic'] if weaknesses else None
    per_attempt = {a.id: [] for a in attempts_sorted}
    for r in rows:
        per_attempt.setdefault(r.attempt_id, []).append(r)
    trend = []
    for a in attempts_sorted:
        ar = per_attempt.get(a.id, [])
        oc = sum(1 for x in ar if x.is_correct)
        ot = len(ar)
        focus = None
        if focus_topic:
            fc = sum(1 for x in ar if (x.topic == focus_topic) and x.is_correct)
            ft = sum(1 for x in ar if x.topic == focus_topic)
            focus = _rate(fc, ft)
        trend.append({'mock': (a.exam.display_name if a.exam else f'Mock #{a.mock_exam_id}'),
                      'date': (a.exam.exam_date.isoformat() if a.exam and a.exam.exam_date else None),
                      'score': a.total_score, 'overall_rate': _rate(oc, ot),
                      'focus_rate': focus})

    # improvement / decline signal from first→last overall topic-correct rate
    direction = None
    rates = [t['overall_rate'] for t in trend if t['overall_rate'] is not None]
    if len(rates) >= 2:
        delta = round(rates[-1] - rates[0], 1)
        direction = {'delta': delta,
                     'label': 'improving' if delta >= 3 else 'declining' if delta <= -3 else 'steady'}

    return {'meta': meta, 'subjects': subjects_view, 'strengths': strengths,
            'weaknesses': weaknesses, 'subtopics': subtopics[:20], 'trend': trend,
            'focus_topic': focus_topic, 'direction': direction, 'has_data': True}


def cohort_topic_gaps(allowed_ids=None, exam_id=None, min_attempts=10, limit=15):
    """Topics MOST students get wrong across submitted mocks — the cohort's
    weakest spots, ranked by lowest correct-rate (with enough evidence). Also
    returns the strongest topics and per-subtopic gaps."""
    attempts = _submitted_attempts(allowed_ids=allowed_ids, exam_id=exam_id)
    meta = {'mocks': len({a.mock_exam_id for a in attempts}),
            'students': len({a.student_id for a in attempts}),
            'attempts': len(attempts)}
    if not attempts:
        return {'meta': meta, 'weak_topics': [], 'strong_topics': [],
                'weak_subtopics': [], 'has_data': False}
    rows = _answer_rows([a.id for a in attempts])

    topic_agg = _aggregate(rows, lambda r: (r.topic or None))
    students_by_topic = {}
    # count distinct students struggling isn't needed; rate over answers is enough
    ranked = [{'topic': tp, 'correct': c, 'total': t, 'rate': _rate(c, t),
               'band': _band(_rate(c, t))}
              for tp, (c, t) in topic_agg.items() if t >= min_attempts]
    weak = sorted([r for r in ranked if r['rate'] is not None],
                  key=lambda x: (x['rate'], -x['total']))[:limit]
    strong = sorted([r for r in ranked if r['rate'] is not None],
                    key=lambda x: (-x['rate'], -x['total']))[:limit]

    sub_agg = _aggregate(rows, lambda r: ((r.topic or '(untagged)'), r.subtopic) if r.subtopic else None)
    weak_sub = sorted(
        [{'topic': tp, 'subtopic': st, 'correct': c, 'total': t, 'rate': _rate(c, t),
          'band': _band(_rate(c, t))}
         for (tp, st), (c, t) in sub_agg.items() if t >= min_attempts and _rate(c, t) is not None],
        key=lambda x: (x['rate'], -x['total']))[:limit]

    return {'meta': meta, 'weak_topics': weak, 'strong_topics': strong,
            'weak_subtopics': weak_sub, 'has_data': True}
