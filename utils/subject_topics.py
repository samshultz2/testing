"""Subject-level topic mastery — aggregate topic performance across *all* of a
subject's CBT / mock exams (optionally within a term), so a head of department
sees which syllabus topics are persistently weak across every test rather than
just one sitting.

Built from the per-item ``CBTAnswer`` responses on topic-tagged questions. One
bulk fetch of questions, attempts and answers — no N+1.
"""
from __future__ import annotations


def _band(m):
    return 'weak' if m < 50 else 'developing' if m < 70 else 'secure'


def subject_topic_mastery(subject_id, term_id=None, branch_id=None):
    """Topic-mastery league for one subject across its CBT exams."""
    from models import (db, Subject, CBTExam, CBTQuestion, CBTAttempt, CBTAnswer)

    subject = db.session.get(Subject, subject_id) if subject_id else None
    if not subject:
        return None
    q = CBTExam.query.filter_by(subject_id=subject_id)
    if term_id:
        q = q.filter_by(term_id=term_id)
    if branch_id is not None:
        q = q.filter_by(branch_id=branch_id)
    exams = q.order_by(CBTExam.exam_date, CBTExam.id).all()
    meta = {'subject_id': subject.id, 'subject': subject.name,
            'term_id': term_id, 'exams': len(exams)}
    if not exams:
        meta['insufficient'] = True
        meta['reason'] = 'No CBT exams for this subject in the selected scope.'
        return {'meta': meta, 'topics': [], 'summary': {}, 'recommendations': []}

    exam_ids = [e.id for e in exams]
    exam_name = {e.id: e.title for e in exams}

    # Topic-tagged questions across those exams.
    questions = CBTQuestion.query.filter(CBTQuestion.exam_id.in_(exam_ids)).all()
    topic_of_q, exam_of_q = {}, {}
    topic_items_by_exam = {}          # (exam_id, topic) -> item count
    for qq in questions:
        t = (getattr(qq, 'topic', None) or '').strip()
        if not t:
            continue
        topic_of_q[qq.id] = t
        exam_of_q[qq.id] = qq.exam_id
        topic_items_by_exam[(qq.exam_id, t)] = topic_items_by_exam.get((qq.exam_id, t), 0) + 1
    if not topic_of_q:
        meta['insufficient'] = True
        meta['reason'] = ('None of this subject’s CBT questions are tagged with a topic. '
                          'Tag questions with a topic to unlock this.')
        return {'meta': meta, 'topics': [], 'summary': {}, 'recommendations': []}

    # Submitted attempts (per exam count + which students sat each exam).
    attempts = [a for a in CBTAttempt.query.filter(CBTAttempt.exam_id.in_(exam_ids)).all()
                if a.status == 'Submitted']
    submitted_ids = [a.id for a in attempts]
    submitted_by_exam, students_by_exam = {}, {}
    for a in attempts:
        submitted_by_exam[a.exam_id] = submitted_by_exam.get(a.exam_id, 0) + 1
        students_by_exam.setdefault(a.exam_id, set()).add(a.student_id)
    if not submitted_ids:
        meta['insufficient'] = True
        meta['reason'] = 'No submitted attempts yet for this subject’s exams.'
        return {'meta': meta, 'topics': [], 'summary': {}, 'recommendations': []}

    # Correct answers on the tagged questions.
    correct_by_topic = {}
    qid_set = set(topic_of_q)
    for ans in CBTAnswer.query.filter(CBTAnswer.attempt_id.in_(submitted_ids)).all():
        if ans.question_id in qid_set and ans.is_correct:
            t = topic_of_q[ans.question_id]
            correct_by_topic[t] = correct_by_topic.get(t, 0) + 1

    # Aggregate per topic across exams.
    topics_set = set(topic_of_q.values())
    per_exam_mastery = {t: [] for t in topics_set}     # trend across exams
    total_cells = {t: 0 for t in topics_set}
    items = {t: 0 for t in topics_set}
    exams_with = {t: 0 for t in topics_set}
    students = {t: set() for t in topics_set}
    for e in exams:
        sub_n = submitted_by_exam.get(e.id, 0)
        for t in topics_set:
            k = topic_items_by_exam.get((e.id, t), 0)
            if k == 0:
                continue
            items[t] += k
            exams_with[t] += 1
            students[t] |= students_by_exam.get(e.id, set())
            cells = sub_n * k
            total_cells[t] += cells
            # per-exam mastery for the trend (needs per-exam correct count)

    # Per-exam correct counts (for the trend) — recompute grouped by exam+topic.
    correct_exam_topic = {}
    attempt_exam = {a.id: a.exam_id for a in attempts}
    for ans in CBTAnswer.query.filter(CBTAnswer.attempt_id.in_(submitted_ids)).all():
        if ans.question_id in qid_set and ans.is_correct:
            key = (attempt_exam.get(ans.attempt_id), topic_of_q[ans.question_id])
            correct_exam_topic[key] = correct_exam_topic.get(key, 0) + 1
    for e in exams:
        sub_n = submitted_by_exam.get(e.id, 0)
        for t in topics_set:
            k = topic_items_by_exam.get((e.id, t), 0)
            if k and sub_n:
                m = round(100 * correct_exam_topic.get((e.id, t), 0) / (sub_n * k), 1)
                per_exam_mastery[t].append({'exam': exam_name[e.id], 'mastery': m})

    league = []
    for t in topics_set:
        tc = total_cells[t]
        mastery = round(100 * correct_by_topic.get(t, 0) / tc, 1) if tc else 0
        league.append({
            'topic': t, 'mastery': mastery, 'band': _band(mastery),
            'items': items[t], 'exams': exams_with[t], 'students': len(students[t]),
            'trend': per_exam_mastery[t],
        })
    league.sort(key=lambda x: x['mastery'])       # weakest first

    masteries = [x['mastery'] for x in league]
    summary = {
        'exams': len(exams), 'topics': len(league),
        'submitted': len(submitted_ids),
        'mean_mastery': round(sum(masteries) / len(masteries), 1) if masteries else 0,
        'weak': sum(1 for x in league if x['band'] == 'weak'),
        'secure': sum(1 for x in league if x['band'] == 'secure'),
    }
    return {'meta': meta, 'summary': summary, 'topics': league,
            'recommendations': _recommendations(subject.name, league)}


def _recommendations(subject, league):
    recs = []

    def add(tone, title, text):
        recs.append({'tone': tone, 'title': title, 'text': text})

    weak = [t for t in league if t['band'] == 'weak']
    persistent = [t for t in weak if t['exams'] >= 2]
    if persistent:
        add('negative', 'Persistently weak topics',
            f"{', '.join(t['topic'] for t in persistent[:6])} stayed below 50% mastery "
            f"across {'/'.join(str(t['exams']) for t in persistent[:1])}+ {subject} tests. "
            f"These need a scheme-of-work rethink, not just revision.")
    elif weak:
        add('negative', 'Weak topics',
            f"{', '.join(t['topic'] for t in weak[:6])} are below 50% mastery in {subject}. "
            f"Prioritise them for reteaching.")
    developing = [t for t in league if t['band'] == 'developing']
    if developing:
        add('watch', 'Topics still developing',
            f"{', '.join(t['topic'] for t in developing[:6])} sit at 50–70% — a "
            f"targeted revision push would make them secure.")
    secure = [t for t in league if t['band'] == 'secure']
    if secure and not weak:
        add('positive', 'Strong topic coverage',
            f"Every assessed {subject} topic is at or above 70% mastery — maintain "
            f"with light revision and reallocate time to other subjects.")
    return recs
