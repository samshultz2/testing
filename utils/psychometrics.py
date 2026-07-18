"""Psychometric item analysis for CBT / mock examinations.

Classical Test Theory analysis of an objective (MCQ) CBT exam, computed from the
per-item responses already captured in ``CBTAnswer``. For every item it reports:

* **Difficulty index (p)** — proportion of candidates answering correctly.
* **Discrimination index (D)** — upper-27% minus lower-27% correct proportion.
* **Point-biserial correlation (r_pb)** — item/total-score correlation.
* **Distractor analysis** — how each option performed, flagging non-functioning
  or mis-keyed distractors.
* **Item quality verdict** — keep / review / reject, from the combined evidence.

For the whole exam it reports **KR-20 reliability**, the standard error of
measurement, score descriptives, and plain-English recommendations a teacher or
exams officer can act on. One bulk answer fetch — no N+1.

References: Ebel & Frisbie (difficulty/discrimination bands), Kuder-Richardson
20 (internal consistency), point-biserial for item-total correlation.
"""
from __future__ import annotations

import math


# Ebel & Frisbie discrimination bands.
def _discrimination_band(d):
    if d is None:
        return 'na', 'Not enough data'
    if d < 0:
        return 'negative', 'Negative — likely mis-keyed or flawed'
    if d < 0.20:
        return 'poor', 'Poor — revise'
    if d < 0.30:
        return 'fair', 'Fair — could improve'
    if d < 0.40:
        return 'good', 'Good'
    return 'excellent', 'Excellent'


def _difficulty_band(p):
    if p is None:
        return 'na', 'Not enough data'
    if p >= 0.90:
        return 'too_easy', 'Very easy'
    if p <= 0.20:
        return 'too_hard', 'Very hard'
    if 0.30 <= p <= 0.70:
        return 'ideal', 'Ideal'
    return 'ok', 'Acceptable'


def _kr20_band(r):
    if r is None:
        return 'na', 'Not enough data'
    if r >= 0.90:
        return 'excellent', 'Excellent internal consistency'
    if r >= 0.80:
        return 'good', 'Good'
    if r >= 0.70:
        return 'acceptable', 'Acceptable'
    if r >= 0.60:
        return 'questionable', 'Questionable — several weak items'
    return 'poor', 'Poor — the test is not measuring reliably'


def _item_verdict(d_band, p_band, rpb):
    """Combine the evidence into keep / review / reject."""
    if d_band in ('negative',) or (rpb is not None and rpb < 0):
        return 'reject', 'Reject — negative discrimination (mis-key or ambiguous)'
    if d_band == 'poor' or p_band in ('too_easy', 'too_hard') or (rpb is not None and rpb < 0.15):
        return 'review', 'Review — weak item'
    if d_band == 'fair':
        return 'review', 'Review — modest discrimination'
    return 'keep', 'Keep — sound item'


def item_analysis(exam_id):
    """Full psychometric analysis for a CBT exam. Returns None if the exam is
    missing; a payload with ``insufficient=True`` when there are too few
    submitted attempts to be meaningful (< 5)."""
    from models import db, CBTExam, CBTQuestion, CBTAttempt, CBTAnswer

    exam = db.session.get(CBTExam, exam_id)
    if not exam:
        return None
    questions = exam.questions.order_by(CBTQuestion.order, CBTQuestion.id).all()
    attempts = [a for a in exam.attempts.all() if a.status == 'Submitted']
    n = len(attempts)
    meta = {'exam_id': exam.id, 'title': exam.title,
            'question_count': len(questions), 'respondents': n}
    if n < 5 or not questions:
        meta['insufficient'] = True
        meta['reason'] = ('Need at least 5 submitted attempts for a reliable '
                          'analysis.' if questions else 'This exam has no questions.')
        return {'meta': meta, 'items': [], 'summary': {}, 'recommendations': [],
                'difficulty_hist': [], 'discrimination_hist': [],
                'topics': {'has_topics': False, 'items': [], 'students': [], 'columns': []}}

    attempt_ids = [a.id for a in attempts]
    qids = [q.id for q in questions]
    correct_by_attempt = {aid: set() for aid in attempt_ids}       # aid -> {qid correct}
    chosen = {qid: {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'blank': 0} for qid in qids}
    chosen_by_group = {qid: {} for qid in qids}                    # filled after grouping
    picked = {qid: {} for qid in qids}                             # qid -> {aid: option}
    for ans in CBTAnswer.query.filter(CBTAnswer.attempt_id.in_(attempt_ids)).all():
        if ans.question_id not in chosen:
            continue
        opt = (ans.selected_option or '').upper()
        picked[ans.question_id][ans.attempt_id] = opt or 'blank'
        chosen[ans.question_id][opt if opt in ('A', 'B', 'C', 'D') else 'blank'] += 1
        if ans.is_correct:
            correct_by_attempt[ans.attempt_id].add(ans.question_id)

    # Each attempt's number-correct is its total score for the analysis (sum of
    # item scores — the psychometric standard, independent of mark weighting).
    totals = {aid: len(correct_by_attempt[aid]) for aid in attempt_ids}
    total_values = list(totals.values())
    mean_total = sum(total_values) / n
    var_total = sum((t - mean_total) ** 2 for t in total_values) / n     # population
    sd_total = math.sqrt(var_total)

    # Upper / lower 27% groups (by total score) for the discrimination index.
    ranked = sorted(attempt_ids, key=lambda a: totals[a], reverse=True)
    g = max(1, round(0.27 * n))
    upper, lower = set(ranked[:g]), set(ranked[-g:])
    small_groups = n < 10          # D / r_pb less trustworthy below ~10

    items = []
    sum_pq = 0.0                    # for KR-20
    for idx, q in enumerate(questions, 1):
        qid = q.id
        key = (q.correct_option or '').upper()
        n_correct = sum(1 for aid in attempt_ids if qid in correct_by_attempt[aid])
        p = n_correct / n
        sum_pq += p * (1 - p)
        # Discrimination (upper-lower).
        cu = sum(1 for aid in upper if qid in correct_by_attempt[aid])
        cl = sum(1 for aid in lower if qid in correct_by_attempt[aid])
        d = cu / len(upper) - cl / len(lower) if upper and lower else None
        # Point-biserial (uncorrected item-total correlation).
        rpb = None
        if 0 < n_correct < n and sd_total > 0:
            m1 = sum(totals[aid] for aid in attempt_ids if qid in correct_by_attempt[aid]) / n_correct
            rpb = (m1 - mean_total) / sd_total * math.sqrt(p / (1 - p))
            rpb = round(rpb, 3)
        # Distractor analysis: pick-rate per option + how the upper group split.
        opt_stats = []
        for letter in ('A', 'B', 'C', 'D'):
            picks = chosen[qid][letter]
            up_picks = sum(1 for aid in upper if picked[qid].get(aid) == letter)
            lo_picks = sum(1 for aid in lower if picked[qid].get(aid) == letter)
            rate = round(100 * picks / n, 1)
            is_key = (letter == key)
            # A distractor is "non-functioning" if <5% chose it; a distractor
            # that the upper group prefers to the key hints at a mis-key.
            flag = None
            if not is_key:
                if rate < 5:
                    flag = 'weak'
                elif up_picks > lo_picks and up_picks > 0:
                    flag = 'attractive'      # pulling strong students — check wording
            opt_stats.append({'option': letter, 'picks': picks, 'rate': rate,
                              'is_key': is_key, 'upper': up_picks, 'lower': lo_picks,
                              'flag': flag})
        dead = sum(1 for o in opt_stats if not o['is_key'] and o['flag'] == 'weak')
        d_band, d_label = _discrimination_band(d)
        p_band, p_label = _difficulty_band(p)
        verdict, verdict_label = _item_verdict(d_band, p_band, rpb)
        items.append({
            'number': idx, 'question_id': qid,
            'text': (q.question_text or '')[:180],
            'topic': (getattr(q, 'topic', None) or '').strip() or None,
            'key': key or '—',
            'p': round(p, 3), 'p_pct': round(p * 100, 1),
            'p_band': p_band, 'p_label': p_label,
            'd': round(d, 3) if d is not None else None,
            'd_band': d_band, 'd_label': d_label,
            'rpb': rpb, 'blank': chosen[qid]['blank'],
            'dead_distractors': dead, 'options': opt_stats,
            'verdict': verdict, 'verdict_label': verdict_label,
        })

    # KR-20 internal-consistency reliability.
    k = len(questions)
    kr20 = None
    if k > 1 and var_total > 0:
        kr20 = (k / (k - 1)) * (1 - sum_pq / var_total)
        kr20 = round(max(-1.0, min(1.0, kr20)), 3)
    sem = round(sd_total * math.sqrt(1 - kr20), 2) if kr20 is not None else None
    kr_band, kr_label = _kr20_band(kr20)

    keep = sum(1 for it in items if it['verdict'] == 'keep')
    review = sum(1 for it in items if it['verdict'] == 'review')
    reject = sum(1 for it in items if it['verdict'] == 'reject')
    mean_p = round(sum(it['p'] for it in items) / k, 3)
    mean_d = round(sum(it['d'] for it in items if it['d'] is not None) /
                   max(1, sum(1 for it in items if it['d'] is not None)), 3)

    summary = {
        'respondents': n, 'items': k, 'small_groups': small_groups,
        'kr20': kr20, 'kr20_band': kr_band, 'kr20_label': kr_label,
        'sem': sem, 'mean_score': round(mean_total, 2), 'sd_score': round(sd_total, 2),
        'max_score': max(total_values), 'min_score': min(total_values),
        'mean_pct': round(mean_total / k * 100, 1),
        'mean_difficulty': mean_p, 'mean_discrimination': mean_d,
        'keep': keep, 'review': review, 'reject': reject,
    }

    # Difficulty & discrimination histograms (for charts).
    diff_bins = [('0–20', 0, 0.2), ('20–40', 0.2, 0.4), ('40–60', 0.4, 0.6),
                 ('60–80', 0.6, 0.8), ('80–100', 0.8, 1.01)]
    difficulty_hist = [{'band': lbl, 'count': sum(1 for it in items if lo <= it['p'] < hi)}
                       for lbl, lo, hi in diff_bins]
    disc_bins = [('<0', -1, 0), ('0–0.2', 0, 0.2), ('0.2–0.3', 0.2, 0.3),
                 ('0.3–0.4', 0.3, 0.4), ('≥0.4', 0.4, 1.01)]
    discrimination_hist = [{'band': lbl, 'count': sum(
        1 for it in items if it['d'] is not None and lo <= it['d'] < hi)}
        for lbl, lo, hi in disc_bins]

    # ---- topic mastery (only when questions carry syllabus topics) --------
    name_by_attempt = {a.id: (a.student.full_name if a.student else str(a.student_id))
                       for a in attempts}
    sid_by_attempt = {a.id: a.student_id for a in attempts}
    topics = _topic_mastery(questions, correct_by_attempt, attempt_ids, n,
                            name_by_attempt, sid_by_attempt)

    return {'meta': meta, 'summary': summary, 'items': items,
            'difficulty_hist': difficulty_hist,
            'discrimination_hist': discrimination_hist,
            'topics': topics,
            'recommendations': _recommendations(summary, items, topics)}


def _topic_mastery(questions, correct_by_attempt, attempt_ids, n,
                   name_by_attempt=None, sid_by_attempt=None):
    """Per-syllabus-topic mastery across the cohort, plus a per-student × topic
    matrix for targeted intervention. ``has_topics=False`` when nothing is
    tagged with a topic."""
    name_by_attempt = name_by_attempt or {}
    sid_by_attempt = sid_by_attempt or {}
    topic_qids = {}
    for q in questions:
        t = (getattr(q, 'topic', None) or '').strip()
        if t:
            topic_qids.setdefault(t, []).append(q.id)
    if not topic_qids:
        return {'has_topics': False, 'items': [], 'students': [], 'columns': []}

    out = []
    for topic, qids in topic_qids.items():
        qset = set(qids)
        total_cells = n * len(qids)
        correct_cells = sum(len(correct_by_attempt[a] & qset) for a in attempt_ids)
        below = sum(1 for a in attempt_ids if len(correct_by_attempt[a] & qset) / len(qids) < 0.5)
        mastery = round(100 * correct_cells / total_cells, 1) if total_cells else 0
        band = ('weak' if mastery < 50 else 'developing' if mastery < 70 else 'secure')
        out.append({'topic': topic, 'questions': len(qids), 'mastery': mastery,
                    'band': band, 'below_half': below,
                    'below_half_pct': round(100 * below / n, 1) if n else 0})
    out.sort(key=lambda x: x['mastery'])       # weakest first
    ordered_topics = [t['topic'] for t in out]

    # Per-student matrix: each student's % on each topic (weakest topics first
    # for the columns), their overall topic %, and their own weakest topic.
    students = []
    for a in attempt_ids:
        cells, worst_pct, worst_topic, tot_c, tot_q = {}, 101, None, 0, 0
        for topic in ordered_topics:
            qset = set(topic_qids[topic])
            c = len(correct_by_attempt[a] & qset)
            k = len(qset)
            pct = round(100 * c / k, 0) if k else 0
            cells[topic] = pct
            tot_c += c; tot_q += k
            if pct < worst_pct:
                worst_pct, worst_topic = pct, topic
        students.append({
            'student_id': sid_by_attempt.get(a),
            'name': name_by_attempt.get(a, str(a)),
            'overall': round(100 * tot_c / tot_q, 0) if tot_q else 0,
            'cells': cells, 'weakest': worst_topic,
        })
    students.sort(key=lambda s: s['overall'])   # neediest students first
    return {'has_topics': True, 'items': out, 'columns': ordered_topics, 'students': students}


def _topic_recommendations(topics, add):
    items = (topics or {}).get('items') or []
    if not items:
        return
    weak = [t for t in items if t['band'] == 'weak']
    if weak:
        names = ', '.join(t['topic'] for t in weak[:6])
        add('negative', f'{len(weak)} topic(s) not yet mastered',
            f"Cohort mastery is below 50% on {names}. These are the highest-priority "
            f"topics to reteach before the next assessment.")
    developing = [t for t in items if t['band'] == 'developing']
    if developing:
        add('watch', 'Topics still developing',
            f"{', '.join(t['topic'] for t in developing[:6])} sit at 50–70% mastery — "
            f"a targeted revision session would push them to secure.")
    secure = [t for t in items if t['band'] == 'secure']
    if secure and not weak:
        add('positive', 'Well-understood topics',
            f"{', '.join(t['topic'] for t in secure[:6])} are secure (≥70% mastery) — "
            f"maintain with light revision and reallocate teaching time to weaker areas.")


def _recommendations(summary, items, topics=None):
    recs = []

    def add(tone, title, text):
        recs.append({'tone': tone, 'title': title, 'text': text})

    # Topic mastery leads — it's the most actionable teaching signal.
    _topic_recommendations(topics, add)

    kr = summary.get('kr20')
    if kr is not None:
        if kr >= 0.8:
            add('positive', 'Reliable test',
                f"KR-20 reliability is {kr} ({summary['kr20_label'].lower()}). Scores "
                f"from this test can be trusted for ranking and decisions.")
        elif kr >= 0.7:
            add('watch', 'Acceptable reliability',
                f"KR-20 is {kr}. Usable, but tightening the flagged items would sharpen it.")
        else:
            add('negative', 'Low reliability',
                f"KR-20 is {kr} — below the 0.70 threshold. Several items are not "
                f"pulling in the same direction; revise or replace the flagged ones "
                f"before relying on these scores.")
    if summary.get('small_groups'):
        add('watch', 'Small candidate group',
            "With under 10 candidates, difficulty and discrimination estimates are "
            "indicative rather than definitive — treat item flags as prompts to review.")

    rejects = [it for it in items if it['verdict'] == 'reject']
    if rejects:
        nums = ', '.join(f"Q{it['number']}" for it in rejects[:8])
        add('negative', f'{len(rejects)} item(s) to reject',
            f"{nums} show negative discrimination — strong students got them wrong more "
            f"often than weak students. Check for a mis-keyed answer or ambiguous wording.")
    reviews = [it for it in items if it['verdict'] == 'review']
    if reviews:
        nums = ', '.join(f"Q{it['number']}" for it in reviews[:8])
        add('watch', f'{len(reviews)} item(s) to review',
            f"{nums} are weak (too easy/hard or low discrimination). Rework them to "
            f"better separate stronger and weaker candidates.")
    too_easy = [it for it in items if it['p_band'] == 'too_easy']
    too_hard = [it for it in items if it['p_band'] == 'too_hard']
    if too_easy:
        nums = ', '.join('Q%d' % it['number'] for it in too_easy[:8])
        add('watch', f'{len(too_easy)} very easy item(s)',
            f"Answered correctly by ≥90% ({nums}). "
            f"They add little information — replace some with more discriminating items.")
    if too_hard:
        nums = ', '.join('Q%d' % it['number'] for it in too_hard[:8])
        add('watch', f'{len(too_hard)} very hard item(s)',
            f"Answered correctly by ≤20% ({nums}). "
            f"Confirm the topic was taught and the wording is clear.")
    dead = [it for it in items if it['dead_distractors']]
    if dead:
        total_dead = sum(it['dead_distractors'] for it in dead)
        add('watch', f'{total_dead} non-functioning distractor(s)',
            f"Across {len(dead)} item(s), some options were chosen by under 5% of "
            f"candidates. Replace them with more plausible alternatives to make the "
            f"items work harder.")
    if summary['keep'] and not rejects and not reviews:
        add('positive', 'Strong item bank',
            f"All {summary['items']} items are psychometrically sound — good difficulty "
            f"spread and positive discrimination. Bank them for reuse.")
    return recs
