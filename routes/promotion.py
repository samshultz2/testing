"""
Student Promotion Management routes
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from utils.helpers import get_active_session
from models import (
    db, Student, StudentEnrollment, ClassArmAssignment, PromotionRule, PromotionRecord,
    Term, AcademicSession, SchoolClass, StudentScore, ClassSubject, Subject,
    SchoolSettings, ClassArm
)
from utils.helpers import login_required, get_sss3_enrolled_students, safe_redirect
from utils.access_control import (
    admin_required, graduates_access_required, assert_graduate_access,
)
from utils.branch_scope import scope_query, scope_by_student
from utils.db_tx import safe_transaction
from utils.audit import log_action
from utils.security import rate_limited
from datetime import date
import json

promotion_bp = Blueprint('promotion', __name__, url_prefix='/promotion')

_STATUS_BADGE = {'promoted': 'badge-success', 'graduated': 'badge-primary',
                 'repeated': 'badge-warning'}


def _wants_json():
    return request.headers.get('X-Requested-With') == 'fetch' or request.is_json


def _ok(message, redirect_url=None):
    if _wants_json():
        return jsonify({'ok': True, 'message': message, 'redirect': redirect_url})
    flash(message, 'success')
    return redirect(redirect_url or url_for('promotion.index'))


def _err(message, redirect_url=None):
    if _wants_json():
        return jsonify({'ok': False, 'error': message}), 400
    flash(message, 'error')
    return redirect(redirect_url or url_for('promotion.index'))


def _render(payload):
    from utils.spa import render_or_json
    return render_or_json('promotion/app.html', 'promo_json', payload)


def _sessions_json():
    return [{'id': s.id, 'name': s.name} for s in
            AcademicSession.query.order_by(AcademicSession.id.desc()).all()]


# ============================================================================
# GRADUATES
# ============================================================================

@promotion_bp.route('/graduates')
@graduates_access_required
def graduates_list():
    """List all graduated students"""
    from models import GRADUATE_STATUSES, GRADUATE_DOC_TYPES, DocumentRequest
    session_id = request.args.get('session_id', type=int)
    status = (request.args.get('status') or '').strip()

    from utils.branch_scope import scope_query
    query = scope_query(Student.query.filter_by(is_graduated=True), Student)

    if session_id:
        query = query.filter_by(graduation_session_id=session_id)
    if status in GRADUATE_STATUSES:
        # older graduates may have a NULL status but are effectively 'Graduated'
        if status == 'Graduated':
            query = query.filter((Student.graduate_status == 'Graduated')
                                 | (Student.graduate_status.is_(None)))
        else:
            query = query.filter(Student.graduate_status == status)

    graduates = query.order_by(Student.surname, Student.first_name).all()

    return _render({
        'page': 'graduates', 'session_id': session_id or '', 'sessions': _sessions_json(),
        'status': status, 'statuses': GRADUATE_STATUSES,
        'doc_types': [{'type': k, 'label': v} for k, v in GRADUATE_DOC_TYPES.items()],
        'bulk_url': url_for('promotion.bulk_documents'),
        'alumni_url': url_for('promotion.alumni_directory'),
        'doc_templates_url': url_for('promotion.doc_templates'),
        'verifications_url': url_for('promotion.document_verifications'),
        'pending_requests': scope_by_student(
            DocumentRequest.query.filter_by(status='pending'), DocumentRequest).count(),
        'preview_url': url_for('promotion.graduate_sss3_preview'),
        'compare_url': url_for('promotion.graduate_compare'),
        'graduates': [{
            'id': s.id, 'full_name': s.full_name, 'student_id': s.student_id, 'gender': s.gender,
            'status': s.graduate_status or 'Graduated',
            'graduation_date': s.graduation_date.strftime('%d %b %Y') if s.graduation_date else None,
            'graduation_session': s.graduation_session.name if s.graduation_session else None,
            'has_waec': s.waec_results.count() > 0, 'has_jamb': s.jamb_results.count() > 0,
            'profile_url': url_for('promotion.graduate_profile', student_id=s.id),
        } for s in graduates],
    })


@promotion_bp.route('/graduate/<int:student_id>', methods=['POST'])
@admin_required
def mark_graduate(student_id):
    """Mark a single (SSS3) student as graduated."""
    from utils.branch_scope import require_branch_access
    student = db.get_or_404(Student, student_id)
    require_branch_access(student.branch_id)   # don't graduate another branch's student
    active_session = get_active_session()
    try:
        student.is_graduated = True
        student.graduation_date = date.today()
        student.graduate_status = student.graduate_status or 'Graduated'
        if active_session:
            student.graduation_session_id = active_session.id
        db.session.commit()
        log_action('graduate', student.full_name)
        flash(f'{student.full_name} has been marked as a graduate.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return safe_redirect(url_for('main.view_student', student_id=student.id))


@promotion_bp.route('/ungraduate/<int:student_id>', methods=['POST'])
@admin_required
def unmark_graduate(student_id):
    """Reverse a graduation (in case it was marked by mistake)."""
    from utils.branch_scope import require_branch_access
    student = db.get_or_404(Student, student_id)
    require_branch_access(student.branch_id)   # don't alter another branch's student
    try:
        student.is_graduated = False
        student.graduation_date = None
        student.graduation_session_id = None
        db.session.commit()
        log_action('ungraduate', student.full_name)
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('main.view_student', student_id=student.id))
    return _ok(f'{student.full_name} is no longer marked as a graduate.',
               url_for('promotion.graduates_list'))


@promotion_bp.route('/graduates/<int:student_id>/status', methods=['POST'])
@admin_required
def change_graduate_status(student_id):
    """Advance a graduate's lifecycle status. Elevated (admin) only, and every
    change is written to the GraduateAudit trail with old/new value + reason."""
    from utils.branch_scope import require_branch_access
    from models import GraduateAudit, GRADUATE_STATUSES
    from utils.access_control import get_current_user
    student = db.get_or_404(Student, student_id)
    require_branch_access(student.branch_id)
    prof_url = url_for('promotion.graduate_profile', student_id=student.id)
    if not student.is_graduated:
        return _err('This student is not a graduate.', prof_url)
    new_status = (request.form.get('status') or '').strip()
    reason = (request.form.get('reason') or '').strip()
    if new_status not in GRADUATE_STATUSES:
        return _err('Choose a valid graduate status.', prof_url)
    old_status = student.graduate_status or 'Graduated'
    if new_status == old_status:
        return _ok('Status is already set to that.', prof_url)
    me = get_current_user()
    try:
        student.graduate_status = new_status
        db.session.add(GraduateAudit(
            student_id=student.id, field='graduate_status',
            old_value=old_status, new_value=new_status, reason=reason or None,
            actor=(me.username if me else 'admin')))
        db.session.commit()
        log_action('graduate_status', f'{student.full_name}: {old_status} -> {new_status}')
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', prof_url)
    return _ok(f'Status updated to "{new_status}".', prof_url)


@promotion_bp.route('/graduate-sss3/preview')
@admin_required
def graduate_sss3_preview():
    """Review which SSS3 students will be graduated before committing."""
    enrolled = get_sss3_enrolled_students()
    students = [s for s in enrolled if not s.is_graduated]
    already = [s for s in enrolled if s.is_graduated]
    return _render({
        'page': 'graduate_preview', 'already_count': len(already),
        'confirm_url': url_for('promotion.graduate_sss3'),
        'urls': {'graduates': url_for('promotion.graduates_list')},
        'students': [{'student_id': s.student_id, 'full_name': s.full_name, 'gender': s.gender}
                     for s in students],
    })


@promotion_bp.route('/graduate-sss3', methods=['POST'])
@admin_required
def graduate_sss3():
    """Mark every current SSS3 student (active term) as a graduate in one click."""
    active_session = get_active_session()
    students = get_sss3_enrolled_students()
    graduated = 0
    try:
        for student in students:
            if not student.is_graduated:
                student.is_graduated = True
                student.graduation_date = date.today()
                student.graduate_status = student.graduate_status or 'Graduated'
                if active_session:
                    student.graduation_session_id = active_session.id
                graduated += 1
        db.session.commit()
        log_action('graduate_sss3', f'{graduated} students')
        msg = (f'{graduated} SSS3 student(s) marked as graduates.' if graduated
               else 'No new SSS3 students to graduate.')
        return _ok(msg, url_for('promotion.graduates_list'))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('promotion.graduates_list'))


@promotion_bp.route('/graduates/<int:student_id>/document/<doc_type>')
@admin_required
def graduate_document(student_id, doc_type):
    """Issue (or reprint) a graduate document and return the PDF. Records the
    issuance in the GraduateAudit trail and logs the action."""
    from flask import send_file
    from utils.branch_scope import require_branch_access
    from utils.access_control import get_current_user
    from utils.production import secure_external_url
    from utils import graduate_docs
    from models import GraduateAudit, GRADUATE_DOC_TYPES
    student = db.get_or_404(Student, student_id)
    require_branch_access(student.branch_id)
    if not student.is_graduated:
        abort(404)
    if doc_type not in GRADUATE_DOC_TYPES:
        abort(404)
    me = get_current_user()
    doc = graduate_docs.issue(student, doc_type, actor=(me.username if me else 'admin'))
    verify_url = secure_external_url('graduate_verify.verify', code=doc.verification_code)
    buf, fname = graduate_docs.render(student, doc, verify_url)
    db.session.add(GraduateAudit(
        student_id=student.id, field='document',
        old_value=None, new_value=f'{doc_type}:{doc.document_number}',
        reason=('reprint' if doc.reprint_count else 'issued'),
        actor=(me.username if me else 'admin')))
    db.session.commit()
    log_action('graduate_document', f'{student.full_name}: {doc.label} ({doc.document_number})')
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=fname)


@promotion_bp.route('/graduates/<int:student_id>/document/<doc_type>/revoke', methods=['POST'])
@admin_required
def revoke_document(student_id, doc_type):
    """Toggle a document's revoked flag. A revoked document verifies as invalid on
    the public portal. Logged + audited."""
    from utils.branch_scope import require_branch_access
    from utils.access_control import get_current_user
    from models import GraduateDocument, GraduateAudit
    student = db.get_or_404(Student, student_id)
    require_branch_access(student.branch_id)
    prof_url = url_for('promotion.graduate_profile', student_id=student.id)
    doc = GraduateDocument.query.filter_by(student_id=student.id, doc_type=doc_type).first()
    if not doc:
        return _err('That document has not been issued yet.', prof_url)
    was = bool(doc.revoked)
    doc.revoked = not was
    me = get_current_user()
    db.session.add(GraduateAudit(
        student_id=student.id, field='document_revoke',
        old_value=('revoked' if was else 'active'),
        new_value=('revoked' if doc.revoked else 'active'),
        reason=(request.form.get('reason') or '').strip() or None,
        actor=(me.username if me else 'admin')))
    db.session.commit()
    log_action('graduate_document_revoke',
               f'{student.full_name}: {doc.label} -> {"revoked" if doc.revoked else "reinstated"}')
    return _ok(f'{doc.label} {"revoked" if doc.revoked else "reinstated"}.', prof_url)


@promotion_bp.route('/graduates/documents/bulk')
@admin_required
@rate_limited('grad_bulk_docs', max_requests=6, window_minutes=15)
def bulk_documents():
    """Generate one document type for a whole graduating cohort as a ZIP of PDFs.
    Capped per run to keep memory/time bounded."""
    import io, zipfile
    from flask import send_file
    from utils.branch_scope import scope_query
    from utils.access_control import get_current_user
    from utils.production import secure_external_url
    from utils import graduate_docs
    from models import GRADUATE_DOC_TYPES, GRADUATE_STATUSES
    doc_type = (request.args.get('doc_type') or '').strip()
    if doc_type not in GRADUATE_DOC_TYPES:
        abort(404)
    session_id = request.args.get('session_id', type=int)
    status = (request.args.get('status') or '').strip()
    q = scope_query(Student.query.filter_by(is_graduated=True), Student)
    if session_id:
        q = q.filter_by(graduation_session_id=session_id)
    if status in GRADUATE_STATUSES:
        if status == 'Graduated':
            q = q.filter((Student.graduate_status == 'Graduated') | (Student.graduate_status.is_(None)))
        else:
            q = q.filter(Student.graduate_status == status)
    students = q.order_by(Student.surname, Student.first_name).limit(300).all()
    if not students:
        return _err('No graduates match that filter.', url_for('promotion.graduates_list'))
    me = get_current_user()
    actor = me.username if me else 'admin'
    memzip = io.BytesIO()
    with zipfile.ZipFile(memzip, 'w', zipfile.ZIP_DEFLATED) as z:
        for s in students:
            try:
                doc = graduate_docs.issue(s, doc_type, actor=actor)
                verify_url = secure_external_url('graduate_verify.verify', code=doc.verification_code)
                buf, fname = graduate_docs.render(s, doc, verify_url)
                z.writestr(f"{s.surname}_{s.first_name}_{fname}".replace(' ', '_'), buf.getvalue())
            except Exception:
                db.session.rollback()
    memzip.seek(0)
    log_action('graduate_documents_bulk', f'{doc_type} x{len(students)}')
    return send_file(memzip, mimetype='application/zip', as_attachment=True,
                     download_name=f'{doc_type}_documents.zip')


@promotion_bp.route('/graduates/documents/verifications')
@graduates_access_required
def document_verifications():
    """Audit trail of public document-verification attempts: who checked which
    document and the outcome (valid / revoked / unknown code). Branch-scoped —
    an admin sees only checks of documents belonging to graduates in their
    branch. Powers the 'Verification activity' panel."""
    from datetime import timedelta
    from sqlalchemy import func, false as _false
    from models import DocumentVerification, GRADUATE_DOC_TYPES
    # Only verifications tied to a graduate in scope (unknown-code attempts carry
    # no student, so they surface only in the org-wide totals below).
    scoped_ids = [s.id for s in scope_query(
        Student.query.filter_by(is_graduated=True), Student).with_entities(Student.id).all()]
    days = min(max(request.args.get('days', 90, type=int) or 90, 1), 365)
    since = date.today() - timedelta(days=days)
    base = DocumentVerification.query.filter(DocumentVerification.created_at >= since)
    scoped = base.filter(DocumentVerification.student_id.in_(scoped_ids)) if scoped_ids \
        else base.filter(_false())
    # summary tallies (by outcome) over scoped student docs + unknown-code hits
    by_result = dict(db.session.query(DocumentVerification.result, func.count())
                     .filter(DocumentVerification.created_at >= since)
                     .filter((DocumentVerification.student_id.in_(scoped_ids) if scoped_ids
                              else _false()) | (DocumentVerification.result == 'not_found'))
                     .group_by(DocumentVerification.result).all())
    rows = (scoped.order_by(DocumentVerification.created_at.desc()).limit(200).all())
    unknown = (base.filter(DocumentVerification.result == 'not_found')
               .order_by(DocumentVerification.created_at.desc()).limit(50).all())

    def _row(v):
        return {
            'id': v.id, 'code': v.code, 'result': v.result, 'source': v.source or 'manual',
            'doc_label': GRADUATE_DOC_TYPES.get(v.doc_type, v.doc_type or '—'),
            'student': (v.student.full_name if v.student else None),
            'student_url': (url_for('promotion.graduate_profile', student_id=v.student_id)
                            if v.student_id else None),
            'at': v.created_at.strftime('%d %b %Y %H:%M') if v.created_at else '',
        }
    return _render({
        'page': 'doc_verifications',
        'days': days,
        'summary': {'valid': int(by_result.get('valid', 0)),
                    'revoked': int(by_result.get('revoked', 0)),
                    'not_found': int(by_result.get('not_found', 0)),
                    'total': int(sum(by_result.values()))},
        'rows': [_row(v) for v in rows],
        'unknown': [_row(v) for v in unknown],
        'urls': {'graduates': url_for('promotion.graduates_list')},
    })


# ============================================================================
# DOCUMENT DESIGNS (Phase 2 — per-school templates)
# ============================================================================

def _design_doc_labels():
    """Every designed document type (school-selectable collection), sourced from
    the central catalogue so new document types appear automatically."""
    from utils import document_catalog as cat
    return {dt: cat.label(dt) for dt in cat.designed_types()}


_DESIGN_DOC_LABELS = _design_doc_labels()


@promotion_bp.route('/doc-templates')
@graduates_access_required
def doc_templates():
    """Gallery of document designs a school can choose from + set a default."""
    from utils import graduate_docs
    labels = _design_doc_labels()
    doc_type = (request.args.get('doc_type') or 'transcript').strip()
    if doc_type not in labels:
        doc_type = 'transcript'
    current = graduate_docs.design_key_for(doc_type)
    templates = [{
        **t,
        'preview_url': url_for('promotion.doc_template_preview', doc_type=doc_type, key=t['key']),
        'set_url': url_for('promotion.set_doc_template', doc_type=doc_type),
        'is_default': t['key'] == current,
    } for t in graduate_docs.list_designs(doc_type)]
    from utils import document_catalog as cat
    doc_types_grouped = [{
        'category': category,
        'items': [{'key': dt, 'label': lbl,
                   'url': url_for('promotion.doc_templates', doc_type=dt)}
                  for dt, lbl, designed in items if designed],
    } for category, items in cat.by_category()]
    from utils.school import document_branding
    br = document_branding()
    return _render({
        'page': 'doc_templates', 'graduates': url_for('promotion.graduates_list'),
        'doc_type': doc_type, 'doc_type_label': labels[doc_type],
        'doc_types': [{'key': k, 'label': v,
                       'url': url_for('promotion.doc_templates', doc_type=k)}
                      for k, v in labels.items()],
        'doc_types_grouped': [g for g in doc_types_grouped if g['items']],
        'templates': templates, 'current': current,
        'branding': {'primary_color': br.get('primary_color') or '',
                     'accent_color': br.get('accent_color') or '',
                     'secondary_color': br.get('secondary_color') or '',
                     'motto': br.get('motto') or '',
                     'verify_enabled': bool(br.get('verify_enabled', True))},
        'branding_save_url': url_for('promotion.set_doc_branding'),
    })


@promotion_bp.route('/doc-templates/branding', methods=['POST'])
@admin_required
def set_doc_branding():
    """Save per-school document branding (colours, motto, verification). Stored in
    the tenant's SchoolSettings KV, so every design preview updates instantly."""
    from models import SchoolSettings
    data = request.get_json(silent=True) or request.form

    def _hex(v):
        v = (v or '').strip()
        return v if (v.startswith('#') and len(v) in (4, 7)) else ''

    SchoolSettings.set('doc_primary_color', _hex(data.get('primary_color')), 'string',
                       'Academic document primary colour')
    SchoolSettings.set('doc_accent_color', _hex(data.get('accent_color')), 'string',
                       'Academic document accent colour')
    SchoolSettings.set('doc_secondary_color', _hex(data.get('secondary_color')), 'string',
                       'Academic document secondary/gold colour')
    motto = (data.get('motto') or '').strip()
    if motto:
        SchoolSettings.set('school_motto', motto[:160], 'string', 'School motto')
    verify = data.get('verify_enabled')
    verify_on = str(verify).lower() not in ('0', 'false', 'no', 'off', 'none', '')
    SchoolSettings.set('doc_verify_enabled', '1' if verify_on else '0', 'string',
                       'Show QR/verification block on documents')
    db.session.commit()
    log_action('doc_branding', 'updated document branding')
    return _ok('Document branding saved.', url_for('promotion.doc_templates', doc_type='transcript'))


@promotion_bp.route('/doc-templates/<doc_type>/default', methods=['POST'])
@admin_required
def set_doc_template(doc_type):
    from utils import graduate_docs
    from utils.access_control import get_current_user
    from models import DocTemplatePref
    if doc_type not in _DESIGN_DOC_LABELS:
        abort(404)
    data = request.get_json(silent=True) or request.form
    key = (data.get('template_key') or '').strip()
    if not graduate_docs.valid_design(doc_type, key):
        return _err('Unknown template.', url_for('promotion.doc_templates', doc_type=doc_type))
    pref = DocTemplatePref.query.filter_by(doc_type=doc_type).first()
    if pref is None:
        pref = DocTemplatePref(doc_type=doc_type)
        db.session.add(pref)
    pref.template_key = key
    me = get_current_user()
    pref.updated_by = me.username if me else 'admin'
    db.session.commit()
    name = next((t['name'] for t in graduate_docs.list_designs(doc_type) if t['key'] == key), key)
    log_action('doc_template_default', f'{doc_type} -> {key}')
    return _ok(f'“{name}” is now the default {_DESIGN_DOC_LABELS[doc_type]} design.',
               url_for('promotion.doc_templates', doc_type=doc_type))


@promotion_bp.route('/doc-templates/<doc_type>/<key>/preview')
@graduates_access_required
def doc_template_preview(doc_type, key):
    """A sample PDF of a design (dummy data), so admins can compare designs."""
    from flask import send_file
    from utils import graduate_docs
    if doc_type not in _DESIGN_DOC_LABELS or not graduate_docs.valid_design(doc_type, key):
        abort(404)
    buf = graduate_docs.preview_document(doc_type, key)
    return send_file(buf, mimetype='application/pdf', as_attachment=False,
                     download_name=f'{doc_type}_{key}_preview.pdf')


# ============================================================================
# ALUMNI (Phase 3 — admin side)
# ============================================================================

def _alumni_json(prof):
    from models import AlumniProfile
    if prof is None:
        return {f: None for f in AlumniProfile.EDITABLE} | {
            'willing_to_mentor': False, 'updated_at': None, 'updated_by': None}
    return prof.to_dict()


def _alumni_filters(args):
    """The set of advanced-search filters currently applied (echoed back to the
    UI and reused verbatim for export + bulk email)."""
    return {
        'q': (args.get('q') or '').strip(),
        'session_id': args.get('session_id', type=int) or '',
        'occupation': (args.get('occupation') or '').strip(),
        'employer': (args.get('employer') or '').strip(),
        'institution': (args.get('institution') or '').strip(),
        'city': (args.get('city') or '').strip(),
        'country': (args.get('country') or '').strip(),
        'mentor': args.get('mentor') == '1',
        'career': args.get('career') == '1',
        'has_contact': args.get('has_contact') == '1',
    }


def _alumni_rows(f):
    """Return ``[(Student, AlumniProfile|None), …]`` for graduates matching the
    advanced-search filters ``f`` (from :func:`_alumni_filters`), branch-scoped."""
    from models import AlumniProfile
    q = (scope_query(Student.query.filter_by(is_graduated=True), Student)
         .outerjoin(AlumniProfile, AlumniProfile.student_id == Student.id))
    if f['q']:
        like = f"%{f['q']}%"
        q = q.filter(db.or_(Student.first_name.ilike(like), Student.surname.ilike(like),
                            Student.student_id.ilike(like)))
    if f['session_id']:
        q = q.filter(Student.graduation_session_id == f['session_id'])
    for key, col in (('occupation', AlumniProfile.occupation), ('employer', AlumniProfile.employer),
                     ('institution', AlumniProfile.higher_institution),
                     ('city', AlumniProfile.city), ('country', AlumniProfile.country)):
        if f[key]:
            q = q.filter(col.ilike(f"%{f[key]}%"))
    if f['mentor']:
        q = q.filter(AlumniProfile.willing_to_mentor.is_(True))
    if f['career']:
        q = q.filter(db.or_(AlumniProfile.occupation.isnot(None),
                            AlumniProfile.employer.isnot(None),
                            AlumniProfile.higher_institution.isnot(None)))
    if f['has_contact']:
        q = q.filter(db.or_(AlumniProfile.email.isnot(None), AlumniProfile.phone.isnot(None)))
    grads = q.order_by(Student.surname, Student.first_name).all()
    ids = [g.id for g in grads] or [0]
    profiles = {p.student_id: p for p in
                AlumniProfile.query.filter(AlumniProfile.student_id.in_(ids)).all()}
    return [(g, profiles.get(g.id)) for g in grads]


@promotion_bp.route('/alumni')
@graduates_access_required
def alumni_directory():
    """Admin alumni directory: graduates matching the advanced-search filters,
    plus the pending document-request inbox."""
    from models import DocumentRequest
    f = _alumni_filters(request.args)
    rows = [{
        'id': g.id, 'full_name': g.full_name, 'student_id': g.student_id,
        'profile_url': url_for('promotion.graduate_profile', student_id=g.id),
        'occupation': p.occupation if p else None,
        'employer': p.employer if p else None,
        'higher_institution': p.higher_institution if p else None,
        'phone': p.phone if p else None, 'email': p.email if p else None,
        'willing_to_mentor': bool(p.willing_to_mentor) if p else False,
    } for g, p in _alumni_rows(f)]
    from utils.branch_scope import scope_by_student
    pend = (scope_by_student(DocumentRequest.query.filter_by(status='pending'), DocumentRequest)
            .order_by(DocumentRequest.requested_at.asc()).all())
    requests_json = [{
        'id': r.id, 'student_id': r.student_id,
        'student_name': r.student.full_name if r.student else '—',
        'admission_no': r.student.student_id if r.student else '',
        'doc_type': r.doc_type, 'label': r.label,
        'note': r.note, 'requested_at': r.requested_at.strftime('%d %b %Y') if r.requested_at else '',
        'fulfil_url': url_for('promotion.fulfill_request', req_id=r.id),
        'decline_url': url_for('promotion.decline_request', req_id=r.id),
        'profile_url': url_for('promotion.graduate_profile', student_id=r.student_id),
    } for r in pend]
    total = scope_query(Student.query.filter_by(is_graduated=True), Student).count()
    contactable = sum(1 for r in rows if r['email'])
    return _render({
        'page': 'alumni', 'graduates': url_for('promotion.graduates_list'),
        'analytics_url': url_for('promotion.alumni_analytics'),
        'export_url': url_for('promotion.alumni_export'),
        'bulk_email_url': url_for('promotion.alumni_bulk_email'),
        'email_configured': _email_ready(),
        'sessions': _sessions_json(),
        'alumni': rows, 'requests': requests_json, 'filters': f,
        'total': total, 'shown': len(rows),
        'mentors': sum(1 for r in rows if r['willing_to_mentor']),
        'contactable': contactable,
    })


def _email_ready():
    try:
        from utils.mailer import is_configured
        return bool(is_configured())
    except Exception:
        return False


@promotion_bp.route('/alumni/analytics')
@graduates_access_required
def alumni_analytics():
    """Aggregate view of the alumni base: destinations, sectors, mentorship,
    documents and requests."""
    from models import AlumniProfile, GraduateDocument, DocumentRequest, GRADUATE_STATUSES
    from utils.branch_scope import scope_by_student
    grads = scope_query(Student.query.filter_by(is_graduated=True), Student).all()
    ids = [g.id for g in grads] or [0]
    profiles = {p.student_id: p for p in
                AlumniProfile.query.filter(AlumniProfile.student_id.in_(ids)).all()}

    def _top(getter, limit=8):
        from collections import Counter
        c = Counter()
        for g in grads:
            p = profiles.get(g.id)
            val = (getter(p) or '').strip() if p else ''
            if val:
                c[val] += 1
        return [{'label': k, 'count': v} for k, v in c.most_common(limit)]

    # status breakdown (NULL == 'Graduated')
    from collections import Counter
    status_c = Counter((g.graduate_status or 'Graduated') for g in grads)
    by_status = [{'label': s, 'count': status_c.get(s, 0)}
                 for s in GRADUATE_STATUSES if status_c.get(s, 0)]
    # by graduation session
    sess_c = Counter()
    for g in grads:
        sess_c[g.graduation_session.name if g.graduation_session else 'Unspecified'] += 1
    by_session = [{'label': k, 'count': v} for k, v in sorted(sess_c.items(), reverse=True)]

    with_profile = sum(1 for g in grads if profiles.get(g.id))
    mentors = sum(1 for p in profiles.values() if p.willing_to_mentor)
    employed = sum(1 for p in profiles.values() if (p.occupation or p.employer))
    higher_ed = sum(1 for p in profiles.values() if p.higher_institution)
    contactable = sum(1 for p in profiles.values() if (p.email or p.phone))

    docs = scope_by_student(GraduateDocument.query, GraduateDocument).all()
    doc_c = Counter(d.doc_type for d in docs)
    from models import GRADUATE_DOC_TYPES
    docs_by_type = [{'label': GRADUATE_DOC_TYPES.get(k, k), 'count': v}
                    for k, v in doc_c.most_common()]
    req_c = Counter(r.status for r in
                    scope_by_student(DocumentRequest.query, DocumentRequest).all())

    total = len(grads)
    return _render({
        'page': 'alumni_analytics',
        'alumni_dir': url_for('promotion.alumni_directory'),
        'total': total, 'with_profile': with_profile, 'mentors': mentors,
        'employed': employed, 'higher_ed': higher_ed, 'contactable': contactable,
        'by_status': by_status, 'by_session': by_session,
        'top_employers': _top(lambda p: p.employer),
        'top_institutions': _top(lambda p: p.higher_institution),
        'top_occupations': _top(lambda p: p.occupation),
        'top_locations': _top(lambda p: (p.city or '') + ((', ' + p.country) if p.country else '') if (p.city or p.country) else ''),
        'docs_by_type': docs_by_type, 'docs_total': len(docs),
        'requests': {'pending': req_c.get('pending', 0), 'fulfilled': req_c.get('fulfilled', 0),
                     'declined': req_c.get('declined', 0)},
    })


@promotion_bp.route('/alumni/export')
@graduates_access_required
def alumni_export():
    """CSV export of the filtered alumni set."""
    import csv, io
    f = _alumni_filters(request.args)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Admission No', 'Name', 'Graduation Session', 'Status', 'Occupation',
                'Job Title', 'Employer', 'Higher Institution', 'Course', 'Phone', 'Email',
                'LinkedIn', 'City', 'Country', 'Willing to Mentor'])
    rows = _alumni_rows(f)
    for g, p in rows:
        w.writerow([
            g.student_id or '', g.full_name,
            g.graduation_session.name if g.graduation_session else '',
            g.graduate_status or 'Graduated',
            (p.occupation if p else '') or '', (p.job_title if p else '') or '',
            (p.employer if p else '') or '', (p.higher_institution if p else '') or '',
            (p.course_of_study if p else '') or '', (p.phone if p else '') or '',
            (p.email if p else '') or '', (p.linkedin_url if p else '') or '',
            (p.city if p else '') or '', (p.country if p else '') or '',
            'Yes' if (p and p.willing_to_mentor) else 'No',
        ])
    from flask import Response
    log_action('alumni_export', f'{len(rows)} rows')
    return Response(buf.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=alumni.csv'})


@promotion_bp.route('/alumni/bulk-email', methods=['POST'])
@admin_required
@rate_limited('alumni_bulk_email', max_requests=10, window_minutes=60)
def alumni_bulk_email():
    """Email every alumnus in the filtered set who has an email address. Sent
    individually (no shared To: header) in the background."""
    from utils.mailer import is_configured, send_email, branded_html
    if not is_configured():
        return _err('Email is not configured on this server.', url_for('promotion.alumni_directory'))
    data = request.get_json(silent=True) or request.form
    subject = (data.get('subject') or '').strip()
    body = (data.get('body') or '').strip()
    if not subject or not body:
        return _err('A subject and message are both required.', url_for('promotion.alumni_directory'))
    f = _alumni_filters(data)
    emails = []
    for g, p in _alumni_rows(f):
        if p and p.email:
            emails.append(p.email.strip())
    emails = sorted(set(e for e in emails if e))
    if not emails:
        return _err('No alumni in the current filter have an email address.',
                    url_for('promotion.alumni_directory'))
    html = branded_html(subject, [ln for ln in body.split('\n') if ln.strip()])

    def _blast(app, recipients, subject, body, html):
        with app.app_context():
            for addr in recipients:
                try:
                    send_email(addr, subject, body, html=html)
                except Exception:
                    pass
    import threading
    from flask import current_app
    threading.Thread(target=_blast,
                     args=(current_app._get_current_object(), emails, subject, body, html),
                     daemon=True, name='alumni-blast').start()
    log_action('alumni_bulk_email', f'{len(emails)} recipients: {subject[:60]}')
    return _ok(f'Sending to {len(emails)} alumnus/alumni in the background.',
               url_for('promotion.alumni_directory'))


@promotion_bp.route('/graduates/<int:student_id>/alumni', methods=['POST'])
@admin_required
def save_alumni_profile(student_id):
    """Admin edit of a graduate's alumni profile."""
    from utils.branch_scope import require_branch_access
    from utils.access_control import get_current_user
    from models import AlumniProfile
    student = db.get_or_404(Student, student_id)
    require_branch_access(student.branch_id)
    prof = AlumniProfile.query.filter_by(student_id=student.id).first()
    if prof is None:
        prof = AlumniProfile(student_id=student.id)
        db.session.add(prof)
    data = request.get_json(silent=True) or request.form
    for f in AlumniProfile.EDITABLE:
        setattr(prof, f, (data.get(f) or '').strip() or None)
    prof.willing_to_mentor = bool(data.get('willing_to_mentor'))
    me = get_current_user()
    prof.updated_by = (me.username if me else 'admin')
    db.session.commit()
    log_action('alumni_profile_update', student.full_name)
    return _ok('Alumni details saved.',
               url_for('promotion.graduate_profile', student_id=student.id))


@promotion_bp.route('/graduates/<int:student_id>/portal-password', methods=['POST'])
@admin_required
def set_alumni_password(student_id):
    """Set/reset the graduate's portal password so they can sign in to the
    alumni portal (they can also use a document verification code)."""
    from utils.branch_scope import require_branch_access
    student = db.get_or_404(Student, student_id)
    require_branch_access(student.branch_id)
    prof_url = url_for('promotion.graduate_profile', student_id=student.id)
    data = request.get_json(silent=True) or request.form
    pw = (data.get('password') or '').strip()
    if len(pw) < 6:
        return _err('Password must be at least 6 characters.', prof_url)
    student.set_portal_password(pw)
    db.session.commit()
    log_action('alumni_portal_password', student.full_name)
    return _ok('Portal password set. The graduate can now sign in to the alumni portal.', prof_url)


@promotion_bp.route('/alumni/requests/<int:req_id>/fulfil')
@admin_required
def fulfill_request(req_id):
    """Fulfil a document request: issue the document and return the PDF."""
    from flask import send_file
    from utils.branch_scope import require_branch_access
    from utils.access_control import get_current_user
    from utils.production import secure_external_url
    from utils import graduate_docs
    from models import DocumentRequest, GraduateAudit
    from datetime import datetime
    req = db.get_or_404(DocumentRequest, req_id)
    student = db.get_or_404(Student, req.student_id)
    require_branch_access(student.branch_id)
    me = get_current_user()
    actor = me.username if me else 'admin'
    doc = graduate_docs.issue(student, req.doc_type, actor=actor)
    verify_url = secure_external_url('graduate_verify.verify', code=doc.verification_code)
    buf, fname = graduate_docs.render(student, doc, verify_url)
    req.status = 'fulfilled'
    req.handled_at = datetime.now()
    req.handled_by = actor
    req.response_note = (req.response_note or 'Issued.')
    db.session.add(GraduateAudit(
        student_id=student.id, field='document', old_value=None,
        new_value=f'{req.doc_type}:{doc.document_number}', reason='request fulfilled', actor=actor))
    db.session.commit()
    log_action('alumni_request_fulfil', f'{student.full_name}: {doc.label}')
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=fname)


@promotion_bp.route('/alumni/requests/<int:req_id>/decline', methods=['POST'])
@admin_required
def decline_request(req_id):
    from utils.branch_scope import require_branch_access
    from utils.access_control import get_current_user
    from models import DocumentRequest
    from datetime import datetime
    req = db.get_or_404(DocumentRequest, req_id)
    student = db.get_or_404(Student, req.student_id)
    require_branch_access(student.branch_id)
    me = get_current_user()
    data = request.get_json(silent=True) or request.form
    req.status = 'declined'
    req.handled_at = datetime.now()
    req.handled_by = (me.username if me else 'admin')
    req.response_note = (data.get('response_note') or '').strip()[:500] or 'Declined.'
    db.session.commit()
    log_action('alumni_request_decline', student.full_name)
    return _ok('Request declined.', url_for('promotion.alumni_directory'))


@promotion_bp.route('/graduates/<int:student_id>')
@graduates_access_required
def graduate_profile(student_id):
    """View graduate profile with all external results"""
    from models import WAECResult, JAMBResult

    student = db.get_or_404(Student, student_id)
    assert_graduate_access(student)   # admin / SSS3 form teacher, branch-scoped

    # Get WAEC results
    waec_results = WAECResult.query.filter_by(student_id=student_id).order_by(
        WAECResult.exam_year.desc()
    ).all()
    
    # Group WAEC by exam year
    waec_by_year = {}
    for result in waec_results:
        key = f"{result.exam_year}"
        if key not in waec_by_year:
            waec_by_year[key] = {
                'exam_year': result.exam_year,
                'exam_number': None,      # WAECResult has no exam-number column
                'subjects': []
            }
        waec_by_year[key]['subjects'].append(result)
    
    # Get JAMB results
    jamb_results = JAMBResult.query.filter_by(student_id=student_id).order_by(
        JAMBResult.exam_year.desc()
    ).all()
    
    # Get graduation info
    graduation_session = None
    if student.graduation_session_id:
        graduation_session = db.session.get(AcademicSession, student.graduation_session_id)
    
    from models import (GraduateAudit, GRADUATE_STATUSES, GRADUATE_DOC_TYPES,
                        GraduateDocument, AlumniProfile, DocumentRequest, DocumentVerification)
    from utils.graduate_record import build_record
    from utils.production import secure_external_url
    history = (GraduateAudit.query
               .filter_by(student_id=student.id, field='graduate_status')
               .order_by(GraduateAudit.created_at.desc()).limit(50).all())
    issued = {d.doc_type: d for d in GraduateDocument.query.filter_by(student_id=student.id).all()}
    # How many times each issued document has been publicly verified.
    from sqlalchemy import func
    vcounts = dict(db.session.query(DocumentVerification.document_id, func.count())
                   .filter(DocumentVerification.student_id == student.id,
                           DocumentVerification.result == 'valid')
                   .group_by(DocumentVerification.document_id).all())
    documents = []
    for dt, dlabel in GRADUATE_DOC_TYPES.items():
        d = issued.get(dt)
        documents.append({
            'type': dt, 'label': dlabel,
            'download_url': url_for('promotion.graduate_document', student_id=student.id, doc_type=dt),
            'revoke_url': url_for('promotion.revoke_document', student_id=student.id, doc_type=dt),
            'number': d.document_number if d else None,
            'reprint_count': d.reprint_count if d else 0,
            'revoked': bool(d.revoked) if d else False,
            'verify_count': int(vcounts.get(d.id, 0)) if d else 0,
            'verify_url': secure_external_url('graduate_verify.verify', code=d.verification_code) if d else None,
        })
    alumni_prof = AlumniProfile.query.filter_by(student_id=student.id).first()
    doc_requests = (DocumentRequest.query.filter_by(student_id=student.id)
                    .order_by(DocumentRequest.requested_at.desc()).limit(30).all())
    return _render({
        'page': 'graduate_profile',
        'alumni': _alumni_json(alumni_prof),
        'alumni_fields': list(AlumniProfile.EDITABLE),
        'alumni_save_url': url_for('promotion.save_alumni_profile', student_id=student.id),
        'set_password_url': url_for('promotion.set_alumni_password', student_id=student.id),
        'alumni_login_url': secure_external_url('alumni.login'),
        'doc_requests': [{
            'id': r.id, 'label': r.label, 'status': r.status, 'note': r.note,
            'response_note': r.response_note,
            'requested_at': r.requested_at.strftime('%d %b %Y') if r.requested_at else '',
            'fulfil_url': url_for('promotion.fulfill_request', req_id=r.id),
            'decline_url': url_for('promotion.decline_request', req_id=r.id),
        } for r in doc_requests],
        'student': {'id': student.id, 'full_name': student.full_name,
                    'student_id': student.student_id, 'gender': student.gender},
        'record': build_record(student),
        'documents': documents,
        'status': student.graduate_status or 'Graduated',
        'statuses': GRADUATE_STATUSES,
        'status_history': [{'old': h.old_value, 'new': h.new_value, 'reason': h.reason,
                            'actor': h.actor,
                            'at': h.created_at.strftime('%d %b %Y %H:%M') if h.created_at else ''}
                           for h in history],
        'graduation_session': graduation_session.name if graduation_session else None,
        'graduation_date': student.graduation_date.strftime('%d %B %Y') if student.graduation_date else None,
        'waec_by_year': [{'exam_year': v['exam_year'], 'exam_number': v['exam_number'],
                          'subjects': [{'subject': r.subject, 'grade': r.grade} for r in v['subjects']]}
                         for v in waec_by_year.values()],
        'jamb_results': [{'exam_year': j.exam_year, 'total_score': j.total_score,
                          'registration_number': student.jamb_reg_number,
                          'subjects': [{'name': j.subject1, 'score': j.subject1_score},
                                       {'name': j.subject2, 'score': j.subject2_score},
                                       {'name': j.subject3, 'score': j.subject3_score},
                                       {'name': j.subject4, 'score': j.subject4_score}]} for j in jamb_results],
        'contacts': [{'name': c.name or c.relationship, 'relationship': c.relationship,
                      'phone': c.phone_number} for c in student.parent_contacts],
        'urls': {'graduates': url_for('promotion.graduates_list'),
                 'full_profile': url_for('main.view_student', student_id=student.id),
                 'ungraduate': url_for('promotion.unmark_graduate', student_id=student.id),
                 'change_status': url_for('promotion.change_graduate_status', student_id=student.id),
                 'add_waec': url_for('results.add_waec') + f'?student_id={student.id}',
                 'add_jamb': url_for('results.add_jamb') + f'?student_id={student.id}'},
    })


@promotion_bp.route('/graduates/compare')
@graduates_access_required
def graduate_compare():
    """Compare a graduate cohort's mock & real WAEC/JAMB with the current SSS3
    class — credit patterns, pass rates, grade spreads and a data-grounded
    projection of where the current class is tracking. Restricted to branch /
    central admins and SSS3 form teachers, branch-scoped throughout."""
    from models.graduate_compare import compare_cohorts
    from utils.branch_scope import scope_query

    session_id = request.args.get('session_id', type=int)

    grad_q = scope_query(Student.query.filter_by(is_active=True, is_graduated=True), Student)
    if session_id:
        grad_q = grad_q.filter_by(graduation_session_id=session_id)
    grad_ids = [s.id for s in grad_q.all()]

    # Current SSS3 (already branch/section/term scoped, graduates excluded).
    sss3 = [s for s in get_sss3_enrolled_students() if not s.is_graduated]
    sss3_ids = [s.id for s in sss3]

    data = compare_cohorts(grad_ids, sss3_ids)

    return _render({
        'page': 'graduate_compare', 'session_id': session_id or '',
        'sessions': _sessions_json(),
        'urls': {'graduates': url_for('promotion.graduates_list'),
                 'self': url_for('promotion.graduate_compare')},
        'comparison': data,
    })


@promotion_bp.route('/')
@login_required
def index():
    """Promotion dashboard"""
    # Get sessions
    sessions = AcademicSession.query.order_by(AcademicSession.id.desc()).all()
    active_session = get_active_session()
    
    # Get promotion rules count
    rules_count = PromotionRule.query.filter_by(is_active=True).count()
    
    # Get recent promotions (branch-scoped)
    recent_promotions = scope_by_student(PromotionRecord.query, PromotionRecord).order_by(
        PromotionRecord.created_at.desc()
    ).limit(10).all()
    
    return _render({
        'page': 'index', 'rules_count': rules_count,
        'active_session': active_session.name if active_session else None,
        'recent': [{'name': p.student.full_name, 'status': p.status,
                    'status_badge': _STATUS_BADGE.get(p.status, 'badge-secondary'),
                    'from_class': p.from_class.name if p.from_class else '-',
                    'to_class': p.to_class.name if p.to_class else '-', 'stream': p.stream}
                   for p in recent_promotions],
        'urls': {'rules': url_for('promotion.rules_list'), 'process': url_for('promotion.process_promotion'),
                 'graduates': url_for('promotion.graduates_list'), 'history': url_for('promotion.promotion_history')},
    })


# ============================================================================
# PROMOTION RULES
# ============================================================================

@promotion_bp.route('/rules')
@login_required
def rules_list():
    """List promotion rules"""
    rules = PromotionRule.query.filter_by(is_active=True).order_by(
        PromotionRule.from_class_id, PromotionRule.priority.desc()
    ).all()
    
    return _render({
        'page': 'rules', 'add_url': url_for('promotion.add_rule'),
        'rules': [{'id': r.id, 'from_class': r.from_class.name, 'to_class': r.to_class.name,
                   'stream_name': r.stream_name, 'min_average': r.min_average, 'priority': r.priority,
                   'required_count': len(r.get_required_subjects()) if r.required_subjects else 0,
                   'delete_url': url_for('promotion.delete_rule', rule_id=r.id)} for r in rules],
    })


@promotion_bp.route('/rules/add', methods=['GET', 'POST'])
@login_required
def add_rule():
    """Add promotion rule"""
    if request.method == 'POST':
        try:
            from_class_id = request.form.get('from_class_id', type=int)
            to_class_id = request.form.get('to_class_id', type=int)
            stream_name = request.form.get('stream_name', '').strip() or None
            min_average = request.form.get('min_average', type=float) or 50.0
            priority = request.form.get('priority', type=int) or 0
            required_subject_ids = request.form.getlist('required_subjects[]')
            
            rule = PromotionRule(
                from_class_id=from_class_id,
                to_class_id=to_class_id,
                stream_name=stream_name,
                min_average=min_average,
                priority=priority,
                required_subjects=json.dumps([int(s) for s in required_subject_ids]) if required_subject_ids else None
            )
            db.session.add(rule)
            db.session.commit()
            return _ok('Promotion rule added!', url_for('promotion.rules_list'))
        except Exception as e:
            db.session.rollback()
            return _err(f'Error: {str(e)}', url_for('promotion.add_rule'))

    classes = SchoolClass.query.order_by(SchoolClass.level).all()
    subjects = Subject.query.filter_by(is_active=True).order_by(Subject.name).all()
    return _render({
        'page': 'add_rule', 'submit_url': url_for('promotion.add_rule'),
        'urls': {'rules': url_for('promotion.rules_list')},
        'classes': [{'id': c.id, 'name': c.name} for c in classes],
        'subjects': [{'id': s.id, 'name': s.name} for s in subjects],
    })


@promotion_bp.route('/rules/<int:rule_id>/delete', methods=['POST'])
@login_required
def delete_rule(rule_id):
    """Delete promotion rule"""
    rule = db.get_or_404(PromotionRule, rule_id)
    rule.is_active = False
    db.session.commit()
    return _ok('Rule deleted!', url_for('promotion.rules_list'))


# ============================================================================
# PROMOTION PROCESSING
# ============================================================================

@promotion_bp.route('/process')
@login_required
def process_promotion():
    """Process promotions for a session"""
    from_session_id = request.args.get('from_session_id', type=int)
    to_session_id = request.args.get('to_session_id', type=int)
    class_id = request.args.get('class_id', type=int)
    
    sessions = AcademicSession.query.order_by(AcademicSession.id.desc()).all()
    classes = SchoolClass.query.order_by(SchoolClass.level).all()
    
    students_data = []
    from_session = None
    to_session = None
    selected_class = None
    promotion_threshold = SchoolSettings.get('promotion_threshold', 50)
    
    if from_session_id and class_id:
        from_session = db.session.get(AcademicSession, from_session_id)
        to_session = db.session.get(AcademicSession, to_session_id) if to_session_id else None
        selected_class = db.session.get(SchoolClass, class_id)
        
        # Get third term for the session
        third_term = Term.query.filter_by(
            session_id=from_session_id,
            term_number=3
        ).first()
        
        if third_term:
            # Get all class arm assignments for this class in the term (scoped)
            assignments = scope_query(ClassArmAssignment.query.filter_by(
                term_id=third_term.id,
                class_id=class_id
            ), ClassArmAssignment).all()
            
            for assignment in assignments:
                # Get enrolled students
                enrollments = StudentEnrollment.query.filter_by(
                    class_arm_assignment_id=assignment.id,
                    is_active=True
                ).all()
                
                for enrollment in enrollments:
                    student = enrollment.student
                    
                    # Calculate average score
                    avg_score = calculate_student_average(student.id, third_term.id, assignment)
                    
                    # Check existing promotion record
                    existing_promotion = PromotionRecord.query.filter_by(
                        student_id=student.id,
                        from_session_id=from_session_id
                    ).first()
                    
                    # Determine recommended action
                    recommendation = get_promotion_recommendation(
                        student.id, class_id, avg_score, promotion_threshold
                    )
                    
                    students_data.append({
                        'student': student,
                        'enrollment': enrollment,
                        'assignment': assignment,
                        'average': avg_score,
                        'recommendation': recommendation,
                        'existing_promotion': existing_promotion
                    })
            
            # Sort by average descending
            students_data.sort(key=lambda x: x['average'] or 0, reverse=True)
    
    classes_json = [{'id': c.id, 'name': c.name} for c in classes]
    # Streams (class arms) available per class, so the UI can prefill a dropdown
    # for the chosen destination class. Falls back to the global stream list.
    from utils.helpers import STREAMS
    from collections import defaultdict
    arm_pairs = (db.session.query(ClassArmAssignment.class_id, ClassArm.name)
                 .join(ClassArm, ClassArmAssignment.arm_id == ClassArm.id)
                 .filter(ClassArm.is_active.is_(True),
                         ClassArm.is_default.is_(False)).distinct().all())   # hide the default arm
    class_streams = defaultdict(list)
    for cid, arm_name in arm_pairs:
        if arm_name and arm_name not in class_streams[cid]:
            class_streams[cid].append(arm_name)
    class_streams_json = {str(cid): sorted(names) for cid, names in class_streams.items()}
    return _render({
        'page': 'process', 'sessions': _sessions_json(), 'classes': classes_json,
        'class_streams': class_streams_json, 'streams': list(STREAMS),
        'from_session_id': from_session_id or '', 'to_session_id': to_session_id or '',
        'class_id': class_id or '', 'threshold': promotion_threshold,
        'selected_class_name': selected_class.name if selected_class else '',
        'execute_url': url_for('promotion.execute_promotion'),
        'urls': {'self': url_for('promotion.process_promotion')},
        'students': [{
            'id': it['student'].id, 'name': it['student'].full_name,
            'assignment': it['assignment'].display_name, 'average': it['average'],
            'over_threshold': bool(it['average'] and it['average'] >= promotion_threshold),
            'recommendation': {'message': it['recommendation'].get('message', ''),
                               'status': it['recommendation'].get('status'),
                               'to_class': it['recommendation'].get('to_class'),
                               'stream': it['recommendation'].get('stream')},
            'existing_status': it['existing_promotion'].status if it['existing_promotion'] else None,
        } for it in students_data],
    })


@promotion_bp.route('/execute', methods=['POST'])
@login_required
def execute_promotion():
    """Execute promotions"""
    try:
        from datetime import date
        
        from_session_id = request.form.get('from_session_id', type=int)
        to_session_id = request.form.get('to_session_id', type=int)
        
        student_ids = request.form.getlist('student_id[]')
        actions = request.form.getlist('action[]')
        to_class_ids = request.form.getlist('to_class_id[]')
        streams = request.form.getlist('stream[]')
        averages = request.form.getlist('average[]')
        
        promoted = 0
        repeated = 0
        graduated = 0
        
        for i, student_id in enumerate(student_ids):
            action = actions[i] if i < len(actions) else 'skip'
            
            if action == 'skip':
                continue
            
            student = db.session.get(Student, int(student_id))
            if not student:
                continue
            # Never promote/graduate a student outside the user's branch, even if
            # a crafted student_id[] is posted (the single-student routes already
            # guard; the bulk path must match).
            from utils.branch_scope import can_access_branch
            if not can_access_branch(student.branch_id):
                continue

            # Get current class
            current_enrollment = StudentEnrollment.query.join(ClassArmAssignment).join(Term).filter(
                StudentEnrollment.student_id == int(student_id),
                Term.session_id == from_session_id,
                StudentEnrollment.is_active == True
            ).first()
            
            if not current_enrollment:
                continue
            
            from_class_id = current_enrollment.class_arm_assignment.class_id
            to_class_id = int(to_class_ids[i]) if i < len(to_class_ids) and to_class_ids[i] else from_class_id
            stream = streams[i] if i < len(streams) else None
            avg = float(averages[i]) if i < len(averages) and averages[i] else None
            
            # Check for existing record
            existing = PromotionRecord.query.filter_by(
                student_id=int(student_id),
                from_session_id=from_session_id
            ).first()
            
            if existing:
                # Update existing
                existing.to_session_id = to_session_id
                existing.to_class_id = to_class_id
                existing.stream = stream or None
                existing.average_score = avg
                existing.status = action
                existing.is_manual = True
            else:
                # Create new record
                record = PromotionRecord(
                    student_id=int(student_id),
                    from_session_id=from_session_id,
                    to_session_id=to_session_id,
                    from_class_id=from_class_id,
                    to_class_id=to_class_id,
                    stream=stream or None,
                    average_score=avg,
                    status=action,
                    is_manual=True,
                    promoted_by='Admin'
                )
                db.session.add(record)
            
            # Handle graduation - update student record
            if action == 'graduated':
                student.is_graduated = True
                student.graduation_date = date.today()
                student.graduation_session_id = from_session_id
                graduated += 1
            elif action == 'promoted':
                promoted += 1
            elif action == 'repeated':
                repeated += 1
        
        db.session.commit()
        
        msg_parts = []
        if promoted:
            msg_parts.append(f'{promoted} promoted')
        if repeated:
            msg_parts.append(f'{repeated} repeated')
        if graduated:
            msg_parts.append(f'{graduated} graduated')
        
        dest = url_for('promotion.process_promotion',
                       from_session_id=from_session_id, to_session_id=to_session_id)
        return _ok(f'Processed: {", ".join(msg_parts)}', dest)
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('promotion.process_promotion',
                    from_session_id=from_session_id, to_session_id=to_session_id))


@promotion_bp.route('/enroll-promoted', methods=['POST'])
@login_required
def enroll_promoted():
    """Enroll promoted students in new session"""
    try:
        to_session_id = request.form.get('to_session_id', type=int)
        from_session_id = request.form.get('from_session_id', type=int)
        
        if not to_session_id:
            flash('Select destination session.', 'error')
            return redirect(url_for('promotion.index'))
        
        to_session = db.session.get(AcademicSession, to_session_id)
        
        # Get first term of new session
        first_term = Term.query.filter_by(
            session_id=to_session_id,
            term_number=1
        ).first()
        
        if not first_term:
            flash('First term not found for new session. Please create terms first.', 'error')
            return redirect(url_for('promotion.index'))
        
        # Get promoted students (branch-scoped)
        promotions = scope_by_student(PromotionRecord.query, PromotionRecord).filter_by(
            from_session_id=from_session_id,
            to_session_id=to_session_id,
            status='promoted'
        ).all()
        
        enrolled = 0
        for promo in promotions:
            # Find or create class arm assignment
            # Try to keep same arm as before
            old_enrollment = StudentEnrollment.query.join(ClassArmAssignment).join(Term).filter(
                StudentEnrollment.student_id == promo.student_id,
                Term.session_id == from_session_id
            ).first()
            
            arm_id = old_enrollment.class_arm_assignment.arm_id if old_enrollment else None

            assignment = None
            # Prefer the explicitly chosen stream (arm) for the destination class.
            if promo.stream:
                assignment = (ClassArmAssignment.query.join(ClassArm)
                              .filter(ClassArmAssignment.term_id == first_term.id,
                                      ClassArmAssignment.class_id == promo.to_class_id,
                                      ClassArm.name == promo.stream).first())
            # Otherwise keep the same arm as before.
            if not assignment and arm_id is not None:
                assignment = ClassArmAssignment.query.filter_by(
                    term_id=first_term.id,
                    class_id=promo.to_class_id,
                    arm_id=arm_id
                ).first()
            if not assignment:
                # Try any arm
                assignment = ClassArmAssignment.query.filter_by(
                    term_id=first_term.id,
                    class_id=promo.to_class_id
                ).first()
            
            if assignment:
                # Check not already enrolled
                existing = StudentEnrollment.query.filter_by(
                    student_id=promo.student_id,
                    class_arm_assignment_id=assignment.id
                ).first()
                
                if not existing:
                    enrollment = StudentEnrollment(
                        student_id=promo.student_id,
                        class_arm_assignment_id=assignment.id
                    )
                    db.session.add(enrollment)
                    enrolled += 1
        
        db.session.commit()
        flash(f'{enrolled} students enrolled in new session!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('promotion.index'))


@promotion_bp.route('/history')
@login_required
def promotion_history():
    """View promotion history"""
    session_id = request.args.get('session_id', type=int)
    
    sessions = AcademicSession.query.order_by(AcademicSession.id.desc()).all()
    
    records = []
    if session_id:
        records = scope_by_student(PromotionRecord.query.filter_by(
            from_session_id=session_id
        ), PromotionRecord).join(Student).order_by(Student.surname).all()
    
    return _render({
        'page': 'history', 'session_id': session_id or '', 'sessions': _sessions_json(),
        'records': [{'name': r.student.full_name, 'status': r.status,
                     'status_badge': _STATUS_BADGE.get(r.status, 'badge-secondary'),
                     'from_class': r.from_class.name if r.from_class else '-',
                     'to_class': r.to_class.name if r.to_class else '-', 'stream': r.stream,
                     'average': r.average_score, 'is_manual': bool(r.is_manual)} for r in records],
    })


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def calculate_student_average(student_id, term_id, assignment):
    """Calculate student's average score for a term"""
    # Get class subjects
    class_subjects = ClassSubject.query.filter_by(
        term_id=term_id,
        class_id=assignment.class_id,
        is_active=True
    ).filter(
        (ClassSubject.arm_id == None) | (ClassSubject.arm_id == assignment.arm_id)
    ).all()
    
    if not class_subjects:
        return None
    
    total_score = 0
    subjects_with_scores = 0
    
    for cs in class_subjects:
        # Sum all scores for this subject
        scores = StudentScore.query.filter_by(
            student_id=student_id,
            class_subject_id=cs.id
        ).all()
        
        subject_total = sum(s.score for s in scores)
        if subject_total > 0:
            total_score += subject_total
            subjects_with_scores += 1
    
    if subjects_with_scores == 0:
        return None
    
    return round(total_score / subjects_with_scores, 2)


def get_promotion_recommendation(student_id, class_id, average, threshold):
    """Get promotion recommendation based on rules"""
    if average is None:
        return {'status': 'unknown', 'message': 'No scores', 'to_class': None, 'stream': None}
    
    current_class = db.session.get(SchoolClass, class_id)
    
    # Check if graduating (SSS3) - always graduate, no repeating
    if current_class and current_class.level == 6:
        return {'status': 'graduated', 'message': 'Graduate', 'to_class': None, 'stream': None}
    
    # Get promotion rules
    rules = PromotionRule.query.filter_by(
        from_class_id=class_id,
        is_active=True
    ).order_by(PromotionRule.priority.desc()).all()
    
    # Check each rule
    for rule in rules:
        if average >= rule.min_average:
            # Check required subjects if specified
            if rule.required_subjects:
                # For stream-based promotion (like Science/Arts)
                # This would need subject-specific score checking
                pass
            
            return {
                'status': 'promote',
                'message': f'Promote to {rule.to_class.name}' + (f' ({rule.stream_name})' if rule.stream_name else ''),
                'to_class': rule.to_class_id,
                'stream': rule.stream_name
            }
    
    # Default: check basic threshold
    if average >= threshold:
        next_class = SchoolClass.query.filter(SchoolClass.level == current_class.level + 1).first()
        if next_class:
            return {'status': 'promote', 'message': f'Promote to {next_class.name}', 'to_class': next_class.id, 'stream': None}
    
    return {'status': 'repeat', 'message': f'Below threshold ({average:.1f}%)', 'to_class': class_id, 'stream': None}
