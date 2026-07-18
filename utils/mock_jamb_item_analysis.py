"""Item- and topic-level analysis for the *online* Mock JAMB sitting.

Where ``mock_deep_analytics`` works off the final subject scores
(``MockJAMBResult``), this engine reaches into the actual keystrokes of the
online sitting — every ``MockJAMBAnswer`` against every ``MockJAMBQuestion`` —
to answer the questions a head of department actually asks after a mock:

* **Which questions were flawed?** Classic item analysis — difficulty
  (p-value), discrimination (upper/lower 27% index) and distractor analysis —
  surfaces items that are too easy/hard, don't separate strong from weak
  candidates, or have a mis-keyed / stronger-than-the-answer distractor.
* **Which topics and sub-topics did the cohort fail?** Every served question is
  tagged with its syllabus topic/sub-topic, so correct/served rolls up to a
  topic mastery league and a sub-topic drill-down — the weakest areas to
  re-teach, per subject.
* **What should management, teachers and students do about it?** An
  evidence-based recommendation layer for the three audiences, mirroring the
  deep-analytics report.

Denominator care: a candidate is only counted on a question that was actually
*served* to them (the sitting serves a randomised, possibly capped subset per
candidate). The served set is reconstructed deterministically from the attempt
(the same function the sitting and grader use), so a blank on a served question
counts as wrong, while a question the candidate never saw is not held against
them — or against the item's difficulty.

Query budget: one batched fetch of submitted attempts, one of their answers,
one of the exam's questions/passages; the per-attempt served set is computed in
memory.
"""
from __future__ import annotations

import datetime

# ---------------------------------------------------------------------------
# psychometric thresholds (objective, 4-option MCQ — JAMB style)
# ---------------------------------------------------------------------------
DIFF_TOO_EASY = 0.85        # p-value at/above this: nearly everyone right
DIFF_TOO_HARD = 0.30        # p-value below this: nearly everyone wrong
DISC_EXCELLENT = 0.40
DISC_GOOD = 0.30
DISC_ACCEPTABLE = 0.20
DISC_POOR = 0.10            # below this: revise; below 0 = negative (mis-key?)
MIN_ITEM_RESPONSES = 5      # fewer served responses than this: read with caution
GROUP_FRACTION = 0.27       # upper / lower group size for the discrimination index
GUESS_RATE = 0.25           # 1/4 — chance level on a 4-option item


def _rate(num, den):
    return round(100 * num / den, 1) if den else None


def _pct(x):
    return round(100 * x, 1) if x is not None else None


# ---------------------------------------------------------------------------
# served-set reconstruction (who actually saw each question)
# ---------------------------------------------------------------------------

def _served_by_attempt(exam, attempts):
    """``{attempt_id: set(question_id served)}`` — reproduces exactly the paper
    each candidate sat, using the same deterministic builder as the sitting."""
    from utils.mock_jamb_sitting import candidate_subject_ids, subject_items
    out = {}
    for att in attempts:
        served = set()
        for sid in candidate_subject_ids(exam, att.student):
            _items, s = subject_items(exam, sid, att)
            served |= s
        out[att.id] = served
    return out


# ---------------------------------------------------------------------------
# item analysis
# ---------------------------------------------------------------------------

def _difficulty_band(p):
    if p is None:
        return ('unknown', 'No data')
    if p >= DIFF_TOO_EASY:
        return ('easy', 'Too easy')
    if p < DIFF_TOO_HARD:
        return ('hard', 'Too hard')
    return ('ideal', 'Well-pitched')


def _discrimination_band(d):
    if d is None:
        return ('unknown', 'Too few')
    if d < 0:
        return ('negative', 'Negative — check key')
    if d < DISC_POOR:
        return ('poor', 'Poor')
    if d < DISC_ACCEPTABLE:
        return ('marginal', 'Marginal')
    if d < DISC_GOOD:
        return ('acceptable', 'Acceptable')
    if d < DISC_EXCELLENT:
        return ('good', 'Good')
    return ('excellent', 'Excellent')


def _item_flags(p, d, distractors, correct_letter, served):
    """Human-readable review flags for one item (empty list = clean)."""
    flags = []
    if served < MIN_ITEM_RESPONSES:
        flags.append(('info', f'Only {served} candidate(s) served — indicative only'))
    if p is not None and p >= DIFF_TOO_EASY:
        flags.append(('warn', 'Almost everyone correct — adds little discrimination'))
    if p is not None and p < DIFF_TOO_HARD:
        flags.append(('warn', 'Very few correct — too hard, mis-keyed or off-syllabus'))
    if d is not None and d < 0:
        flags.append(('bad', 'Strong candidates did WORSE — likely a wrong key or ambiguous stem'))
    elif d is not None and d < DISC_POOR:
        flags.append(('warn', 'Does not separate strong from weak candidates — revise'))
    # a distractor picked by the upper group more than the key
    for opt in distractors:
        if opt['letter'] == correct_letter:
            continue
        if opt['upper'] is not None and opt['key_upper'] is not None and opt['upper'] > opt['key_upper'] and opt['count'] >= 2:
            flags.append(('bad', f"Option {opt['letter']} lured strong candidates more than the key — ambiguous or mis-keyed"))
            break
    # a dead distractor nobody chose
    dead = [o['letter'] for o in distractors
            if o['letter'] != correct_letter and o['count'] == 0 and served >= MIN_ITEM_RESPONSES]
    if len(dead) >= 2:
        flags.append(('info', f"Options {', '.join(dead)} chosen by no one — implausible distractors"))
    return flags


def _analyse_items(questions, answers_by_q, served_ids_by_q, upper_ids, lower_ids):
    """Full item analysis for every question that was served at least once."""
    items = []
    for q in questions:
        served_atts = served_ids_by_q.get(q.id, set())
        served = len(served_atts)
        if served == 0:
            continue
        alist = answers_by_q.get(q.id, {})     # attempt_id -> answer
        correct_letter = (q.correct_option or '').upper()

        n_correct = sum(1 for aid in served_atts
                        if alist.get(aid) and alist[aid].is_correct)
        blank = sum(1 for aid in served_atts if aid not in alist or not alist[aid].selected_option)
        p = n_correct / served if served else None

        # upper / lower split among *this item's* served candidates
        up = served_atts & upper_ids
        lo = served_atts & lower_ids
        up_correct = sum(1 for aid in up if alist.get(aid) and alist[aid].is_correct)
        lo_correct = sum(1 for aid in lo if alist.get(aid) and alist[aid].is_correct)
        p_up = (up_correct / len(up)) if up else None
        p_lo = (lo_correct / len(lo)) if lo else None
        d = (p_up - p_lo) if (p_up is not None and p_lo is not None) else None

        # distractor analysis on ORIGINAL letters (grading-safe)
        distractors = []
        for letter, text in q.options:
            if not text:
                continue
            chosen = [aid for aid in served_atts
                      if alist.get(aid) and (alist[aid].selected_option or '').upper() == letter]
            up_ch = sum(1 for aid in chosen if aid in upper_ids)
            lo_ch = sum(1 for aid in chosen if aid in lower_ids)
            distractors.append({
                'letter': letter, 'text': text, 'count': len(chosen),
                'pct': _rate(len(chosen), served - blank) if (served - blank) else None,
                'is_correct': letter == correct_letter,
                'upper': (up_ch / len(up)) if up else None,
                'lower': (lo_ch / len(lo)) if lo else None,
                'key_upper': (up_correct / len(up)) if up else None,
            })

        diff_band, diff_label = _difficulty_band(p)
        disc_band, disc_label = _discrimination_band(d)
        flags = _item_flags(p, d, distractors, correct_letter, served)
        items.append({
            'id': q.id, 'order': q.order, 'subject': q.subject.name if q.subject else '',
            'subject_id': q.subject_id, 'topic': q.topic or 'Untagged',
            'subtopic': q.subtopic or '', 'text': q.question_text,
            'correct_option': correct_letter,
            'served': served, 'answered': served - blank, 'blank': blank,
            'correct': n_correct, 'p_value': _pct(p), 'p_raw': p,
            'diff_band': diff_band, 'diff_label': diff_label,
            'discrimination': (round(d, 2) if d is not None else None),
            'disc_band': disc_band, 'disc_label': disc_label,
            'blank_rate': _rate(blank, served),
            'distractors': distractors,
            'flags': flags, 'needs_review': any(f[0] in ('bad', 'warn') for f in flags),
        })
    return items


# ---------------------------------------------------------------------------
# topic / sub-topic mastery
# ---------------------------------------------------------------------------

def _mastery_band(rate):
    if rate is None:
        return ('unknown', 'No data')
    if rate < 40:
        return ('critical', 'Critical')
    if rate < 55:
        return ('weak', 'Weak')
    if rate < 70:
        return ('fair', 'Fair')
    if rate < 85:
        return ('good', 'Good')
    return ('strong', 'Mastered')


def _topic_mastery(items):
    """Roll served/correct up to (subject, topic) and (subject, topic, sub-topic)."""
    topics, subs = {}, {}
    for it in items:
        tkey = (it['subject'], it['topic'])
        t = topics.setdefault(tkey, {'subject': it['subject'], 'topic': it['topic'],
                                     'served': 0, 'correct': 0, 'items': 0, 'subtopics': {}})
        t['served'] += it['answered']       # mastery over attempted responses
        t['correct'] += it['correct']
        t['items'] += 1
        if it['subtopic']:
            skey = it['subtopic']
            s = t['subtopics'].setdefault(skey, {'subtopic': skey, 'served': 0, 'correct': 0, 'items': 0})
            s['served'] += it['answered']
            s['correct'] += it['correct']
            s['items'] += 1

    out = []
    for t in topics.values():
        rate = _rate(t['correct'], t['served'])
        band, label = _mastery_band(rate)
        sub_rows = []
        for s in t['subtopics'].values():
            srate = _rate(s['correct'], s['served'])
            sband, slabel = _mastery_band(srate)
            sub_rows.append({'subtopic': s['subtopic'], 'items': s['items'],
                             'served': s['served'], 'correct': s['correct'],
                             'mastery': srate, 'band': sband, 'band_label': slabel})
        sub_rows.sort(key=lambda r: (r['mastery'] if r['mastery'] is not None else 0))
        out.append({'subject': t['subject'], 'topic': t['topic'], 'items': t['items'],
                    'served': t['served'], 'correct': t['correct'], 'mastery': rate,
                    'band': band, 'band_label': label, 'subtopics': sub_rows})
    out.sort(key=lambda r: (r['mastery'] if r['mastery'] is not None else 0))
    return out


def _subject_mastery(items):
    acc = {}
    for it in items:
        a = acc.setdefault(it['subject'], {'subject': it['subject'], 'served': 0,
                                           'correct': 0, 'items': 0})
        a['served'] += it['answered']
        a['correct'] += it['correct']
        a['items'] += 1
    out = []
    for a in acc.values():
        rate = _rate(a['correct'], a['served'])
        band, label = _mastery_band(rate)
        out.append({'subject': a['subject'], 'items': a['items'], 'served': a['served'],
                    'correct': a['correct'], 'mastery': rate, 'band': band, 'band_label': label})
    out.sort(key=lambda r: (r['mastery'] if r['mastery'] is not None else 0))
    return out


# ---------------------------------------------------------------------------
# recommendations
# ---------------------------------------------------------------------------

def _recommendations(subject_mastery, topics, flagged, blank_heavy, cohort_mastery):
    students, teachers, mgmt = [], [], []

    def rec(bucket, tone, title, text):
        bucket.append({'tone': tone, 'title': title, 'text': text})

    weak_topics = [t for t in topics if t['band'] in ('critical', 'weak')][:6]
    crit_subj = [s for s in subject_mastery if s['band'] in ('critical', 'weak')]

    # --- students ---
    if weak_topics:
        rec(students, 'negative', 'Topics the cohort has not mastered',
            'Re-drill ' + ', '.join(f"{t['topic']} ({t['subject']}, {t['mastery']}%)"
                                    for t in weak_topics[:5]) +
            '. Set targeted past-questions and a short timed quiz on each until mastery clears 70%.')
    if blank_heavy:
        rec(students, 'warning', 'Questions left blank under time pressure',
            f"{len(blank_heavy)} item(s) were skipped by many candidates — coach exam pacing and "
            f"'never leave a blank' guessing strategy, since JAMB does not penalise wrong answers.")
    strong_subj = [s for s in subject_mastery if s['band'] in ('good', 'strong')]
    if strong_subj:
        rec(students, 'positive', 'Subjects on top',
            ', '.join(s['subject'] for s in strong_subj[:5]) +
            ' are well mastered — stretch with harder items and protect the lead.')

    # --- teachers ---
    if crit_subj:
        rec(teachers, 'negative', 'Re-teach the weak subjects',
            'Focus department time on ' + ', '.join(f"{s['subject']} ({s['mastery']}%)"
                                                     for s in crit_subj[:5]) +
            '. Rebuild from the sub-topics with the lowest mastery and re-test.')
    if weak_topics:
        rec(teachers, 'warning', 'Sub-topic clinics',
            'Run focused clinics on the weakest sub-topics: ' +
            ', '.join(f"{sub['subtopic']}" for t in weak_topics for sub in t['subtopics'][:1] if sub['band'] in ('critical', 'weak'))[:400] +
            ' — short, specific and re-tested next mock.')

    # --- management ---
    if flagged:
        rec(mgmt, 'insight', 'Clean the question bank',
            f"{len(flagged)} item(s) are flawed (too easy/hard, poor discrimination or a "
            f"mis-keyed/ambiguous option). Review and fix or retire them so future mocks measure "
            f"ability, not item defects — the biggest single lift to data quality.")
    neg = [f for f in flagged if f['disc_band'] == 'negative']
    if neg:
        rec(mgmt, 'negative', 'Possible wrong answer keys',
            f"{len(neg)} item(s) had strong candidates scoring WORSE than weak ones — a classic "
            f"sign of a wrong key. Verify each answer key before trusting these scores.")
    if cohort_mastery is not None and cohort_mastery < 50:
        rec(mgmt, 'negative', 'Cohort below 50% mastery',
            f"Overall item mastery is {cohort_mastery}%. Treat as a whole-school priority: revision "
            f"timetable, extra contact hours and weekly tracked mocks to the real exam.")
    rec(mgmt, 'insight', 'Read items with the cohort, not alone',
        'Difficulty and discrimination depend on this cohort. Confirm flagged items across the next '
        'mock before retiring them, and use topic mastery to steer the revision plan.')

    return {'students': students, 'teachers': teachers, 'management': mgmt}


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------

def item_analysis(exam_id, allowed_ids=None):
    """Item- and topic-level analysis of the online sitting for one Mock JAMB.

    ``allowed_ids`` optionally restricts candidates to a set of branch ids.
    Returns ``meta``, ``kpis``, ``subject_mastery``, ``topics``, ``items``,
    ``flagged``, ``distribution`` (difficulty + discrimination) and
    ``recommendations``; ``meta.empty`` is True when no one has sat it online.
    """
    from models import (db, MockJAMBExam, MockJAMBQuestion, MockJAMBAttempt,
                        MockJAMBAnswer)
    exam = db.session.get(MockJAMBExam, exam_id)
    if not exam:
        return None

    meta = {
        'exam_id': exam.id, 'exam_name': exam.display_name, 'full_name': exam.name,
        'exam_date': exam.exam_date.strftime('%d %B %Y') if exam.exam_date else '',
        'session_name': exam.session.name if exam.session else '',
        'generated_at': datetime.datetime.now().strftime('%d %b %Y, %H:%M'),
        'empty': False,
    }

    attempts = MockJAMBAttempt.query.filter_by(
        mock_exam_id=exam.id, status='Submitted').all()
    if allowed_ids is not None:
        attempts = [a for a in attempts if a.student and a.student.branch_id in allowed_ids]

    empty_payload = {'meta': meta, 'kpis': [], 'subject_mastery': [], 'topics': [],
                     'items': [], 'flagged': [], 'blank_heavy': [],
                     'distribution': {'difficulty': [], 'discrimination': []},
                     'recommendations': {'students': [], 'teachers': [], 'management': []}}
    if not attempts:
        meta['empty'] = True
        return empty_payload

    # served set per attempt + answers indexed by question
    served_by_att = _served_by_attempt(exam, attempts)
    att_ids = {a.id for a in attempts}
    answers = (MockJAMBAnswer.query
               .filter(MockJAMBAnswer.attempt_id.in_(att_ids)).all())
    answers_by_q = {}
    for a in answers:
        answers_by_q.setdefault(a.question_id, {})[a.attempt_id] = a
    served_ids_by_q = {}
    for aid, qids in served_by_att.items():
        for qid in qids:
            served_ids_by_q.setdefault(qid, set()).add(aid)

    # upper / lower groups by total score (for discrimination)
    ranked = sorted(attempts, key=lambda a: (a.total_score or 0), reverse=True)
    gsize = max(1, int(len(ranked) * GROUP_FRACTION)) if len(ranked) >= 4 else 0
    upper_ids = {a.id for a in ranked[:gsize]} if gsize else set()
    lower_ids = {a.id for a in ranked[-gsize:]} if gsize else set()

    questions = (MockJAMBQuestion.query.filter_by(mock_exam_id=exam.id).all())
    items = _analyse_items(questions, answers_by_q, served_ids_by_q, upper_ids, lower_ids)
    if not items:
        meta['empty'] = True
        return empty_payload

    subject_mastery = _subject_mastery(items)
    topics = _topic_mastery(items)
    flagged = sorted([it for it in items if it['needs_review']],
                     key=lambda it: (it['disc_band'] != 'negative', it['p_raw'] if it['p_raw'] is not None else 1))
    blank_heavy = sorted([it for it in items if (it['blank_rate'] or 0) >= 40],
                         key=lambda it: -(it['blank_rate'] or 0))

    total_correct = sum(it['correct'] for it in items)
    total_served = sum(it['answered'] for it in items)
    cohort_mastery = _rate(total_correct, total_served)

    # KPIs
    disc_scored = [it for it in items if it['discrimination'] is not None]
    ideal = sum(1 for it in items if it['diff_band'] == 'ideal')
    kpis = [
        {'label': 'Online sitters', 'value': len(attempts), 'sub': 'submitted attempts', 'tone': 'blue'},
        {'label': 'Questions analysed', 'value': len(items), 'sub': 'served ≥ 1 candidate', 'tone': 'teal'},
        {'label': 'Cohort mastery', 'value': f'{cohort_mastery}%' if cohort_mastery is not None else '—',
         'sub': 'correct of attempted', 'tone': ('green' if (cohort_mastery or 0) >= 55 else 'red')},
        {'label': 'Well-pitched items', 'value': f'{_rate(ideal, len(items))}%' if items else '—',
         'sub': f'{ideal} of {len(items)} items', 'tone': 'purple'},
        {'label': 'Items to review', 'value': len(flagged),
         'sub': 'flawed / mis-keyed', 'tone': ('amber' if flagged else 'green')},
    ]

    # distributions for charts
    diff_dist = [
        {'band': 'Too hard (<30%)', 'key': 'hard', 'count': sum(1 for it in items if it['diff_band'] == 'hard')},
        {'band': 'Well-pitched', 'key': 'ideal', 'count': ideal},
        {'band': 'Too easy (≥85%)', 'key': 'easy', 'count': sum(1 for it in items if it['diff_band'] == 'easy')},
    ]
    disc_order = [('negative', 'Negative'), ('poor', 'Poor'), ('marginal', 'Marginal'),
                  ('acceptable', 'Acceptable'), ('good', 'Good'), ('excellent', 'Excellent')]
    disc_dist = [{'band': label, 'key': key,
                  'count': sum(1 for it in disc_scored if it['disc_band'] == key)}
                 for key, label in disc_order]

    meta['sitters'] = len(attempts)
    meta['items_count'] = len(items)
    meta['cohort_mastery'] = cohort_mastery
    meta['flagged_count'] = len(flagged)
    meta['group_size'] = gsize

    recommendations = _recommendations(subject_mastery, topics, flagged, blank_heavy, cohort_mastery)

    return {
        'meta': meta, 'kpis': kpis, 'subject_mastery': subject_mastery, 'topics': topics,
        'items': items, 'flagged': flagged, 'blank_heavy': blank_heavy,
        'distribution': {'difficulty': diff_dist, 'discrimination': disc_dist},
        'recommendations': recommendations,
    }
