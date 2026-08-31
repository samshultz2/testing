"""Comparative external-exams analytics: reduce WAEC/JAMB school statistics to a
common headline-metric shape so branches (branch-vs-branch) and cohorts
(year-vs-year) can be laid side by side.

Pure functions only — they take the already-computed school-stat dicts (from the
cached wrappers in ``routes.results``) and return comparison rows, so they add no
queries and are trivially testable.
"""
from __future__ import annotations


def _pct(n, d):
    return round(n / d * 100, 1) if d else 0.0


def headline_metrics(jamb_stats=None, waec_stats=None):
    """The common set of comparable headline numbers for one (branch, year) or
    (year) slice. Missing stats degrade to ``None``/0 rather than raising."""
    j = jamb_stats or None
    w = waec_stats or None
    return {
        'jamb_candidates': j['total_students'] if j else 0,
        'jamb_mean': j['mean_score'] if j else None,
        'above_200': j['above_200'] if j else 0,
        'above_200_pct': _pct(j['above_200'], j['total_students']) if j else None,
        'waec_students': w['unique_students'] if w else 0,
        'waec_pass_rate': w['overall_pass_rate'] if w else None,
        'waec_distinction_rate': w['overall_distinction_rate'] if w else None,
        'has_data': bool(j or w),
    }


# The metrics worth ranking/deltaing, with display metadata. ``higher_better`` is
# used to colour deltas; ``suffix`` for rendering.
COMPARE_METRICS = [
    ('jamb_mean', 'JAMB mean', '', True),
    ('above_200_pct', 'University-ready (≥200)', '%', True),
    ('waec_pass_rate', 'WAEC pass rate', '%', True),
    ('waec_distinction_rate', 'WAEC distinction rate', '%', True),
]


def rank_branches(rows, by='jamb_mean'):
    """Sort branch rows (each ``{'label':…, 'metrics':{…}}``) best-first on a
    metric, pushing branches with no value for it to the end."""
    def key(r):
        v = r['metrics'].get(by)
        return (v is None, -(v if v is not None else 0))
    return sorted(rows, key=key)


def compare_years(metrics_a, metrics_b):
    """Side-by-side A/B of two headline-metric dicts with per-metric deltas.

    Returns a list of ``{key, label, suffix, a, b, delta, improved}`` (delta is
    ``a - b`` — i.e. how the *primary* year compares to the comparison year).
    ``improved`` is None when either side is missing."""
    out = []
    for key, label, suffix, higher_better in COMPARE_METRICS:
        a, b = metrics_a.get(key), metrics_b.get(key)
        if a is None or b is None:
            delta = improved = None
        else:
            delta = round(a - b, 1)
            improved = None if delta == 0 else ((delta > 0) == higher_better)
        out.append({'key': key, 'label': label, 'suffix': suffix,
                    'a': a, 'b': b, 'delta': delta, 'improved': improved})
    return out
