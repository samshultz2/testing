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


def _blank(v):
    return v is None or (isinstance(v, str) and not v.strip())


def copy_to_student(applicant, student):
    """Carry everything the application holds over to the student record:
    names, gender, date of birth, address, blood group / genotype, the
    passport photo, and the parent and emergency contacts. Only EMPTY student
    fields are filled — nothing already on the student record is overwritten
    — so it is safe to run again on a student admitted earlier. Returns the
    list of things copied (for a message)."""
    from models import ParentContact
    done = []
    for src, dst, label in (('first_name', 'first_name', 'first name'), ('middle_name', 'middle_name', 'middle name'),
                            ('surname', 'surname', 'surname'), ('gender', 'gender', 'gender'),
                            ('date_of_birth', 'date_of_birth', 'date of birth'), ('address', 'home_address', 'address'),
                            ('blood_group', 'blood_group', 'blood group'), ('genotype', 'genotype', 'genotype')):
        val = getattr(applicant, src, None)
        if not _blank(val) and _blank(getattr(student, dst, None)):
            setattr(student, dst, val)
            done.append(label)

    # Passport photo: the applicant's stored image becomes the student's own.
    try:
        from models import StudentPhoto
        from utils.applicant_photo import load as _load
        if not StudentPhoto.query.filter_by(student_id=student.id).first():
            raw, _mime = _load(applicant.id)
            if raw:
                from utils.student_photo import save_bytes
                save_bytes(student, raw)
                done.append('passport photo')
    except Exception:   # a bad image must never block admission
        pass

    existing = {(c.phone_number or '').replace(' ', '') for c in student.parent_contacts.all()}
    has_primary = any(c.is_primary for c in student.parent_contacts.all())

    def add_contact(phone, name, rel, email=None, primary=False):
        ph = (phone or '').strip()
        if not ph or ph.replace(' ', '') in existing:
            return False
        db.session.add(ParentContact(student_id=student.id, phone_number=ph[:15], name=name,
                                     relationship=(rel or 'Guardian')[:20], email=email or None,
                                     is_primary=primary))
        existing.add(ph.replace(' ', ''))
        return True

    if add_contact(applicant.parent_phone, applicant.parent_name, applicant.relationship,
                   applicant.parent_email, primary=not has_primary):
        done.append('parent contact')
    elif applicant.parent_email and applicant.parent_phone:
        # Contact already there (e.g. added by hand) — fill in a missing email.
        for c in student.parent_contacts.all():
            if (c.phone_number or '').replace(' ', '') == applicant.parent_phone.strip().replace(' ', '') and not c.email:
                c.email = applicant.parent_email
                done.append('parent email')
    if add_contact(applicant.emergency_phone, applicant.emergency_name,
                   applicant.emergency_relationship or 'Emergency'):
        done.append('emergency contact')
    return done


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
        student_id=Student.generate_student_id(applicant.branch_id),
        branch_id=applicant.branch_id,
        first_name=applicant.first_name,
        middle_name=applicant.middle_name,
        surname=applicant.surname,
        gender=applicant.gender,
    )
    db.session.add(student)
    db.session.flush()
    copy_to_student(applicant, student)

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


# ---------------------------------------------------------------------------
# Linking an application to a student created by hand
# ---------------------------------------------------------------------------
def _norm(v):
    return ' '.join((v or '').lower().replace('-', ' ').split())


def _digits(p):
    d = ''.join(ch for ch in (p or '') if ch.isdigit())
    return d[-10:]          # 0803… and +234803… compare equal


def _current_class(student):
    from models import ClassArmAssignment
    e = (student.enrollments.join(ClassArmAssignment)
         .order_by(ClassArmAssignment.term_id.desc(), StudentEnrollment.is_active.desc(),
                   StudentEnrollment.id.desc()).first())
    return e.class_arm_assignment.display_name if e and e.class_arm_assignment else None


def match_students(applicant, limit=5, students=None):
    """Students who look like this applicant (for linking a profile created by
    hand). Scored on name, date of birth, gender and the parent's phone;
    students already linked to another application are left out. Returns
    [{student, score, reasons}] best first, only reasonable matches."""
    from utils.branch_scope import scope_query
    taken = {sid for (sid,) in db.session.query(Applicant.admitted_student_id)
             .filter(Applicant.admitted_student_id.isnot(None), Applicant.id != applicant.id).all()}
    fn, sn, mn = _norm(applicant.first_name), _norm(applicant.surname), _norm(applicant.middle_name)
    pp = _digits(applicant.parent_phone)
    if students is None:
        q = scope_query(Student.query, Student).filter(
            db.or_(func.lower(Student.surname) == sn, func.lower(Student.first_name) == fn,
                   func.lower(Student.surname) == fn, func.lower(Student.first_name) == sn))
        students = q.limit(200).all()
        if pp:
            by_phone = (Student.query.join(ParentContact, ParentContact.student_id == Student.id)
                        .filter(ParentContact.phone_number.like('%' + pp[-7:])).limit(50).all())
            students = list({s.id: s for s in list(students) + by_phone}.values())
    out = []
    for s in students:
        if s.id in taken:
            continue
        score, why = 0, []
        sf, ss, sm = _norm(s.first_name), _norm(s.surname), _norm(s.middle_name)
        if sf == fn and ss == sn:
            score += 4; why.append('same name')
        elif sf == sn and ss == fn:
            score += 3; why.append('same name (swapped)')
        elif ss == sn or sf == fn:
            score += 1; why.append('same surname' if ss == sn else 'same first name')
        if mn and sm and mn == sm:
            score += 1; why.append('same middle name')
        if applicant.date_of_birth and s.date_of_birth:
            if applicant.date_of_birth == s.date_of_birth:
                score += 3; why.append('same date of birth')
            else:
                score -= 2
        if applicant.gender and s.gender and applicant.gender != s.gender:
            score -= 3
        if pp and any(_digits(c.phone_number) == pp for c in s.parent_contacts.all()):
            score += 3; why.append('same parent phone')
        if score >= 3:
            out.append({'student': s, 'score': score, 'reasons': why})
    out.sort(key=lambda x: (-x['score'], x['student'].surname or ''))
    return out[:limit]


def link_to_student(applicant, student):
    """Attach an application to an existing (hand-made) student record, mark
    it admitted and copy over whatever the student record is missing.
    Returns (copied_list, error)."""
    if applicant.admitted_student_id and applicant.admitted_student_id != student.id:
        return None, 'This application is already linked to another student.'
    other = Applicant.query.filter(Applicant.admitted_student_id == student.id, Applicant.id != applicant.id).first()
    if other:
        return None, f'{student.full_name} is already linked to application {other.application_no}.'
    applicant.admitted_student_id = student.id
    applicant.status = 'Admitted'
    applicant.decision_date = applicant.decision_date or timeutil.today()
    done = copy_to_student(applicant, student)
    db.session.commit()
    return done, None
