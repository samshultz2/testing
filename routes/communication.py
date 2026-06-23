"""
Parent Communication routes — broadcast messaging to parents via WhatsApp / SMS
deep links, reusable templates, audience targeting (class, arm, fee defaulters,
selected students), a full send log and CSV export for bulk SMS gateways.
"""
from datetime import datetime
from utils.helpers import get_active_term
import csv
import io

from flask import (Blueprint, request, redirect, url_for,
                   flash, jsonify, Response)
from sqlalchemy import func

from models import (
    db, Student, Term, SchoolClass, ClassArm, StudentEnrollment,
    ClassArmAssignment, MessageTemplate,
    Message, MessageRecipient, Announcement,
)
from utils.access_control import login_required, admin_required
from utils.branch_scope import scope_query, require_branch_access
from utils import comms

comms_bp = Blueprint('comms', __name__, url_prefix='/communication')

CHANNELS = ['WhatsApp', 'SMS']


# --- SPA helpers (no-reload React shell + JSON-aware action responses) ---
from utils.spa import section_responders
_wants_json, _render, _ok, _err = section_responders(
    'communication/app.html', 'comm_json', 'comms.dashboard')


def _is_admin():
    from utils.access_control import is_admin
    return is_admin()


def _nav_urls():
    return {'dashboard': url_for('comms.dashboard'), 'compose': url_for('comms.compose'),
            'announcements': url_for('comms.announcements'), 'messages': url_for('comms.messages_list'),
            'templates': url_for('comms.templates_list'), 'contacts': url_for('comms.contacts'),
            'settings': url_for('comms.settings')}


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
    total_campaigns = scope_query(Message.query, Message).count()
    total_recipients = scope_query(db.session.query(func.coalesce(func.sum(Message.recipient_count), 0)), Message).scalar() or 0
    total_sent = scope_query(db.session.query(func.coalesce(func.sum(Message.sent_count), 0)), Message).scalar() or 0
    channel_rows = (scope_query(db.session.query(Message.channel, func.count(Message.id)), Message)
                    .group_by(Message.channel).all())
    channel_chart = [{'channel': ch or 'Other', 'count': n} for ch, n in channel_rows]
    recent = scope_query(Message.query, Message).order_by(Message.created_at.desc()).limit(8).all()
    template_count = MessageTemplate.query.filter_by(is_active=True).count()
    return _render({
        'page': 'dashboard', 'nav': _nav_urls(),
        'cov': cov, 'total_campaigns': total_campaigns,
        'total_recipients': int(total_recipients), 'total_sent': int(total_sent),
        'channel_chart': channel_chart, 'template_count': template_count,
        'recent': [{'id': m.id, 'date': m.created_at.strftime('%d %b'),
                    'title': m.title or 'Message', 'audience_label': m.audience_label,
                    'channel': m.channel, 'sent_count': m.sent_count or 0,
                    'recipient_count': m.recipient_count or 0,
                    'url': url_for('comms.message_detail', message_id=m.id)} for m in recent],
        'urls': {'contacts_missing': url_for('comms.contacts', missing=1)},
    })


# ============================================================================
# CONTACT DIRECTORY
# ============================================================================

@comms_bp.route('/announcements')
@login_required
def announcements():
    items = Announcement.query.order_by(Announcement.is_pinned.desc(),
                                        Announcement.created_at.desc()).all()
    return _render({
        'page': 'announcements', 'nav': _nav_urls(),
        'items': [{'id': a.id, 'title': a.title, 'body': a.body or '',
                   'category': a.category or 'Info', 'audience': a.audience or 'All',
                   'is_pinned': bool(a.is_pinned), 'is_active': bool(a.is_active),
                   'created_at': a.created_at.strftime('%d %b %Y') if a.created_at else '',
                   'created_by': a.created_by or '',
                   'starts_on': a.starts_on.strftime('%d %b') if a.starts_on else '',
                   'ends_on': a.ends_on.strftime('%d %b') if a.ends_on else '',
                   'delete_url': url_for('comms.delete_announcement', ann_id=a.id)} for a in items],
        'add_url': url_for('comms.add_announcement'),
    })


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
        return _err('Title is required.', url_for('comms.announcements'))
    a = Announcement(created_by=_current_user())
    _read_announcement(a)
    db.session.add(a)
    db.session.commit()
    return _ok('Announcement posted.', url_for('comms.announcements'))


@comms_bp.route('/announcements/<int:ann_id>/edit', methods=['POST'])
@login_required
def edit_announcement(ann_id):
    a = db.get_or_404(Announcement, ann_id)
    _read_announcement(a)
    db.session.commit()
    return _ok('Announcement updated.', url_for('comms.announcements'))


@comms_bp.route('/announcements/<int:ann_id>/delete', methods=['POST'])
@login_required
def delete_announcement(ann_id):
    a = db.get_or_404(Announcement, ann_id)
    from utils.audit import log_action
    log_action('communication.announcement_delete', target=a)
    db.session.delete(a)
    db.session.commit()
    return _ok('Announcement deleted.', url_for('comms.announcements'))


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
        rows.append({
            'student': {'id': s.id, 'full_name': s.full_name, 'student_id': s.student_id,
                        'view_url': url_for('main.view_student', student_id=s.id)},
            'contacts': [{'name': c.name or 'Parent', 'relationship': c.relationship or '',
                          'is_primary': bool(c.is_primary), 'phone_number': c.phone_number,
                          'wa_intl': comms.normalise_phone(c.phone_number)} for c in contacts_list],
        })

    return _render({
        'page': 'contacts', 'nav': _nav_urls(), 'rows': rows,
        'terms': [{'id': t.id, 'full_name': t.full_name} for t in terms],
        'classes': [{'id': c.id, 'name': c.name} for c in classes],
        'term_id': term.id if term else '', 'class_id': class_id or '',
        'q': q, 'missing': bool(missing), 'cov': comms.coverage_stats(),
        'self_url': url_for('comms.contacts'),
    })


# ============================================================================
# TEMPLATES
# ============================================================================

@comms_bp.route('/templates')
@login_required
def templates_list():
    tpls = MessageTemplate.query.order_by(MessageTemplate.is_active.desc(),
                                          MessageTemplate.category, MessageTemplate.name).all()
    return _render({
        'page': 'templates', 'nav': _nav_urls(), 'placeholders': comms.PLACEHOLDERS,
        'templates': [{'id': t.id, 'name': t.name, 'body': t.body,
                       'category': t.category or '', 'is_active': bool(t.is_active),
                       'use_url': url_for('comms.compose', tpl=t.id),
                       'edit_url': url_for('comms.edit_template', template_id=t.id),
                       'delete_url': url_for('comms.delete_template', template_id=t.id)} for t in tpls],
        'add_url': url_for('comms.add_template'),
    })


@comms_bp.route('/templates/add', methods=['POST'])
@login_required
def add_template():
    name = (request.form.get('name') or '').strip()
    body = (request.form.get('body') or '').strip()
    if not (name and body):
        return _err('Template name and body are required.', url_for('comms.templates_list'))
    db.session.add(MessageTemplate(name=name, body=body,
        category=(request.form.get('category') or 'General').strip()))
    db.session.commit()
    return _ok(f'Template "{name}" saved.', url_for('comms.templates_list'))


@comms_bp.route('/templates/<int:template_id>/edit', methods=['POST'])
@login_required
def edit_template(template_id):
    t = db.get_or_404(MessageTemplate, template_id)
    t.name = (request.form.get('name') or t.name).strip()
    t.body = (request.form.get('body') or t.body).strip()
    t.category = (request.form.get('category') or t.category or 'General').strip()
    t.is_active = bool(request.form.get('is_active'))
    db.session.commit()
    return _ok('Template updated.', url_for('comms.templates_list'))


@comms_bp.route('/templates/<int:template_id>/delete', methods=['POST'])
@login_required
def delete_template(template_id):
    t = db.get_or_404(MessageTemplate, template_id)
    db.session.delete(t)
    db.session.commit()
    return _ok('Template deleted.', url_for('comms.templates_list'))


# ============================================================================
# COMPOSE / SEND
# ============================================================================

@comms_bp.route('/compose', methods=['GET', 'POST'])
@login_required
def compose():
    term = _term_from(request.values.get('term_id', type=int))
    terms = Term.query.order_by(Term.id.desc()).all()
    classes = SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.level).all()
    arms = ClassArm.query.filter_by(is_active=True, is_default=False).order_by(ClassArm.name).all()
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
            return _err('Message body cannot be empty.', url_for('comms.compose'))

        targets = comms.resolve_audience(audience, term, class_id=class_id,
                                         arm_id=arm_id, student_ids=student_ids)
        # Only those with a phone number can actually be messaged.
        reachable = [t for t in targets if t['phone']]
        if not reachable:
            return _err('No recipients with a phone number matched that audience.',
                        url_for('comms.compose'))

        # Optional scheduling (auto-send via gateway at a future time).
        from utils import sms_gateway
        scheduled_at = None
        status = 'Draft'
        if request.form.get('schedule') and sms_gateway.is_configured():
            scheduled_at = _dt(request.form.get('scheduled_at'))
            if scheduled_at and scheduled_at > datetime.now():
                status = 'Scheduled'

        label = _audience_label(audience, classes, arms, class_id, arm_id, len(reachable))
        from utils.branch_scope import branch_for_new
        msg = Message(title=title or label, body=body, channel=channel,
                      audience=audience, audience_label=label,
                      term_id=term.id if term else None, branch_id=branch_for_new(),
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
            note = (f'Campaign scheduled for {scheduled_at.strftime("%d %b %Y, %I:%M %p")} '
                    f'({len(reachable)} parent(s)).')
        else:
            note = f'Campaign created for {len(reachable)} parent(s).'
        return _ok(note, url_for('comms.message_detail', message_id=msg.id))

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
    return _render({
        'page': 'compose', 'nav': _nav_urls(),
        'term_id': term.id if term else '',
        'terms': [{'id': t.id, 'full_name': t.full_name} for t in terms],
        'classes': [{'id': c.id, 'name': c.name} for c in classes],
        'arms': [{'id': a.id, 'name': a.name} for a in arms],
        'templates': [{'id': t.id, 'name': t.name, 'category': t.category or '', 'body': t.body}
                      for t in templates],
        'channels': CHANNELS, 'placeholders': comms.PLACEHOLDERS, 'cov': comms.coverage_stats(),
        'gateway_ready': sms_gateway.is_configured(gw),
        'gateway_label': sms_gateway.provider_label(gw),
        'pre_audience': pre_audience, 'pre_class': pre_class or '',
        'pre_tpl': pre_tpl or '', 'pre_body': pre_body,
        'urls': {'submit': url_for('comms.compose'), 'preview': url_for('comms.compose_preview'),
                 'search': url_for('comms.students_search'), 'settings': url_for('comms.settings')},
    })


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
    return jsonify([{'id': s.id, 'name': s.full_name, 'sid': s.student_id,
                     'label': f'{s.full_name} ({s.student_id})'} for s in rows])


@comms_bp.route('/messages/<int:message_id>/cancel-schedule', methods=['POST'])
@login_required
def cancel_schedule(message_id):
    msg = db.get_or_404(Message, message_id)
    require_branch_access(msg.branch_id)
    msg.status = 'Draft'
    msg.scheduled_at = None
    db.session.commit()
    return _ok('Schedule cancelled — the campaign is now on hold.',
               url_for('comms.message_detail', message_id=message_id))


@comms_bp.route('/process-scheduled', methods=['POST'])
@admin_required
def process_scheduled():
    n = comms.dispatch_due_scheduled()
    return _ok(f'Processed {n} due scheduled campaign(s).' if n else 'No campaigns were due.',
               url_for('comms.messages_list'))


# ============================================================================
# CAMPAIGN HISTORY + DETAIL
# ============================================================================

@comms_bp.route('/messages')
@login_required
def messages_list():
    msgs = scope_query(Message.query, Message).order_by(Message.created_at.desc()).all()
    return _render({
        'page': 'messages', 'nav': _nav_urls(), 'is_admin': _is_admin(),
        'messages': [{'id': m.id, 'date': m.created_at.strftime('%d %b %Y') if m.created_at else '',
                      'title': m.title or 'Message', 'status': m.status,
                      'scheduled_at': m.scheduled_at.strftime('%d %b %H:%M') if m.scheduled_at else '',
                      'audience_label': m.audience_label, 'channel': m.channel,
                      'recipient_count': m.recipient_count or 0, 'sent_count': m.sent_count or 0,
                      'url': url_for('comms.message_detail', message_id=m.id)} for m in msgs],
        'urls': {'compose': url_for('comms.compose'),
                 'process_scheduled': url_for('comms.process_scheduled')},
    })


@comms_bp.route('/messages/<int:message_id>')
@login_required
def message_detail(message_id):
    msg = db.get_or_404(Message, message_id)
    require_branch_access(msg.branch_id)
    recips = msg.recipients.order_by(MessageRecipient.parent_name).all()
    rows = []
    for r in recips:
        rows.append({'id': r.id, 'parent_name': r.parent_name,
                     'student_name': r.student.full_name if r.student else '—',
                     'phone': r.phone, 'intl': comms.normalise_phone(r.phone),
                     'status': r.status, 'error': r.error or '', 'body': r.body,
                     'sent_url': url_for('comms.mark_sent', message_id=msg.id, rid=r.id)})
    from utils import sms_gateway
    gw = sms_gateway.get_config()
    return _render({
        'page': 'message_detail', 'nav': _nav_urls(), 'is_admin': _is_admin(),
        'msg': {'id': msg.id, 'title': msg.title or 'Campaign', 'channel': msg.channel,
                'audience_label': msg.audience_label, 'status': msg.status, 'body': msg.body,
                'scheduled_at': msg.scheduled_at.strftime('%d %b, %I:%M %p') if msg.scheduled_at else '',
                'created_at': msg.created_at.strftime('%d %b %Y, %I:%M %p') if msg.created_at else '',
                'created_by': msg.created_by or '', 'sent_count': msg.sent_count or 0,
                'recipient_count': msg.recipient_count or 0},
        'rows': rows, 'segments': comms.sms_segments(msg.body),
        'gateway_ready': sms_gateway.is_configured(gw),
        'gateway_label': sms_gateway.provider_label(gw),
        'failed_count': msg.recipients.filter(MessageRecipient.status == 'Failed').count(),
        'pending_count': msg.recipients.filter(MessageRecipient.status != 'Sent').count(),
        'urls': {'export': url_for('comms.export_recipients', message_id=msg.id),
                 'compose': url_for('comms.compose'),
                 'cancel_schedule': url_for('comms.cancel_schedule', message_id=msg.id),
                 'send_gateway': url_for('comms.send_gateway', message_id=msg.id),
                 'mark_all_sent': url_for('comms.mark_all_sent', message_id=msg.id),
                 'delete': url_for('comms.delete_message', message_id=msg.id),
                 'list': url_for('comms.messages_list')},
    })


@comms_bp.route('/messages/<int:message_id>/recipient/<int:rid>/sent', methods=['POST'])
@login_required
def mark_sent(message_id, rid):
    r = db.get_or_404(MessageRecipient, rid)
    if r.message_id != message_id:
        return ('', 404)
    require_branch_access(r.message.branch_id)
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
    require_branch_access(msg.branch_id)
    n = 0
    for r in msg.recipients.filter(MessageRecipient.status != 'Sent').all():
        r.status = 'Sent'
        r.sent_at = datetime.now()
        n += 1
    msg.sent_count = msg.recipients.filter_by(status='Sent').count()
    db.session.commit()
    return _ok(f'Marked {n} recipient(s) as sent.',
               url_for('comms.message_detail', message_id=message_id))


@comms_bp.route('/messages/<int:message_id>/export')
@login_required
def export_recipients(message_id):
    msg = db.get_or_404(Message, message_id)
    require_branch_access(msg.branch_id)
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
    require_branch_access(msg.branch_id)
    from utils.audit import log_action
    log_action('communication.message_delete',
               target_type='message', target_id=msg.id, target_label=getattr(msg, 'title', None))
    db.session.delete(msg)
    db.session.commit()
    return _ok('Campaign deleted.', url_for('comms.messages_list'))


@comms_bp.route('/messages/<int:message_id>/send-gateway', methods=['POST'])
@login_required
def send_gateway(message_id):
    """Dispatch all pending recipients through the configured SMS gateway."""
    from utils import sms_gateway
    msg = db.get_or_404(Message, message_id)
    require_branch_access(msg.branch_id)
    cfg = sms_gateway.get_config()
    if not sms_gateway.is_configured(cfg):
        return _err('No SMS gateway is configured. Add your provider key in Settings.',
                    url_for('comms.message_detail', message_id=message_id))

    # Claim a scheduled campaign so this manual send can't race the worker.
    if msg.status in ('Scheduled', 'Sending') and not comms._claim_message(msg.id, msg.status):
        return _err('This campaign is already being sent.',
                    url_for('comms.message_detail', message_id=message_id))

    # Send in the background: each gateway call can take seconds, so sending a
    # whole batch inline would tie up this web worker for minutes.
    from flask import current_app
    pending = msg.recipients.filter(MessageRecipient.status != 'Sent').count()
    msg.status = 'Sending'
    db.session.commit()
    comms.dispatch_campaign_async(current_app._get_current_object(), msg.id, cfg)
    return _ok(f'Sending {pending} message(s) via {sms_gateway.provider_label(cfg)} in the '
               'background. Refresh this page to see delivery progress.',
               url_for('comms.message_detail', message_id=message_id))


# ============================================================================
# SMS GATEWAY SETTINGS
# ============================================================================

@comms_bp.route('/settings')
@login_required
def settings():
    from utils import sms_gateway
    cfg = sms_gateway.get_config()
    configured = sms_gateway.is_configured(cfg)
    balance_ok, balance = (sms_gateway.get_balance(cfg) if configured else (False, ''))
    return _render({
        'page': 'settings', 'nav': _nav_urls(), 'is_admin': _is_admin(),
        'cfg': {'provider': cfg.get('provider', 'none'), 'sender': cfg.get('sender', ''),
                'termii_key': cfg.get('termii_key', ''), 'twilio_sid': cfg.get('twilio_sid', ''),
                'twilio_token': cfg.get('twilio_token', '')},
        'providers': [{'key': k, 'label': v} for k, v in sms_gateway.PROVIDERS.items()],
        'configured': configured, 'balance_ok': balance_ok, 'balance': balance,
        'provider_label': sms_gateway.provider_label(cfg),
        'urls': {'save': url_for('comms.save_settings'), 'test': url_for('comms.test_sms')},
    })


@comms_bp.route('/settings/save', methods=['POST'])
@admin_required
def save_settings():
    from utils import sms_gateway
    sms_gateway.save_config(request.form)
    cfg = sms_gateway.get_config()
    if cfg['provider'] != 'none' and not sms_gateway.is_configured(cfg):
        return _ok('Settings saved, but some required fields for this provider are missing.',
                   url_for('comms.settings'))
    return _ok('SMS gateway settings saved.', url_for('comms.settings'))


@comms_bp.route('/settings/test', methods=['POST'])
@admin_required
def test_sms():
    from utils import sms_gateway
    phone = (request.form.get('phone') or '').strip()
    if not phone:
        return _err('Enter a phone number to send the test to.', url_for('comms.settings'))
    ok, info = sms_gateway.send_sms(phone,
        f'Test message from {comms.school_name()} via PosyHub. Your SMS gateway is working!')
    if ok:
        return _ok(f'Test SMS sent successfully (ref: {info}).', url_for('comms.settings'))
    return _err(f'Test failed: {info}', url_for('comms.settings'))
