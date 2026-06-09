"""
Parent Communication routes — broadcast messaging to parents via WhatsApp / SMS
deep links, reusable templates, audience targeting (class, arm, fee defaulters,
selected students), a full send log and CSV export for bulk SMS gateways.
"""
from datetime import datetime
from utils.helpers import get_active_term
import csv
import io

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify, Response)
from sqlalchemy import func

from models import (
    db, Student, Term, SchoolClass, ClassArm, StudentEnrollment,
    ClassArmAssignment, MessageTemplate,
    Message, MessageRecipient, Announcement,
)
from utils.access_control import login_required, admin_required
from utils import comms

comms_bp = Blueprint('comms', __name__, url_prefix='/communication')

CHANNELS = ['WhatsApp', 'SMS']


def _active_term():
    return get_active_term()


def _term_from(tid):
    """Term for an id (None-safe), falling back to the active term."""
    return (db.session.get(Term, tid) if tid else None) or _active_term()


def _dt(value):
    """Parse an HTML datetime-local value ('YYYY-MM-DDTHH:MM')."""
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(value, fmt)
        except (ValueError, TypeError):
            continue
    return None


# ============================================================================
# DASHBOARD
# ============================================================================

@comms_bp.route('/')
@login_required
def dashboard():
    cov = comms.coverage_stats()
    total_campaigns = Message.query.count()
    total_recipients = db.session.query(func.coalesce(func.sum(Message.recipient_count), 0)).scalar() or 0
    total_sent = db.session.query(func.coalesce(func.sum(Message.sent_count), 0)).scalar() or 0
    channel_rows = (db.session.query(Message.channel, func.count(Message.id))
                    .group_by(Message.channel).all())
    channel_chart = [{'channel': ch or 'Other', 'count': n} for ch, n in channel_rows]
    recent = Message.query.order_by(Message.created_at.desc()).limit(8).all()
    template_count = MessageTemplate.query.filter_by(is_active=True).count()
    return render_template('communication/dashboard.html',
        cov=cov, total_campaigns=total_campaigns, total_recipients=total_recipients,
        total_sent=total_sent, channel_chart=channel_chart, recent=recent,
        template_count=template_count)


# ============================================================================
# CONTACT DIRECTORY
# ============================================================================

@comms_bp.route('/announcements')
@login_required
def announcements():
    items = Announcement.query.order_by(Announcement.is_pinned.desc(),
                                        Announcement.created_at.desc()).all()
    return render_template('communication/announcements.html', items=items)


def _read_announcement(a):
    a.title = (request.form.get('title') or '').strip()
    a.body = (request.form.get('body') or '').strip() or None
    a.audience = request.form.get('audience') or 'All'
    a.category = request.form.get('category') or 'Info'
    a.is_pinned = bool(request.form.get('is_pinned'))
    a.starts_on = _date(request.form.get('starts_on'))
    a.ends_on = _date(request.form.get('ends_on'))


def _date(v):
    try:
        return datetime.strptime(v, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


@comms_bp.route('/announcements/add', methods=['POST'])
@login_required
def add_announcement():
    if not (request.form.get('title') or '').strip():
        flash('Title is required.', 'error')
        return redirect(url_for('comms.announcements'))
    a = Announcement(created_by=_current_user())
    _read_announcement(a)
    db.session.add(a)
    db.session.commit()
    flash('Announcement posted.', 'success')
    return redirect(url_for('comms.announcements'))


@comms_bp.route('/announcements/<int:ann_id>/edit', methods=['POST'])
@login_required
def edit_announcement(ann_id):
    a = db.get_or_404(Announcement, ann_id)
    _read_announcement(a)
    db.session.commit()
    flash('Announcement updated.', 'success')
    return redirect(url_for('comms.announcements'))


@comms_bp.route('/announcements/<int:ann_id>/delete', methods=['POST'])
@login_required
def delete_announcement(ann_id):
    a = db.get_or_404(Announcement, ann_id)
    from utils.audit import log_action
    log_action('communication.announcement_delete', target=a)
    db.session.delete(a)
    db.session.commit()
    flash('Announcement deleted.', 'success')
    return redirect(url_for('comms.announcements'))


@comms_bp.route('/contacts')
@login_required
def contacts():
    term = _term_from(request.args.get('term_id', type=int))
    class_id = request.args.get('class_id', type=int)
    q = (request.args.get('q') or '').strip()
    missing = request.args.get('missing')  # only students without a contact

    terms = Term.query.order_by(Term.id.desc()).all()
    classes = SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.level).all()

    if class_id and term:
        ids = [e.student_id for e in (StudentEnrollment.query
               .join(ClassArmAssignment,
                     StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
               .filter(StudentEnrollment.is_active == True,
                       ClassArmAssignment.term_id == term.id,
                       ClassArmAssignment.class_id == class_id).all())]
        base = Student.query.filter(Student.id.in_(ids or [-1]))
    else:
        base = Student.query.filter_by(is_active=True)
    from utils.branch_scope import scope_query
    from utils.access_control import teacher_form_student_ids
    base = scope_query(base, Student)
    form_ids = teacher_form_student_ids()
    if form_ids is not None:
        base = base.filter(Student.id.in_(form_ids or [-1]))
    if q:
        like = f'%{q}%'
        base = base.filter(db.or_(Student.surname.ilike(like),
                                  Student.first_name.ilike(like),
                                  Student.student_id.ilike(like)))
    students = base.order_by(Student.surname, Student.first_name).limit(400).all()

    rows = []
    for s in students:
        contacts_list = [c for c in s.parent_contacts.all() if c.phone_number]
        if missing and contacts_list:
            continue
        rows.append({'student': s, 'contacts': contacts_list})

    return render_template('communication/contacts.html',
        rows=rows, terms=terms, classes=classes, term=term,
        class_id=class_id, q=q, missing=missing, cov=comms.coverage_stats())


# ============================================================================
# TEMPLATES
# ============================================================================

@comms_bp.route('/templates')
@login_required
def templates_list():
    tpls = MessageTemplate.query.order_by(MessageTemplate.is_active.desc(),
                                          MessageTemplate.category, MessageTemplate.name).all()
    return render_template('communication/templates.html',
        templates=tpls, placeholders=comms.PLACEHOLDERS)


@comms_bp.route('/templates/add', methods=['POST'])
@login_required
def add_template():
    name = (request.form.get('name') or '').strip()
    body = (request.form.get('body') or '').strip()
    if not (name and body):
        flash('Template name and body are required.', 'error')
        return redirect(url_for('comms.templates_list'))
    db.session.add(MessageTemplate(name=name, body=body,
        category=(request.form.get('category') or 'General').strip()))
    db.session.commit()
    flash(f'Template "{name}" saved.', 'success')
    return redirect(url_for('comms.templates_list'))


@comms_bp.route('/templates/<int:template_id>/edit', methods=['POST'])
@login_required
def edit_template(template_id):
    t = db.get_or_404(MessageTemplate, template_id)
    t.name = (request.form.get('name') or t.name).strip()
    t.body = (request.form.get('body') or t.body).strip()
    t.category = (request.form.get('category') or t.category or 'General').strip()
    t.is_active = bool(request.form.get('is_active'))
    db.session.commit()
    flash('Template updated.', 'success')
    return redirect(url_for('comms.templates_list'))


@comms_bp.route('/templates/<int:template_id>/delete', methods=['POST'])
@login_required
def delete_template(template_id):
    t = db.get_or_404(MessageTemplate, template_id)
    db.session.delete(t)
    db.session.commit()
    flash('Template deleted.', 'success')
    return redirect(url_for('comms.templates_list'))


# ============================================================================
# COMPOSE / SEND
# ============================================================================

@comms_bp.route('/compose', methods=['GET', 'POST'])
@login_required
def compose():
    term = _term_from(request.values.get('term_id', type=int))
    terms = Term.query.order_by(Term.id.desc()).all()
    classes = SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.level).all()
    arms = ClassArm.query.filter_by(is_active=True).order_by(ClassArm.name).all()
    templates = MessageTemplate.query.filter_by(is_active=True).order_by(MessageTemplate.name).all()

    if request.method == 'POST':
        audience = request.form.get('audience') or 'all'
        body = (request.form.get('body') or '').strip()
        channel = request.form.get('channel') or 'WhatsApp'
        title = (request.form.get('title') or '').strip()
        class_id = request.form.get('class_id', type=int)
        arm_id = request.form.get('arm_id', type=int)
        student_ids = request.form.getlist('student_ids', type=int)

        if not body:
            flash('Message body cannot be empty.', 'error')
            return redirect(url_for('comms.compose'))

        targets = comms.resolve_audience(audience, term, class_id=class_id,
                                         arm_id=arm_id, student_ids=student_ids)
        # Only those with a phone number can actually be messaged.
        reachable = [t for t in targets if t['phone']]
        if not reachable:
            flash('No recipients with a phone number matched that audience.', 'warning')
            return redirect(url_for('comms.compose'))

        # Optional scheduling (auto-send via gateway at a future time).
        from utils import sms_gateway
        scheduled_at = None
        status = 'Draft'
        if request.form.get('schedule') and sms_gateway.is_configured():
            scheduled_at = _dt(request.form.get('scheduled_at'))
            if scheduled_at and scheduled_at > datetime.now():
                status = 'Scheduled'

        label = _audience_label(audience, classes, arms, class_id, arm_id, len(reachable))
        msg = Message(title=title or label, body=body, channel=channel,
                      audience=audience, audience_label=label,
                      term_id=term.id if term else None,
                      created_by=_current_user(), recipient_count=len(reachable),
                      status=status, scheduled_at=scheduled_at)
        db.session.add(msg)
        db.session.flush()

        for t in reachable:
            ctx = comms.build_context(t['student'], term, t['parent_name'], t['balance'])
            db.session.add(MessageRecipient(
                message_id=msg.id, student_id=t['student'].id,
                parent_name=t['parent_name'], phone=t['phone'],
                body=comms.render(body, ctx)))
        db.session.commit()
        if status == 'Scheduled':
            flash(f'Campaign scheduled for {scheduled_at.strftime("%d %b %Y, %I:%M %p")} '
                  f'({len(reachable)} parent(s)).', 'success')
        else:
            flash(f'Campaign created for {len(reachable)} parent(s).', 'success')
        return redirect(url_for('comms.message_detail', message_id=msg.id))

    # Pre-selection from query params (e.g. "Message defaulters" from Finance,
    # or "Use" from the templates page).
    pre_audience = request.args.get('audience') or 'all'
    pre_class = request.args.get('class_id', type=int)
    pre_tpl = request.args.get('tpl', type=int)
    pre_body = ''
    if pre_tpl:
        t = db.session.get(MessageTemplate, pre_tpl)
        if t:
            pre_body = t.body
    elif pre_audience == 'defaulters':
        # Convenience: default to the Fee Reminder template when messaging debtors.
        t = MessageTemplate.query.filter(MessageTemplate.name.ilike('%fee%reminder%'),
                                         MessageTemplate.is_active == True).first()
        if t:
            pre_tpl, pre_body = t.id, t.body
    elif request.args.get('notice') == 'results':
        # Pre-select the result-notification template when releasing results.
        t = MessageTemplate.query.filter(MessageTemplate.name.ilike('%result%'),
                                         MessageTemplate.is_active == True).first()
        if t:
            pre_tpl, pre_body = t.id, t.body

    from utils import sms_gateway
    gw = sms_gateway.get_config()
    return render_template('communication/compose.html',
        term=term, terms=terms, classes=classes, arms=arms, templates=templates,
        channels=CHANNELS, placeholders=comms.PLACEHOLDERS, cov=comms.coverage_stats(),
        gateway_ready=sms_gateway.is_configured(gw),
        gateway_label=sms_gateway.provider_label(gw),
        pre_audience=pre_audience, pre_class=pre_class, pre_tpl=pre_tpl, pre_body=pre_body)


def _current_user():
    from flask import session
    return session.get('username') or session.get('user') or 'Admin'


def _audience_label(audience, classes, arms, class_id, arm_id, count):
    if audience == 'all':
        return f'All parents ({count})'
    if audience == 'defaulters':
        base = 'Fee defaulters'
        if class_id:
            cls = next((c for c in classes if c.id == class_id), None)
            if cls:
                base += f' · {cls.name}'
        return f'{base} ({count})'
    if audience in ('class', 'arm'):
        cls = next((c for c in classes if c.id == class_id), None)
        arm = next((a for a in arms if a.id == arm_id), None)
        name = ' '.join(p for p in [cls.name if cls else '', arm.name if arm else ''] if p)
        return f'{name or "Class"} ({count})'
    return f'Selected students ({count})'


@comms_bp.route('/compose/preview', methods=['POST'])
@login_required
def compose_preview():
    """JSON: count of recipients + a personalised sample for the chosen audience."""
    term = _term_from(request.form.get('term_id', type=int))
    audience = request.form.get('audience') or 'all'
    body = request.form.get('body') or ''
    targets = comms.resolve_audience(audience, term,
        class_id=request.form.get('class_id', type=int),
        arm_id=request.form.get('arm_id', type=int),
        student_ids=request.form.getlist('student_ids', type=int))
    reachable = [t for t in targets if t['phone']]
    sample = ''
    if reachable:
        t = reachable[0]
        ctx = comms.build_context(t['student'], term, t['parent_name'], t['balance'])
        sample = comms.render(body, ctx)
    return jsonify({'total': len(targets), 'reachable': len(reachable),
                    'no_phone': len(targets) - len(reachable), 'sample': sample})


@comms_bp.route('/students/search')
@login_required
def students_search():
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify([])
    like = f'%{q}%'
    from utils.branch_scope import scope_query
    rows = (scope_query(Student.query.filter_by(is_active=True), Student)
            .filter(db.or_(Student.surname.ilike(like), Student.first_name.ilike(like),
                           Student.student_id.ilike(like)))
            .order_by(Student.surname).limit(15).all())
    return jsonify([{'id': s.id, 'name': s.full_name, 'sid': s.student_id} for s in rows])


@comms_bp.route('/messages/<int:message_id>/cancel-schedule', methods=['POST'])
@login_required
def cancel_schedule(message_id):
    msg = db.get_or_404(Message, message_id)
    msg.status = 'Draft'
    msg.scheduled_at = None
    db.session.commit()
    flash('Schedule cancelled — the campaign is now on hold.', 'success')
    return redirect(url_for('comms.message_detail', message_id=message_id))


@comms_bp.route('/process-scheduled', methods=['POST'])
@admin_required
def process_scheduled():
    n = comms.dispatch_due_scheduled()
    flash(f'Processed {n} due scheduled campaign(s).' if n else 'No campaigns were due.',
          'success' if n else 'info')
    return redirect(url_for('comms.messages_list'))


# ============================================================================
# CAMPAIGN HISTORY + DETAIL
# ============================================================================

@comms_bp.route('/messages')
@login_required
def messages_list():
    msgs = Message.query.order_by(Message.created_at.desc()).all()
    return render_template('communication/messages.html', messages=msgs)


@comms_bp.route('/messages/<int:message_id>')
@login_required
def message_detail(message_id):
    msg = db.get_or_404(Message, message_id)
    recips = msg.recipients.order_by(MessageRecipient.parent_name).all()
    rows = []
    for r in recips:
        rows.append({'r': r, 'intl': comms.normalise_phone(r.phone)})
    from utils import sms_gateway
    gw = sms_gateway.get_config()
    return render_template('communication/message_detail.html',
        msg=msg, rows=rows, segments=comms.sms_segments(msg.body),
        gateway_ready=sms_gateway.is_configured(gw),
        gateway_label=sms_gateway.provider_label(gw),
        pending_count=msg.recipients.filter(MessageRecipient.status != 'Sent').count())


@comms_bp.route('/messages/<int:message_id>/recipient/<int:rid>/sent', methods=['POST'])
@login_required
def mark_sent(message_id, rid):
    r = db.get_or_404(MessageRecipient, rid)
    if r.message_id != message_id:
        return ('', 404)
    if r.status != 'Sent':
        r.status = 'Sent'
        r.sent_at = datetime.now()
        r.message.sent_count = (r.message.sent_count or 0) + 1
        db.session.commit()
    if request.headers.get('X-Requested-With') == 'fetch':
        return jsonify({'ok': True, 'sent': r.message.sent_count})
    return redirect(url_for('comms.message_detail', message_id=message_id))


@comms_bp.route('/messages/<int:message_id>/mark-all-sent', methods=['POST'])
@login_required
def mark_all_sent(message_id):
    msg = db.get_or_404(Message, message_id)
    n = 0
    for r in msg.recipients.filter(MessageRecipient.status != 'Sent').all():
        r.status = 'Sent'
        r.sent_at = datetime.now()
        n += 1
    msg.sent_count = msg.recipients.filter_by(status='Sent').count()
    db.session.commit()
    flash(f'Marked {n} recipient(s) as sent.', 'success')
    return redirect(url_for('comms.message_detail', message_id=message_id))


@comms_bp.route('/messages/<int:message_id>/export')
@login_required
def export_recipients(message_id):
    msg = db.get_or_404(Message, message_id)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['Parent', 'Phone', 'Phone (intl)', 'Student', 'Message', 'Status'])
    for r in msg.recipients.all():
        w.writerow([r.parent_name, r.phone, comms.normalise_phone(r.phone),
                    r.student.full_name if r.student else '', r.body, r.status])
    fname = f'campaign_{msg.id}_recipients.csv'
    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={fname}'})


@comms_bp.route('/messages/<int:message_id>/delete', methods=['POST'])
@admin_required
def delete_message(message_id):
    msg = db.get_or_404(Message, message_id)
    from utils.audit import log_action
    log_action('communication.message_delete',
               target_type='message', target_id=msg.id, target_label=getattr(msg, 'title', None))
    db.session.delete(msg)
    db.session.commit()
    flash('Campaign deleted.', 'success')
    return redirect(url_for('comms.messages_list'))


@comms_bp.route('/messages/<int:message_id>/send-gateway', methods=['POST'])
@login_required
def send_gateway(message_id):
    """Dispatch all pending recipients through the configured SMS gateway."""
    from utils import sms_gateway
    msg = db.get_or_404(Message, message_id)
    cfg = sms_gateway.get_config()
    if not sms_gateway.is_configured(cfg):
        flash('No SMS gateway is configured. Add your provider key in Settings.', 'error')
        return redirect(url_for('comms.message_detail', message_id=message_id))

    # Claim a scheduled campaign so this manual send can't race the worker.
    if msg.status in ('Scheduled', 'Sending') and not comms._claim_message(msg.id, msg.status):
        flash('This campaign is already being sent.', 'warning')
        return redirect(url_for('comms.message_detail', message_id=message_id))

    sent, failed = comms.dispatch_campaign(msg, cfg)
    msg.status = 'Sent'
    db.session.commit()
    if sent:
        flash(f'Sent {sent} message(s) via {sms_gateway.provider_label(cfg)}.', 'success')
    if failed:
        flash(f'{failed} message(s) failed — see the recipient list for details.', 'warning')
    return redirect(url_for('comms.message_detail', message_id=message_id))


# ============================================================================
# SMS GATEWAY SETTINGS
# ============================================================================

@comms_bp.route('/settings')
@login_required
def settings():
    from utils import sms_gateway
    cfg = sms_gateway.get_config()
    return render_template('communication/settings.html',
        cfg=cfg, providers=sms_gateway.PROVIDERS,
        configured=sms_gateway.is_configured(cfg),
        provider_label=sms_gateway.provider_label(cfg))


@comms_bp.route('/settings/save', methods=['POST'])
@admin_required
def save_settings():
    from utils import sms_gateway
    sms_gateway.save_config(request.form)
    cfg = sms_gateway.get_config()
    if cfg['provider'] != 'none' and not sms_gateway.is_configured(cfg):
        flash('Settings saved, but some required fields for this provider are missing.', 'warning')
    else:
        flash('SMS gateway settings saved.', 'success')
    return redirect(url_for('comms.settings'))


@comms_bp.route('/settings/test', methods=['POST'])
@admin_required
def test_sms():
    from utils import sms_gateway
    phone = (request.form.get('phone') or '').strip()
    if not phone:
        flash('Enter a phone number to send the test to.', 'error')
        return redirect(url_for('comms.settings'))
    ok, info = sms_gateway.send_sms(phone,
        f'Test message from {comms.school_name()} via PosyHub. Your SMS gateway is working!')
    if ok:
        flash(f'Test SMS sent successfully (ref: {info}).', 'success')
    else:
        flash(f'Test failed: {info}', 'error')
    return redirect(url_for('comms.settings'))
