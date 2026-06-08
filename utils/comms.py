"""
Parent-communication helpers — phone normalisation, placeholder rendering and
audience resolution (turning "JSS1 Rose" or "fee defaulters" into a concrete
list of parents to message).
"""
import re

from models import (
    db, Student, ParentContact, StudentEnrollment, ClassArmAssignment, SchoolSettings,
)

PLACEHOLDERS = ['{student}', '{first_name}', '{surname}', '{class}', '{arm}',
                '{term}', '{balance}', '{parent}', '{school}']

SMS_SEGMENT = 160


def normalise_phone(phone, country='234'):
    """Digits-only international form for wa.me links (e.g. 080… -> 23480…)."""
    if not phone:
        return ''
    digits = re.sub(r'\D', '', phone)
    if digits.startswith('00'):
        digits = digits[2:]
    if digits.startswith('0'):
        digits = country + digits[1:]
    elif digits.startswith(country):
        pass
    elif len(digits) == 10:               # missing leading 0
        digits = country + digits
    return digits


def school_name():
    try:
        return SchoolSettings.get('school_name', 'the school')
    except Exception:
        return 'the school'


def student_placement_label(student_id, term_id):
    """'JSS1 Rose' for a student's enrolment in a term (class + arm), or ''."""
    enr = (StudentEnrollment.query
           .join(ClassArmAssignment,
                 StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
           .filter(StudentEnrollment.student_id == student_id,
                   StudentEnrollment.is_active == True,
                   ClassArmAssignment.term_id == term_id).first()) if term_id else None
    if not enr:
        return '', ''
    asg = enr.class_arm_assignment
    return (asg.school_class.name if asg.school_class else '',
            asg.arm.name if asg.arm else '')


def build_context(student, term, parent_name='Parent', balance=None):
    """Placeholder values for one student/parent."""
    cls, arm = student_placement_label(student.id, term.id if term else None)
    bal = ''
    if balance is not None:
        bal = '₦{:,.2f}'.format(balance)
    return {
        '{student}': student.full_name,
        '{first_name}': student.first_name or student.full_name,
        '{surname}': student.surname or '',
        '{class}': cls,
        '{arm}': arm,
        '{term}': term.full_name if term else '',
        '{balance}': bal,
        '{parent}': parent_name or 'Parent',
        '{school}': school_name(),
    }


def render(text, context):
    """Replace {placeholders} in a message body."""
    out = text or ''
    for key, val in context.items():
        out = out.replace(key, str(val))
    return out


def sms_segments(text):
    """Number of 160-char SMS segments a body needs."""
    n = len(text or '')
    if n == 0:
        return 0
    return (n + SMS_SEGMENT - 1) // SMS_SEGMENT


def primary_contact(student):
    """Best parent contact for a student: primary first, else first with a phone."""
    contacts = student.parent_contacts.all() if hasattr(student.parent_contacts, 'all') else list(student.parent_contacts)
    contacts = [c for c in contacts if c.phone_number]
    if not contacts:
        return None
    contacts.sort(key=lambda c: (not c.is_primary,))
    return contacts[0]


def dispatch_campaign(msg, cfg=None):
    """Send every pending recipient of a campaign via the SMS gateway.

    Commits after each recipient so an interruption never resends an already
    delivered message and the DB write-lock is held only briefly. Returns
    (sent, failed). Requires a configured gateway."""
    from datetime import datetime
    from models import MessageRecipient
    from utils import sms_gateway
    cfg = cfg or sms_gateway.get_config()
    sent = failed = 0
    for r in msg.recipients.filter(MessageRecipient.status != 'Sent').all():
        ok, info = sms_gateway.send_sms(r.phone, r.body, cfg)
        if ok:
            r.status, r.sent_at, r.error = 'Sent', datetime.now(), None
            sent += 1
        else:
            r.status, r.error = 'Failed', info
            failed += 1
        db.session.commit()           # persist each result immediately
    msg.sent_count = msg.recipients.filter_by(status='Sent').count()
    db.session.commit()
    return sent, failed


def _claim_message(message_id, from_status='Scheduled'):
    """Atomically flip a campaign's status to 'Sending'. Returns True if THIS
    caller won the claim — guards against the worker and a manual send racing."""
    from models import Message
    updated = (Message.query
               .filter(Message.id == message_id, Message.status == from_status)
               .update({Message.status: 'Sending'}, synchronize_session=False))
    db.session.commit()
    return updated == 1


def dispatch_due_scheduled():
    """Process scheduled campaigns whose time has come (used by the worker)."""
    from datetime import datetime
    from models import Message
    from utils import sms_gateway
    cfg = sms_gateway.get_config()
    if not sms_gateway.is_configured(cfg):
        return 0
    due = Message.query.filter(Message.status == 'Scheduled',
                               Message.scheduled_at != None,
                               Message.scheduled_at <= datetime.now()).all()
    processed = 0
    for msg in due:
        if not _claim_message(msg.id):   # someone else already grabbed it
            continue
        db.session.refresh(msg)
        dispatch_campaign(msg, cfg)
        msg.status = 'Sent'
        db.session.commit()
        processed += 1
    return processed


def coverage_stats():
    """How many active students have at least one parent phone number."""
    total = Student.query.filter_by(is_active=True).count()
    with_contact = (db.session.query(ParentContact.student_id)
                    .join(Student, Student.id == ParentContact.student_id)
                    .filter(Student.is_active == True,
                            ParentContact.phone_number != None,
                            ParentContact.phone_number != '')
                    .distinct().count())
    pct = round(with_contact / total * 100, 1) if total else 0.0
    return {'total': total, 'with_contact': with_contact,
            'without_contact': total - with_contact, 'pct': pct}


def resolve_audience(audience, term, class_id=None, arm_id=None, student_ids=None):
    """
    Return a list of dicts {student, parent_name, phone, balance} for the chosen
    audience. ``balance`` is only populated for the 'defaulters' audience.
    """
    students = []
    balances = {}
    # Branch users only message their own branch's parents.
    from utils.branch_scope import scope_query

    if audience == 'all':
        students = scope_query(Student.query.filter_by(is_active=True),
                               Student).order_by(Student.surname).all()

    elif audience in ('class', 'arm'):
        q = scope_query(
            StudentEnrollment.query
            .join(ClassArmAssignment,
                  StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
            .filter(StudentEnrollment.is_active == True),
            ClassArmAssignment)
        if term:
            q = q.filter(ClassArmAssignment.term_id == term.id)
        if class_id:
            q = q.filter(ClassArmAssignment.class_id == class_id)
        if arm_id:
            q = q.filter(ClassArmAssignment.arm_id == arm_id)
        students = [e.student for e in q.all() if e.student and e.student.is_active]

    elif audience == 'students':
        if student_ids:
            students = scope_query(
                Student.query.filter(Student.id.in_(student_ids)), Student).all()

    elif audience == 'defaulters':
        from utils.finance import student_bill
        if term:
            enr = scope_query(
                StudentEnrollment.query
                .join(ClassArmAssignment,
                      StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
                .filter(StudentEnrollment.is_active == True,
                        ClassArmAssignment.term_id == term.id),
                ClassArmAssignment)
            if class_id:
                enr = enr.filter(ClassArmAssignment.class_id == class_id)
            for e in enr.all():
                if not e.student:
                    continue
                bill = student_bill(e.student_id, term.id)
                if bill['balance'] > 0.005:
                    students.append(e.student)
                    balances[e.student_id] = bill['balance']

    # De-duplicate, attach the best contact.
    seen = set()
    out = []
    for s in students:
        if s.id in seen:
            continue
        seen.add(s.id)
        c = primary_contact(s)
        out.append({
            'student': s,
            'parent_name': (c.name if c and c.name else 'Parent'),
            'phone': (c.phone_number if c else ''),
            'balance': balances.get(s.id),
        })
    return out
