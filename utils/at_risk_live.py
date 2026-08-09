"""Live at-risk watchlist (roadmap #6).

Unlike the persisted risk register (which needs the nightly risk engine to have
run), this projects every SSS3 candidate's admission readiness *now* — from their
mock-WAEC / mock-JAMB signals — and flags those who are not on track, grouped by
class arm so a form teacher sees their own class. Reuses the existing
``exam_insights`` projection layer; no new modelling.
"""

# Statuses that put a candidate on the watchlist, most severe first.
_FLAG_ORDER = {'NOT_READY': 0, 'AT_RISK': 1, 'CONDITIONAL': 2}


def live_at_risk(session_id=None, branch_id=None, calibration=None):
    """Return ``{total_flagged, counts, by_class}``.

    ``by_class`` is a list of ``{class, count, students}`` (class arms A–Z), each
    student ``{student_id, name, status, blockers, waec_credits, jamb_score}``
    sorted most-severe first. Empty when there are no SSS3 candidates.
    """
    from utils import exam_insights
    from utils.helpers import get_sss3_students
    from utils.focus_areas import _cohort

    students = get_sss3_students()
    if not students:
        return {'total_flagged': 0, 'counts': {}, 'by_class': []}

    coh = exam_insights.cohort_readiness(students, session_id, calibration)
    labels = {sid: info.get('class') for sid, info in _cohort(session_id, branch_id).items()}

    groups, counts = {}, {}
    for row in coh['rows']:
        r = row['readiness']
        status = r.get('status')
        if status not in _FLAG_ORDER:
            continue
        st = row['student']
        counts[status] = counts.get(status, 0) + 1
        waec = r.get('waec') or {}
        jamb = r.get('jamb') or {}
        label = labels.get(st.id) or 'Unassigned'
        groups.setdefault(label, []).append({
            'student_id': st.id,
            'name': st.full_name,
            'status': status,
            'blockers': r.get('blockers', []),
            'waec_credits': waec.get('credits'),
            'jamb_score': jamb.get('score'),
        })

    by_class = []
    for label in sorted(groups):
        items = sorted(groups[label], key=lambda e: _FLAG_ORDER.get(e['status'], 9))
        by_class.append({'class': label, 'count': len(items), 'students': items})
    return {
        'total_flagged': sum(g['count'] for g in by_class),
        'counts': counts,
        'by_class': by_class,
    }
