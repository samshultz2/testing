"""Break a single subject *total* down into the term's assessment components.

Schools often keep only the final total per subject on a broadsheet (e.g. 82),
not the CA1/CA2/CA3/HA/CBT/MID/EXAM split. When importing such a sheet we must
reconstruct a plausible per-component split that:

* uses exactly the components configured for that subject in that term
  (``utils.assessments.subject_columns`` — already honours per-term settings and
  the per-subject Midterm/Practical rule);
* gives every component a whole-number score between 0 and its max;
* sums **exactly** to the student's total.

The split is proportional (each component gets roughly its share of the total),
with the leftover units handed to the components whose fractional share is
largest — the standard "largest remainder" apportionment. This yields a natural
spread (not "fill the exam first, zero the CAs") that a teacher can then tweak in
the preview before saving.
"""


def distribute_total(total, comp_maxes):
    """Split ``total`` across components with the given integer maxima.

    ``comp_maxes`` is an ordered list of positive ints (each component's max).
    Returns a list of ints, same length/order, each ``0 <= x <= max`` and
    ``sum(result) == min(total, sum(comp_maxes))``. A total above the ceiling is
    capped at the ceiling; a negative/None total yields all zeros.
    """
    n = len(comp_maxes)
    if n == 0:
        return []
    try:
        total = int(round(float(total)))
    except (TypeError, ValueError):
        total = 0
    ceiling = sum(comp_maxes)
    total = max(0, min(total, ceiling))
    if total == 0:
        return [0] * n
    if total == ceiling:
        return list(comp_maxes)

    # Proportional share, then hand out the remaining whole units by the largest
    # fractional part (skipping components already at their max).
    shares = [total * m / ceiling for m in comp_maxes]
    base = [min(int(s), comp_maxes[i]) for i, s in enumerate(shares)]
    remaining = total - sum(base)
    order = sorted(range(n), key=lambda i: (shares[i] - int(shares[i])), reverse=True)
    idx = 0
    guard = 0
    while remaining > 0 and guard < 10 * n + 10:
        i = order[idx % n]
        if base[i] < comp_maxes[i]:
            base[i] += 1
            remaining -= 1
        idx += 1
        guard += 1
    # Fallback (only if maxes were saturated oddly): fill left-to-right.
    if remaining > 0:
        for i in range(n):
            room = comp_maxes[i] - base[i]
            take = min(room, remaining)
            base[i] += take
            remaining -= take
            if remaining <= 0:
                break
    return base


def breakdown_for_subject(subject, term_id, total):
    """Convenience wrapper: resolve the subject's components for the term and
    return ``[(assessment_type, max, score)]`` whose scores sum to ``total``."""
    from utils.assessments import subject_columns
    cols = subject_columns(subject, term_id)
    scores = distribute_total(total, [mx for _at, mx in cols])
    return [(at, mx, sc) for (at, mx), sc in zip(cols, scores)]
