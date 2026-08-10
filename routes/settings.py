"""
Settings, Backup, and Configuration routes
"""
from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   Response, send_file, session, jsonify, current_app)
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import shutil
import json
from models import (
    db, SchoolSettings, GradeScale, AssessmentType, TimetableSlot,
    Student, AcademicSession, Term, User
)
from utils.helpers import login_required
from utils.access_control import (admin_required, central_admin_required, is_admin,
                                  can_access_module)
from utils.security import rate_limited
from utils.audit import log_action

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')


@settings_bp.before_request
def _settings_admin_only():
    """The whole settings area — school config, grading scale, assessment
    weights, timetable slots, database backup/restore and user management — is
    an administrative surface. Gate every route (GET pages included) behind
    administrative surface, gated behind the 'settings' module. Admins always
    pass; a non-admin needs the module granted. The most sensitive routes (user
    accounts, branches, database backup/restore) layer a stricter central-admin
    check on top of this, so a delegated settings user still cannot reach them."""
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    if not (is_admin() or can_access_module('settings')):
        flash('You do not have access to that section.', 'error')
        return redirect(url_for('main.dashboard'))
    return None


# --- SPA helpers (no-reload React shell + JSON-aware action responses) -------
from utils.spa import section_responders
_wants_json, _render, _ok, _err = section_responders(
    'settings/app.html', 'settings_json', 'settings.index')


def _settings_dict():
    return {s.key: s.value for s in SchoolSettings.query.all()}


# ============================================================================
# SCHOOL SETTINGS
# ============================================================================

@settings_bp.route('/')
@login_required
def index():
    """Settings main page"""
    from utils.branch_scope import is_central
    return _render({
        'page': 'index',
        'is_central': is_central(),
        'urls': {
            'school': url_for('settings.school_settings'),
            'academic': url_for('settings.academic_settings'),
            'grades': url_for('settings.grades_list'),
            'traits': url_for('settings.traits_list'),
            'assessments': url_for('settings.assessments_list'),
            'timetable_slots': url_for('settings.timetable_slots'),
            'users': url_for('settings.users_list'),
            'branches': url_for('settings.branches'),
            'backup': url_for('settings.backup_page'),
            'audit': url_for('settings.audit_log'),
            'ocr': url_for('settings.ocr_settings'),
            'notifications': url_for('settings.notification_prefs'),
            'performance': url_for('settings.performance'),
            'admissions': url_for('settings.admissions_data'),
        },
    })


@settings_bp.route('/audit')
@central_admin_required
def audit_log():
    """Audit-trail viewer inside the settings app (central-admin only).

    The audit log is append-only evidence of who did what — this surfaces it in
    the React settings section with the same filters as the classic /audit page
    (free-text search, action, user, date range) and page-by-page navigation."""
    from models import AuditLog, Branch
    from datetime import datetime as _dt
    from utils.search import like_term, ilike_contains

    page = request.args.get('page', 1, type=int)
    q = (request.args.get('q') or '').strip()
    action = (request.args.get('action') or '').strip()
    user = (request.args.get('user') or '').strip()
    from_s = (request.args.get('from') or '').strip()
    to_s = (request.args.get('to') or '').strip()

    query = AuditLog.query
    if q:
        like = like_term(q)
        query = query.filter(db.or_(AuditLog.action.ilike(like, escape='\\'),
                                    AuditLog.detail.ilike(like, escape='\\'),
                                    AuditLog.user.ilike(like, escape='\\'),
                                    AuditLog.target_label.ilike(like, escape='\\')))
    if action:
        query = query.filter(AuditLog.action == action)
    if user:
        query = query.filter(ilike_contains(AuditLog.user, user))
    try:
        if from_s:
            query = query.filter(AuditLog.created_at >= _dt.strptime(from_s, '%Y-%m-%d'))
        if to_s:
            d = _dt.strptime(to_s, '%Y-%m-%d')
            query = query.filter(AuditLog.created_at < d.replace(hour=23, minute=59, second=59))
    except ValueError:
        pass

    logs = query.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=50, error_out=False)
    actions = [a[0] for a in db.session.query(AuditLog.action).distinct().order_by(AuditLog.action).all()]
    branch_names = {b.id: b.name for b in Branch.query.all()}

    def _row(l):
        return {
            'id': l.id,
            'created_at': l.created_at.strftime('%d %b %Y, %H:%M') if l.created_at else '',
            'user': l.user or '—',
            'role': l.role or '',
            'action': l.action,
            'target_type': l.target_type or '',
            'target_label': l.target_label or '',
            'branch': branch_names.get(l.branch_id) or '',
            'detail': l.detail or '',
            'ip_address': l.ip_address or '',
            'user_agent': l.user_agent or '',
        }

    return _render({
        'page': 'audit',
        'logs': [_row(l) for l in logs.items],
        'actions': actions,
        'filters': {'q': q, 'action': action, 'user': user, 'from': from_s, 'to': to_s},
        'pagination': {
            'page': logs.page or 1, 'pages': logs.pages or 1, 'total': logs.total or 0,
            'has_prev': logs.has_prev, 'has_next': logs.has_next,
            'prev_page': (logs.page or 1) - 1, 'next_page': (logs.page or 1) + 1,
        },
        'base_url': url_for('settings.audit_log'),
        'back_url': url_for('settings.index'),
    })


@settings_bp.route('/performance', methods=['GET', 'POST'])
@central_admin_required
def performance():
    """Observability: the most-recent slow requests and slow SQL queries this
    worker has seen, plus the active thresholds. Backed by the in-process ring
    buffers in utils.perf_logging (no DB, no shell access to logs needed)."""
    from utils.perf_logging import (recent_slow_requests, recent_slow_queries,
                                     clear_perf_buffers)
    if request.method == 'POST':
        clear_perf_buffers()
        flash('Cleared the captured performance samples.', 'success')
        return redirect(url_for('settings.performance'))
    return render_template(
        'settings/performance.html',
        slow_requests=recent_slow_requests(50),
        slow_queries=recent_slow_queries(50),
        req_ms=current_app.config.get('SLOW_REQUEST_MS', 1500),
        query_ms=current_app.config.get('SLOW_QUERY_MS', 500),
    )


@settings_bp.route('/admissions', methods=['GET', 'POST'])
@central_admin_required
def admissions_data():
    """Manage the university-aspiration reference data: universities (with their
    competitive cut-off bump), courses (department, base competitive JAMB cut-off,
    JAMB/WAEC subject requirements), and a one-click seed of the starter set."""
    from models import University, Course
    if request.method == 'POST':
        action = request.form.get('action')
        try:
            if action == 'seed':
                from utils.university_seed import seed_university_data
                res = seed_university_data()
                flash(f"Seeded {res['universities']} universities, {res['courses']} courses, "
                      f"{res['overrides']} cut-off overrides.", 'success')
            elif action == 'save_university':
                uid = request.form.get('id', type=int)
                u = db.session.get(University, uid) if uid else University()
                u.name = (request.form.get('name') or '').strip()
                u.abbreviation = (request.form.get('abbreviation') or '').strip() or None
                u.state = (request.form.get('state') or '').strip() or None
                u.ownership = (request.form.get('ownership') or '').strip() or None
                u.cutoff_bump = request.form.get('cutoff_bump', type=int) or 0
                u.is_active = request.form.get('is_active') != '0'
                if not u.name:
                    flash('University name is required.', 'error')
                else:
                    if not uid:
                        db.session.add(u)
                    db.session.commit()
                    flash('University saved.', 'success')
            elif action == 'delete_university':
                u = db.session.get(University, request.form.get('id', type=int))
                if u:
                    db.session.delete(u); db.session.commit(); flash('University deleted.', 'success')
            elif action == 'save_course':
                cid = request.form.get('id', type=int)
                c = db.session.get(Course, cid) if cid else Course()
                c.name = (request.form.get('name') or '').strip()
                c.department = (request.form.get('department') or '').strip() or None
                c.base_cutoff = request.form.get('base_cutoff', type=int) or 180
                c.jamb_subjects = (request.form.get('jamb_subjects') or '').strip() or None
                c.waec_subjects = (request.form.get('waec_subjects') or '').strip() or None
                c.is_active = request.form.get('is_active') != '0'
                if not c.name:
                    flash('Course name is required.', 'error')
                else:
                    if not cid:
                        db.session.add(c)
                    db.session.commit()
                    flash('Course saved.', 'success')
            elif action == 'delete_course':
                c = db.session.get(Course, request.form.get('id', type=int))
                if c:
                    db.session.delete(c); db.session.commit(); flash('Course deleted.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Could not save: {e}', 'error')
        return redirect(url_for('settings.admissions_data'))

    universities = University.query.order_by(University.name).all()
    courses = Course.query.order_by(Course.name).all()
    return render_template('settings/admissions.html',
                           universities=universities, courses=courses)


@settings_bp.route('/ocr', methods=['GET', 'POST'])
@login_required
def ocr_settings():
    """Optional Claude-vision OCR for WAEC/JAMB scans — manage the API key, the
    on/off toggle, and the model. The key is stored encrypted at rest (when
    FIELD_ENCRYPTION_KEY is set) and never sent back to the browser in full."""
    if not is_admin():
        return _err('Only an admin can change OCR settings.', url_for('settings.index'))

    if request.method == 'POST':
        try:
            enabled = (request.form.get('enabled') or '').strip().lower() in ('1', 'true', 'on', 'yes')
            model = (request.form.get('model') or 'claude-haiku-4-5').strip()
            SchoolSettings.set('ocr_vision_enabled', enabled, 'bool', 'Use Claude vision for WAEC/JAMB scans')
            SchoolSettings.set('ocr_vision_model', model, 'string', 'Claude model for vision OCR')
            if (request.form.get('clear_key') or '').strip().lower() in ('1', 'true', 'on', 'yes'):
                SchoolSettings.set('ocr_vision_api_key', '', 'string', 'Anthropic API key (encrypted)')
            else:
                new_key = (request.form.get('api_key') or '').strip()
                if new_key:                          # only overwrite when a real key is supplied
                    from utils.crypto import encrypt
                    SchoolSettings.set('ocr_vision_api_key', encrypt(new_key), 'string',
                                       'Anthropic API key (encrypted)')
        except Exception as e:
            return _err(f'Error: {str(e)}', url_for('settings.ocr_settings'))
        return _ok('OCR settings saved.', url_for('settings.ocr_settings'))

    from utils.waec_ocr import _vision_config, vision_available
    cfg = _vision_config()
    return _render({
        'page': 'ocr',
        'enabled': cfg['enabled'],
        'model': cfg['model'],
        'has_key': cfg['has_key'],
        'key_masked': cfg['key_masked'],
        'key_source': cfg['key_source'],          # 'settings' | 'env' | None
        'anthropic_installed': cfg['installed'],
        'active': vision_available(),
        'models': ['claude-haiku-4-5', 'claude-sonnet-4-6', 'claude-opus-4-8'],
        'submit_url': url_for('settings.ocr_settings'),
        'back_url': url_for('settings.index'),
    })


# ---------------------------------------------------------------------------
# Branches (multi-branch support)
# ---------------------------------------------------------------------------

@settings_bp.route('/branches')
@central_admin_required
def branches():
    from models import Branch
    rows = Branch.query.order_by(Branch.is_default.desc(), Branch.name).all()
    return _render({
        'page': 'branches',
        'add_url': url_for('settings.add_branch'),
        'back_url': url_for('settings.index'),
        'branches': [{
            'id': b.id, 'name': b.name, 'code': b.code, 'phone': b.phone,
            'address': b.address, 'is_active': b.is_active, 'is_default': b.is_default,
            'edit_url': url_for('settings.edit_branch', branch_id=b.id),
        } for b in rows],
    })


@settings_bp.route('/branches/add', methods=['POST'])
@central_admin_required
def add_branch():
    from models import db, Branch
    name = (request.form.get('name') or '').strip()
    if not name:
        return _err('Branch name is required.', url_for('settings.branches'))
    if Branch.query.filter_by(name=name).first():
        return _err('A branch with that name already exists.', url_for('settings.branches'))
    first = Branch.query.count() == 0
    db.session.add(Branch(
        name=name,
        code=(request.form.get('code') or '').strip() or None,
        address=(request.form.get('address') or '').strip() or None,
        phone=(request.form.get('phone') or '').strip() or None,
        is_default=first))   # the very first branch is the default
    db.session.commit()
    from utils.audit import log_action
    log_action('branch.create', target_type='branch', target_label=name)
    return _ok(f'Branch "{name}" added.', url_for('settings.branches'))


@settings_bp.route('/branches/<int:branch_id>/edit', methods=['POST'])
@central_admin_required
def edit_branch(branch_id):
    from models import db, Branch
    b = db.get_or_404(Branch, branch_id)
    b.name = (request.form.get('name') or b.name).strip()
    b.code = (request.form.get('code') or '').strip() or None
    b.address = (request.form.get('address') or '').strip() or None
    b.phone = (request.form.get('phone') or '').strip() or None
    b.is_active = request.form.get('is_active') == 'on'
    if request.form.get('make_default') == 'on' and not b.is_default:
        Branch.query.update({Branch.is_default: False})
        b.is_default = True
        b.is_active = True
    db.session.commit()
    from utils.audit import log_action
    log_action('branch.update', target=b)
    return _ok('Branch updated.', url_for('settings.branches'))


@settings_bp.route('/payments', methods=['GET', 'POST'])
@login_required
def payments_settings():
    """This school's OWN Paystack keys, for collecting fees online (parents paying
    tuition/books). Separate from the platform subscription — money goes straight
    to this school's Paystack account. The secret key is stored encrypted."""
    from utils import payments as pay_gw
    from utils import payment_gateways as gw
    from config import Config
    if request.method == 'POST':
        if request.form.get('action') == 'clear':
            pay_gw.clear_keys()
            log_action('payment_keys_cleared', target_type='settings')
            return _ok('Payment keys removed — online fee payment is now off.',
                       url_for('settings.payments_settings'))
        provider = (request.form.get('provider') or 'paystack').strip().lower()
        if provider not in gw.PROVIDERS:
            provider = 'paystack'
        pub = (request.form.get('public_key') or '').strip()
        sec = (request.form.get('secret_key') or '').strip()
        extra = (request.form.get('extra') or '').strip()
        if provider == 'paystack':
            if pub and not pub.startswith('pk_'):
                return _err('Paystack public key should start with "pk_".', url_for('settings.payments_settings'))
            if sec and not sec.startswith('sk_'):
                return _err('Paystack secret key should start with "sk_".', url_for('settings.payments_settings'))
        pay_gw.save_keys(provider, pub, sec, extra or None)
        log_action('payment_keys_updated', detail=provider, target_type='settings')  # never logs the key itself
        msg = ('Payment settings saved — online fee collection is on.'
               if pay_gw.is_configured()
               else 'Saved. Add the remaining credentials to start collecting.')
        return _ok(msg, url_for('settings.payments_settings'))

    base = Config.TENANT_BASE_DOMAIN
    from utils.tenant_runtime import current_tenant
    t = current_tenant()
    host = f'{t.subdomain}.{base}' if (t and base) else request.host
    return render_template('settings/payments.html',
                           provider=pay_gw.active_provider(),
                           providers=[{'id': p, 'name': gw.PROVIDER_LABELS[p]} for p in gw.PROVIDERS],
                           configured=pay_gw.is_configured(),
                           public_key=pay_gw.public_key(),
                           has_extra=bool(pay_gw.provider_keys().get('extra')),
                           webhook_url=f'https://{host}/parent/pay/webhook',
                           back_url=url_for('settings.index'))


@settings_bp.route('/school', methods=['GET', 'POST'])
@login_required
def school_settings():
    """School information settings"""
    if request.method == 'POST':
        try:
            # Update school settings
            SchoolSettings.set('school_name', request.form.get('school_name', ''), 'string', 'Name of the school')
            SchoolSettings.set('school_address', request.form.get('school_address', ''), 'string', 'School address')
            SchoolSettings.set('school_phone', request.form.get('school_phone', ''), 'string', 'School phone number')
            SchoolSettings.set('school_email', request.form.get('school_email', ''), 'string', 'School email')
            SchoolSettings.set('school_motto', request.form.get('school_motto', ''), 'string', 'School motto')
            SchoolSettings.set('next_term_fees', request.form.get('next_term_fees', ''), 'string', 'Next term fees (shown on report cards)')
            SchoolSettings.set('next_term_begins', request.form.get('next_term_begins', ''), 'string', 'Next term resumption date (shown on report cards)')
            tz = (request.form.get('timezone') or '').strip()
            if tz:
                SchoolSettings.set('timezone', tz, 'string', 'Site-wide timezone')
                from utils.timeutil import clear_cache
                clear_cache()
        except Exception as e:
            return _err(f'Error: {str(e)}', url_for('settings.school_settings'))
        return _ok('School settings updated!', url_for('settings.school_settings'))

    from utils.timeutil import all_timezones, get_timezone
    from utils.school import logo_url
    return _render({
        'page': 'school',
        'settings': _settings_dict(),
        'timezones': all_timezones(),
        'current_tz': get_timezone(),
        'logo_url': logo_url(),
        'submit_url': url_for('settings.school_settings'),
        'logo_upload_url': url_for('settings.upload_school_logo'),
        'logo_remove_url': url_for('settings.remove_school_logo'),
        'back_url': url_for('settings.index'),
    })


# --- School logo: one school-wide image, resized once, reused everywhere ------
_LOGO_EXTS = {'.png', '.jpg', '.jpeg', '.webp'}
_LOGO_MAX_H = 240          # px — plenty for letterhead-size printing, small on disk


def _logo_fs_path():
    from utils.school import logo_rel
    return os.path.join(current_app.root_path, 'static', logo_rel())


@settings_bp.route('/school/logo', methods=['POST'])
@login_required
def upload_school_logo():
    """Accept a PNG/JPG/WEBP, flatten + resize it, and store it as the school logo."""
    file = request.files.get('school_logo') or request.files.get('file')
    if not file or not file.filename:
        return _err('Choose an image file to upload.', url_for('settings.school_settings'))
    ext = os.path.splitext(secure_filename(file.filename))[1].lower()
    if ext not in _LOGO_EXTS:
        return _err('Logo must be a PNG, JPG or WEBP image.', url_for('settings.school_settings'))
    try:
        from PIL import Image
        from utils.uploads import open_image
        im = open_image(file)                     # Pillow decode + decompression-bomb cap
        # Flatten any transparency onto white so the logo prints cleanly on paper.
        if im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info):
            im = im.convert('RGBA')
            bg = Image.new('RGBA', im.size, (255, 255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg.convert('RGB')
        else:
            im = im.convert('RGB')
        if im.height > _LOGO_MAX_H:
            w = max(1, int(im.width * (_LOGO_MAX_H / im.height)))
            im = im.resize((w, _LOGO_MAX_H), Image.LANCZOS)
        path = _logo_fs_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        im.save(path, 'PNG')
    except Exception as e:
        return _err(f'Could not process that image: {e}', url_for('settings.school_settings'))
    from utils.school import logo_rel
    url = url_for('static', filename=logo_rel()) + ('?v=%d' % int(os.path.getmtime(path)))
    SchoolSettings.set('school_logo_url', url, 'string', 'Uploaded school logo (shell + printouts)')
    from utils.audit import log_action
    log_action('settings.logo.upload')
    return _ok('School logo updated.', url_for('settings.school_settings'))


@settings_bp.route('/school/logo/remove', methods=['POST'])
@login_required
def remove_school_logo():
    """Remove the uploaded logo; shell and printouts fall back to the app brand."""
    try:
        path = _logo_fs_path()
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
    s = SchoolSettings.query.filter_by(key='school_logo_url').first()
    if s:
        db.session.delete(s)
        db.session.commit()
    from utils.audit import log_action
    log_action('settings.logo.remove')
    return _ok('School logo removed.', url_for('settings.school_settings'))


@settings_bp.route('/academic', methods=['GET', 'POST'])
@login_required
def academic_settings():
    """Academic and timetable settings"""
    if request.method == 'POST':
        try:
            SchoolSettings.set('school_day_start', request.form.get('school_day_start', '08:20'), 'string')
            SchoolSettings.set('school_day_end', request.form.get('school_day_end', '14:10'), 'string')
            SchoolSettings.set('period_duration', request.form.get('period_duration', '40'), 'int')
            SchoolSettings.set('break_duration', request.form.get('break_duration', '30'), 'int')
            SchoolSettings.set('periods_per_day', request.form.get('periods_per_day', '8'), 'int')
            SchoolSettings.set('promotion_threshold', request.form.get('promotion_threshold', '50'), 'float')
            SchoolSettings.set('pass_mark', request.form.get('pass_mark', '50'), 'int')
            uses_arms = (request.form.get('uses_class_arms') or '').strip().lower() in ('1', 'true', 'on', 'yes')
            SchoolSettings.set('uses_class_arms', uses_arms, 'bool', 'School streams classes into arms')
            if not uses_arms:
                from models import ClassArm
                ClassArm.default()                        # provision the hidden default arm
        except Exception as e:
            return _err(f'Error: {str(e)}', url_for('settings.academic_settings'))
        return _ok('Academic settings updated!', url_for('settings.academic_settings'))

    return _render({
        'page': 'academic',
        'settings': _settings_dict(),
        'submit_url': url_for('settings.academic_settings'),
        'back_url': url_for('settings.index'),
    })


# ============================================================================
# GRADE SCALE
# ============================================================================

@settings_bp.route('/grades')
@login_required
def grades_list():
    """List grade scale"""
    grades = GradeScale.query.order_by(GradeScale.order).all()
    return _render({
        'page': 'grades',
        'save_url': url_for('settings.save_grades'),
        'back_url': url_for('settings.index'),
        'grades': [{'grade': g.grade, 'min_score': g.min_score,
                    'max_score': g.max_score, 'remark': g.remark} for g in grades],
    })


@settings_bp.route('/grades/save', methods=['POST'])
@login_required
def save_grades():
    """Save grade scale"""
    try:
        # Get form data
        grades = request.form.getlist('grade[]')
        min_scores = request.form.getlist('min_score[]')
        max_scores = request.form.getlist('max_score[]')
        remarks = request.form.getlist('remark[]')

        # Delete existing grades
        GradeScale.query.delete()

        # Add new grades
        for i, grade in enumerate(grades):
            if grade.strip():
                db.session.add(GradeScale(
                    grade=grade.strip(),
                    min_score=int(min_scores[i]) if min_scores[i] else 0,
                    max_score=int(max_scores[i]) if max_scores[i] else 100,
                    remark=remarks[i].strip() if i < len(remarks) else '',
                    order=i + 1
                ))

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('settings.grades_list'))
    return _ok('Grade scale saved!', url_for('settings.grades_list'))


# ============================================================================
# BEHAVIOURAL TRAITS
# ============================================================================

def _slugify(text):
    import re
    s = re.sub(r'[^a-z0-9]+', '_', (text or '').lower()).strip('_')
    return s or 'trait'


@settings_bp.route('/traits')
@login_required
def traits_list():
    from models import BehaviouralTrait
    traits = BehaviouralTrait.query.order_by(BehaviouralTrait.order, BehaviouralTrait.id).all()
    return _render({
        'page': 'traits',
        'save_url': url_for('settings.save_traits'),
        'back_url': url_for('settings.index'),
        'traits': [{'key': t.key, 'label': t.label, 'is_active': t.is_active} for t in traits],
    })


@settings_bp.route('/traits/save', methods=['POST'])
@login_required
def save_traits():
    from models import BehaviouralTrait
    keys = request.form.getlist('key[]')
    labels = request.form.getlist('label[]')
    active_set = set(request.form.getlist('active[]'))   # values are row indices
    seen = set()
    try:
        for i, label in enumerate(labels):
            label = label.strip()
            if not label:
                continue
            key = (keys[i].strip() if i < len(keys) and keys[i].strip() else _slugify(label))
            # avoid colliding with a different existing trait's key
            base, n = key, 1
            while key in seen:
                n += 1; key = f'{base}_{n}'
            is_active = str(i) in active_set
            trait = BehaviouralTrait.query.filter_by(key=key).first()
            if trait:
                trait.label, trait.order, trait.is_active = label, i, is_active
            else:
                db.session.add(BehaviouralTrait(key=key, label=label, order=i, is_active=is_active))
            seen.add(key)
        # Traits dropped from the form are deactivated (keys kept so ratings survive).
        for t in BehaviouralTrait.query.all():
            if t.key not in seen:
                t.is_active = False
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('settings.traits_list'))
    return _ok('Behavioural traits saved!', url_for('settings.traits_list'))


# ============================================================================
# ASSESSMENT TYPES
# ============================================================================

@settings_bp.route('/assessments')
@login_required
def assessments_list():
    """List assessment types"""
    assessments = AssessmentType.query.filter_by(is_active=True).order_by(AssessmentType.order).all()
    total_max = sum(a.max_score for a in assessments)
    return _render({
        'page': 'assessments',
        'total_max': total_max,
        'save_url': url_for('settings.save_assessments'),
        'back_url': url_for('settings.index'),
        'assessments': [{'name': a.name, 'short_name': a.short_name,
                         'max_score': a.max_score} for a in assessments],
    })


@settings_bp.route('/assessments/save', methods=['POST'])
@login_required
def save_assessments():
    """Save assessment types"""
    try:
        names = request.form.getlist('name[]')
        short_names = request.form.getlist('short_name[]')
        max_scores = request.form.getlist('max_score[]')

        # Deactivate all existing
        AssessmentType.query.update({AssessmentType.is_active: False})

        # Add/update assessment types
        for i, name in enumerate(names):
            if name.strip():
                # Check if exists
                existing = AssessmentType.query.filter_by(name=name.strip()).first()
                if existing:
                    existing.short_name = short_names[i].strip() if i < len(short_names) else ''
                    existing.max_score = int(max_scores[i]) if i < len(max_scores) and max_scores[i] else 10
                    existing.order = i + 1
                    existing.is_active = True
                else:
                    db.session.add(AssessmentType(
                        name=name.strip(),
                        short_name=short_names[i].strip() if i < len(short_names) else '',
                        max_score=int(max_scores[i]) if i < len(max_scores) and max_scores[i] else 10,
                        order=i + 1,
                        is_active=True
                    ))

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('settings.assessments_list'))
    return _ok('Assessment types saved!', url_for('settings.assessments_list'))


# ============================================================================
# PER-TERM ASSESSMENT SETTINGS
# ============================================================================
@settings_bp.route('/assessments/terms')
@login_required
@admin_required
def term_assessments():
    """List terms and whether each has its own (peculiar) assessment settings."""
    from utils.assessments import term_maxes
    terms = Term.query.order_by(Term.id.desc()).all()
    rows = [{'term': t, 'custom': bool(term_maxes(t.id))} for t in terms]
    return render_template('settings/term_assessments.html', rows=rows)


@settings_bp.route('/assessments/terms/<int:term_id>')
@login_required
@admin_required
def term_assessment_edit(term_id):
    from utils.assessments import term_maxes
    term = db.get_or_404(Term, term_id)
    types = AssessmentType.query.filter_by(is_active=True).order_by(AssessmentType.order).all()
    tset = term_maxes(term_id)
    custom = bool(tset)
    items = [{'at': at, 'max': tset.get(at.id, at.max_score), 'is_default': at.id not in tset}
             for at in types]
    others = [t for t in Term.query.order_by(Term.id.desc()).all() if t.id != term_id]
    return render_template('settings/term_assessment_edit.html',
                           term=term, items=items, custom=custom, others=others,
                           total=sum(i['max'] for i in items))


@settings_bp.route('/assessments/terms/<int:term_id>/save', methods=['POST'])
@login_required
@admin_required
def term_assessment_save(term_id):
    from utils.assessments import save_term_settings
    db.get_or_404(Term, term_id)
    if request.form.get('clear'):
        save_term_settings(term_id, {})           # revert to the normal defaults
        log_action('settings.term_assessment_clear', detail=str(term_id))
        flash('This term now uses the normal assessment settings.', 'success')
        return redirect(url_for('settings.term_assessments'))
    maxes = {}
    for at_id, val in zip(request.form.getlist('at_id[]'), request.form.getlist('max_score[]')):
        if str(at_id).isdigit():
            try:
                maxes[int(at_id)] = max(0, int(val or 0))
            except (TypeError, ValueError):
                maxes[int(at_id)] = 0
    save_term_settings(term_id, maxes)
    log_action('settings.term_assessment_save', detail=str(term_id))
    flash('Assessment settings saved for this term.', 'success')
    return redirect(url_for('settings.term_assessment_edit', term_id=term_id))


@settings_bp.route('/assessments/terms/<int:term_id>/copy', methods=['POST'])
@login_required
@admin_required
def term_assessment_copy(term_id):
    from utils.assessments import copy_term_settings
    db.get_or_404(Term, term_id)
    src = request.form.get('from_term_id', type=int)
    n = copy_term_settings(src, term_id) if src else 0
    log_action('settings.term_assessment_copy', detail=f'{src}->{term_id}')
    flash(f'Copied {n} assessment setting(s) from the selected term.' if n
          else 'That term has no custom settings to copy.', 'success' if n else 'warning')
    return redirect(url_for('settings.term_assessment_edit', term_id=term_id))


# ============================================================================
# TIMETABLE SLOTS
# ============================================================================

@settings_bp.route('/timetable-slots')
@login_required
def timetable_slots():
    """Manage timetable slots/periods"""
    slots = TimetableSlot.query.filter_by(is_active=True).order_by(TimetableSlot.order).all()
    return _render({
        'page': 'timetable_slots',
        'settings': _settings_dict(),
        'save_url': url_for('settings.save_timetable_slots'),
        'generate_url': url_for('settings.generate_timetable_slots'),
        'back_url': url_for('settings.index'),
        'slots': [{'id': s.id, 'name': s.name,
                   'start_time': s.start_time.strftime('%H:%M') if s.start_time else '',
                   'end_time': s.end_time.strftime('%H:%M') if s.end_time else '',
                   'is_break': s.is_break} for s in slots],
    })


@settings_bp.route('/timetable-slots/generate', methods=['POST'])
@login_required
def generate_timetable_slots():
    """Auto-generate timetable slots based on settings"""
    try:
        from datetime import timedelta, datetime as dt

        # Get settings
        start_time_str = SchoolSettings.get('school_day_start', '08:20')
        period_duration = SchoolSettings.get('period_duration', 40)
        break_duration = SchoolSettings.get('break_duration', 30)
        periods_per_day = SchoolSettings.get('periods_per_day', 8)

        # Parse start time
        start_hour, start_min = map(int, start_time_str.split(':'))
        current_time = dt(2000, 1, 1, start_hour, start_min)

        # Delete existing slots
        TimetableSlot.query.delete()

        slot_number = 1
        order = 1

        for i in range(periods_per_day):
            # Add period
            end_time = current_time + timedelta(minutes=period_duration)
            db.session.add(TimetableSlot(
                slot_number=slot_number,
                name=f'Period {slot_number}',
                start_time=current_time.time(),
                end_time=end_time.time(),
                is_break=False,
                duration_minutes=period_duration,
                order=order
            ))
            current_time = end_time
            slot_number += 1
            order += 1

            # Add break after period 4 and period 6 (configurable)
            if i == 3 or i == 5:  # After 4th and 6th periods
                break_end = current_time + timedelta(minutes=break_duration)
                break_name = 'Short Break' if i == 3 else 'Long Break'
                db.session.add(TimetableSlot(
                    slot_number=0,  # 0 for breaks
                    name=break_name,
                    start_time=current_time.time(),
                    end_time=break_end.time(),
                    is_break=True,
                    duration_minutes=break_duration,
                    order=order
                ))
                current_time = break_end
                order += 1

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('settings.timetable_slots'))
    return _ok(f'{periods_per_day} periods and 2 breaks generated!', url_for('settings.timetable_slots'))


@settings_bp.route('/timetable-slots/save', methods=['POST'])
@login_required
def save_timetable_slots():
    """Save timetable slots"""
    try:
        from datetime import time

        slot_ids = request.form.getlist('slot_id[]')
        names = request.form.getlist('name[]')
        start_times = request.form.getlist('start_time[]')
        end_times = request.form.getlist('end_time[]')
        is_breaks = request.form.getlist('is_break[]')

        for i, slot_id in enumerate(slot_ids):
            if slot_id:
                slot = db.session.get(TimetableSlot, int(slot_id))
                if slot:
                    slot.name = names[i] if i < len(names) else slot.name

                    if i < len(start_times) and start_times[i]:
                        h, m = map(int, start_times[i].split(':'))
                        slot.start_time = time(h, m)

                    if i < len(end_times) and end_times[i]:
                        h, m = map(int, end_times[i].split(':'))
                        slot.end_time = time(h, m)

                    slot.is_break = str(i) in is_breaks
                    slot.order = i + 1

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('settings.timetable_slots'))
    return _ok('Timetable slots updated!', url_for('settings.timetable_slots'))


# ============================================================================
# DATABASE BACKUP & RESTORE
# ============================================================================

@settings_bp.route('/backup')
@central_admin_required
def backup_page():
    """Backup and restore page. Central-admin only: the backup subsystem operates
    on the entire multi-branch database, and this page lists backup filenames and
    whole-DB record counts."""
    # Get database info
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'school.db')
    db_size = 0
    if os.path.exists(db_path):
        db_size = os.path.getsize(db_path)

    # Get record counts
    counts = {
        'students': Student.query.count(),
        'sessions': AcademicSession.query.count(),
        'terms': Term.query.count(),
        'users': User.query.count()
    }

    from flask import current_app
    from utils.backup import list_backups
    backups = list_backups(current_app)
    return _render({
        'page': 'backup',
        'db_size': db_size,
        'counts': counts,
        'download_url': url_for('settings.download_backup'),
        'export_json_url': url_for('settings.export_json'),
        'create_url': url_for('settings.create_backup'),
        'restore_url': url_for('settings.restore_backup'),
        'back_url': url_for('settings.index'),
        'backups': [{
            'name': b['name'],
            'modified': b['modified'].strftime('%d %b %Y %H:%M') if b.get('modified') else '',
            'size': b['size'],
            'download_url': url_for('settings.download_backup_file', name=b['name']),
        } for b in backups],
    })


@settings_bp.route('/backup/create', methods=['POST'])
@central_admin_required
def create_backup():
    from flask import current_app
    from utils.backup import make_backup
    path = make_backup(current_app)
    if path:
        return _ok('Backup created.', url_for('settings.backup_page'))
    return _err('Could not create backup.', url_for('settings.backup_page'))


@settings_bp.route('/backup/file/<path:name>')
@central_admin_required
@rate_limited('db_export', max_requests=12, window_minutes=10)
def download_backup_file(name):
    import os as _os
    from flask import current_app
    safe = _os.path.basename(name)
    if not (safe.startswith('school_') and safe.endswith(('.db', '.sql'))):
        flash('Invalid backup file.', 'error')
        return redirect(url_for('settings.backup_page'))
    path = _os.path.join(current_app.config['BASE_DIR'], 'instance', 'backups', safe)
    if not _os.path.exists(path):
        flash('Backup not found.', 'error')
        return redirect(url_for('settings.backup_page'))
    mimetype = 'application/sql' if safe.endswith('.sql') else 'application/x-sqlite3'
    log_action('data.backup_download', detail=safe)
    return send_file(path, as_attachment=True, download_name=safe, mimetype=mimetype)


@settings_bp.route('/backup/download')
@central_admin_required
@rate_limited('db_export', max_requests=12, window_minutes=10)
def download_backup():
    """Download database backup"""
    try:
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'school.db')

        if not os.path.exists(db_path):
            flash('Database file not found!', 'error')
            return redirect(url_for('settings.backup_page'))

        # Create backup filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f'school_backup_{timestamp}.db'

        log_action('data.backup_download', detail=backup_filename)
        return send_file(
            db_path,
            as_attachment=True,
            download_name=backup_filename,
            mimetype='application/x-sqlite3'
        )
    except Exception as e:
        flash(f'Error creating backup: {str(e)}', 'error')
        return redirect(url_for('settings.backup_page'))


@settings_bp.route('/backup/export-json')
@central_admin_required
@rate_limited('db_export', max_requests=12, window_minutes=10)
def export_json():
    """Export all data to JSON"""
    log_action('data.export_json', detail='full data export')   # log the authorized attempt
    try:
        from models import (
            Student, ParentContact, AcademicSession, SchoolSettings, GradeScale, AssessmentType
        )

        data = {
            'export_date': datetime.now().isoformat(),
            'school_settings': [{
                'key': s.key, 'value': s.value, 'value_type': s.value_type
            } for s in SchoolSettings.query.all()],
            'grade_scales': [{
                'grade': g.grade, 'min_score': g.min_score, 'max_score': g.max_score,
                'remark': g.remark, 'order': g.order
            } for g in GradeScale.query.all()],
            'assessment_types': [{
                'name': a.name, 'short_name': a.short_name, 'max_score': a.max_score, 'order': a.order
            } for a in AssessmentType.query.filter_by(is_active=True).all()],
            'students': [{
                'student_id': s.student_id, 'first_name': s.first_name, 'middle_name': s.middle_name,
                'surname': s.surname, 'gender': s.gender,
                'date_of_birth': s.date_of_birth.isoformat() if s.date_of_birth else None,
                'religion': s.religion, 'home_address': s.home_address, 'hobbies': s.hobbies,
                'is_active': s.is_active
            } for s in Student.query.all()],
            'parent_contacts': [{
                'student_id': p.student.student_id, 'phone_number': p.phone_number,
                'relationship': p.relationship, 'name': p.name, 'is_primary': p.is_primary
            } for p in ParentContact.query.all()],
            'academic_sessions': [{
                'name': s.name,
                'start_date': s.start_date.isoformat() if s.start_date else None,
                'end_date': s.end_date.isoformat() if s.end_date else None,
                'is_active': s.is_active
            } for s in AcademicSession.query.all()],
        }

        # Create JSON response
        json_str = json.dumps(data, indent=2)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        return Response(
            json_str,
            mimetype='application/json',
            headers={'Content-Disposition': f'attachment; filename=school_export_{timestamp}.json'}
        )
    except Exception as e:
        flash(f'Error exporting data: {str(e)}', 'error')
        return redirect(url_for('settings.backup_page'))


@settings_bp.route('/backup/restore', methods=['POST'])
@central_admin_required
def restore_backup():
    """Restore database from an uploaded backup (SQLite .db or Postgres .sql)."""
    import tempfile
    from flask import current_app
    from utils.backup import restore_database

    if 'file' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('settings.backup_page'))

    file = request.files['file']
    if not file.filename:
        flash('No file selected.', 'error')
        return redirect(url_for('settings.backup_page'))

    if not file.filename.lower().endswith(('.db', '.sql')):
        flash('Please upload a .db (SQLite) or .sql (PostgreSQL) backup file.', 'error')
        return redirect(url_for('settings.backup_page'))

    # Wholesale live-DB replacement is destructive and admin-equivalent — require
    # an explicit typed confirmation in addition to the central-admin gate.
    if (request.form.get('confirm') or '').strip().upper() != 'RESTORE':
        flash('Type RESTORE to confirm the database replacement.', 'error')
        return redirect(url_for('settings.backup_page'))

    # Stage the upload to a temp file, then let the backend-aware helper apply it.
    suffix = '.sql' if file.filename.lower().endswith('.sql') else '.db'
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        file.save(tmp_path)
        # Defence-in-depth: validate the content, not just the extension, before
        # handing it to psql / overwriting the SQLite file.
        with open(tmp_path, 'rb') as fh:
            head = fh.read(512)
        if suffix == '.db' and not head.startswith(b'SQLite format 3\x00'):
            flash('That .db file is not a valid SQLite database.', 'error')
            return redirect(url_for('settings.backup_page'))
        if suffix == '.sql':
            try:
                text_head = head.decode('utf-8', 'ignore')
            except Exception:
                text_head = ''
            if not any(m in text_head for m in ('--', 'SET ', 'CREATE', 'INSERT', 'COPY', 'PGDMP')):
                flash('That .sql file does not look like a PostgreSQL dump.', 'error')
                return redirect(url_for('settings.backup_page'))
        ok, message = restore_database(current_app, tmp_path, file.filename)
        # Audit this high-impact action regardless of outcome.
        try:
            from utils.audit import log_action
            log_action('settings.restore_database',
                       detail=('ok' if ok else 'failed') + f': {file.filename}',
                       target_type='database', target_label=file.filename)
        except Exception:
            pass
        flash(message, 'success' if ok else 'error')
    except Exception as e:
        flash(f'Error restoring backup: {str(e)}', 'error')
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    return redirect(url_for('settings.backup_page'))


# ============================================================================
# USER MANAGEMENT
# ============================================================================

def _user_dict(u):
    return {'id': u.id, 'username': u.username, 'full_name': u.full_name,
            'email': u.email, 'role': u.role, 'is_active': u.is_active}


@settings_bp.route('/users')
@central_admin_required
def users_list():
    """List all users"""
    users = User.query.order_by(User.role, User.username).all()
    return _render({
        'page': 'users',
        'add_url': url_for('settings.add_user'),
        'back_url': url_for('settings.index'),
        'users': [{**_user_dict(u),
                   'edit_url': url_for('settings.edit_user', user_id=u.id),
                   'delete_url': url_for('settings.delete_user', user_id=u.id)}
                  for u in users],
    })


@settings_bp.route('/users/add', methods=['GET', 'POST'])
@central_admin_required
def add_user():
    """Add new user"""
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip().lower()
            email = request.form.get('email', '').strip().lower()
            full_name = request.form.get('full_name', '').strip()
            password = request.form.get('password', '')
            role = request.form.get('role', 'teacher')

            if not username or not password:
                return _err('Username and password are required.', url_for('settings.add_user'))

            # Check for duplicates
            if User.query.filter_by(username=username).first():
                return _err('Username already exists.', url_for('settings.add_user'))

            user = User(
                username=username,
                email=email or None,
                full_name=full_name or None,
                role=role
            )
            user.set_password(password)

            db.session.add(user)
            db.session.commit()

            return _ok(f'User {username} created!', url_for('settings.users_list'))
        except Exception as e:
            db.session.rollback()
            return _err(f'Error: {str(e)}', url_for('settings.add_user'))

    return _render({
        'page': 'add_user',
        'submit_url': url_for('settings.add_user'),
        'back_url': url_for('settings.users_list'),
    })


@settings_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@central_admin_required
def edit_user(user_id):
    """Edit user"""
    user = db.get_or_404(User, user_id)

    if request.method == 'POST':
        try:
            user.email = request.form.get('email', '').strip().lower() or None
            user.full_name = request.form.get('full_name', '').strip() or None
            user.role = request.form.get('role', 'teacher')
            user.is_active = request.form.get('is_active') == 'on'

            # Update password if provided
            new_password = request.form.get('password', '').strip()
            if new_password:
                user.set_password(new_password)

            db.session.commit()
            return _ok('User updated!', url_for('settings.users_list'))
        except Exception as e:
            db.session.rollback()
            return _err(f'Error: {str(e)}', url_for('settings.edit_user', user_id=user_id))

    return _render({
        'page': 'edit_user',
        'user': _user_dict(user),
        'submit_url': url_for('settings.edit_user', user_id=user.id),
        'back_url': url_for('settings.users_list'),
    })


@settings_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@central_admin_required
def delete_user(user_id):
    """Delete user"""
    user = db.get_or_404(User, user_id)

    # Prevent deleting last admin
    if user.role == 'admin':
        admin_count = User.query.filter_by(role='admin', is_active=True).count()
        if admin_count <= 1:
            return _err('Cannot delete the last admin user!', url_for('settings.users_list'))

    try:
        db.session.delete(user)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('settings.users_list'))
    return _ok('User deleted!', url_for('settings.users_list'))


@settings_bp.route('/notifications', methods=['GET', 'POST'])
@login_required
def notification_prefs():
    """Per-user notification-channel preferences (opt-out). Enforcement is gated
    by the NOTIFY_PREFS flag; today the in-app bell honours it."""
    from utils.notify_prefs import (CHANNELS, CHANNEL_LABELS, get_prefs, set_pref,
                                    flag_enabled, PUSH_TOPICS, PUSH_TOPIC_LABELS,
                                    set_push_topic, get_push_topics)
    uid = session.get('user_id')
    if request.method == 'POST':
        if uid:
            for ch in CHANNELS:
                set_pref(uid, ch, request.form.get('ch_' + ch) == 'on')
            # Per-category push toggles (only meaningful while the push channel is on).
            for topic in PUSH_TOPICS:
                set_push_topic(uid, topic, request.form.get('pushcat_' + topic) == 'on')
            flash('Notification preferences saved.', 'success')
        else:
            flash('Sign in with a staff account to set notification preferences.', 'warning')
        return redirect(url_for('settings.notification_prefs'))
    return render_template('settings/notifications.html',
                           prefs=get_prefs(uid) if uid else {}, channels=CHANNELS,
                           labels=CHANNEL_LABELS, has_user=bool(uid), flag_on=flag_enabled(),
                           push_topics=PUSH_TOPICS, push_topic_labels=PUSH_TOPIC_LABELS,
                           push_topic_prefs=get_push_topics(uid) if uid else {})
