"""Mock-examination validation — how well do the school's mock exams predict the
real thing?

Pairs each candidate's **mock** result with their **actual** external result and
reports the predictive quality of the mock:

* **JAMB** (numeric 0–400): correlation, R², mean absolute error, bias
  (systematic over/under-prediction), RMSE, a calibration line
  (actual ≈ a + b·mock), a 95% confidence interval for the average error, and a
  threshold confusion matrix at the admission cut-off (does a mock ≥ cut-off
  actually predict a real ≥ cut-off?).
* **WAEC** (grades A1–F9): exact-grade agreement, within-one-grade agreement,
  correlation on grade points, average grade error/bias, and per-subject
  reliability plus a credit-agreement (C6+) confusion matrix.

The verdict tells a school whether its mocks are realistic, optimistic or
pessimistic — so mock scores can be trusted (or adjusted) for guidance and
intervention decisions.
"""
from __future__ import annotations

import math

CUTOFF_DEFAULT = 200          # typical JAMB admission threshold


# --------------------------------------------------------------------------- #
# small stats helpers
# --------------------------------------------------------------------------- #
def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return cov / math.sqrt(vx * vy)


def _regression(xs, ys):
    """Least-squares slope & intercept of y (actual) on x (mock)."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None, None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    return b, a


def _confusion(pred_pos, actual_pos):
    """(tp, fp, fn, tn) from two equal-length boolean lists."""
    tp = sum(1 for p, a in zip(pred_pos, actual_pos) if p and a)
    fp = sum(1 for p, a in zip(pred_pos, actual_pos) if p and not a)
    fn = sum(1 for p, a in zip(pred_pos, actual_pos) if not p and a)
    tn = sum(1 for p, a in zip(pred_pos, actual_pos) if not p and not a)
    return tp, fp, fn, tn


def _rate(num, den):
    return round(100 * num / den, 1) if den else None


# --------------------------------------------------------------------------- #
# JAMB (numeric)
# --------------------------------------------------------------------------- #
def _resolve_jamb_mock(session_id, mock_exam_id):
    from models import db
    from models.mock_jamb import MockJAMBExam
    if mock_exam_id:
        return db.session.get(MockJAMBExam, mock_exam_id)
    if session_id:
        return (MockJAMBExam.query.filter_by(session_id=session_id)
                .order_by(MockJAMBExam.exam_number.desc()).first())
    return None


def jamb_validation(session_id=None, mock_exam_id=None, year=None):
    """Validate Mock JAMB against actual JAMB. Uses the given mock exam, or the
    final (highest-numbered) mock of the session."""
    from models import db, JAMBResult
    from models.mock_jamb import MockJAMBExam, MockJAMBResult

    mock = _resolve_jamb_mock(session_id, mock_exam_id)
    if not mock:
        return None
    session_id = mock.session_id
    meta = {'kind': 'jamb', 'mock_exam_id': mock.id, 'mock_name': mock.display_name,
            'session_id': session_id, 'cutoff': CUTOFF_DEFAULT}

    def actual_for(student_id):
        q = JAMBResult.query.filter_by(student_id=student_id)
        if year:
            q = q.filter_by(exam_year=year)
        return q.order_by(JAMBResult.exam_year.desc()).first()

    mocks = MockJAMBResult.query.filter_by(mock_exam_id=mock.id).all()
    pairs = []
    for r in mocks:
        a = actual_for(r.student_id)
        if a and a.total_score is not None and r.total_score is not None:
            pairs.append({'student_id': r.student_id,
                          'name': r.student.full_name if r.student else str(r.student_id),
                          'mock': r.total_score, 'actual': a.total_score,
                          'year': a.exam_year})
    if len(pairs) < 3:
        meta['insufficient'] = True
        meta['matched'] = len(pairs)
        meta['reason'] = ('Need at least 3 candidates with both a mock and an '
                          'actual JAMB result to validate.')
        return {'meta': meta, 'summary': {}, 'pairs': pairs, 'per_mock': [],
                'recommendations': [], 'scatter': []}

    xs = [p['mock'] for p in pairs]
    ys = [p['actual'] for p in pairs]
    n = len(pairs)
    errors = [p['actual'] - p['mock'] for p in pairs]      # +ve = mock under-predicted
    mae = sum(abs(e) for e in errors) / n
    me = sum(errors) / n                                    # bias
    rmse = math.sqrt(sum(e * e for e in errors) / n)
    r = _pearson(xs, ys)
    b, a_int = _regression(xs, ys)
    within20 = sum(1 for e in errors if abs(e) <= 20)
    within40 = sum(1 for e in errors if abs(e) <= 40)
    over = sum(1 for e in errors if e < -5)                # mock higher than actual
    under = sum(1 for e in errors if e > 5)
    sd_err = math.sqrt(sum((e - me) ** 2 for e in errors) / (n - 1)) if n > 1 else 0
    ci_half = 1.96 * sd_err / math.sqrt(n) if n else 0

    cut = CUTOFF_DEFAULT
    pred_pos = [p['mock'] >= cut for p in pairs]
    act_pos = [p['actual'] >= cut for p in pairs]
    tp, fp, fn, tn = _confusion(pred_pos, act_pos)

    bias_dir = ('optimistic' if me < -8 else 'pessimistic' if me > 8 else 'well-calibrated')
    summary = {
        'matched': n, 'mock_mean': round(sum(xs) / n, 1), 'actual_mean': round(sum(ys) / n, 1),
        'correlation': round(r, 3) if r is not None else None,
        'r_squared': round(r * r, 3) if r is not None else None,
        'mae': round(mae, 1), 'bias': round(me, 1), 'rmse': round(rmse, 1),
        'bias_ci_low': round(me - ci_half, 1), 'bias_ci_high': round(me + ci_half, 1),
        'within20_pct': _rate(within20, n), 'within40_pct': _rate(within40, n),
        'over_pred': over, 'under_pred': under,
        'slope': round(b, 3) if b is not None else None,
        'intercept': round(a_int, 1) if a_int is not None else None,
        'bias_direction': bias_dir,
        'threshold': {
            'cutoff': cut, 'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'accuracy': _rate(tp + tn, n), 'sensitivity': _rate(tp, tp + fn),
            'specificity': _rate(tn, tn + fp), 'ppv': _rate(tp, tp + fp),
        },
    }

    # Which mock in the session predicts actual best (correlation + MAE)?
    per_mock = []
    exams = (MockJAMBExam.query.filter_by(session_id=session_id)
             .order_by(MockJAMBExam.exam_number).all())
    for ex in exams:
        exs, eys = [], []
        for r2 in MockJAMBResult.query.filter_by(mock_exam_id=ex.id).all():
            a = actual_for(r2.student_id)
            if a and a.total_score is not None and r2.total_score is not None:
                exs.append(r2.total_score); eys.append(a.total_score)
        if len(exs) >= 3:
            rr = _pearson(exs, eys)
            emae = sum(abs(ay - mx) for mx, ay in zip(exs, eys)) / len(exs)
            per_mock.append({'name': ex.display_name, 'number': ex.exam_number,
                             'matched': len(exs),
                             'correlation': round(rr, 3) if rr is not None else None,
                             'mae': round(emae, 1)})

    scatter = [{'mock': p['mock'], 'actual': p['actual'], 'name': p['name']} for p in pairs]
    return {'meta': meta, 'summary': summary, 'pairs': pairs, 'per_mock': per_mock,
            'scatter': scatter,
            'recommendations': _jamb_recommendations(summary)}


def _jamb_recommendations(s):
    recs = []

    def add(tone, title, text):
        recs.append({'tone': tone, 'title': title, 'text': text})

    r = s.get('correlation')
    if r is not None:
        if r >= 0.7:
            add('positive', 'Mock strongly tracks the real exam',
                f"Correlation r={r} (R²={s['r_squared']}) — mock rankings closely match "
                f"actual JAMB. Mock scores are a trustworthy guide for streaming and targets.")
        elif r >= 0.4:
            add('watch', 'Moderate predictive strength',
                f"Correlation r={r}. Mocks give a fair signal but rank order shifts; use "
                f"them alongside classwork, not alone, for high-stakes decisions.")
        else:
            add('negative', 'Weak predictive link',
                f"Correlation r={r}. The mock is not tracking actual performance — review "
                f"how closely it mirrors JAMB in coverage, timing and difficulty.")
    me = s.get('bias')
    if me is not None:
        if s['bias_direction'] == 'optimistic':
            add('negative', 'Mocks are optimistic',
                f"On average actual scores are {abs(me)} points BELOW the mock "
                f"(95% CI {s['bias_ci_low']}…{s['bias_ci_high']}). Students may be lulled "
                f"into complacency — harden the mock or communicate the gap.")
        elif s['bias_direction'] == 'pessimistic':
            add('watch', 'Mocks are pessimistic',
                f"Actual scores average {me} points ABOVE the mock. The mock is harder "
                f"than JAMB; reassure students and recalibrate targets upward.")
        else:
            add('positive', 'Well-calibrated difficulty',
                f"Average error is just {me} points (95% CI {s['bias_ci_low']}…"
                f"{s['bias_ci_high']}) — the mock's difficulty mirrors the real exam well.")
    if s.get('mae') is not None:
        add('watch', 'Typical error band',
            f"A mock score is typically within ±{s['mae']} points of the eventual JAMB "
            f"(RMSE {s['rmse']}); {s['within40_pct']}% of candidates land within 40 points. "
            f"Treat a mock as a range, not a fixed prediction.")
    th = s.get('threshold') or {}
    if th.get('sensitivity') is not None:
        add('watch', f"Cut-off ({th['cutoff']}) reliability",
            f"Of candidates who really cleared {th['cutoff']}, the mock flagged "
            f"{th['sensitivity']}% in advance; overall the mock's pass/fail call was "
            f"{th['accuracy']}% accurate. {th['fn']} candidate(s) cleared despite a "
            f"below-cut-off mock, and {th['fp']} fell short despite passing the mock.")
    return recs


# --------------------------------------------------------------------------- #
# WAEC (grades)
# --------------------------------------------------------------------------- #
def _norm_subject(s):
    return (s or '').strip().upper()


def _resolve_waec_mock(session_id, mock_exam_id):
    from models import db
    from models.mock_waec import MockWAECExam
    if mock_exam_id:
        return db.session.get(MockWAECExam, mock_exam_id)
    if session_id:
        return (MockWAECExam.query.filter_by(session_id=session_id)
                .order_by(MockWAECExam.exam_number.desc()).first())
    return None


def waec_validation(session_id=None, mock_exam_id=None, year=None):
    """Validate Mock WAEC grades against actual WAEC grades, per subject."""
    from models import db, WAECResult
    from models.mock_waec import MockWAECExam, MockWAECResult

    mock = _resolve_waec_mock(session_id, mock_exam_id)
    if not mock:
        return None
    meta = {'kind': 'waec', 'mock_exam_id': mock.id, 'mock_name': mock.display_name,
            'session_id': mock.session_id}
    gp = WAECResult.grade_to_points

    # Actual grades indexed by (student, subject) — the student's latest year, or
    # the requested year.
    def actual_grade(student_id, subject_norm):
        q = WAECResult.query.filter_by(student_id=student_id)
        if year:
            q = q.filter_by(exam_year=year)
        best = None
        for w in q.all():
            if _norm_subject(w.subject) == subject_norm:
                if best is None or w.exam_year > best.exam_year:
                    best = w
        return best

    pairs = []
    for r in MockWAECResult.query.filter_by(mock_exam_id=mock.id).all():
        if not r.grade:
            continue
        subj = _norm_subject(r.subject)
        a = actual_grade(r.student_id, subj)
        if a and a.grade:
            pairs.append({'student_id': r.student_id, 'subject': r.subject,
                          'subject_norm': subj, 'mock_grade': r.grade,
                          'actual_grade': a.grade, 'mock_pts': gp(r.grade),
                          'actual_pts': gp(a.grade)})
    if len(pairs) < 3:
        meta['insufficient'] = True
        meta['matched'] = len(pairs)
        meta['reason'] = ('Need at least 3 subject results with both a mock and an '
                          'actual WAEC grade to validate.')
        return {'meta': meta, 'summary': {}, 'subjects': [], 'recommendations': []}

    def credit(gr):
        return WAECResult.is_pass(gr)

    def block(rows):
        n = len(rows)
        exact = sum(1 for p in rows if p['mock_grade'] == p['actual_grade'])
        within1 = sum(1 for p in rows if abs(p['mock_pts'] - p['actual_pts']) <= 1)
        errs = [p['actual_pts'] - p['mock_pts'] for p in rows]     # +ve = actual worse
        mae = sum(abs(e) for e in errs) / n
        bias = sum(errs) / n
        rr = _pearson([p['mock_pts'] for p in rows], [p['actual_pts'] for p in rows])
        pred = [credit(p['mock_grade']) for p in rows]
        act = [credit(p['actual_grade']) for p in rows]
        tp, fp, fn, tn = _confusion(pred, act)
        return {'matched': n, 'exact_pct': _rate(exact, n), 'within1_pct': _rate(within1, n),
                'grade_mae': round(mae, 2), 'grade_bias': round(bias, 2),
                'correlation': round(rr, 3) if rr is not None else None,
                'credit_accuracy': _rate(tp + tn, n),
                'credit_sensitivity': _rate(tp, tp + fn),
                'credit_specificity': _rate(tn, tn + fp),
                'credit_fp': fp, 'credit_fn': fn}

    summary = block(pairs)
    summary['bias_direction'] = ('optimistic' if summary['grade_bias'] > 0.3
                                 else 'pessimistic' if summary['grade_bias'] < -0.3
                                 else 'well-calibrated')

    by_subj = {}
    for p in pairs:
        by_subj.setdefault(p['subject_norm'], []).append(p)
    subjects = []
    for norm, rows in by_subj.items():
        blk = block(rows)
        blk['subject'] = rows[0]['subject']
        subjects.append(blk)
    subjects.sort(key=lambda x: (x['exact_pct'] if x['exact_pct'] is not None else 0))

    return {'meta': meta, 'summary': summary, 'subjects': subjects,
            'recommendations': _waec_recommendations(summary, subjects)}


def _waec_recommendations(s, subjects):
    recs = []

    def add(tone, title, text):
        recs.append({'tone': tone, 'title': title, 'text': text})

    ex = s.get('exact_pct')
    if ex is not None:
        if ex >= 60:
            add('positive', 'Grades predict well',
                f"{ex}% of grades matched exactly and {s['within1_pct']}% were within one "
                f"grade of the real WAEC. Mock grades are a dependable planning tool.")
        elif ex >= 40:
            add('watch', 'Moderate grade agreement',
                f"{ex}% exact, {s['within1_pct']}% within one grade. Reasonable, but treat "
                f"borderline mock grades cautiously.")
        else:
            add('negative', 'Low grade agreement',
                f"Only {ex}% of mock grades matched actual WAEC. Review marking standards "
                f"and grade boundaries so the mock mirrors WAEC.")
    if s.get('bias_direction') == 'optimistic':
        add('negative', 'Mock grades are lenient',
            "Actual WAEC grades came out worse than the mock on average — the mock is "
            "over-grading. Tighten marking to avoid false reassurance.")
    elif s.get('bias_direction') == 'pessimistic':
        add('watch', 'Mock grades are strict',
            "Actual grades were better than the mock on average — the mock is tougher "
            "than WAEC. Reassure students and recalibrate.")
    if s.get('credit_sensitivity') is not None:
        add('watch', 'Credit (C6+) prediction',
            f"Of subjects actually credited, the mock predicted {s['credit_sensitivity']}%; "
            f"overall credit calls were {s['credit_accuracy']}% accurate. "
            f"{s['credit_fp']} predicted credit(s) did not materialise.")
    weak = [x for x in subjects if x['exact_pct'] is not None and x['exact_pct'] < 40][:6]
    if weak:
        add('watch', 'Subjects where the mock misleads',
            f"{', '.join(x['subject'] for x in weak)} show the weakest grade agreement — "
            f"review how these are set and marked against WAEC standards.")
    return recs
