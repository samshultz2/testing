"""
Parent-communication helpers — phone normalisation, placeholder rendering and
audience resolution (turning "JSS1 Rose" or "fee defaulters" into a concrete
list of parents to message).
"""
import re

from models import (
    db, Student, ParentContact, StudentEnrollment, ClassArmAssignment, SchoolSettings,
)

PLACEHOLDERS = ['{name}', '{student}', '{first_name}', '{surname}', '{class}', '{arm}',
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
            asg.arm_label)


def build_context(student, term, parent_name='Parent', balance=None):
    """Placeholder values for one student/parent."""
    cls, arm = student_placement_label(student.id, term.id if term else None)
    bal = ''
    if balance is not None:
        bal = '₦{:,.2f}'.format(balance)
    return {
        '{name}': parent_name or 'Parent',
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


def build_staff_context(staff):
    """Placeholder values for a staff recipient (no student-specific fields)."""
    name = staff.display_name or staff.full_name
    return {
        '{name}': name,
        '{student}': '',
        '{first_name}': staff.first_name or name,
        '{surname}': staff.surname or '',
        '{class}': '', '{arm}': '', '{term}': '', '{balance}': '',
        '{parent}': name,
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


def dispatch_campaign_async(app, message_id, cfg=None):
    """Send a campaign in a background thread so the request returns at once.

    Each SMS gateway call can take seconds; sending a large batch inline blocks a
    web worker for minutes. The campaign should already be claimed ('Sending')
    before calling this. Marks the message 'Sent' when done.
    """
    import threading

    def _run():
        with app.app_context():
            from models import db, Message
            try:
                msg = db.session.get(Message, message_id)
                if msg is None:
                    return
                dispatch_campaign(msg, cfg)
                msg.status = 'Sent'
                db.session.commit()
            except Exception:
                db.session.rollback()
                app.logger.exception('Background SMS dispatch failed for message %s',
                                     message_id)

    threading.Thread(target=_run, daemon=True).start()


def dispatch_campaign_email(msg):
    """Send every pending recipient of an Email-channel campaign via SMTP.

    Mirrors :func:`dispatch_campaign` (per-recipient commit so an interruption
    never resends) but delivers over email. The campaign title is the subject and
    each recipient's personalised body is the plain-text content. Requires a
    configured mailer. Returns (sent, failed)."""
    from datetime import datetime
    from models import MessageRecipient
    from utils import mailer
    subject = msg.title or 'Message from your school'
    sent = failed = 0
    for r in msg.recipients.filter(MessageRecipient.status != 'Sent').all():
        if r.email and mailer.send_email(r.email, subject, r.body):
            r.status, r.sent_at, r.error = 'Sent', datetime.now(), None
            sent += 1
        else:
            r.status = 'Failed'
            r.error = 'No email address' if not r.email else 'Email delivery failed'
            failed += 1
        db.session.commit()
    msg.sent_count = msg.recipients.filter_by(status='Sent').count()
    db.session.commit()
    return sent, failed


def dispatch_campaign_email_async(app, message_id):
    """Send an email campaign in a background thread so the request returns at once.
    The campaign should already be claimed ('Sending'). Marks it 'Sent' when done."""
    import threading

    def _run():
        with app.app_context():
            from models import db as _db, Message
            try:
                msg = _db.session.get(Message, message_id)
                if msg is None:
                    return
                dispatch_campaign_email(msg)
                msg.status = 'Sent'
                _db.session.commit()
            except Exception:
                _db.session.rollback()
                app.logger.exception('Background email dispatch failed for message %s',
                                     message_id)

    threading.Thread(target=_run, daemon=True).start()


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

    # Teachers may only message parents of their own form-class students.
    from utils.access_control import teacher_form_student_ids
    form_ids = teacher_form_student_ids()
    if form_ids is not None:
        students = [s for s in students if s.id in form_ids]

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
            'email': ((getattr(c, 'email', '') or '') if c else ''),
            'balance': balances.get(s.id),
        })
    return out


# --- unified recipient engine (Phase 2) -------------------------------------
# A recipient "spec" is a plain dict, so it round-trips cleanly through form
# fields and saved groups. It targets either parents (of students) or staff, with
# optional filters and exclusions layered on top of the base audience.
STAFF_SCOPES = ['all', 'teaching', 'non-teaching', 'department']


def resolve_recipients(spec, term=None):
    """Resolve a recipient spec into a list of targets (the same shape used by
    :func:`build_campaign`). ``spec['to']`` selects 'parents' (default) or 'staff'.

    Parents accept the legacy audience (all/class/arm/students/defaulters) plus
    optional ``gender`` / ``stream`` filters and an ``exclude_ids`` list of student
    ids. Staff accept a ``staff_scope`` (all/teaching/non-teaching/department) and
    optional ``department_id`` / ``exclude_ids`` (staff ids). Kept branch-scoped.
    """
    spec = spec or {}
    if (spec.get('to') or 'parents').lower() == 'staff':
        return _resolve_staff(spec)
    return _resolve_parents(spec, term)


def _resolve_parents(spec, term):
    targets = resolve_audience(
        spec.get('audience') or 'all', term,
        class_id=spec.get('class_id'), arm_id=spec.get('arm_id'),
        student_ids=spec.get('student_ids') or [])
    gender = (spec.get('gender') or '').strip()
    stream = (spec.get('stream') or '').strip()
    exclude = {int(x) for x in (spec.get('exclude_ids') or []) if str(x).strip()}
    out = []
    for t in targets:
        s = t['student']
        if gender and (s.gender or '') != gender:
            continue
        if stream and (s.stream or '') != stream:
            continue
        if s.id in exclude:
            continue
        out.append(t)
    return out


def _resolve_staff(spec):
    from models import StaffMember
    from utils.branch_scope import scope_query
    q = scope_query(StaffMember.query.filter(StaffMember.is_active.is_(True)), StaffMember)
    scope = (spec.get('staff_scope') or 'all').lower()
    if scope == 'teaching':
        q = q.filter(StaffMember.staff_type == 'Teaching')
    elif scope in ('non-teaching', 'nonteaching'):
        q = q.filter(StaffMember.staff_type == 'Non-teaching')
    elif scope == 'department' and spec.get('department_id'):
        q = q.filter(StaffMember.department_id == int(spec['department_id']))
    exclude = {int(x) for x in (spec.get('exclude_ids') or []) if str(x).strip()}
    out = []
    for st in q.order_by(StaffMember.surname, StaffMember.first_name).all():
        if st.id in exclude:
            continue
        name = st.display_name or st.full_name
        out.append({
            'student': None, 'staff': st, 'name': name, 'parent_name': name,
            'phone': st.phone or '', 'email': st.email or '', 'balance': None,
            'user_id': st.user_id,      # for in-app (bell) delivery
        })
    return out


def channel_is_email(channel):
    return (channel or '').lower() == 'email'


def channel_is_inapp(channel):
    return (channel or '').lower() in ('in-app', 'inapp', 'in_app')


def reachable_targets(targets, channel):
    """Filter resolved audience targets to those actually reachable on ``channel``
    — an email address for Email, a linked user account for In-app, else a phone
    number for SMS/WhatsApp."""
    if channel_is_inapp(channel):
        return [t for t in targets if t.get('user_id')]
    by_email = channel_is_email(channel)
    return [t for t in targets if (t.get('email') if by_email else t.get('phone'))]


def campaign_context(target, term):
    """Personalisation context for a target, staff- or parent-aware."""
    if target.get('staff') is not None:
        return build_staff_context(target['staff'])
    return build_context(target['student'], term,
                         target.get('parent_name') or target.get('name'),
                         target.get('balance'))


def build_campaign(body, *, channel='SMS', audience='all', term=None, title=None,
                   audience_label=None, class_id=None, arm_id=None, student_ids=None,
                   created_by='system', status='Draft', scheduled_at=None,
                   branch_id=None, spec=None):
    """The single campaign builder used by every entry point (the composer UI and
    automated triggers alike). Resolves recipients, keeps only those reachable on
    the chosen channel, persists the Message + one personalised MessageRecipient
    each, and returns the Message — or None when the body is empty or nobody is
    reachable.

    Pass ``spec`` (a recipient dict, see :func:`resolve_recipients`) for the full
    parents/staff + filters engine; omit it to use the legacy ``audience`` args.
    Reachability is channel-aware (phone for SMS/WhatsApp, email for Email). A
    'Draft'/'Scheduled' status controls whether the scheduler may auto-send it.
    """
    from models import Message, MessageRecipient
    from utils.branch_scope import branch_for_new

    body = (body or '').strip()
    if not body:
        return None
    if spec is not None:
        targets = resolve_recipients(spec, term)
        audience = spec.get('audience') or (spec.get('to') or 'parents')
    else:
        targets = resolve_audience(audience, term, class_id=class_id, arm_id=arm_id,
                                   student_ids=student_ids or [])
    reachable = reachable_targets(targets, channel)
    if not reachable:
        return None

    # In-app (bell) notifications are instant and gateway-free, so they're
    # delivered on creation and the campaign is recorded as already Sent.
    inapp = channel_is_inapp(channel)
    if inapp:
        status = 'Sent'
    label = audience_label or title or f'{str(audience).title()} ({len(reachable)})'
    msg = Message(title=title or label, body=body, channel=channel,
                  audience=str(audience), audience_label=label,
                  term_id=term.id if term else None,
                  branch_id=(branch_id if branch_id is not None else branch_for_new()),
                  created_by=created_by, recipient_count=len(reachable),
                  status=status, scheduled_at=scheduled_at,
                  sent_count=(len(reachable) if inapp else 0))
    db.session.add(msg)
    db.session.flush()
    from datetime import datetime as _now
    for t in reachable:
        ctx = campaign_context(t, term)
        rendered = render(body, ctx)
        db.session.add(MessageRecipient(
            message_id=msg.id,
            student_id=(t['student'].id if t.get('student') is not None else None),
            parent_name=(t.get('parent_name') or t.get('name')),
            phone=t['phone'], email=t.get('email') or None,
            body=rendered,
            status=('Sent' if inapp else 'Pending'),
            sent_at=(_now.now() if inapp else None)))
        if inapp and t.get('user_id'):
            from models import Notification
            db.session.add(Notification(
                user_id=t['user_id'], title=(title or 'Notice'), body=rendered,
                category='info'))
    db.session.commit()
    return msg


def create_draft_campaign(body, *, audience='all', term=None, title=None,
                          channel='SMS', class_id=None, arm_id=None,
                          student_ids=None, created_by='system'):
    """Create a *Draft* campaign (never auto-dispatched) for a human to review and
    send — the safe entry point for automated triggers. Thin wrapper over
    :func:`build_campaign`; see it for reachability semantics."""
    return build_campaign(body, channel=channel, audience=audience, term=term,
                          title=title, class_id=class_id, arm_id=arm_id,
                          student_ids=student_ids, created_by=created_by,
                          status='Draft', scheduled_at=None)
