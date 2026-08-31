"""School-level exam intelligence: turn the WAEC/JAMB analytics into a ranked
list of *actionable* observations.

Where :mod:`utils.exam_insights` judges a single student's admission readiness,
this module reads the already-computed cohort statistics on the analytics hub
(school stats, correlation, projection, cut-off readiness, gender split, class
comparison, mock trajectory, at-risk register) and synthesises an executive
"what is happening / why it matters / what to do next" summary.

Everything here is pure: it takes the dicts the route already built and returns a
ranked ``list`` of insight dicts, so it adds **no** database queries. Each insight
is::

    {'level': 'critical'|'warn'|'good'|'info',
     'icon':  'fa-…',
     'title': 'short headline (what)',
     'detail':'one sentence of why it matters',
     'action':{'label': 'Do X', 'url': '…'} | None}

The caller renders them top-to-bottom; :func:`school_insights` already sorts the
most urgent first and caps the list so the panel stays scannable.
"""
from __future__ import annotations

# Common Nigerian university admission thresholds used for the narrative.
JAMB_FLOOR = 200          # the score most universities treat as the entry floor
WAEC_PASS_TARGET = 75     # a healthy cohort WAEC pass rate (%)
_LEVEL_RANK = {'critical': 0, 'warn': 1, 'good': 2, 'info': 3}


def _pct(n, d):
    return round(n / d * 100, 1) if d else 0.0


def school_insights(*, year=None, waec_stats=None, jamb_stats=None, correlation=None,
                    projection=None, cutoff=None, class_compare=None, internal_corr=None,
                    at_risk=None, mock_trend=None, waec_gender_stats=None,
                    jamb_gender_stats=None, urls=None, limit=8):
    """Build the ranked executive-insight list for the analytics hub.

    All arguments are the dicts/lists the ``analytics_hub`` route already computed
    (any may be ``None``/empty — the relevant insight is simply skipped). ``urls``
    is a small dict of pre-built links (readiness / at-risk / recompute) so the
    actions can deep-link without importing Flask here.
    """
    urls = urls or {}
    out = []

    def add(level, icon, title, detail, action=None):
        out.append({'level': level, 'icon': icon, 'title': title,
                    'detail': detail, 'action': action})

    # --- JAMB university-readiness (the headline number for SSS3) ---------- #
    if cutoff:
        pct = cutoff['eligible_200_pct']
        if pct < 40:
            add('critical', 'fa-triangle-exclamation',
                f'Only {pct}% of JAMB candidates cleared {JAMB_FLOOR}',
                f'Most universities treat {JAMB_FLOOR} as the entry floor — the '
                'majority of this cohort is currently below it.',
                {'label': 'Open readiness funnel', 'url': urls.get('readiness')})
        elif pct < 65:
            add('warn', 'fa-graduation-cap',
                f'{pct}% of JAMB candidates cleared {JAMB_FLOOR}',
                f'{cutoff["competitive_250_pct"]}% reached the competitive 250 mark — '
                'push the 150–199 band to lift university eligibility.',
                {'label': 'Open readiness funnel', 'url': urls.get('readiness')})
        else:
            add('good', 'fa-graduation-cap',
                f'{pct}% of JAMB candidates cleared {JAMB_FLOOR}',
                f'Strong university eligibility — {cutoff["competitive_250_pct"]}% are '
                'already at the competitive 250 level.')

    # --- JAMB projection / direction of travel ---------------------------- #
    if projection:
        d = projection['direction']
        if d == 'down':
            add('warn', 'fa-arrow-trend-down',
                f'JAMB mean is trending down (≈{projection["projected_mean"]} next year)',
                f'The mean has fallen about {abs(projection["slope_per_year"])} points a '
                f'year; last sitting was {projection["latest_mean"]}.')
        elif d == 'up':
            add('good', 'fa-arrow-trend-up',
                f'JAMB mean is trending up (≈{projection["projected_mean"]} next year)',
                f'Up about {projection["slope_per_year"]} points a year — the current '
                'interventions are working; keep them.')

    # --- At-risk register: the single most concrete action list ----------- #
    if at_risk:
        red = sum(1 for s in at_risk if s.get('risk_level') == 'RED')
        add('critical' if red else 'warn', 'fa-user-clock',
            f'{len(at_risk)} SSS3 student(s) flagged at risk'
            + (f' — {red} critical' if red else ''),
            'These students have the weakest projected outcomes; targeted support now '
            'has the highest payoff before the real sittings.',
            {'label': 'Review at-risk register', 'url': urls.get('readiness')})

    # --- WAEC pass rate + the subject dragging it down -------------------- #
    if waec_stats:
        pr = waec_stats['overall_pass_rate']
        worst = None
        if waec_stats.get('most_failed_subjects'):
            worst = max(waec_stats['most_failed_subjects'], key=lambda s: s['fail_rate'])
        if pr < 60:
            detail = f'Cohort WAEC pass rate is {pr}% (target ≥{WAEC_PASS_TARGET}%).'
            if worst:
                detail += f' {worst["subject"]} is the biggest drag at {worst["fail_rate"]}% failing.'
            add('critical', 'fa-book', f'WAEC pass rate is {pr}%', detail)
        elif pr < WAEC_PASS_TARGET:
            detail = f'Pass rate {pr}% is below the {WAEC_PASS_TARGET}% target.'
            if worst:
                detail += f' Focus on {worst["subject"]} ({worst["fail_rate"]}% failing).'
            add('warn', 'fa-book', f'WAEC pass rate is {pr}%', detail)
        else:
            add('good', 'fa-book', f'WAEC pass rate is a healthy {pr}%',
                f'{waec_stats["overall_distinction_rate"]}% of entries were distinctions.')

    # --- WAEC↔JAMB correlation: how much internal exams predict JAMB ------ #
    if correlation and not correlation.get('error'):
        r = correlation.get('correlation_coefficient')
        if r is not None and r < 0.3:
            add('info', 'fa-link-slash',
                f'WAEC and JAMB are weakly linked here (r={r})',
                'Strong WAEC results are not translating into JAMB scores — likely an '
                'exam-technique / UTME-practice gap rather than a knowledge gap.')

    # --- Internal term average vs JAMB ------------------------------------ #
    if internal_corr and internal_corr.get('r') is not None and internal_corr['r'] < 0.3:
        add('info', 'fa-scale-unbalanced',
            f'Term averages barely predict JAMB (r={internal_corr["r"]})',
            f'Across {internal_corr["n"]} students internal marks and JAMB diverge — '
            'internal assessments may be easier than the UTME.')

    # --- Gender gap (WAEC pass rate or JAMB mean) ------------------------- #
    gap = _gender_gap(waec_gender_stats, jamb_gender_stats)
    if gap:
        add('info', 'fa-venus-mars', gap['title'], gap['detail'])

    # --- Weakest class/arm ------------------------------------------------ #
    if class_compare:
        withj = [c for c in class_compare if c.get('jamb_count')]
        if len(withj) >= 2:
            lo = min(withj, key=lambda c: c['jamb_mean'])
            hi = max(withj, key=lambda c: c['jamb_mean'])
            if hi['jamb_mean'] - lo['jamb_mean'] >= 25:
                add('warn', 'fa-users-between-lines',
                    f'{lo["arm"]} trails on JAMB (mean {lo["jamb_mean"]})',
                    f'{hi["arm"]} averages {hi["jamb_mean"]} — a {round(hi["jamb_mean"] - lo["jamb_mean"], 1)}-'
                    f'point gap worth investigating (teaching, timetable or intake).')

    # --- Mock trajectory: is the cohort climbing between sittings? -------- #
    if mock_trend and len(mock_trend) >= 2:
        first, last = mock_trend[0]['average'], mock_trend[-1]['average']
        delta = round(last - first, 1)
        if delta <= -5:
            add('warn', 'fa-flask',
                f'Mock JAMB average is sliding ({first} → {last})',
                'The cohort is losing ground across mock sittings — review coverage and '
                'exam-technique drills before the real UTME.')
        elif delta >= 5:
            add('good', 'fa-flask',
                f'Mock JAMB average is climbing ({first} → {last})',
                f'Up {delta} points across sittings — momentum into the real UTME.')

    if not out:
        add('info', 'fa-circle-info', 'Not enough data yet for insights',
            'Record more WAEC/JAMB results (or run mock exams) for this year and the '
            'analysis will populate automatically.')

    out.sort(key=lambda i: _LEVEL_RANK.get(i['level'], 9))
    return out[:limit]


def _gender_gap(waec_gender_stats, jamb_gender_stats):
    """Surface the larger of the WAEC pass-rate gap or the JAMB mean-score gap
    between genders, if either is material. Returns an insight body or None."""
    def two(rows, key):
        vals = {r['gender']: r[key] for r in (rows or []) if r['gender'] in ('Male', 'Female')}
        if 'Male' in vals and 'Female' in vals:
            return vals['Male'], vals['Female']
        return None

    w = two(waec_gender_stats, 'pass_rate')
    j = two(jamb_gender_stats, 'mean_score')
    cand = []
    if w:
        cand.append(('waec', abs(w[0] - w[1]), w))
    if j:
        cand.append(('jamb', abs(j[0] - j[1]), j))
    if not cand:
        return None
    kind, size, (male, female) = max(cand, key=lambda c: c[1])
    lead = 'Boys' if male > female else 'Girls'
    if kind == 'waec' and size >= 8:
        return {'title': f'{lead} lead on WAEC pass rate by {round(size, 1)} pts',
                'detail': f'WAEC pass rate: boys {male}% vs girls {female}% — worth a '
                          'look at which subjects drive the gap.'}
    if kind == 'jamb' and size >= 15:
        return {'title': f'{lead} lead on JAMB by {round(size, 1)} points',
                'detail': f'Mean JAMB score: boys {male} vs girls {female}.'}
    return None
