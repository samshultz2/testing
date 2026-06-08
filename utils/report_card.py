"""Shared term report-card computation.

Used by the staff report-card view and the public (scratch-card) result checker
so both render identical numbers from a single source of truth.
"""
from models import (
    db, StudentEnrollment, ClassArmAssignment, ClassSubject, Subject, AssessmentType,
    SchoolSettings, StudentScore, GradeScale, TermSummary, Attendance, Week,
)


def _subject_totals(student_id, class_subjects, pass_mark):
    """(total_score, subjects_passed, subjects_failed) for one student."""
    total = passed = failed = 0
    for cs in class_subjects:
        subject_total = sum(
            s.score for s in StudentScore.query.filter_by(
                student_id=student_id, class_subject_id=cs.id).all() if s.score)
        if subject_total > 0:
            total += subject_total
            if subject_total >= pass_mark:
                passed += 1
            else:
                failed += 1
    return total, passed, failed


def _attendance_pct(enrollment_id, week_ids):
    """Term attendance % for an enrolment, or None when there are no records."""
    if not week_ids:
        return None
    recs = Attendance.query.filter(
        Attendance.enrollment_id == enrollment_id,
        Attendance.week_id.in_(week_ids)).all()
    if not recs:
        return None
    marks = sum((1 if a.morning_present else 0) + (1 if a.afternoon_present else 0)
                for a in recs)
    return round(marks / (len(recs) * 2) * 100, 1)


def compute_term_summaries(term_id, class_id):
    """Compute & persist TermSummary (totals, class/arm positions, attendance) for
    every active student in a class (across all its arms) for a term.

    Ranks by average score. Existing teacher/principal comments and promotion
    decisions are preserved. Returns the number of students processed.
    """
    assignments = ClassArmAssignment.query.filter_by(
        term_id=term_id, class_id=class_id).all()
    if not assignments:
        return 0
    arm_of = {a.id: a.arm_id for a in assignments}
    enrollments = StudentEnrollment.query.filter(
        StudentEnrollment.class_arm_assignment_id.in_(list(arm_of)),
        StudentEnrollment.is_active == True).all()
    if not enrollments:
        return 0

    pass_mark = SchoolSettings.get('pass_mark', 50)
    week_ids = [w.id for w in Week.query.filter_by(term_id=term_id).all()]

    cs_cache = {}

    def subjects_for(arm_id):
        if arm_id not in cs_cache:
            cs_cache[arm_id] = (ClassSubject.query.filter_by(
                term_id=term_id, class_id=class_id, is_active=True)
                .filter((ClassSubject.arm_id == None) | (ClassSubject.arm_id == arm_id)).all())
        return cs_cache[arm_id]

    rows = []
    for e in enrollments:
        css = subjects_for(arm_of[e.class_arm_assignment_id])
        total, passed, failed = _subject_totals(e.student_id, css, pass_mark)
        average = round(total / len(css), 2) if css else 0
        rows.append({
            'enrollment': e, 'subjects': len(css), 'total': total, 'average': average,
            'passed': passed, 'failed': failed,
            'attendance': _attendance_pct(e.id, week_ids),
        })

    # Class position (whole class) + arm position (within each arm), by average.
    for i, r in enumerate(sorted(rows, key=lambda x: x['average'], reverse=True)):
        r['pos_class'] = i + 1
    by_arm = {}
    for r in rows:
        by_arm.setdefault(r['enrollment'].class_arm_assignment_id, []).append(r)
    for arm_rows in by_arm.values():
        for i, r in enumerate(sorted(arm_rows, key=lambda x: x['average'], reverse=True)):
            r['pos_arm'] = i + 1

    for r in rows:
        e = r['enrollment']
        ts = TermSummary.query.filter_by(student_id=e.student_id, term_id=term_id).first()
        if not ts:
            ts = TermSummary(student_id=e.student_id, term_id=term_id, enrollment_id=e.id)
            db.session.add(ts)
        ts.enrollment_id = e.id
        ts.total_subjects = r['subjects']
        ts.subjects_passed = r['passed']
        ts.subjects_failed = r['failed']
        ts.total_score = r['total']
        ts.average_score = r['average']
        ts.position_in_class = r['pos_class']
        ts.position_in_arm = r['pos_arm']
        if r['attendance'] is not None:
            ts.attendance_percentage = r['attendance']
    db.session.commit()
    return len(rows)


def build_report_card(student_id, term_id):
    """Return (enrollment, report_data) for a student in a term, or (None, None).

    report_data mirrors the structure used by templates/subjects/report_card.html.
    """
    enrollment = (StudentEnrollment.query.join(ClassArmAssignment).filter(
        StudentEnrollment.student_id == student_id,
        ClassArmAssignment.term_id == term_id,
        StudentEnrollment.is_active == True).first())
    if not enrollment:
        return None, None

    assignment = enrollment.class_arm_assignment
    class_subjects = (ClassSubject.query.filter_by(
        term_id=term_id, class_id=assignment.class_id, is_active=True)
        .filter((ClassSubject.arm_id == None) | (ClassSubject.arm_id == assignment.arm_id))
        .join(Subject).order_by(Subject.name).all())

    assessment_types = (AssessmentType.query.filter_by(is_active=True)
                        .order_by(AssessmentType.order).all())
    pass_mark = SchoolSettings.get('pass_mark', 50)

    subjects_data = []
    total_score = 0
    subjects_passed = 0
    subjects_failed = 0

    for cs in class_subjects:
        row = {'subject': cs.subject, 'teacher': cs.teacher_name,
               'assessments': {}, 'total': 0, 'grade': '-', 'remark': '-'}
        scores = StudentScore.query.filter_by(
            student_id=student_id, class_subject_id=cs.id).all()
        scores_dict = {s.assessment_type_id: s.score for s in scores}
        subject_total = 0
        for at in assessment_types:
            score = scores_dict.get(at.id)
            row['assessments'][at.id] = score
            if score:
                subject_total += score
        row['total'] = subject_total
        if subject_total > 0:
            row['grade'] = GradeScale.get_grade(subject_total)
            row['remark'] = GradeScale.get_remark(subject_total)
            total_score += subject_total
            if subject_total >= pass_mark:
                subjects_passed += 1
            else:
                subjects_failed += 1
        subjects_data.append(row)

    average = round(total_score / len(class_subjects), 2) if class_subjects else 0
    term_summary = TermSummary.query.filter_by(
        student_id=student_id, term_id=term_id).first()

    report_data = {
        'enrollment': enrollment,
        'assignment': assignment,
        'subjects': subjects_data,
        'assessment_types': assessment_types,
        'total_score': total_score,
        'average': average,
        'overall_grade': GradeScale.get_grade(average) if average else '-',
        'subjects_passed': subjects_passed,
        'subjects_failed': subjects_failed,
        'total_subjects': len(class_subjects),
        'term_summary': term_summary,
    }
    return enrollment, report_data
