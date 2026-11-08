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
    """Return the watchlist payload.

    ``total_flagged``, ``counts`` (flagged statuses) and ``by_class`` (flagged
    candidates per class arm, most severe first) as before, plus:

    * ``total`` / ``assessed`` / ``all_counts`` — every SSS3 candidate's status
      (READY, CONDITIONAL, AT_RISK, NOT_READY, NO_DATA);
    * ``projected`` — share projected for 5 credits incl. English & Maths, for
      their JAMB target, and for both;
    * ``rows`` — one flat row per flagged candidate for the filterable list;
    * ``blockers`` — how many flagged candidates each problem affects;
    * ``groups`` — intervention groups (English / Maths clinic, credit booster,
      JAMB drill, missing mocks) with their members;
    * ``classes`` — every class arm's full status mix.
    """
    from utils import exam_insights
    from utils.helpers import get_sss3_students
    from utils.focus_areas import _cohort

    students = get_sss3_students()
    empty = {'total_flagged': 0, 'counts': {}, 'by_class': [], 'total': 0, 'assessed': 0,
             'all_counts': {}, 'projected': {}, 'rows': [], 'blockers': {}, 'groups': [], 'classes': [],
             'no_data': []}
    if not students:
        return empty

    coh = exam_insights.cohort_readiness(students, session_id, calibration)
    labels = {sid: info.get('class') for sid, info in _cohort(session_id, branch_id).items()}

    groups, counts, rows = {}, {}, []
    classes, no_data = {}, []
    blockers = {'credits': 0, 'english': 0, 'maths': 0, 'jamb': 0, 'no_waec': 0, 'no_jamb': 0}
    for row in coh['rows']:
        r = row['readiness']
        status = r.get('status')
        st = row['student']
        label = labels.get(st.id) or 'Unassigned'
        c = classes.setdefault(label, {'class': label, 'total': 0, 'READY': 0, 'CONDITIONAL': 0,
                                       'AT_RISK': 0, 'NOT_READY': 0, 'NO_DATA': 0})
        c['total'] += 1
        c[status] = c.get(status, 0) + 1
        if status == 'NO_DATA':
            no_data.append({'student_id': st.id, 'name': st.full_name, 'class': label})
        if status not in _FLAG_ORDER:
            continue
        counts[status] = counts.get(status, 0) + 1
        waec = r.get('waec') or {}
        jamb = r.get('jamb') or {}
        # Chosen-course verdict (reuses this row's readiness — no recompute).
        elig = None
        if getattr(st, 'target_course_id', None):
            try:
                from utils.aspiration import course_eligibility
                ce = course_eligibility(st, session_id, readiness=r)
                elig = {'status': ce.get('status'), 'course': ce.get('course')}
            except Exception:
                elig = None
        missing_core = list(waec.get('missing_core') or []) if waec else []
        threshold = r.get('jamb_threshold')
        jscore = jamb.get('score') if jamb else None
        gap = (jscore - threshold) if (jscore is not None and threshold) else None
        tags = []
        if waec:
            if (waec.get('credits') or 0) < 5:
                tags.append('credits'); blockers['credits'] += 1
            if any('english' in m.lower() for m in missing_core):
                tags.append('english'); blockers['english'] += 1
            if any('math' in m.lower() for m in missing_core):
                tags.append('maths'); blockers['maths'] += 1
        else:
            tags.append('no_waec'); blockers['no_waec'] += 1
        if jamb:
            if gap is not None and gap < 0:
                tags.append('jamb'); blockers['jamb'] += 1
        else:
            tags.append('no_jamb'); blockers['no_jamb'] += 1
        item = {
            'student_id': st.id,
            'name': st.full_name,
            'code': getattr(st, 'student_id', '') or '',
            'class': label,
            'status': status,
            'blockers': r.get('blockers', []),
            'waec_credits': waec.get('credits') if waec else None,
            'missing_core': missing_core,
            'jamb_score': jscore,
            'jamb_threshold': threshold,
            'jamb_gap': gap,
            'eligibility': elig,
            'tags': tags,
            'source': r.get('source'),
        }
        groups.setdefault(label, []).append(item)
        rows.append(item)

    by_class = []
    for label in sorted(groups):
        items = sorted(groups[label], key=lambda e: _FLAG_ORDER.get(e['status'], 9))
        by_class.append({'class': label, 'count': len(items), 'students': items})
    rows.sort(key=lambda e: (_FLAG_ORDER.get(e['status'], 9),
                             e['jamb_gap'] if e['jamb_gap'] is not None else 0, e['name']))

    def members(tag):
        return [x for x in rows if tag in x['tags']]

    interventions = [
        {'key': 'english', 'title': 'English clinic', 'icon': 'fa-spell-check',
         'why': 'Not projected to credit English — required for every course.', 'members': members('english')},
        {'key': 'maths', 'title': 'Maths clinic', 'icon': 'fa-square-root-variable',
         'why': 'Not projected to credit Mathematics — required for almost every course.', 'members': members('maths')},
        {'key': 'credits', 'title': 'Credit booster', 'icon': 'fa-layer-group',
         'why': 'Fewer than 5 credits projected — target the subjects closest to a credit.', 'members': members('credits')},
        {'key': 'jamb', 'title': 'JAMB drill', 'icon': 'fa-stopwatch',
         'why': 'Projected JAMB below their target — timed CBT practice in their four subjects.', 'members': members('jamb')},
        {'key': 'no_signal', 'title': 'Missing mock results', 'icon': 'fa-circle-question',
         'why': 'No mock WAEC or JAMB result to project from — enter or schedule their mocks.',
         'members': [x for x in rows if 'no_waec' in x['tags'] or 'no_jamb' in x['tags']]},
    ]
    total = coh['total']
    return {
        'total_flagged': sum(g['count'] for g in by_class),
        'counts': counts,
        'by_class': by_class,
        'total': total,
        'assessed': coh['assessed'],
        'all_counts': coh['counts'],
        'projected': {'core': coh['projected_5_incl_core'], 'core_pct': coh['projected_5_incl_core_pct'],
                      'jamb': coh['projected_jamb_ok'], 'jamb_pct': coh['projected_jamb_ok_pct'],
                      'both': coh['projected_both'], 'both_pct': coh['projected_both_pct']},
        'rows': rows,
        'blockers': blockers,
        'groups': [g for g in interventions if g['members']],
        'classes': [classes[k] for k in sorted(classes)],
        'no_data': sorted(no_data, key=lambda x: (x['class'], x['name'])),
    }
