"""
Admissions routes — applicant pipeline, screening/decisions, one-click
conversion of an admitted applicant into a Student, dashboard and CSV export.
"""
from datetime import datetime, date
from utils import timeutil
from utils.web_exports import csv_response, pdf_response
from utils.helpers import get_active_session
import csv
import io

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, Response, jsonify)
from sqlalchemy import func

from models import (db, Applicant, AcademicSession, SchoolClass, ClassArmAssignment)
from utils.access_control import login_required, admin_required, is_admin
from utils.branch_scope import scope_query, branch_for_new, require_branch_access, viewing_branch_id
from utils import admissions
from utils.security import strip_tags
from utils.search import like_term

adm_bp = Blueprint('admissions', __name__, url_prefix='/admissions')

TABS = [['dashboard', 'fa-chart-pie', 'Overview'], ['applicants', 'fa-user-plus', 'Applicants']]


@adm_bp.before_request
def _heal_admissions_schema():
    # Add post-baseline applicant columns (emergency contact) to older tenant DBs.
    from utils.admissions_schema import ensure_admissions_schema
    ensure_admissions_schema()


def _d(value, default=None):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return default


def _active_session():
    return get_active_session()


def _wants_json():
    return request.headers.get('X-Requested-With') == 'fetch' or request.is_json


def _ok(message, redirect_url=None):
    if _wants_json():
        return jsonify({'ok': True, 'message': message, 'redirect': redirect_url})
    flash(message, 'success')
    return redirect(redirect_url or url_for('admissions.dashboard'))


def _err(message, redirect_url=None, tone='error'):
    if _wants_json():
        return jsonify({'ok': False, 'error': message}), 400
    flash(message, tone)
    return redirect(redirect_url or url_for('admissions.dashboard'))


def _render(payload):
    payload['is_admin'] = is_admin()
    payload['urls'] = {**{
        'dashboard': url_for('admissions.dashboard'), 'applicants': url_for('admissions.applicants'),
        'add': url_for('admissions.add_applicant'), 'export': url_for('admissions.export'),
        'blank_form': url_for('admissions.blank_application_form'),
    }, **payload.get('urls', {})}
    from utils.spa import render_or_json
    return render_or_json('admissions/app.html', 'adm_json', payload)


def _sessions_json():
    return [{'id': s.id, 'name': s.name} for s in
            AcademicSession.query.order_by(AcademicSession.name.desc()).all()]


def _classes_json():
    return [{'id': c.id, 'name': c.name} for c in
            SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.level).all()]


# ============================================================================
# DASHBOARD
# ============================================================================

@adm_bp.route('/')
@login_required
def dashboard():
    session_id = request.args.get('session_id', type=int)
    bid = viewing_branch_id()
    stats = admissions.pipeline_stats(session_id, bid)
    recent = (scope_query(Applicant.query, Applicant)
              .order_by(Applicant.created_at.desc()).limit(8).all())
    # by intended class (branch-scoped)
    cq = (db.session.query(SchoolClass.name, func.count(Applicant.id))
          .join(Applicant, Applicant.intended_class_id == SchoolClass.id))
    if bid is not None:
        cq = cq.filter(Applicant.branch_id == bid)
    cls_rows = cq.group_by(SchoolClass.name).all()
    badge = admissions.STATUS_BADGE
    return _render({
        'page': 'dashboard', 'tabs': TABS, 'active': 'dashboard',
        'stats': stats, 'session_id': session_id or '', 'sessions': _sessions_json(),
        'class_chart': [{'name': n, 'count': c} for n, c in cls_rows],
        'recent': [{'id': a.id, 'application_no': a.application_no, 'full_name': a.full_name,
                    'intended_class': a.intended_class.name if a.intended_class else '—',
                    'status': a.status, 'status_badge': badge.get(a.status, 'badge-secondary'),
                    'applied': a.applied_date.strftime('%d %b %Y') if a.applied_date else '—',
                    'detail_url': url_for('admissions.applicant_detail', applicant_id=a.id)} for a in recent],
    })


# ============================================================================
# APPLICANTS
# ============================================================================

@adm_bp.route('/applicants')
@login_required
def applicants():
    status = request.args.get('status')
    session_id = request.args.get('session_id', type=int)
    class_id = request.args.get('class_id', type=int)
    q = (request.args.get('q') or '').strip()

    query = scope_query(Applicant.query, Applicant)
    if status:
        query = query.filter_by(status=status)
    if session_id:
        query = query.filter_by(session_id=session_id)
    if class_id:
        query = query.filter_by(intended_class_id=class_id)
    if q:
        like = like_term(q)
        query = query.filter(db.or_(Applicant.first_name.ilike(like, escape='\\'),
                                    Applicant.surname.ilike(like, escape='\\'),
                                    Applicant.application_no.ilike(like, escape='\\'),
                                    Applicant.parent_phone.ilike(like, escape='\\')))
    rows = query.order_by(Applicant.created_at.desc()).all()
    badge = admissions.STATUS_BADGE
    return _render({
        'page': 'applicants', 'tabs': TABS, 'active': 'applicants',
        'status': status or '', 'session_id': session_id or '', 'class_id': class_id or '', 'q': q,
        'sessions': _sessions_json(), 'classes': _classes_json(), 'statuses': admissions.ALL_STATUSES,
        'rows': [{'id': a.id, 'application_no': a.application_no, 'full_name': a.full_name,
                  'gender': a.gender, 'intended_class': a.intended_class.name if a.intended_class else '—',
                  'parent_name': a.parent_name, 'parent_phone': a.parent_phone,
                  'entrance_score': a.entrance_score if a.entrance_score is not None else '—',
                  'status': a.status, 'status_badge': badge.get(a.status, 'badge-secondary'),
                  'linked': bool(a.admitted_student_id),
                  'detail_url': url_for('admissions.applicant_detail', applicant_id=a.id)} for a in rows],
    })


def _read_form(a):
    a.first_name = strip_tags(request.form.get('first_name'))
    a.surname = strip_tags(request.form.get('surname'))
    a.middle_name = strip_tags(request.form.get('middle_name')) or None
    a.gender = request.form.get('gender') or None
    a.date_of_birth = _d(request.form.get('date_of_birth'))
    a.session_id = request.form.get('session_id', type=int) or None
    a.intended_class_id = request.form.get('intended_class_id', type=int) or None
    a.previous_school = strip_tags(request.form.get('previous_school')) or None
    a.source = request.form.get('source') or None
    a.entrance_score = request.form.get('entrance_score', type=float)
    a.parent_name = strip_tags(request.form.get('parent_name')) or None
    a.parent_phone = (request.form.get('parent_phone') or '').strip() or None
    a.parent_email = (request.form.get('parent_email') or '').strip() or None
    a.relationship = strip_tags(request.form.get('relationship')) or None
    a.address = strip_tags(request.form.get('address')) or None
    a.emergency_name = strip_tags(request.form.get('emergency_name')) or None
    a.emergency_phone = (request.form.get('emergency_phone') or '').strip() or None
    a.emergency_relationship = strip_tags(request.form.get('emergency_relationship')) or None
    a.emergency_address = strip_tags(request.form.get('emergency_address')) or None
    a.notes = strip_tags(request.form.get('notes')) or None


@adm_bp.route('/applicants/add', methods=['GET', 'POST'])
@login_required
def add_applicant():
    if request.method == 'POST':
        if not (request.form.get('first_name') and request.form.get('surname')):
            return _err('First name and surname are required.', url_for('admissions.add_applicant'))
        a = Applicant(application_no=Applicant.generate_application_no(),
                      status=request.form.get('status') or 'Applied',
                      applied_date=timeutil.today())
        _read_form(a)
        a.branch_id = branch_for_new()
        db.session.add(a)
        db.session.commit()
        return _ok(f'Application {a.application_no} created for {a.full_name}.',
                   url_for('admissions.applicant_detail', applicant_id=a.id))
    return _render(_form_payload(None))


def _form_payload(a):
    active = _active_session()
    return {
        'page': 'applicant_form', 'tabs': TABS, 'active': 'applicants',
        'applicant': ({
            'id': a.id, 'first_name': a.first_name or '', 'surname': a.surname or '',
            'middle_name': a.middle_name or '', 'gender': a.gender or '',
            'date_of_birth': a.date_of_birth.isoformat() if a.date_of_birth else '',
            'session_id': a.session_id or '', 'intended_class_id': a.intended_class_id or '',
            'previous_school': a.previous_school or '', 'source': a.source or '',
            'entrance_score': a.entrance_score if a.entrance_score is not None else '',
            'parent_name': a.parent_name or '', 'relationship': a.relationship or '',
            'parent_phone': a.parent_phone or '', 'parent_email': a.parent_email or '',
            'address': a.address or '', 'notes': a.notes or '',
            'emergency_name': a.emergency_name or '', 'emergency_phone': a.emergency_phone or '',
            'emergency_relationship': a.emergency_relationship or '',
            'emergency_address': a.emergency_address or '',
            'detail_url': url_for('admissions.applicant_detail', applicant_id=a.id),
        } if a else None),
        'sessions': _sessions_json(), 'classes': _classes_json(),
        'sources': admissions.SOURCES, 'statuses': admissions.ALL_STATUSES,
        'active_session_id': active.id if active else '',
        'submit_url': url_for('admissions.edit_applicant', applicant_id=a.id) if a else url_for('admissions.add_applicant'),
    }


@adm_bp.route('/applicants/<int:applicant_id>')
@login_required
def applicant_detail(applicant_id):
    a = db.get_or_404(Applicant, applicant_id)
    require_branch_access(a.branch_id)   # no cross-branch applicant PII
    # class arms for the intended class (for enrolment on conversion)
    assignments = []
    if a.intended_class_id:
        aq = ClassArmAssignment.query.filter_by(class_id=a.intended_class_id)
        if a.session_id:
            from models import Term
            term_ids = [t.id for t in Term.query.filter_by(session_id=a.session_id).all()]
            if term_ids:
                aq = aq.filter(ClassArmAssignment.term_id.in_(term_ids))
        assignments = aq.all()
    badge = admissions.STATUS_BADGE
    info = [['Gender', a.gender or '—'],
            ['Date of birth', a.date_of_birth.strftime('%d %b %Y') if a.date_of_birth else '—'],
            ['Intended class', a.intended_class.name if a.intended_class else '—'],
            ['Session', a.session.name if a.session else '—'],
            ['Previous school', a.previous_school or '—'],
            ['Entrance score', a.entrance_score if a.entrance_score is not None else '—'],
            ['Source', a.source or '—'],
            ['Applied', a.applied_date.strftime('%d %b %Y') if a.applied_date else '—']]
    parent = [['Name', a.parent_name or '—'], ['Relationship', a.relationship or '—'],
              ['Phone', a.parent_phone or '—'], ['Email', a.parent_email or '—'],
              ['Address', a.address or '—']]
    emergency = [['Name', a.emergency_name or '—'], ['Relationship', a.emergency_relationship or '—'],
                 ['Phone', a.emergency_phone or '—'], ['Address', a.emergency_address or '—']]
    has_emergency = any(v not in (None, '', '—') for _l, v in emergency)
    return _render({
        'page': 'applicant_detail', 'tabs': TABS, 'active': 'applicants',
        'applicant': {
            'id': a.id, 'full_name': a.full_name, 'application_no': a.application_no,
            'initials': (a.first_name[0] if a.first_name else '') + (a.surname[0] if a.surname else ''),
            'intended_class': a.intended_class.name if a.intended_class else None,
            'session': a.session.name if a.session else None,
            'status': a.status, 'status_badge': badge.get(a.status, 'badge-secondary'),
            'gender': a.gender, 'parent_phone': a.parent_phone,
            'admitted_student_id': a.admitted_student_id,
            'student_url': url_for('main.view_student', student_id=a.admitted_student_id) if a.admitted_student_id else None,
        },
        'stages': admissions.STAGES, 'outcomes': admissions.OUTCOMES, 'info': info, 'parent': parent,
        'emergency': emergency if has_emergency else None,
        'notes': a.notes,
        'assignments': [{'id': x.id, 'label': x.display_name + (' · ' + x.term.full_name if x.term else '')} for x in assignments],
        'urls': {'edit': url_for('admissions.edit_applicant', applicant_id=a.id),
                 'status': url_for('admissions.set_status', applicant_id=a.id),
                 'convert': url_for('admissions.convert', applicant_id=a.id),
                 'delete': url_for('admissions.delete_applicant', applicant_id=a.id),
                 'pdf': url_for('admissions.export_applicant', applicant_id=a.id, format='pdf'),
                 'docx': url_for('admissions.export_applicant', applicant_id=a.id, format='docx')},
    })


@adm_bp.route('/applicants/blank-form')
@login_required
def blank_application_form():
    """Download a branded, fillable (interactive AcroForm) blank application form.
    ``?bw=1`` returns a black-and-white, print-friendly variant."""
    from utils.school import school_profile
    from utils.applicant_export import applicant_blank_pdf
    bw = request.args.get('bw') in ('1', 'true', 'yes')
    data = applicant_blank_pdf(school_profile(), bw=bw)
    name = 'application_form_bw.pdf' if bw else 'application_form.pdf'
    return pdf_response(io.BytesIO(data), name, inline=False)


@adm_bp.route('/applicants/<int:applicant_id>/export')
@login_required
def export_applicant(applicant_id):
    """Download the applicant record as a branded PDF (reportlab) or Word file."""
    a = db.get_or_404(Applicant, applicant_id)
    require_branch_access(a.branch_id)
    fmt = request.args.get('format', 'pdf')
    from utils.school import school_profile
    from utils.applicant_export import applicant_pdf, applicant_docx

    def dash(v):
        return v if v not in (None, '') else '—'

    sections = [
        ('Applicant', [
            ('Gender', dash(a.gender)),
            ('Date of Birth', a.date_of_birth.strftime('%d %b %Y') if a.date_of_birth else '—'),
            ('Previous School', dash(a.previous_school)),
            ('How did they hear?', dash(a.source)),
        ]),
        ('Application', [
            ('Intended Class', a.intended_class.name if a.intended_class else '—'),
            ('Session', a.session.name if a.session else '—'),
            ('Entrance Score', a.entrance_score if a.entrance_score is not None else '—'),
            ('Applied', a.applied_date.strftime('%d %b %Y') if a.applied_date else '—'),
        ]),
        ('Parent / Guardian', [
            ('Name', dash(a.parent_name)), ('Relationship', dash(a.relationship)),
            ('Phone', dash(a.parent_phone)), ('Email', dash(a.parent_email)),
            ('Address', dash(a.address)),
        ]),
        ('Emergency Contact', [
            ('Name', dash(a.emergency_name)), ('Relationship', dash(a.emergency_relationship)),
            ('Phone', dash(a.emergency_phone)), ('Address', dash(a.emergency_address)),
        ]),
    ]
    if a.notes:
        sections.append(('Notes', [('', a.notes)]))
    record = {
        'title': 'Applicant Record',
        'name': a.full_name,
        'meta': [('Application No', a.application_no or '—'), ('Status', a.status or '—')],
        'sections': sections,
    }
    base = (a.application_no or 'applicant').replace('/', '-')
    if fmt == 'docx':
        return applicant_docx(record, school_profile(), filename='%s.docx' % base)
    data = applicant_pdf(record, school_profile())
    return pdf_response(io.BytesIO(data), '%s.pdf' % base, inline=False)


@adm_bp.route('/applicants/<int:applicant_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_applicant(applicant_id):
    a = db.get_or_404(Applicant, applicant_id)
    require_branch_access(a.branch_id)
    if request.method == 'POST':
        _read_form(a)
        db.session.commit()
        return _ok('Application updated.', url_for('admissions.applicant_detail', applicant_id=a.id))
    return _render(_form_payload(a))


@adm_bp.route('/applicants/<int:applicant_id>/status', methods=['POST'])
@login_required
def set_status(applicant_id):
    a = db.get_or_404(Applicant, applicant_id)
    require_branch_access(a.branch_id)
    new_status = request.form.get('status')
    if new_status in admissions.ALL_STATUSES:
        a.status = new_status
        if new_status in ('Rejected', 'Admitted'):
            a.decision_date = timeutil.today()
        score = request.form.get('entrance_score', type=float)
        if score is not None:
            a.entrance_score = score
        db.session.commit()
        from utils import automations
        if automations.is_enabled('admission_decision'):
            admissions.notify_decision(a)   # bell admins + email parent on a decision
    return _ok(f'Status set to {new_status}.', url_for('admissions.applicant_detail', applicant_id=applicant_id))


@adm_bp.route('/applicants/<int:applicant_id>/convert', methods=['POST'])
@admin_required
def convert(applicant_id):
    a = db.get_or_404(Applicant, applicant_id)
    require_branch_access(a.branch_id)
    assignment_id = request.form.get('assignment_id', type=int)
    if assignment_id and not db.session.get(ClassArmAssignment, assignment_id):
        flash('Selected class arm no longer exists — admitting without enrolment.', 'warning')
        assignment_id = None
    student, err = admissions.convert_to_student(a, assignment_id)
    if err and not student:
        return _err(err, url_for('admissions.applicant_detail', applicant_id=applicant_id))
    if err:
        flash(err, 'info')
    else:
        flash(f'{a.full_name} admitted as student {student.student_id}.', 'success')
    return _ok('Admitted.', url_for('main.view_student', student_id=student.id))


@adm_bp.route('/applicants/<int:applicant_id>/delete', methods=['POST'])
@admin_required
def delete_applicant(applicant_id):
    a = db.get_or_404(Applicant, applicant_id)
    require_branch_access(a.branch_id)   # no cross-branch deletion
    from utils.audit import log_action
    log_action('admissions.applicant_delete', target=a)
    db.session.delete(a)
    db.session.commit()
    return _ok('Application deleted.', url_for('admissions.applicants'))


@adm_bp.route('/export')
@login_required
def export():
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['Application No', 'Name', 'Gender', 'Intended Class', 'Session',
                'Status', 'Entrance Score', 'Parent', 'Phone', 'Applied'])
    for a in scope_query(Applicant.query, Applicant).order_by(Applicant.created_at.desc()).all():
        w.writerow([a.application_no, a.full_name, a.gender or '',
                    a.intended_class.name if a.intended_class else '',
                    a.session.name if a.session else '', a.status,
                    a.entrance_score if a.entrance_score is not None else '',
                    a.parent_name or '', a.parent_phone or '',
                    a.applied_date or ''])
    return csv_response(out.getvalue(), 'applicants.csv')
