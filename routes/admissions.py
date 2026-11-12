"""
Admissions routes — applicant pipeline, screening/decisions, one-click
conversion of an admitted applicant into a Student, dashboard and CSV export.
"""
from datetime import datetime, date, timedelta
from utils import timeutil
from utils.web_exports import csv_response, pdf_response, formula_guard
from utils.helpers import get_active_session
import csv
import io

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, Response, jsonify, abort)
from sqlalchemy import func

from models import (db, Applicant, AcademicSession, SchoolClass, ClassArmAssignment)
from utils.access_control import login_required, is_admin
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
        'blank_form': url_for('admissions.blank_form_page'),
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
    base = scope_query(Applicant.query, Applicant)
    if session_id:
        base = base.filter(Applicant.session_id == session_id)
    today = timeutil.today()
    pend = base.filter(Applicant.status.in_(['Inquiry', 'Applied', 'Screening'])).all()
    stale = [a for a in pend if a.updated_at and (today - a.updated_at.date()).days >= 14]
    offered = base.filter(Applicant.status == 'Offered').count()
    accepted = base.filter(Applicant.status == 'Accepted').count()
    src = base.with_entities(Applicant.source, func.count(Applicant.id)).group_by(Applicant.source).all()
    gender = dict(base.with_entities(Applicant.gender, func.count(Applicant.id)).group_by(Applicant.gender).all())
    likely = _likely_students()
    week_ago = today - timedelta(days=7)
    new_week = base.filter(Applicant.applied_date >= week_ago).count()
    cls_full = []
    for name, cid in db.session.query(SchoolClass.name, SchoolClass.id).filter(SchoolClass.is_active == True).order_by(SchoolClass.level).all():
        rows = base.filter(Applicant.intended_class_id == cid).all()
        if not rows:
            continue
        sc = [r.entrance_score for r in rows if r.entrance_score is not None]
        cls_full.append({'name': name, 'count': len(rows),
                         'admitted': sum(1 for r in rows if r.status == 'Admitted'),
                         'avg_score': round(sum(sc) / len(sc), 1) if sc else None})
    return _render({
        'page': 'dashboard', 'tabs': TABS, 'active': 'dashboard',
        'classes_full': cls_full,
        'sources': sorted([{'name': n or 'Not recorded', 'count': c} for n, c in src], key=lambda x: -x['count']),
        'gender': {'male': gender.get('Male', 0), 'female': gender.get('Female', 0)},
        'new_week': new_week,
        'action': {'stale': len(stale), 'offered': offered, 'accepted': accepted,
                   'linkable': len(likely), 'linkable_url': url_for('admissions.applicants', possible=1),
                   'stale_url': url_for('admissions.applicants', status='Applied', session_id=session_id or ''),
                   'offered_url': url_for('admissions.applicants', status='Offered', session_id=session_id or ''),
                   'accepted_url': url_for('admissions.applicants', status='Accepted', session_id=session_id or '')},
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
    possible = request.args.get('possible') == '1'
    likely = _likely_students() if possible else {}
    if possible:
        query = query.filter(Applicant.id.in_(list(likely) or [-1]))
    rows = query.order_by(Applicant.created_at.desc()).all()
    badge = admissions.STATUS_BADGE
    return _render({
        'page': 'applicants', 'tabs': TABS, 'active': 'applicants',
        'status': status or '', 'session_id': session_id or '', 'class_id': class_id or '', 'q': q,
        'possible': possible,
        'sessions': _sessions_json(), 'classes': _classes_json(), 'statuses': admissions.ALL_STATUSES,
        'rows': [{'id': a.id, 'application_no': a.application_no, 'full_name': a.full_name,
                  'gender': a.gender, 'intended_class': a.intended_class.name if a.intended_class else '—',
                  'parent_name': a.parent_name, 'parent_phone': a.parent_phone,
                  'entrance_score': a.entrance_score if a.entrance_score is not None else '—',
                  'status': a.status, 'status_badge': badge.get(a.status, 'badge-secondary'),
                  'linked': bool(a.admitted_student_id),
                  'applied': a.applied_date.strftime('%d %b') if a.applied_date else '',
                  'waiting': (timeutil.today() - a.updated_at.date()).days if a.updated_at else None,
                  'source': a.source or '',
                  'match': ({'name': likely[a.id]['student'].full_name, 'student_id': likely[a.id]['student'].student_id}
                            if a.id in likely else None),
                  'photo_url': (url_for('admissions.applicant_photo', applicant_id=a.id)
                                if (a.photo and a.photo.data) else ''),
                  'status_url': url_for('admissions.set_status', applicant_id=a.id),
                  'detail_url': url_for('admissions.applicant_detail', applicant_id=a.id)} for a in rows],
        'stages': admissions.STAGES, 'outcomes': admissions.OUTCOMES,
    })


def _save_photo(a):
    """Store the applicant's passport photo from the form's ``photo_data`` data
    URL (or clear it), after the applicant row exists. Best-effort."""
    data_url = request.form.get('photo_data')
    if data_url == '__clear__':
        from utils.applicant_photo import delete as _del
        _del(a); db.session.commit(); return
    if data_url and data_url.startswith('data:image'):
        try:
            from utils.applicant_photo import save_data_url
            save_data_url(a, data_url); db.session.commit()
        except ValueError:
            db.session.rollback()


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
    a.country = strip_tags(request.form.get('country')) or None
    a.state_of_origin = strip_tags(request.form.get('state_of_origin')) or None
    a.lga = strip_tags(request.form.get('lga')) or None
    a.father_occupation = strip_tags(request.form.get('father_occupation')) or None
    a.languages_spoken = strip_tags(request.form.get('languages_spoken')) or None
    a.blood_group = (request.form.get('blood_group') or '').strip() or None
    a.genotype = (request.form.get('genotype') or '').strip() or None
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
        _save_photo(a)
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
            'country': a.country or '', 'state_of_origin': a.state_of_origin or '',
            'lga': a.lga or '', 'father_occupation': a.father_occupation or '',
            'languages_spoken': a.languages_spoken or '',
            'blood_group': a.blood_group or '', 'genotype': a.genotype or '',
            'photo_url': (url_for('admissions.applicant_photo', applicant_id=a.id)
                          if (a.photo and a.photo.data) else ''),
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
            'gender': a.gender, 'parent_phone': a.parent_phone, 'parent_email': a.parent_email,
            'parent_name': a.parent_name, 'entrance_score': a.entrance_score,
            'applied': a.applied_date.strftime('%d %b %Y') if a.applied_date else None,
            'decision': a.decision_date.strftime('%d %b %Y') if a.decision_date else None,
            'age': ((timeutil.today() - a.date_of_birth).days // 365) if a.date_of_birth else None,
            'photo_url': (url_for('admissions.applicant_photo', applicant_id=a.id)
                          if (a.photo and a.photo.data) else ''),
            'admitted_student_id': a.admitted_student_id,
            'student_url': url_for('main.view_student', student_id=a.admitted_student_id) if a.admitted_student_id else None,
        },
        'matches': ([{'id': m['student'].id, 'name': m['student'].full_name, 'student_id': m['student'].student_id,
                      'class': admissions._current_class(m['student']),
                      'dob': m['student'].date_of_birth.strftime('%d %b %Y') if m['student'].date_of_birth else None,
                      'reasons': m['reasons'], 'strong': m['score'] >= 6,
                      'url': url_for('main.view_student', student_id=m['student'].id)}
                     for m in admissions.match_students(a)] if not a.admitted_student_id else []),
        'stages': admissions.STAGES, 'outcomes': admissions.OUTCOMES, 'info': info, 'parent': parent,
        'emergency': emergency if has_emergency else None,
        'notes': a.notes,
        'assignments': [{'id': x.id, 'label': x.display_name + (' · ' + x.term.full_name if x.term else '')} for x in assignments],
        'urls': {'edit': url_for('admissions.edit_applicant', applicant_id=a.id),
                 'status': url_for('admissions.set_status', applicant_id=a.id),
                 'convert': url_for('admissions.convert', applicant_id=a.id),
                 'copy': url_for('admissions.copy_to_student', applicant_id=a.id),
                 'link': url_for('admissions.link_student', applicant_id=a.id),
                 'student_search': url_for('main.api_search_students'),
                 'delete': url_for('admissions.delete_applicant', applicant_id=a.id),
                 'pdf': url_for('admissions.applicant_pdf_page', applicant_id=a.id),
                 'docx': url_for('admissions.export_applicant', applicant_id=a.id, format='docx')},
    })


@adm_bp.route('/applicants/blank-form')          # legacy path, kept for old links
@adm_bp.route('/applicants/blank-form.pdf')      # canonical (url_for builds this one)
@login_required
def blank_application_form():
    """Download a branded, fillable (interactive AcroForm) blank application form.
    ``?bw=1`` returns a black-and-white, print-friendly variant."""
    from utils.school import school_profile
    from utils.applicant_export import applicant_blank_pdf
    bw = request.args.get('bw') in ('1', 'true', 'yes')
    data = applicant_blank_pdf(school_profile(), bw=bw)
    name = 'application_form_bw.pdf' if bw else 'application_form.pdf'
    # The .pdf link previews (?download=1 saves); the legacy path keeps downloading.
    inline = request.path.endswith('.pdf') and request.args.get('download') != '1'
    return pdf_response(io.BytesIO(data), name, inline=inline)


@adm_bp.route('/blank-form')
@login_required
def blank_form_page():
    """Pick the colour or black & white blank application form, preview it,
    then open, download or print it."""
    return render_template('admissions/pdf_pick.html', title='Blank application form',
                           subtitle='A one-page form parents can fill on screen, or print and complete by hand.',
                           crumb=None, back_url=url_for('admissions.dashboard'), fillable=True,
                           pdf_url=url_for('admissions.blank_application_form'), view_param='',
                           viewer_url=url_for('mock_waec.pdf_viewer'), notes=[
                               ('fa-keyboard', 'Every box is fillable — parents can type into it in any PDF reader, then print or send it back.'),
                               ('fa-stamp', 'The “For office use only” box is for your staff when the form comes back.')])


@adm_bp.route('/applicants/<int:applicant_id>/pdf')
@login_required
def applicant_pdf_page(applicant_id):
    """Pick the colour or black & white applicant record, preview it, then
    download, print or view it full screen."""
    a = db.get_or_404(Applicant, applicant_id)
    require_branch_access(a.branch_id)
    detail = url_for('admissions.applicant_detail', applicant_id=a.id)
    return render_template('admissions/pdf_pick.html', title='Applicant record — %s' % a.full_name,
                           subtitle='%s · %s' % (a.application_no or 'No application number', a.status or ''),
                           crumb=('Applicants', url_for('admissions.applicants')), back_url=detail, fillable=False,
                           pdf_url=url_for('admissions.export_applicant', applicant_id=a.id, format='pdf'),
                           view_param='view=1', viewer_url=url_for('mock_waec.pdf_viewer'), notes=[
                               ('fa-user-shield', 'Contains personal and health details — share it only with staff who need it.'),
                               ('fa-file-word', 'Need to edit it? Use “Download Word” on the applicant page.')])


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
        ('Origin & Health', [
            ('Country', dash(a.country)), ('State of Origin', dash(a.state_of_origin)),
            ('L.G.A. of Origin', dash(a.lga)), ("Father's Occupation", dash(a.father_occupation)),
            ('Languages at Home', dash(a.languages_spoken)),
            ('Blood Group', dash(a.blood_group)), ('Genotype', dash(a.genotype)),
        ]),
    ]
    if a.notes:
        sections.append(('Notes', [('', a.notes)]))
    from utils.applicant_photo import load as _load_photo
    _pb, _ = _load_photo(a.id)
    record = {
        'title': 'Applicant Record',
        'name': a.full_name,
        'meta': [('Application No', a.application_no or '—'), ('Status', a.status or '—')],
        'sections': sections,
        'photo_bytes': _pb,
    }
    base = (a.application_no or 'applicant').replace('/', '-')
    if fmt == 'docx':
        return applicant_docx(record, school_profile(), filename='%s.docx' % base)
    bw = request.args.get('bw') in ('1', 'true', 'yes')
    data = applicant_pdf(record, school_profile(), bw=bw)
    # ?view=1 previews in the browser; otherwise (and with ?download=1) it downloads.
    inline = request.args.get('view') == '1' and request.args.get('download') != '1'
    return pdf_response(io.BytesIO(data), '%s%s.pdf' % (base, '_bw' if bw else ''), inline=inline)


@adm_bp.route('/applicants/<int:applicant_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_applicant(applicant_id):
    a = db.get_or_404(Applicant, applicant_id)
    require_branch_access(a.branch_id)
    if request.method == 'POST':
        _read_form(a)
        db.session.commit()
        _save_photo(a)
        return _ok('Application updated.', url_for('admissions.applicant_detail', applicant_id=a.id))
    return _render(_form_payload(a))


@adm_bp.route('/applicants/<int:applicant_id>/photo')
@login_required
def applicant_photo(applicant_id):
    """Serve an applicant's passport photo from the tenant DB (login + branch
    scoped — it is PII, never public). Cached privately + ETag'd."""
    from flask import Response
    from models import ApplicantPhoto
    a = db.session.get(Applicant, applicant_id)
    if not a:
        abort(404)
    require_branch_access(a.branch_id)
    row = ApplicantPhoto.query.filter_by(applicant_id=a.id).first()
    if row is None or not row.data:
        abort(404)
    etag = 'ap-%d-%d' % (row.id, row.bytes or 0)
    if request.headers.get('If-None-Match') == etag:
        return Response(status=304)
    resp = Response(bytes(row.data), mimetype=row.mime or 'image/jpeg')
    resp.headers['Cache-Control'] = 'private, max-age=3600'
    resp.headers['ETag'] = etag
    return resp


@adm_bp.route('/applicants/<int:applicant_id>/status', methods=['POST'])
@login_required
def set_status(applicant_id):
    a = db.get_or_404(Applicant, applicant_id)
    require_branch_access(a.branch_id)
    new_status = request.form.get('status')
    if new_status == 'Admitted' and not a.admitted_student_id:
        # "Admitted" must create the student record — use Admit, not a bare label.
        return _err('Use “Admit” to admit this applicant — it creates their student record.',
                    url_for('admissions.applicant_detail', applicant_id=applicant_id))
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
@login_required
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


@adm_bp.route('/applicants/<int:applicant_id>/copy-to-student', methods=['POST'])
@login_required
def copy_to_student(applicant_id):
    """Fill the admitted student's record with anything from the application
    it is still missing (photo, contacts, health, address…). Never overwrites."""
    a = db.get_or_404(Applicant, applicant_id)
    require_branch_access(a.branch_id)
    if not a.admitted_student:
        return _err('This applicant has not been admitted yet.', url_for('admissions.applicant_detail', applicant_id=a.id))
    done = admissions.copy_to_student(a, a.admitted_student)
    db.session.commit()
    msg = ('Copied to the student record: ' + ', '.join(done) + '.') if done else \
        'The student record already has everything from the application.'
    return _ok(msg, url_for('admissions.applicant_detail', applicant_id=a.id))


@adm_bp.route('/applicants/<int:applicant_id>/link', methods=['POST'])
@login_required
def link_student(applicant_id):
    """Link an application to a student profile that was created by hand
    (admitted in real life without using Admit), then copy over the details."""
    from models import Student
    a = db.get_or_404(Applicant, applicant_id)
    require_branch_access(a.branch_id)
    st = db.session.get(Student, request.form.get('student_id', type=int) or -1)
    if st is None:
        return _err('Pick the student to link.', url_for('admissions.applicant_detail', applicant_id=a.id))
    require_branch_access(st.branch_id)
    done, err = admissions.link_to_student(a, st)
    if err:
        return _err(err, url_for('admissions.applicant_detail', applicant_id=a.id))
    from utils.audit import log_action
    log_action('admissions.link_student', detail=f'{a.application_no} -> {st.student_id}', target=a)
    msg = f'Linked to {st.full_name} ({st.student_id}).'
    msg += (' Copied: ' + ', '.join(done) + '.') if done else ' Their record already had everything.'
    return _ok(msg, url_for('admissions.applicant_detail', applicant_id=a.id))


def _likely_students(limit=300):
    """{applicant_id: best match} for open applications that look like an
    existing student (strong matches only: name plus DOB or parent phone)."""
    out = {}
    rows = (scope_query(Applicant.query, Applicant)
            .filter(Applicant.admitted_student_id.is_(None), Applicant.status.notin_(['Rejected']))
            .order_by(Applicant.created_at.desc()).limit(limit).all())
    for a in rows:
        m = admissions.match_students(a, limit=1)
        if m and m[0]['score'] >= 6:
            out[a.id] = m[0]
    return out


@adm_bp.route('/applicants/<int:applicant_id>/delete', methods=['POST'])
@login_required
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
        w.writerow([formula_guard(a.application_no), formula_guard(a.full_name), a.gender or '',
                    a.intended_class.name if a.intended_class else '',
                    a.session.name if a.session else '', a.status,
                    a.entrance_score if a.entrance_score is not None else '',
                    formula_guard(a.parent_name or ''), formula_guard(a.parent_phone or ''),
                    a.applied_date or ''])
    return csv_response(out.getvalue(), 'applicants.csv')
