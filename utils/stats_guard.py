"""Sample-size safeguards for analytics: minimum group sizes, confidence
ranges and plain-language confidence labels, so small groups and short
histories are never presented as firm findings."""
from __future__ import annotations

import math

MIN_CORRELATION_N = 15        # students needed before a correlation is shown
MIN_GROUP_N = 10              # below this a rate is "small group — read with caution"
MIN_TREND_YEARS = 4           # years before a trend projection is "reliable"
MAX_YEARLY_CHANGE = 25.0      # cap on a projected JAMB-mean change per year


def wilson(k, n, z=1.96):
    """95% Wilson score interval for k successes out of n, as percentages
    (lo, hi). (0, 0) for n == 0."""
    if not n:
        return (0.0, 0.0)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (round(max(0.0, centre - half) * 100, 1), round(min(1.0, centre + half) * 100, 1))


def rate(k, n):
    """{'pct', 'lo', 'hi', 'n', 'small'} — a rate with its confidence range."""
    lo, hi = wilson(k, n)
    return {'pct': round(k / n * 100, 1) if n else 0.0, 'lo': lo, 'hi': hi, 'n': n,
            'small': n < MIN_GROUP_N}


def correlation_ci(r, n, z=1.96):
    """95% interval for a Pearson r (Fisher z). None when n < 4."""
    if r is None or n < 4 or abs(r) >= 1:
        return None
    zr = math.atanh(r)
    se = 1 / math.sqrt(n - 3)
    return (round(math.tanh(zr - z * se), 2), round(math.tanh(zr + z * se), 2))


def confidence(n, *, kind='group'):
    """'high' | 'medium' | 'low' for a sample of n (students, or years for
    kind='years')."""
    if kind == 'years':
        return 'high' if n >= 6 else 'medium' if n >= MIN_TREND_YEARS else 'low'
    if kind == 'correlation':
        return 'high' if n >= 60 else 'medium' if n >= 30 else 'low'
    return 'high' if n >= 30 else 'medium' if n >= MIN_GROUP_N else 'low'


def two_proportion_test(k1, n1, k2, n2):
    """Two-sided p-value that two rates differ (normal approximation).
    None when either group is empty."""
    if not n1 or not n2:
        return None
    p = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = abs(k1 / n1 - k2 / n2) / se
    return round(math.erfc(z / math.sqrt(2)), 4)


def gap_verdict(k1, n1, k2, n2):
    """Plain-language verdict on a gap between two groups' rates."""
    p = two_proportion_test(k1, n1, k2, n2)
    if p is None:
        return {'p': None, 'real': False, 'label': 'Not enough data'}
    if min(n1, n2) < MIN_GROUP_N:
        return {'p': p, 'real': False, 'label': 'Small group — can\'t tell yet'}
    if p < 0.05:
        return {'p': p, 'real': True, 'label': 'Real difference'}
    return {'p': p, 'real': False, 'label': 'Could be chance'}


def projection(points, *, lo=0, hi=400, cap=MAX_YEARLY_CHANGE):
    """Linear trend over [(year, value)] → next-year projection with a range
    and a confidence label. None with fewer than 2 years."""
    pts = sorted(points)
    n = len(pts)
    if n < 2:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    slope = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / den if den else 0.0
    slope = max(-cap, min(cap, slope))
    nxt = max(xs) + 1
    est = my + slope * (nxt - mx)
    resid = [ys[i] - (my + slope * (xs[i] - mx)) for i in range(n)]
    sd = math.sqrt(sum(r * r for r in resid) / (n - 2)) if n > 2 else abs(ys[-1] - ys[0]) / 2 or 10.0
    band = 1.96 * sd * math.sqrt(1 + 1 / n + ((nxt - mx) ** 2 / den if den else 0))
    clamp = lambda v: max(lo, min(hi, v))  # noqa: E731
    return {'next_year': nxt, 'projected': round(clamp(est), 1),
            'low': round(clamp(est - band), 1), 'high': round(clamp(est + band), 1),
            'slope': round(slope, 1), 'years': n, 'confidence': confidence(n, kind='years')}
