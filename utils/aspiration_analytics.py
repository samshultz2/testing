"""Cohort-level analytics for the university-aspiration feature.

Aggregates the per-student aspiration signals into a school view: how many have
targets, the eligibility mix for their chosen course, the most-wanted
universities and courses, students whose registered JAMB combo doesn't match
their target course (an actionable fix list), and the admission funnel with a
conversion rate. Built on ``utils.aspiration`` — no new modelling.
"""

from utils.aspiration import course_eligibility, ELIGIBILITY_LABELS


def _target_students(branch_id=None):
    """SSS3 candidates in scope who have set a target university or course."""
    from utils.helpers import get_sss3_students
    out = []
    for s in get_sss3_students() or []:
        if getattr(s, 'target_university_id', None) or getattr(s, 'target_course_id', None):
            out.append(s)
    return out


def aspiration_overview(session_id=None, branch_id=None):
    """Return the full aspiration hub payload.

    ``{totals, eligibility, top_universities, top_courses, mismatches, funnel}``.
    Empty-safe: every collection is a list/dict even with no data.
    """
    from utils.helpers import get_sss3_students
    all_sss3 = get_sss3_students() or []
    students = [s for s in all_sss3
                if getattr(s, 'target_university_id', None) or getattr(s, 'target_course_id', None)]

    elig_counts = {k: 0 for k in ('ON_TRACK', 'CLOSE', 'OFF_TRACK', 'NO_DATA', 'NO_TARGET')}
    uni_counts, course_counts, status_counts = {}, {}, {}
    mismatches = []
    # Calibration contingency: predicted eligibility bucket → actual outcome, over
    # students whose admission has RESOLVED (Admitted or Declined). Lets a school
    # see whether "On track" really converted and "Off track" really didn't.
    _RESOLVED = ('Admitted', 'Declined')
    calib = {k: {'admitted': 0, 'not_admitted': 0} for k in ('ON_TRACK', 'CLOSE', 'OFF_TRACK', 'NO_DATA')}

    for s in students:
        # Eligibility mix.
        try:
            e = course_eligibility(s, session_id)
        except Exception:
            e = {'status': 'NO_DATA'}
        status = e.get('status') or 'NO_DATA'
        elig_counts[status] = elig_counts.get(status, 0) + 1

        # Calibration: only students with a resolved admission outcome contribute.
        adm = getattr(s, 'admission_status', None)
        if adm in _RESOLVED and status in calib:
            calib[status]['admitted' if adm == 'Admitted' else 'not_admitted'] += 1

        # Popularity.
        uni = s.target_university_name
        if uni:
            uni_counts[uni] = uni_counts.get(uni, 0) + 1
        course = s.target_course_name
        if course:
            course_counts[course] = course_counts.get(course, 0) + 1

        # Subject-mismatch fix list: registered JAMB combo missing a required subject.
        missing = e.get('missing_jamb') or []
        if missing:
            mismatches.append({
                'student_id': s.id, 'name': s.full_name,
                'course': course or '', 'university': uni or '',
                'missing_jamb': missing,
            })

    # Admission funnel over ALL SSS3 (so "no status" is meaningful).
    for s in all_sss3:
        st = getattr(s, 'admission_status', None) or 'None'
        status_counts[st] = status_counts.get(st, 0) + 1

    admitted = status_counts.get('Admitted', 0)
    offered = status_counts.get('Offered', 0)
    applied = status_counts.get('Applied', 0)
    with_target = len(students)
    conversion = round(100.0 * admitted / with_target, 1) if with_target else 0.0

    def _top(counts, n=10):
        return [{'name': k, 'count': v}
                for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]

    # Build the calibration rows + a headline "hit rate" (predicted-admit that
    # actually got admitted + predicted-no that actually didn't, over all resolved).
    _ELIG_LABELS = ELIGIBILITY_LABELS
    calib_rows, correct, resolved_total = [], 0, 0
    for k in ('ON_TRACK', 'CLOSE', 'OFF_TRACK', 'NO_DATA'):
        adm = calib[k]['admitted']
        not_adm = calib[k]['not_admitted']
        n = adm + not_adm
        resolved_total += n
        # "Predicted admit" = ON_TRACK/CLOSE; treat those admits + OFF_TRACK/NO_DATA
        # rejections as correct calls.
        if k in ('ON_TRACK', 'CLOSE'):
            correct += adm
        else:
            correct += not_adm
        calib_rows.append({
            'status': k, 'label': _ELIG_LABELS.get(k, k),
            'admitted': adm, 'not_admitted': not_adm, 'total': n,
            'admit_rate': round(100.0 * adm / n, 1) if n else None,
        })
    hit_rate = round(100.0 * correct / resolved_total, 1) if resolved_total else None

    return {
        'totals': {
            'sss3': len(all_sss3),
            'with_target': with_target,
            'without_target': max(0, len(all_sss3) - with_target),
            'coverage': round(100.0 * with_target / len(all_sss3), 1) if all_sss3 else 0.0,
        },
        'eligibility': [{'status': k, 'label': ELIGIBILITY_LABELS.get(k, k), 'count': elig_counts[k]}
                        for k in ('ON_TRACK', 'CLOSE', 'OFF_TRACK', 'NO_DATA')],
        'top_universities': _top(uni_counts),
        'top_courses': _top(course_counts),
        'mismatches': sorted(mismatches, key=lambda m: (-len(m['missing_jamb']), m['name'])),
        'funnel': {
            'applied': applied, 'offered': offered, 'admitted': admitted,
            'declined': status_counts.get('Declined', 0),
            'deferred': status_counts.get('Deferred', 0),
            'none': status_counts.get('None', 0),
            'with_target': with_target, 'conversion': conversion,
        },
        'calibration': {
            'rows': calib_rows, 'resolved_total': resolved_total, 'hit_rate': hit_rate,
        },
    }
