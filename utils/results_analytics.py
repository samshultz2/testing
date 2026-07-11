"""Internal-results academic analytics for a class in a term.

Everything is computed from the scores already entered (no new data), with a
single bulk score fetch (no N+1) and cached in ``AnalyticsCache`` because the
same class dashboard is opened repeatedly. Cache is busted whenever scores for
the class change (see routes.subjects.scores / bulk_entry).
"""
from __future__ import annotations


def _cache_key(term_id, assignment_id):
    return f'results_analytics:{term_id}:{assignment_id}'


def bust(term_id, assignment_id):
    """Drop the cached analytics for a class+term (called after a score change)."""
    from models import db, AnalyticsCache
    try:
        row = AnalyticsCache.query.filter_by(cache_key=_cache_key(term_id, assignment_id)).first()
        if row:
            db.session.delete(row)
            db.session.commit()
    except Exception:
        db.session.rollback()


def class_analytics(term_id, assignment_id, *, use_cache=True, ttl=600):
    """Analytics payload for one class (assignment) in a term. Cached for ``ttl``
    seconds; pass use_cache=False to force a fresh computation."""
    from models import AnalyticsCache
    key = _cache_key(term_id, assignment_id)
    if use_cache:
        hit = AnalyticsCache.get(key)
        if hit is not None:
            hit['cached'] = True
            return hit
    data = _compute(term_id, assignment_id)
    try:
        AnalyticsCache.set(key, data, ttl_seconds=ttl)
    except Exception:
        pass
    data['cached'] = False
    return data


def _grade_bands():
    from models import GradeScale
    bands = GradeScale.query.order_by(GradeScale.order, GradeScale.min_score.desc()).all()
    return [(b.grade, b.min_score, b.max_score, b.remark) for b in bands]


def _grade_for(total, bands):
    for grade, lo, hi, _remark in bands:
        if lo <= total <= hi:
            return grade
    return 'F'


def _compute(term_id, assignment_id):
    from sqlalchemy.orm import joinedload
    from models import (db, ClassArmAssignment, ClassSubject, Subject, Student,
                        StudentEnrollment, StudentScore, AssessmentType,
                        SchoolSettings, TermSummary, Term)

    asg = db.session.get(ClassArmAssignment, assignment_id) if assignment_id else None
    if not asg or not term_id:
        return _empty()

    pass_mark = SchoolSettings.get('pass_mark', 50)
    class_subjects = (ClassSubject.query.filter_by(
        term_id=term_id, class_id=asg.class_id, is_active=True)
        .filter((ClassSubject.arm_id == None) | (ClassSubject.arm_id == asg.arm_id))
        .join(Subject).order_by(Subject.name).all())
    enrollments = (StudentEnrollment.query
                   .options(joinedload(StudentEnrollment.student))
                   .filter_by(class_arm_assignment_id=assignment_id, is_active=True)
                   .join(Student).order_by(Student.surname, Student.first_name).all())
    if not class_subjects or not enrollments:
        return _empty()

    cs_ids = [cs.id for cs in class_subjects]
    sids = [e.student_id for e in enrollments]
    # One query for every score in the class.
    present = {}          # (sid, csid) -> total, only where at least one score exists
    for s in StudentScore.query.filter(StudentScore.student_id.in_(sids),
                                       StudentScore.class_subject_id.in_(cs_ids)).all():
        if s.score is None:
            continue
        key = (s.student_id, s.class_subject_id)
        present[key] = present.get(key, 0) + (s.score or 0)

    bands = _grade_bands()
    grade_dist = {g: 0 for g, _lo, _hi, _r in bands} or {'F': 0}
    n_subjects = len(class_subjects)

    # Per-subject accumulators.
    subj = {cs.id: {'name': cs.subject.name, 'totals': []} for cs in class_subjects}
    students = []
    cells_possible = len(enrollments) * n_subjects
    cells_entered = 0

    for e in enrollments:
        assessed_totals = []
        failed = 0
        for cs in class_subjects:
            if (e.student_id, cs.id) in present:
                total = round(present[(e.student_id, cs.id)], 2)
                cells_entered += 1
                assessed_totals.append(total)
                subj[cs.id]['totals'].append(total)
                grade_dist[_grade_for(total, bands)] = grade_dist.get(_grade_for(total, bands), 0) + 1
                if total < pass_mark:
                    failed += 1
        # A student's class average uses the full subject count (matches the
        # broadsheet), so unentered subjects count as 0 until entered.
        avg = round(sum(assessed_totals) / n_subjects, 2) if n_subjects else 0
        students.append({
            'id': e.student_id, 'name': e.student.full_name,
            'average': avg, 'assessed': len(assessed_totals),
            'failed': failed,
        })

    assessed_students = [s for s in students if s['assessed'] > 0]
    averages = [s['average'] for s in assessed_students]
    class_avg = round(sum(averages) / len(averages), 2) if averages else 0
    passed = sum(1 for a in averages if a >= pass_mark)
    ranked = sorted(assessed_students, key=lambda s: -s['average'])

    # Subject difficulty: mean subject total, ascending (hardest first).
    subjects = []
    for cs in class_subjects:
        totals = subj[cs.id]['totals']
        if totals:
            avg = round(sum(totals) / len(totals), 2)
            pr = round(100 * sum(1 for t in totals if t >= pass_mark) / len(totals), 1)
        else:
            avg, pr = 0, 0
        subjects.append({'id': cs.id, 'name': subj[cs.id]['name'], 'average': avg,
                         'pass_rate': pr, 'assessed': len(totals)})
    subjects_by_difficulty = sorted(subjects, key=lambda r: (r['assessed'] == 0, r['average']))

    # Students needing intervention: assessed but below the pass mark on average,
    # or failing 2+ subjects. Lowest average first.
    intervention = sorted(
        [s for s in assessed_students if s['average'] < pass_mark or s['failed'] >= 2],
        key=lambda s: s['average'])[:25]

    # Historical: same class-arm's previous term average (one lookup).
    prev_avg = _previous_term_average(term_id, asg)

    return {
        'summary': {
            'students': len(enrollments), 'assessed': len(assessed_students),
            'class_average': class_avg,
            'highest': round(max(averages), 2) if averages else 0,
            'lowest': round(min(averages), 2) if averages else 0,
            'pass_rate': round(100 * passed / len(averages), 1) if averages else 0,
            'fail_rate': round(100 * (len(averages) - passed) / len(averages), 1) if averages else 0,
            'top_student': ranked[0]['name'] if ranked else '',
            'completion': round(100 * cells_entered / cells_possible, 1) if cells_possible else 0,
            'pass_mark': pass_mark,
            'prev_average': prev_avg,
            'trend': (round(class_avg - prev_avg, 2) if prev_avg is not None else None),
        },
        'grade_distribution': [{'grade': g, 'count': grade_dist.get(g, 0)} for g, _lo, _hi, _r in bands]
                              or [{'grade': 'F', 'count': grade_dist.get('F', 0)}],
        'subjects': subjects_by_difficulty,
        'top_students': [{'name': s['name'], 'average': s['average']} for s in ranked[:10]],
        'intervention': intervention,
    }


def _previous_term_average(term_id, asg):
    """Class average for the same class-arm in the immediately-preceding term of
    the same session, from TermSummary (fast). None when there's no prior term."""
    from models import db, Term, ClassArmAssignment, StudentEnrollment, TermSummary
    term = db.session.get(Term, term_id)
    if not term or not term.term_number or term.term_number <= 1:
        return None
    prev = Term.query.filter_by(session_id=term.session_id,
                                term_number=term.term_number - 1).first()
    if not prev:
        return None
    prev_asg = ClassArmAssignment.query.filter_by(
        class_id=asg.class_id, arm_id=asg.arm_id, term_id=prev.id).first()
    if not prev_asg:
        return None
    enr_ids = [e.student_id for e in StudentEnrollment.query.filter_by(
        class_arm_assignment_id=prev_asg.id).all()]
    if not enr_ids:
        return None
    rows = [ts.average_score for ts in TermSummary.query.filter(
        TermSummary.term_id == prev.id, TermSummary.student_id.in_(enr_ids)).all()
        if ts.average_score]
    return round(sum(rows) / len(rows), 2) if rows else None


def _empty():
    return {'summary': {}, 'grade_distribution': [], 'subjects': [],
            'top_students': [], 'intervention': []}
