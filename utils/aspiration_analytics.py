"""Cohort-level analytics for the university-aspiration feature.

Aggregates the per-student aspiration signals into a school view: target
coverage, the eligibility mix for their chosen course, the most-wanted
universities/courses (with average target/projected and on-track counts), the
target-vs-projected score spread, the subject-mismatch fix list, the admission
funnel with target/course achievement rates, prediction calibration, and a
scholarship summary.

Everything here is DERIVED from existing data — ``utils.aspiration`` (which is
built on the existing ``exam_insights`` projection engine) plus the stored
target/admitted/scholarship fields. No new modelling, no new projection.
"""

from utils.aspiration import course_eligibility, ELIGIBILITY_LABELS

# Configurable thresholds / bands (documented heuristics).
BEHIND_MARGIN = 30          # projected this far below target = "significantly behind"
SCORE_BANDS = [('<180', 0, 179), ('180–199', 180, 199), ('200–219', 200, 219),
               ('220–249', 220, 249), ('250–279', 250, 279), ('280+', 280, 10_000)]


def _band(score):
    for label, lo, hi in SCORE_BANDS:
        if lo <= score <= hi:
            return label
    return None


def aspiration_overview(session_id=None, branch_id=None):
    """Return the full aspiration hub payload (all collections empty-safe).

    ``{totals, eligibility, top_universities, top_courses, score_distribution,
       mismatches, funnel, calibration, scholarships}``.
    """
    from utils.helpers import get_sss3_students
    from utils import exam_insights as ei

    all_sss3 = get_sss3_students() or []
    students = [s for s in all_sss3
                if getattr(s, 'target_university_id', None) or getattr(s, 'target_course_id', None)]

    elig_counts = {k: 0 for k in ('ON_TRACK', 'CLOSE', 'OFF_TRACK', 'NO_DATA', 'NO_TARGET')}
    uni_stats, course_stats = {}, {}
    mismatches = []
    # Target-vs-projected score spread.
    target_bands = {lbl: 0 for lbl, _, _ in SCORE_BANDS}
    proj_bands = {lbl: 0 for lbl, _, _ in SCORE_BANDS}
    significantly_behind = 0
    # Calibration contingency: predicted eligibility bucket → actual outcome, over
    # students whose admission RESOLVED (Admitted or Declined).
    _RESOLVED = ('Admitted', 'Declined')
    calib = {k: {'admitted': 0, 'not_admitted': 0} for k in ('ON_TRACK', 'CLOSE', 'OFF_TRACK', 'NO_DATA')}

    def _acc(store, name, target, proj, on_track):
        d = store.setdefault(name, {'count': 0, 't_sum': 0, 't_n': 0, 'p_sum': 0, 'p_n': 0, 'on_track': 0})
        d['count'] += 1
        if target:
            d['t_sum'] += target; d['t_n'] += 1
        if proj is not None:
            d['p_sum'] += proj; d['p_n'] += 1
        if on_track:
            d['on_track'] += 1

    for s in students:
        # One readiness pass per student, reused by the eligibility verdict (no
        # double projection).
        try:
            r = ei.admission_readiness(s, session_id)
            e = course_eligibility(s, session_id, readiness=r)
        except Exception:
            e = {'status': 'NO_DATA'}
        status = e.get('status') or 'NO_DATA'
        elig_counts[status] = elig_counts.get(status, 0) + 1
        on_track = status == 'ON_TRACK'
        target = e.get('target') or getattr(s, 'jamb_target', None)
        proj = e.get('projected')

        adm = getattr(s, 'admission_status', None)
        if adm in _RESOLVED and status in calib:
            calib[status]['admitted' if adm == 'Admitted' else 'not_admitted'] += 1

        uni = s.target_university_name
        if uni:
            _acc(uni_stats, uni, target, proj, on_track)
        course = s.target_course_name
        if course:
            _acc(course_stats, course, target, proj, on_track)

        # Score spread.
        if target:
            b = _band(target)
            if b:
                target_bands[b] += 1
        if proj is not None:
            b = _band(proj)
            if b:
                proj_bands[b] += 1
            if target and (target - proj) >= BEHIND_MARGIN:
                significantly_behind += 1

        missing = e.get('missing_jamb') or []
        if missing:
            mismatches.append({'student_id': s.id, 'name': s.full_name,
                               'course': course or '', 'university': uni or '', 'missing_jamb': missing})

    # ---- Admission funnel + target/course achievement over ALL SSS3 ----
    status_counts = {}
    uni_hit = uni_alt = course_hit = course_alt = 0
    for s in all_sss3:
        st = getattr(s, 'admission_status', None) or 'None'
        status_counts[st] = status_counts.get(st, 0) + 1
        if st == 'Admitted':
            tu, au = getattr(s, 'target_university_id', None), getattr(s, 'admitted_university_id', None)
            if tu and au:
                uni_hit += (tu == au)
                uni_alt += (tu != au)
            tc, ac = getattr(s, 'target_course_id', None), getattr(s, 'admitted_course_id', None)
            if tc and ac:
                course_hit += (tc == ac)
                course_alt += (tc != ac)

    admitted = status_counts.get('Admitted', 0)
    declined = status_counts.get('Declined', 0)
    with_target = len(students)
    resolved_outcomes = admitted + declined

    def _rate(num, den):
        return round(100.0 * num / den, 1) if den else None

    # ---- Enriched top lists ----
    def _top(store, n=10):
        rows = []
        for name, d in store.items():
            rows.append({
                'name': name, 'count': d['count'],
                'avg_target': round(d['t_sum'] / d['t_n']) if d['t_n'] else None,
                'avg_projected': round(d['p_sum'] / d['p_n']) if d['p_n'] else None,
                'on_track': d['on_track'],
            })
        rows.sort(key=lambda x: (-x['count'], x['name']))
        return rows[:n]

    # ---- Calibration rows + hit rate ----
    calib_rows, correct, resolved_total = [], 0, 0
    for k in ('ON_TRACK', 'CLOSE', 'OFF_TRACK', 'NO_DATA'):
        a, na = calib[k]['admitted'], calib[k]['not_admitted']
        tot = a + na
        resolved_total += tot
        correct += a if k in ('ON_TRACK', 'CLOSE') else na
        calib_rows.append({'status': k, 'label': ELIGIBILITY_LABELS.get(k, k),
                           'admitted': a, 'not_admitted': na, 'total': tot,
                           'admit_rate': _rate(a, tot)})

    return {
        'totals': {
            'sss3': len(all_sss3), 'with_target': with_target,
            'without_target': max(0, len(all_sss3) - with_target),
            'coverage': _rate(with_target, len(all_sss3)) or 0.0,
        },
        'eligibility': [{'status': k, 'label': ELIGIBILITY_LABELS.get(k, k), 'count': elig_counts[k]}
                        for k in ('ON_TRACK', 'CLOSE', 'OFF_TRACK', 'NO_DATA')],
        'top_universities': _top(uni_stats),
        'top_courses': _top(course_stats),
        'score_distribution': {
            'bands': [lbl for lbl, _, _ in SCORE_BANDS],
            'target': [target_bands[lbl] for lbl, _, _ in SCORE_BANDS],
            'projected': [proj_bands[lbl] for lbl, _, _ in SCORE_BANDS],
            'significantly_behind': significantly_behind, 'behind_margin': BEHIND_MARGIN,
            'has_projection': sum(proj_bands.values()) > 0,
        },
        'mismatches': sorted(mismatches, key=lambda m: (-len(m['missing_jamb']), m['name'])),
        'funnel': {
            'applied': status_counts.get('Applied', 0), 'offered': status_counts.get('Offered', 0),
            'admitted': admitted, 'declined': declined,
            'deferred': status_counts.get('Deferred', 0), 'none': status_counts.get('None', 0),
            'with_target': with_target, 'conversion': _rate(admitted, with_target) or 0.0,
            # Achievement: of admitted students (with both ids recorded), how many
            # landed their target vs an alternative.
            'target_university_rate': _rate(uni_hit, uni_hit + uni_alt),
            'alternative_university_rate': _rate(uni_alt, uni_hit + uni_alt),
            'target_course_rate': _rate(course_hit, course_hit + course_alt),
            'alternative_course_rate': _rate(course_alt, course_hit + course_alt),
            'no_admission_rate': _rate(declined, resolved_outcomes),
            'resolved_outcomes': resolved_outcomes,
        },
        'calibration': {'rows': calib_rows, 'resolved_total': resolved_total,
                        'hit_rate': _rate(correct, resolved_total)},
        'scholarships': _scholarship_summary(all_sss3),
    }


def _scholarship_summary(students):
    """Scholarship picture for the cohort in scope (batched — one query for all
    records). Correlational only: recipients tend to be strong candidates, so this
    describes distribution, it does not attribute performance to scholarships."""
    from models import StudentScholarship
    ids = [s.id for s in students]
    if not ids:
        return {'recipients': 0, 'records': 0, 'by_status': [], 'by_course': [],
                'by_university': [], 'awarded_amount': 0.0, 'awarded_count': 0}
    rows = StudentScholarship.query.filter(StudentScholarship.student_id.in_(ids)).all()
    if not rows:
        return {'recipients': 0, 'records': 0, 'by_status': [], 'by_course': [],
                'by_university': [], 'awarded_amount': 0.0, 'awarded_count': 0}

    # Label a student's institution/course by where they were admitted, else target.
    by_id = {s.id: s for s in students}
    def _uni(s):
        return (s.admitted_university.name if getattr(s, 'admitted_university', None)
                else s.target_university_name) or 'Unspecified'
    def _course(s):
        return (s.admitted_course.name if getattr(s, 'admitted_course', None)
                else s.target_course_name) or 'Unspecified'

    status_c, course_c, uni_c = {}, {}, {}
    recipients, awarded_amount, awarded_count = set(), 0.0, 0
    for r in rows:
        recipients.add(r.student_id)
        st = (r.status or 'Unspecified')
        status_c[st] = status_c.get(st, 0) + 1
        if st == 'Awarded' and r.amount:
            awarded_amount += float(r.amount); awarded_count += 1
        s = by_id.get(r.student_id)
        if s:
            course_c[_course(s)] = course_c.get(_course(s), 0) + 1
            uni_c[_uni(s)] = uni_c.get(_uni(s), 0) + 1

    def _rank(counts, n=8):
        return [{'name': k, 'count': v}
                for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]

    return {
        'recipients': len(recipients), 'records': len(rows),
        'by_status': _rank(status_c), 'by_course': _rank(course_c), 'by_university': _rank(uni_c),
        'awarded_amount': round(awarded_amount, 2), 'awarded_count': awarded_count,
    }
