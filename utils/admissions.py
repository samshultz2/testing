"""Admissions helpers — pipeline definitions, stats and applicant→student conversion."""
from datetime import date

from sqlalchemy import func

from models import (db, Applicant, Student, ParentContact, StudentEnrollment,
                    ClassArmAssignment)

# Pipeline stages in order. "Admitted" is terminal-success; Rejected/Waitlisted
# are off-pipeline outcomes.
STAGES = ['Inquiry', 'Applied', 'Screening', 'Offered', 'Accepted', 'Admitted']
OUTCOMES = ['Rejected', 'Waitlisted']
ALL_STATUSES = STAGES + OUTCOMES

SOURCES = ['Referral', 'Social media', 'Website', 'Flyer/Banner', 'Radio/TV',
           'Walk-in', 'Returning family', 'Other']

STATUS_BADGE = {
    'Inquiry': 'badge-secondary', 'Applied': 'badge-info', 'Screening': 'badge-info',
    'Offered': 'badge-warning', 'Accepted': 'badge-warning', 'Admitted': 'badge-success',
    'Rejected': 'badge-danger', 'Waitlisted': 'badge-secondary',
}


def pipeline_stats(session_id=None):
    q = Applicant.query
    if session_id:
        q = q.filter_by(session_id=session_id)
    by_status = dict(db.session.query(Applicant.status, func.count(Applicant.id))
                     .filter(*( [Applicant.session_id == session_id] if session_id else []))
                     .group_by(Applicant.status).all())
    total = sum(by_status.values())
    admitted = by_status.get('Admitted', 0)
    rejected = by_status.get('Rejected', 0)
    decided = admitted + rejected
    conversion = round(admitted / total * 100, 1) if total else 0.0
    funnel = [{'stage': s, 'count': by_status.get(s, 0)} for s in STAGES]
    return {
        'total': total, 'admitted': admitted, 'rejected': rejected,
        'pending': total - admitted - rejected,
        'conversion': conversion, 'by_status': by_status, 'funnel': funnel,
    }


def convert_to_student(applicant, assignment_id=None):
    """
    Create a Student (+ primary ParentContact, + optional enrolment) from an
    admitted applicant and link them. Returns (student, error_or_None).
    """
    if applicant.admitted_student_id:
        return applicant.admitted_student, 'Already converted'
    if not applicant.gender:
        return None, 'Applicant needs a gender before conversion'

    student = Student(
        student_id=Student.generate_student_id(),
        first_name=applicant.first_name,
        middle_name=applicant.middle_name,
        surname=applicant.surname,
        gender=applicant.gender,
        date_of_birth=applicant.date_of_birth,
        home_address=applicant.address,
        photo_url=applicant.photo_url,
    )
    db.session.add(student)
    db.session.flush()

    if applicant.parent_phone:
        db.session.add(ParentContact(
            student_id=student.id, phone_number=applicant.parent_phone,
            name=applicant.parent_name, relationship=applicant.relationship or 'Guardian',
            is_primary=True))

    if assignment_id:
        asg = ClassArmAssignment.query.get(assignment_id)
        if asg:
            db.session.add(StudentEnrollment(
                student_id=student.id, class_arm_assignment_id=asg.id, is_active=True))

    applicant.admitted_student_id = student.id
    applicant.status = 'Admitted'
    applicant.decision_date = date.today()
    db.session.commit()
    return student, None
