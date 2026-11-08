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


# Projected minus target, in JAMB points.
GAP_BUCKETS = ('30+ below', '15–29 below', '1–14 below', '0–19 above', '20+ above')
GAP_TONES = {'30+ below': 'off', '15–29 below': 'off', '1–14 below': 'close', '0–19 above': 'on', '20+ above': 'on'}


def _gap_bucket(gap):
    if gap <= -30:
        return '30+ below'
    if gap <= -15:
        return '15–29 below'
    if gap < 0:
        return '1–14 below'
    if gap < 20:
        return '0–19 above'
    return '20+ above'


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

    def _acc(store, name, target, proj, on_track, status=None):
        d = store.setdefault(name, {'count': 0, 't_sum': 0, 't_n': 0, 'p_sum': 0, 'p_n': 0, 'on_track': 0,
                                    'close': 0, 'off': 0, 'nodata': 0})
        d['count'] += 1
        if target:
            d['t_sum'] += target; d['t_n'] += 1
        if proj is not None:
            d['p_sum'] += proj; d['p_n'] += 1
        if on_track:
            d['on_track'] += 1
        d['close'] += status == 'CLOSE'
        d['off'] += status == 'OFF_TRACK'
        d['nodata'] += status == 'NO_DATA'

    rows = []                       # one row per candidate with a target (the action list)
    blockers = {'score': 0, 'subjects': 0, 'credits': 0, 'olevel': 0, 'nodata': 0}
    gap_buckets = {k: 0 for k in GAP_BUCKETS}
    backup = {'with': 0, 'off_without': 0}

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
            _acc(uni_stats, uni, target, proj, on_track, status)
        course = s.target_course_name
        if course:
            _acc(course_stats, course, target, proj, on_track, status)

        # Why not on track (a candidate can have several reasons).
        if status == 'NO_DATA':
            blockers['nodata'] += 1
        elif status in ('CLOSE', 'OFF_TRACK'):
            if e.get('missing_jamb'):
                blockers['subjects'] += 1
            if any('5 credits' in r for r in (e.get('reasons') or [])):
                blockers['credits'] += 1                 # not projected for 5 credits incl. Eng & Maths
            elif e.get('missing_waec'):
                blockers['olevel'] += 1                  # a course-specific O'level subject missing
            if e.get('score_ok') is False and proj is not None and target:
                blockers['score'] += 1
        gap = (proj - target) if (proj is not None and target) else None
        if gap is not None:
            gap_buckets[_gap_bucket(gap)] += 1
        has_backup = bool(getattr(s, 'target2_university_id', None) or getattr(s, 'target2_course_id', None))
        backup['with'] += has_backup
        backup['off_without'] += (status == 'OFF_TRACK' and not has_backup)
        rows.append({
            'id': s.id, 'name': getattr(s, 'full_name', ''), 'code': getattr(s, 'student_id', '') or '',
            'university': uni or '', 'course': course or '', 'target': target, 'projected': proj, 'gap': gap,
            'status': status, 'label': ELIGIBILITY_LABELS.get(status, status),
            'reasons': e.get('reasons') or [], 'missing_jamb': e.get('missing_jamb') or [],
            'missing_waec': e.get('missing_waec') or [], 'backup': has_backup,
            'admission': getattr(s, 'admission_status', None) or '',
        })

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
                'on_track': d['on_track'], 'close': d['close'], 'off': d['off'], 'nodata': d['nodata'],
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

    # Class of each candidate (current arm), for the list and the class breakdown.
    try:
        from routes.main import current_class_map
        cls = current_class_map([s.id for s in all_sss3])
    except Exception:
        cls = {}
    by_class = {}
    for r in rows:
        r['class'] = cls.get(r['id'], '')
    target_ids = {r['id'] for r in rows}
    for s in all_sss3:
        c = cls.get(s.id) or 'No class'
        d = by_class.setdefault(c, {'name': c, 'total': 0, 'with_target': 0, 'ON_TRACK': 0, 'CLOSE': 0,
                                    'OFF_TRACK': 0, 'NO_DATA': 0})
        d['total'] += 1
    for r in rows:
        d = by_class[r['class'] or 'No class']
        d['with_target'] += 1
        d[r['status']] = d.get(r['status'], 0) + 1
    no_target = sorted(({'id': s.id, 'name': getattr(s, 'full_name', ''), 'class': cls.get(s.id, '')}
                        for s in all_sss3 if s.id not in target_ids), key=lambda x: (x['class'], x['name']))
    order = {'OFF_TRACK': 0, 'CLOSE': 1, 'NO_DATA': 2, 'ON_TRACK': 3}
    rows.sort(key=lambda r: (order.get(r['status'], 4), r['gap'] if r['gap'] is not None else 0, r['name']))
    targets = [r['target'] for r in rows if r['target']]
    projs = [r['projected'] for r in rows if r['projected'] is not None]
    gaps = sorted(r['gap'] for r in rows if r['gap'] is not None)
    insight = {
        'avg_target': round(sum(targets) / len(targets)) if targets else None,
        'avg_projected': round(sum(projs) / len(projs)) if projs else None,
        'median_gap': gaps[len(gaps) // 2] if gaps else None,
        'with_projection': len(projs),
        'blockers': blockers,
        'gap_buckets': [{'label': k, 'count': gap_buckets[k], 'tone': GAP_TONES[k]} for k in GAP_BUCKETS],
        'backup_with': backup['with'], 'backup_rate': _rate(backup['with'], with_target),
        'off_without_backup': backup['off_without'],
        'by_class': sorted(by_class.values(), key=lambda d: d['name']),
        'no_target': no_target[:80], 'no_target_total': len(no_target),
        'admitted_unrecorded': sum(1 for s in all_sss3 if getattr(s, 'admission_status', None) == 'Admitted'
                                   and not getattr(s, 'admitted_university_id', None)),
    }

    insight['actions'] = _next_steps(rows, insight, len(all_sss3), with_target, mismatches,
                                     status_counts, admitted)

    return {
        'students': rows,
        'insight': insight,
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


def _next_steps(rows, ins, sss3, with_target, mismatches, status_counts, admitted):
    """[{tone, icon, title, detail, link}] — the decisions this page supports,
    most urgent first. ``link`` is an in-page anchor or a list filter."""
    out = []
    n = lambda k: sum(1 for r in rows if r['status'] == k)  # noqa: E731
    if mismatches:
        out.append({'tone': 'bad', 'icon': 'fa-file-circle-exclamation',
                    'title': '%d candidate%s registered for the wrong JAMB subjects' % (
                        len(mismatches), '' if len(mismatches) == 1 else 's'),
                    'detail': 'Their subject combination does not meet their chosen course. Fix the registration '
                              'before the UTME — nothing else can make up for it.',
                    'link': '#as-fix'})
    behind = sum(1 for r in rows if r['gap'] is not None and r['gap'] <= -30)
    if behind:
        out.append({'tone': 'bad', 'icon': 'fa-person-falling',
                    'title': '%d projected 30+ points below their target' % behind,
                    'detail': 'Plan intensive JAMB support, or talk through a realistic course / university now.',
                    'link': 'filter:far'})
    if ins['off_without_backup']:
        out.append({'tone': 'warn', 'icon': 'fa-route',
                    'title': '%d off-track candidate%s with no second choice' % (
                        ins['off_without_backup'], '' if ins['off_without_backup'] == 1 else 's'),
                    'detail': 'Help them pick a backup course or university they are on track for.',
                    'link': 'filter:nobackup'})
    close = n('CLOSE')
    if close:
        out.append({'tone': 'warn', 'icon': 'fa-bullseye',
                    'title': '%d close to their target' % close,
                    'detail': 'Within reach — the best return on extra lessons and mock practice.',
                    'link': 'filter:CLOSE'})
    if sss3 - with_target:
        out.append({'tone': 'info', 'icon': 'fa-flag',
                    'title': '%d SSS3 candidate%s have no target set' % (sss3 - with_target, '' if sss3 - with_target == 1 else 's'),
                    'detail': 'Set a target university and course on their profile so they can be tracked here.',
                    'link': '#as-notarget'})
    nodata = n('NO_DATA')
    if nodata:
        out.append({'tone': 'info', 'icon': 'fa-circle-question',
                    'title': '%d with a target but no exam signal yet' % nodata,
                    'detail': 'Enter Mock JAMB / Mock WAEC results to project their readiness.',
                    'link': 'filter:NO_DATA'})
    if ins['admitted_unrecorded']:
        out.append({'tone': 'info', 'icon': 'fa-building-columns',
                    'title': '%d admitted without the university recorded' % ins['admitted_unrecorded'],
                    'detail': 'Record where they were admitted to measure how many reached their target.',
                    'link': None})
    on = n('ON_TRACK')
    if on:
        out.append({'tone': 'good', 'icon': 'fa-circle-check',
                    'title': '%d on track for their chosen course' % on,
                    'detail': 'Keep them steady — confirm their UTME registration and O\'level combination.',
                    'link': 'filter:ON_TRACK'})
    return out
