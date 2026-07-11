"""Unified subject-performance scorecard for the external-exams hub.

The hub already shows WAEC subject stats and JAMB subject stats *separately*
(strongest/most-failed WAEC tables, a JAMB subject chart/table). This merges both
lenses into one ranked, actionable scorecard — WAEC pass rate and JAMB mean for
the *same* subject on one row — and attributes each subject to its current SSS3
teacher(s), so a weak subject points straight at who owns it.

Pure: it takes the already-computed ``subject_analysis`` lists (from the cached
WAEC/JAMB school-stat wrappers) plus a ``{subject: [teacher, ...]}`` map, and
returns scorecard rows. No queries.
"""
from __future__ import annotations

# Thresholds for the concern flag. WAEC pass rate is a % of credit-or-better
# entries; JAMB subject mean is out of 100.
_WAEC_WEAK, _WAEC_WATCH, _WAEC_STRONG = 55, 70, 85
_JAMB_WEAK, _JAMB_WATCH, _JAMB_STRONG = 40, 50, 60
_FLAG_RANK = {'weak': 0, 'watch': 1, 'strong': 3}          # None → 2 (see sort)


def _band(value, weak_below, watch_below, strong_at):
    """Classify one metric: 'weak' / 'watch' / 'strong' / None (mid-range)."""
    if value is None:
        return None
    if value < weak_below:
        return 'weak'
    if value < watch_below:
        return 'watch'
    if value >= strong_at:
        return 'strong'
    return None


def _flag(waec_pass, jamb_mean):
    """Classify a subject from whichever signals exist. The worst band wins for
    the concern flags; 'strong' only when nothing raises concern. Returns
    ``(flag, reason)``."""
    bands = {}
    wb = _band(waec_pass, _WAEC_WEAK, _WAEC_WATCH, _WAEC_STRONG)
    jb = _band(jamb_mean, _JAMB_WEAK, _JAMB_WATCH, _JAMB_STRONG)
    if wb:
        bands.setdefault(wb, []).append(f'WAEC pass {waec_pass}%')
    if jb:
        bands.setdefault(jb, []).append(f'JAMB mean {jamb_mean}')
    for flag in ('weak', 'watch', 'strong'):
        if flag in bands:
            return flag, '; '.join(bands[flag])
    return None, ''


def subject_scorecard(waec_stats=None, jamb_stats=None, teacher_map=None):
    """Merge WAEC + JAMB per-subject analysis into ranked scorecard rows.

    Each row: ``{subject, waec_entries, waec_pass_rate, waec_a1_rate, jamb_count,
    jamb_mean, jamb_above_50_pct, teachers, flag, reason}``. Rows are ordered
    weak → watch → unflagged → strong, then by the weaker of the two rates, so
    intervention candidates surface at the top.
    """
    teacher_map = teacher_map or {}
    waec = {s['subject']: s for s in ((waec_stats or {}).get('subject_analysis') or [])}
    jamb = {s['subject']: s for s in ((jamb_stats or {}).get('subject_analysis') or [])}

    rows = []
    for subject in sorted(set(waec) | set(jamb)):
        w, j = waec.get(subject), jamb.get(subject)
        waec_pass = w['pass_rate'] if w else None
        jamb_mean = j['mean_score'] if j else None
        jamb_above_50_pct = (round(j['above_50'] / j['count'] * 100, 1)
                             if j and j['count'] else None)
        flag, reason = _flag(waec_pass, jamb_mean)
        rows.append({
            'subject': subject,
            'waec_entries': w['total_entries'] if w else 0,
            'waec_pass_rate': waec_pass,
            'waec_a1_rate': w['a1_rate'] if w else None,
            'jamb_count': j['count'] if j else 0,
            'jamb_mean': jamb_mean,
            'jamb_above_50_pct': jamb_above_50_pct,
            'teachers': teacher_map.get(subject, []),
            'flag': flag,
            'reason': reason,
        })

    def _sort_key(r):
        rank = _FLAG_RANK.get(r['flag'], 2)
        # within a flag band, weakest performance first
        worst = min([v for v in (r['waec_pass_rate'], r['jamb_mean']) if v is not None]
                    or [999])
        return (rank, worst, r['subject'])

    rows.sort(key=_sort_key)
    return rows


def scorecard_summary(rows):
    """Headline counts for the scorecard panel header."""
    return {
        'total': len(rows),
        'weak': sum(1 for r in rows if r['flag'] == 'weak'),
        'watch': sum(1 for r in rows if r['flag'] == 'watch'),
        'strong': sum(1 for r in rows if r['flag'] == 'strong'),
        'with_teacher': sum(1 for r in rows if r['teachers']),
    }
