"""External-exam performance rolled up to the class-arm level.

The analytics hub already compares arms on JAMB mean + WAEC pass rate, but only
maps candidates through the *active* term (so past cohorts don't map) and
carries just two metrics. This builds a fuller, cohort-aware league:

* Each candidate is mapped to the class arm of their **most recent senior-section
  enrolment** (any term), so graduated cohorts still resolve.
* Per arm: JAMB candidates / mean / ≥cut-off rate, and WAEC entries, credit rate,
  5-credits-incl-core rate and distinction rate — ranked best → worst with a
  best/worst gap read.

One batched enrolment fetch + two result fetches; no N+1.
"""
from __future__ import annotations

PASS_GRADES = {'A1', 'B2', 'B3', 'C4', 'C5', 'C6'}
DISTINCTION_GRADES = {'A1', 'B2', 'B3'}


def _is_core(subject):
    s = (subject or '').upper()
    return 'ENGLISH' in s or 'MATH' in s


def _rate(num, den):
    return round(100 * num / den, 1) if den else None


def _arm_map(student_ids):
    """{student_id: (arm_label, class_id)} using each student's most recent
    senior-section enrolment. Falls back to any latest enrolment when a school
    doesn't tag sections."""
    from sqlalchemy import func
    from models import (StudentEnrollment, ClassArmAssignment, SchoolClass)
    if not student_ids:
        return {}
    senior_ids = [c.id for c in SchoolClass.query.filter(
        func.lower(SchoolClass.section) == 'senior').all()]
    senior_set = set(senior_ids)
    rows = (StudentEnrollment.query
            .join(ClassArmAssignment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
            .filter(StudentEnrollment.student_id.in_(list(student_ids)))
            .order_by(ClassArmAssignment.term_id.desc()).all())
    # Rows are latest-term-first. Keep, per student, the latest senior-section arm
    # if any, else the latest arm of any kind.
    senior_pick, any_pick = {}, {}
    for e in rows:
        a = e.class_arm_assignment
        if not a:
            continue
        any_pick.setdefault(e.student_id, (a.display_name, a.class_id))
        if (not senior_set) or (a.class_id in senior_set):
            senior_pick.setdefault(e.student_id, (a.display_name, a.class_id))
    return {sid: senior_pick.get(sid, any_pick.get(sid))
            for sid in any_pick}


def exam_class_league(year, branch_id=None, cutoff=200):
    """Per-class-arm external-exam league for an exam year."""
    from models import db, Student, WAECResult, JAMBResult

    def scoped_students(model):
        q = db.session.query(model.student_id).filter(model.exam_year == year)
        if branch_id is not None:
            q = q.join(Student, Student.id == model.student_id).filter(Student.branch_id == branch_id)
        return {sid for (sid,) in q.distinct().all()}

    waec_sids = scoped_students(WAECResult)
    jamb_sids = scoped_students(JAMBResult)
    all_sids = waec_sids | jamb_sids
    meta = {'year': year, 'matched': 0, 'candidates': len(all_sids)}
    if not all_sids:
        meta['insufficient'] = True
        return {'meta': meta, 'units': [], 'summary': {}, 'recommendations': []}

    amap = _arm_map(all_sids)
    meta['matched'] = len({s for s in all_sids if s in amap})
    if not amap:
        meta['insufficient'] = True
        meta['reason'] = ('No senior-class enrolments found for these candidates, so '
                          'results cannot be grouped by arm.')
        return {'meta': meta, 'units': [], 'summary': {}, 'recommendations': []}

    # WAEC per student (credits, distinctions, 5-incl-core).
    waec_q = WAECResult.query.filter_by(exam_year=year)
    if branch_id is not None:
        waec_q = waec_q.join(Student, Student.id == WAECResult.student_id).filter(Student.branch_id == branch_id)
    waec_by_student = {}
    for r in waec_q.all():
        d = waec_by_student.setdefault(r.student_id, {'credits': 0, 'dist': 0, 'entries': 0, 'core': set()})
        d['entries'] += 1
        if r.grade in PASS_GRADES:
            d['credits'] += 1
            if _is_core(r.subject):
                d['core'].add('ENG' if 'ENGLISH' in (r.subject or '').upper() else 'MATH')
        if r.grade in DISTINCTION_GRADES:
            d['dist'] += 1

    jamb_q = JAMBResult.query.filter_by(exam_year=year)
    if branch_id is not None:
        jamb_q = jamb_q.join(Student, Student.id == JAMBResult.student_id).filter(Student.branch_id == branch_id)
    jamb_by_student = {r.student_id: r.total_score for r in jamb_q.all()}

    # Aggregate per arm.
    units = {}
    for sid in all_sids:
        if sid not in amap:
            continue
        label, class_id = amap[sid]
        u = units.setdefault(label, {
            'label': label, 'students': set(), 'jamb': [], 'waec_students': 0,
            'waec_entries': 0, 'credits': 0, 'dist': 0, 'five_core': 0})
        u['students'].add(sid)
        if sid in jamb_by_student:
            u['jamb'].append(jamb_by_student[sid])
        w = waec_by_student.get(sid)
        if w:
            u['waec_students'] += 1
            u['waec_entries'] += w['entries']
            u['credits'] += w['credits']
            u['dist'] += w['dist']
            if w['credits'] >= 5 and len(w['core']) >= 2:
                u['five_core'] += 1

    league = []
    for u in units.values():
        js = u['jamb']
        league.append({
            'label': u['label'], 'students': len(u['students']),
            'jamb_candidates': len(js),
            'jamb_mean': round(sum(js) / len(js), 1) if js else None,
            'jamb_above_rate': _rate(sum(1 for s in js if s >= cutoff), len(js)),
            'waec_students': u['waec_students'],
            'credit_rate': _rate(u['credits'], u['waec_entries']),
            'distinction_rate': _rate(u['dist'], u['waec_entries']),
            'five_core_rate': _rate(u['five_core'], u['waec_students']),
        })
    # Rank: prefer JAMB mean, else 5-credit rate.
    def _key(r):
        return (r['jamb_mean'] if r['jamb_mean'] is not None else -1,
                r['five_core_rate'] if r['five_core_rate'] is not None else -1)
    league.sort(key=_key, reverse=True)

    all_j = [s for u in units.values() for s in u['jamb']]
    summary = {
        'arms': len(league), 'candidates': len(all_sids),
        'jamb_mean': round(sum(all_j) / len(all_j), 1) if all_j else None,
        'cutoff': cutoff,
    }
    return {'meta': meta, 'units': league, 'summary': summary,
            'recommendations': _recommendations(league, cutoff)}


def _recommendations(league, cutoff):
    recs = []

    def add(tone, title, text):
        recs.append({'tone': tone, 'title': title, 'text': text})

    ranked_j = [u for u in league if u['jamb_mean'] is not None]
    if len(ranked_j) >= 2:
        best, worst = ranked_j[0], ranked_j[-1]
        gap = round(best['jamb_mean'] - worst['jamb_mean'], 1)
        add('insight', 'Widest arm gap (JAMB)',
            f"{best['label']} averaged {best['jamb_mean']} while {worst['label']} averaged "
            f"{worst['jamb_mean']} — a {gap}-point gap. Move what works in {best['label']} "
            f"(teaching, streaming, revision) into {worst['label']}.")
    weak = [u for u in league if u['five_core_rate'] is not None and u['five_core_rate'] < 50]
    if weak:
        add('negative', 'Arms below 50% admission-grade rate',
            f"{', '.join(u['label'] for u in weak[:5])} have under half their candidates on "
            f"5 credits incl. English & Maths — the admission threshold. Prioritise core-subject "
            f"intervention there.")
    strong = [u for u in league if u['jamb_above_rate'] is not None and u['jamb_above_rate'] >= 80]
    if strong:
        add('positive', 'Strong arms',
            f"{', '.join(u['label'] for u in strong[:5])} put ≥80% of candidates above the "
            f"{cutoff} cut-off — study and replicate their approach.")
    return recs
