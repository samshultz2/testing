"""WAEC vs NECO for one exam year: how candidates did in each sitting and how
many reach the O'level admission threshold (5 credits including English
Language and Mathematics) in WAEC, in NECO, in either, and when the two
sittings are combined (best grade per subject across both).

Most Nigerian universities accept results from up to two sittings, so the
combined figure is the one that matters for admission. Branch-scoped like the
rest of the analytics hub."""
from collections import defaultdict

CREDIT = {'A1', 'B2', 'B3', 'C4', 'C5', 'C6'}
POINTS = {'A1': 1, 'B2': 2, 'B3': 3, 'C4': 4, 'C5': 5, 'C6': 6, 'D7': 7, 'E8': 8, 'F9': 9}


def _meets(credited):
    """5+ credits including English and Mathematics (names matched loosely, as
    on the broadsheet: 'English Language', 'General Mathematics' …)."""
    low = {s.lower() for s in credited}
    return (len(credited) >= 5 and any('english' in s for s in low)
            and any('math' in s and 'further' not in s for s in low))


def _by_student(model, year, branch_id):
    from models import Student
    q = model.query.filter_by(exam_year=year)
    if branch_id is not None:
        q = q.join(Student, Student.id == model.student_id).filter(Student.branch_id == branch_id)
    out = defaultdict(dict)
    for r in q.all():
        out[r.student_id][r.subject] = r.grade
    return out


def compare(year, branch_id=None):
    """None when the year has no NECO or no WAEC results; else a summary dict."""
    from models import WAECResult, NECOResult, Student
    if not year:
        return None
    waec = _by_student(WAECResult, year, branch_id)
    neco = _by_student(NECOResult, year, branch_id)
    if not waec or not neco:
        return None
    both = sorted(set(waec) & set(neco))

    def credited(gmap):
        return {s for s, g in gmap.items() if g in CREDIT}

    w_ok = sum(1 for sid in waec if _meets(credited(waec[sid])))
    n_ok = sum(1 for sid in neco if _meets(credited(neco[sid])))
    either = combined = 0
    gained = []        # candidates who only qualify by combining the two sittings
    for sid in both:
        cw, cn = credited(waec[sid]), credited(neco[sid])
        if _meets(cw) or _meets(cn):
            either += 1
        if _meets(cw | cn):
            combined += 1
            if not (_meets(cw) or _meets(cn)):
                gained.append(sid)
    names = {s.id: s.full_name for s in Student.query.filter(Student.id.in_(gained or [-1])).all()}

    # Per-subject credit rate in each exam, for subjects sat in both.
    def subj_rates(data):
        tot, cr, pts = defaultdict(int), defaultdict(int), defaultdict(list)
        for gmap in data.values():
            for s, g in gmap.items():
                tot[s] += 1
                cr[s] += g in CREDIT
                pts[s].append(POINTS.get(g, 9))
        return {s: {'entries': tot[s], 'credit_rate': round(cr[s] / tot[s] * 100, 1),
                    'mean_points': round(sum(pts[s]) / len(pts[s]), 2)} for s in tot}
    wr, nr = subj_rates(waec), subj_rates(neco)
    subjects = []
    for s in sorted(set(wr) & set(nr)):
        diff = round(nr[s]['credit_rate'] - wr[s]['credit_rate'], 1)
        subjects.append({'subject': s, 'waec': wr[s], 'neco': nr[s], 'diff': diff})
    subjects.sort(key=lambda x: (-max(x['waec']['entries'], x['neco']['entries']), x['subject']))

    # Same candidate, same subject: did they do better in WAEC or NECO?
    better_w = better_n = same = 0
    for sid in both:
        for s in set(waec[sid]) & set(neco[sid]):
            a, b = POINTS.get(waec[sid][s], 9), POINTS.get(neco[sid][s], 9)
            if a < b:
                better_w += 1
            elif b < a:
                better_n += 1
            else:
                same += 1
    pairs = better_w + better_n + same

    def pct(n, d):
        return round(n / d * 100, 1) if d else 0
    return {
        'year': year,
        'waec_candidates': len(waec), 'neco_candidates': len(neco), 'both': len(both),
        'waec_ok': w_ok, 'waec_ok_pct': pct(w_ok, len(waec)),
        'neco_ok': n_ok, 'neco_ok_pct': pct(n_ok, len(neco)),
        'either_ok': either, 'either_ok_pct': pct(either, len(both)),
        'combined_ok': combined, 'combined_ok_pct': pct(combined, len(both)),
        'gained_by_combining': [names.get(sid, '') for sid in gained],
        'subjects': subjects,
        'head_to_head': {'pairs': pairs, 'waec_better': better_w, 'neco_better': better_n, 'same': same,
                         'waec_better_pct': pct(better_w, pairs), 'neco_better_pct': pct(better_n, pairs),
                         'same_pct': pct(same, pairs)},
    }
