"""Shared term report-card computation.

Used by the staff report-card view and the public (scratch-card) result checker
so both render identical numbers from a single source of truth.
"""
from models import (
    StudentEnrollment, ClassArmAssignment, ClassSubject, Subject, AssessmentType,
    SchoolSettings, StudentScore, GradeScale, TermSummary,
)


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
