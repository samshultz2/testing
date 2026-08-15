"""Admissions helpers — pipeline definitions, stats and applicant→student conversion."""
from datetime import date
from utils import timeutil

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


def pipeline_stats(session_id=None, branch_id=None):
    filters = []
    if session_id:
        filters.append(Applicant.session_id == session_id)
    if branch_id is not None:
        filters.append(Applicant.branch_id == branch_id)
    by_status = dict(db.session.query(Applicant.status, func.count(Applicant.id))
                     .filter(*filters)
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
        asg = db.session.get(ClassArmAssignment, assignment_id)
        if asg:
            db.session.add(StudentEnrollment(
                student_id=student.id, class_arm_assignment_id=asg.id, is_active=True))

    applicant.admitted_student_id = student.id
    applicant.status = 'Admitted'
    applicant.decision_date = timeutil.today()
    db.session.commit()
    return student, None


# Decisions worth telling people about: admins get a bell, and the parent gets an
# email when an address is on file (admissions is the one place we hold a parent
# email — the student records are phone-first).
DECISION_NOTIFY_STATUSES = {'Offered', 'Admitted', 'Rejected', 'Waitlisted'}


def _decision_message(applicant):
    """(subject, heading, paragraphs) for the parent email about a decision."""
    name = applicant.full_name
    greeting = f'Dear {applicant.parent_name or "Parent/Guardian"},'
    cls = applicant.intended_class.name if applicant.intended_class else 'the school'
    status = applicant.status
    if status == 'Offered':
        return (f'Admission offer for {name}', 'Admission offer',
                [greeting, f'We are pleased to offer {name} a place in {cls}.',
                 'Please contact the school to accept the offer and complete enrolment.'])
    if status == 'Admitted':
        return (f'{name} has been admitted', 'Admission confirmed',
                [greeting, f'Congratulations! {name} has been admitted to {cls}.',
                 'We look forward to welcoming your ward. The school will share next steps.'])
    if status == 'Waitlisted':
        return (f'Update on {name}’s application', 'Application waitlisted',
                [greeting, f'{name} has been placed on our waiting list for {cls}.',
                 'We will contact you should a place become available.'])
    # Rejected
    return (f'Update on {name}’s application', 'Application update',
            [greeting,
             f'Thank you for your interest in our school. Unfortunately we are '
             f'unable to offer {name} admission at this time.',
             'We wish you the very best.'])


def notify_decision(applicant):
    """Bell admins and (if a parent email is on file) email the parent about an
    admission decision. Best-effort — never raises into the caller."""
    if applicant.status not in DECISION_NOTIFY_STATUSES:
        return
    name = applicant.full_name
    try:
        from utils.notify import notify_admins
        notify_admins(f'Applicant {applicant.status.lower()}: {name}',
                      f'Application {applicant.application_no or ""} is now '
                      f'{applicant.status}.', category='admissions')
    except Exception:
        pass
    email = (applicant.parent_email or '').strip()
    if not email:
        return
    try:
        from utils import mailer
        if not mailer.is_configured():
            return
        subject, heading, paragraphs = _decision_message(applicant)
        html = mailer.branded_html(heading, paragraphs)
        mailer.send_email_async(email, subject, '\n\n'.join(paragraphs), html=html)
    except Exception:
        pass
