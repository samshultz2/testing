"""University-aspiration decision support.

Turns a stored target (university + course) into an actionable verdict for the
chosen course: does the student's registered JAMB combo match, are the required
O'level subjects projected to credit, and does the projected JAMB clear the
course's competitive target? Plus a recommender that surfaces courses the student
is actually competitive for. Built on the existing exam_insights projections — no
new modelling.
"""

# Status the chosen-course verdict can take.
ELIGIBILITY_STATUSES = ('ON_TRACK', 'CLOSE', 'OFF_TRACK', 'NO_DATA', 'NO_TARGET')

_CLOSE_MARGIN = 30   # within this many JAMB points of target counts as "close"


def course_eligibility(student, session_id=None, readiness=None):
    """Verdict on the student's PRIMARY chosen course. Returns a dict with
    ``status`` plus the target/projection, the score gap, subject-combo and
    credit checks, and plain-English reasons. ``readiness`` may be passed to
    avoid recomputing the projection."""
    course = getattr(student, 'target_course', None)
    if course is None:
        return {'status': 'NO_TARGET'}
    from utils import exam_insights as ei
    r = readiness if readiness is not None else ei.admission_readiness(student, session_id)
    target = r.get('jamb_threshold') or getattr(student, 'jamb_target', None)
    jamb = r.get('jamb')
    waec = r.get('waec')
    base = {'status': None, 'target': target, 'course': course.name,
            'university': getattr(student, 'target_university_name', None),
            'department': getattr(student, 'target_department', None) or (course.department or None)}
    if not jamb and not waec:
        return {**base, 'status': 'NO_DATA'}

    proj = jamb['score'] if jamb else None
    gap = (target - proj) if (target and proj is not None) else None
    have_jamb = set(student.jamb_subject_list)
    # Each requirement slot may list interchangeable subjects (e.g. Commerce or
    # Financial Accounting); a slot is satisfied when ANY of its options is held.
    missing_jamb = [' or '.join(g) for g in course.jamb_requirement_groups
                    if not any(s in have_jamb for s in g)]
    credited = set(waec['credited_subjects']) if waec else set()
    meets_ssc = bool(waec and waec.get('meets_ssc'))
    missing_waec = [' or '.join(g) for g in course.waec_requirement_groups
                    if not any(s in credited for s in g)]

    subject_ok = not missing_jamb
    credits_ok = meets_ssc and not missing_waec
    score_ok = bool(proj is not None and target and proj >= target)

    reasons = []
    if missing_jamb:
        reasons.append('Not registered for required JAMB subject(s): ' + ', '.join(missing_jamb))
    if not meets_ssc:
        reasons.append('Not projected for 5 credits including English & Maths')
    elif missing_waec:
        reasons.append("Required O'level subject(s) not projected to credit: " + ', '.join(missing_waec))
    if target and proj is not None and proj < target:
        reasons.append(f'Projected JAMB {proj} below target {target}')

    if subject_ok and credits_ok and score_ok:
        status = 'ON_TRACK'
    elif subject_ok and meets_ssc and (score_ok or (gap is not None and gap <= _CLOSE_MARGIN)):
        status = 'CLOSE'
    else:
        status = 'OFF_TRACK'

    return {**base, 'status': status, 'projected': proj, 'gap': gap,
            'subject_ok': subject_ok, 'credits_ok': credits_ok, 'score_ok': score_ok,
            'missing_jamb': missing_jamb, 'missing_waec': missing_waec, 'reasons': reasons}


ELIGIBILITY_LABELS = {
    'ON_TRACK': 'On track', 'CLOSE': 'Close', 'OFF_TRACK': 'Off track',
    'NO_DATA': 'No exam signal yet', 'NO_TARGET': 'No target set',
}


def recommend_courses(student, session_id=None, university=None, limit=8):
    """Courses the student is projected to be competitive for at a given (or their
    target) university — projected JAMB at/above the course cut-off — ranked by
    subject fit then margin. Empty when there's no JAMB signal to project from."""
    from utils import exam_insights as ei
    from models import Course, effective_cutoff
    r = ei.admission_readiness(student, session_id)
    jamb = r.get('jamb')
    proj = jamb['score'] if jamb else None
    if proj is None:
        return []
    uni = university if university is not None else getattr(student, 'target_university', None)
    have_jamb = set(student.jamb_subject_list)
    out = []
    for c in Course.query.filter_by(is_active=True).all():
        cutoff = effective_cutoff(uni, c) or (c.base_cutoff or 180)
        if proj < cutoff:
            continue
        subj_fit = bool(have_jamb) and all(
            any(s in have_jamb for s in g) for g in c.jamb_requirement_groups)
        out.append({'course_id': c.id, 'course': c.name, 'department': c.department or '',
                    'cutoff': cutoff, 'margin': proj - cutoff, 'subject_fit': subj_fit})
    out.sort(key=lambda x: (x['subject_fit'], x['margin']), reverse=True)
    return out[:limit]
