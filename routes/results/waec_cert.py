"""WAEC result certificate generator — routes.

Single generation: pick student → year → template → toggle components → LIVE
preview → PNG / JPEG / PDF. Plus template management (per-year/branch assignment,
status, default, versioning), reusable component presets, bulk ZIP generation and
public QR verification. Rendering is deterministic (ReportLab + PyMuPDF) via
utils.waec_result_gen; every generation is audited and recorded for verification.
"""
import io
import json
import zipfile

from flask import send_file, abort, session, jsonify

from routes.results import *  # noqa: F401,F403  (results_bp, db, Student, request, …)
from utils import waec_result_gen as W
from utils.search import like_term
from utils.branch_scope import can_access_branch
from models import WAECCertTemplate, WAECCertPreset, WAECCertIssue, Branch


# --------------------------------------------------------------------------- #
#  helpers                                                                     #
# --------------------------------------------------------------------------- #
def _load_student(student_id):
    s = db.session.get(Student, student_id) if student_id else None
    if not s:
        abort(404)
    require_branch_access(s.branch_id)
    _assert_exam_student(s.id)
    return s


def _requested_show(ctx):
    raw = request.values.get('c')
    if raw is not None:
        enabled = {k for k in raw.split(',') if k}
        return W.resolve_show(ctx, {k: (k in enabled) for k in W._ALL_COMPONENTS})
    if any(k in request.values for k in W._ALL_COMPONENTS):
        return W.resolve_show(ctx, {k: (request.values.get(k) in ('1', 'on', 'true'))
                                    for k in W._ALL_COMPONENTS})
    return W.default_show(ctx)


def _requested_cfg():
    raw = request.values.get('cfg')
    if not raw:
        return {}
    try:
        return json.loads(raw) or {}
    except (ValueError, TypeError):
        return {}


def _all_presets():
    """Built-in + saved component presets for the generator UI (keys client-side)."""
    out = [{'key': k, 'label': v['label'], 'keys': v['keys']} for k, v in W.PRESETS.items()]
    try:
        for p in WAECCertPreset.query.order_by(WAECCertPreset.name).all():
            out.append({'key': f'db-{p.id}', 'label': p.name, 'keys': p.components()})
    except Exception:
        pass
    return out


def _recommend_template(year, branch_id):
    """The managed template that best fits this year/branch (or None). Never
    returns one that contradicts the year/branch (e.g. a 2025-only template for
    a 2026 result)."""
    try:
        cands = WAECCertTemplate.query.filter_by(exam_type='waec', status='active').all()
    except Exception:
        return None
    valid = [t for t in cands
             if t.year in (None, year) and t.branch_id in (None, branch_id)]
    if not valid:
        return None

    def score(t):
        s = 0
        s += 4 if t.year == year else 1
        s += 2 if (branch_id is not None and t.branch_id == branch_id) else (1 if t.branch_id is None else 0)
        s += 1 if t.is_default else 0
        return s
    return max(valid, key=score)


def _options_show(ctx, opts):
    if opts.get('components') is not None:
        keys = set(opts['components'])
        return W.resolve_show(ctx, {k: (k in keys) for k in W._ALL_COMPONENTS})
    if opts.get('preset'):
        return W.preset_show(ctx, opts['preset'])
    return W.default_show(ctx)


def _verify_url_for(code):
    try:
        return url_for('results.waec_cert_verify', code=code, _external=True)
    except Exception:
        return ''


def _record_issue(student, year, template, fmt, show):
    """Persist an issued-cert record and return its verification code."""
    enabled = [k for k, v in show.items() if v]
    from utils.access_control import is_admin  # noqa
    me = session.get('username') or 'admin'
    code = WAECCertIssue.new_code()
    rec = WAECCertIssue(code=code, student_id=student.id, exam_year=year,
                        template_key=template, output_format=fmt,
                        components_summary=', '.join(enabled)[:400], issued_by=me)
    db.session.add(rec); db.session.commit()
    return code


# --------------------------------------------------------------------------- #
#  single generation                                                          #
# --------------------------------------------------------------------------- #
@results_bp.route('/waec/certificate')
@login_required
def waec_cert_generator():
    student_id = request.args.get('student_id', type=int)
    if not student_id:
        q = (request.args.get('q') or '').strip()
        base = scope_query(db.session.query(Student).join(WAECResult), Student).distinct()
        if q:
            term = like_term(q)
            base = base.filter(db.or_(Student.first_name.ilike(term, escape='\\'),
                                      Student.surname.ilike(term, escape='\\'),
                                      Student.student_id.ilike(term, escape='\\')))
        students = base.order_by(Student.surname).limit(50).all()
        # Live search: the picker fetches this endpoint as-you-type and renders the
        # matches client-side (no full page reload).
        if request.headers.get('X-Requested-With') == 'fetch':
            return jsonify({'students': [
                {'id': s.id, 'full_name': s.full_name, 'student_id': s.student_id,
                 'url': url_for('results.waec_cert_generator', student_id=s.id)} for s in students]})
        return render_template('results/waec_cert.html', student=None, students=students, q=q)

    student = _load_student(student_id)
    years = W.available_years(student)
    year = resolve_exam_year(request.args.get('year', type=int), years)
    ctx = W.build_context(student, year) if year else None
    groups = W.available_components(ctx) if ctx else []
    rec = _recommend_template(year, student.branch_id) if ctx else None
    default_template = (rec.base_layout if rec else W.DEFAULT_TEMPLATE)
    show = _options_show(ctx, rec.options()) if (ctx and rec) else (W.default_show(ctx) if ctx else {})
    warnings = W.missing_warnings(ctx, show) if ctx else []
    return render_template(
        'results/waec_cert.html', student=student, years=years, year=year,
        templates=W.list_templates(), default_template=default_template,
        groups=groups, show=show, warnings=warnings, presets=_all_presets(),
        recommended=(rec.name if rec else None),
        preview_url=url_for('results.waec_cert_preview', student_id=student.id, year=year),
        generate_url=url_for('results.waec_cert_generate'),
        save_preset_url=url_for('results.waec_cert_save_preset'),
        manage_url=url_for('results.waec_cert_templates'),
        bulk_url=url_for('results.waec_cert_bulk'))


def _preview_etag(student, year):
    """A strong ETag for the live preview: the full request query (which encodes
    the template + every component toggle + scale) plus a fingerprint of the
    student's results for the year, so an identical request is a cheap 304 but any
    grade edit invalidates it. Rendering is deterministic, so this is exact."""
    import hashlib
    rows = (WAECResult.query.filter_by(student_id=student.id, exam_year=year)
            .with_entities(WAECResult.subject, WAECResult.grade,
                           WAECResult.updated_at).all())
    fp = '|'.join(f'{s}:{g}:{u}' for s, g, u in sorted((str(a), str(b), str(c)) for a, b, c in rows))
    raw = (request.query_string or b'').decode('utf-8', 'ignore') + '||' + fp
    return '"' + hashlib.sha1(raw.encode('utf-8')).hexdigest() + '"'


@results_bp.route('/waec/certificate/preview')
@login_required
def waec_cert_preview():
    student = _load_student(request.args.get('student_id', type=int))
    year = request.args.get('year', type=int)
    if not year:
        abort(400)
    # Skip the (expensive) render when the browser already holds this exact frame.
    etag = _preview_etag(student, year)
    _inm = [t.strip() for t in (request.headers.get('If-None-Match') or '').split(',')]
    if etag in _inm:
        from flask import Response
        r304 = Response(status=304)
        r304.headers['ETag'] = etag
        r304.headers['Cache-Control'] = 'private, max-age=0, must-revalidate'
        return r304
    ctx = W.build_context(student, year)
    ctx['verify_code'] = 'PREVIEW'
    template = request.args.get('template') or W.DEFAULT_TEMPLATE
    preset = request.args.get('preset')
    show = W.preset_show(ctx, preset) if preset else _requested_show(ctx)
    png = W.render_image(W.render_pdf(ctx, template, show, _requested_cfg(),
                                      _verify_url_for('PREVIEW')),
                         'png', scale=float(request.args.get('scale', 2.0)))
    resp = send_file(io.BytesIO(png), mimetype='image/png')
    # Always revalidate (data may change) but let the ETag turn an unchanged
    # re-request into a cheap 304 instead of a re-render.
    resp.headers['ETag'] = etag
    resp.headers['Cache-Control'] = 'private, max-age=0, must-revalidate'
    return resp


@results_bp.route('/waec/certificate/generate', methods=['POST'])
@admin_required
def waec_cert_generate():
    student = _load_student(request.form.get('student_id', type=int))
    year = request.form.get('year', type=int)
    if not year:
        abort(400)
    ctx = W.build_context(student, year)
    template = request.form.get('template') or W.DEFAULT_TEMPLATE
    fmt = (request.form.get('format') or 'pdf').lower()
    preset = request.form.get('preset')
    show = W.preset_show(ctx, preset) if preset else _requested_show(ctx)
    cfg = _requested_cfg()
    code = _record_issue(student, year, template, fmt, show)
    ctx['verify_code'] = code
    data, mimetype, ext = W.render(ctx, template, show, cfg, fmt=fmt,
                                   verify_url=_verify_url_for(code), scale=3.0)
    log_action('results.waec_cert_generate', target=student,
               detail=f"{ctx['exam']['short']} {year} · {template} · {fmt} · {code}")
    safe = ''.join(ch if ch.isalnum() else '_' for ch in (student.full_name or 'student')).strip('_')
    fname = f"{ctx['exam']['short']}_{year}_{safe}.{ext}"
    return send_file(io.BytesIO(data), mimetype=mimetype, as_attachment=True, download_name=fname)


# --------------------------------------------------------------------------- #
#  reusable presets                                                           #
# --------------------------------------------------------------------------- #
@results_bp.route('/waec/certificate/presets', methods=['POST'])
@admin_required
def waec_cert_save_preset():
    name = (request.form.get('name') or '').strip()
    keys = [k for k in (request.form.get('c') or '').split(',') if k in W._ALL_COMPONENTS]
    if not name or not keys:
        flash('Give the preset a name and select at least one component.', 'error')
        return redirect(request.referrer or url_for('results.waec_cert_generator'))
    cfg = request.form.get('cfg') or '{}'
    db.session.add(WAECCertPreset(name=name, components_json=json.dumps(keys),
                                  config_json=cfg, created_by=session.get('username') or 'admin'))
    db.session.commit()
    log_action('results.waec_cert_preset_save', detail=f'{name} · {len(keys)} components')
    flash(f'Preset “{name}” saved.', 'success')
    return redirect(request.referrer or url_for('results.waec_cert_generator'))


@results_bp.route('/waec/certificate/presets/<int:preset_id>/delete', methods=['POST'])
@admin_required
def waec_cert_delete_preset(preset_id):
    p = db.session.get(WAECCertPreset, preset_id)
    if p:
        db.session.delete(p); db.session.commit()
        flash('Preset deleted.', 'success')
    return redirect(request.referrer or url_for('results.waec_cert_templates'))


# --------------------------------------------------------------------------- #
#  template management (per-year/branch assignment, status, default, version) #
# --------------------------------------------------------------------------- #
@results_bp.route('/waec/certificate/templates')
@admin_required
def waec_cert_templates():
    rows = WAECCertTemplate.query.order_by(
        WAECCertTemplate.status, WAECCertTemplate.year.desc(), WAECCertTemplate.name).all()
    branches = Branch.query.order_by(Branch.name).all()
    years = [y[0] for y in db.session.query(WAECResult.exam_year).distinct()
             .order_by(WAECResult.exam_year.desc()).all()]
    edit_row = db.session.get(WAECCertTemplate, request.args.get('edit', type=int)) \
        if request.args.get('edit') else None
    return render_template('results/waec_cert_templates.html',
                           rows=rows, branches=branches, years=years, edit_row=edit_row,
                           layouts=W.list_templates(), presets=_all_presets(),
                           db_presets=WAECCertPreset.query.order_by(WAECCertPreset.name).all())


def _tpl_options_from_form():
    keys = [k for k in (request.form.get('components') or '').split(',') if k in W._ALL_COMPONENTS]
    opts = {}
    if keys:
        opts['components'] = keys
    preset = (request.form.get('preset') or '').strip()
    if preset and not keys:
        opts['preset'] = preset
    return opts


@results_bp.route('/waec/certificate/templates', methods=['POST'])
@admin_required
def waec_cert_create_template():
    name = (request.form.get('name') or '').strip()
    layout = request.form.get('base_layout')
    if not name or layout not in W.TEMPLATES:
        flash('A name and a valid base design are required.', 'error')
        return redirect(url_for('results.waec_cert_templates'))
    t = WAECCertTemplate(
        name=name, description=(request.form.get('description') or '').strip() or None,
        base_layout=layout, exam_type='waec',
        year=request.form.get('year', type=int),
        branch_id=request.form.get('branch_id', type=int),
        is_default=request.form.get('is_default') == 'on',
        status='active', version=1,
        options_json=json.dumps(_tpl_options_from_form()),
        created_by=session.get('username') or 'admin')
    db.session.add(t); db.session.flush()
    if t.is_default:
        _clear_other_defaults(t)
    db.session.commit()
    log_action('results.waec_cert_template_create', detail=f'{name} · {layout} · {t.year or "any"}')
    flash(f'Template “{name}” created.', 'success')
    return redirect(url_for('results.waec_cert_templates'))


def _clear_other_defaults(t):
    """Only one default per (year, branch) scope."""
    (WAECCertTemplate.query
     .filter(WAECCertTemplate.id != t.id, WAECCertTemplate.exam_type == 'waec',
             WAECCertTemplate.year.is_(t.year) if t.year is None else WAECCertTemplate.year == t.year,
             WAECCertTemplate.branch_id.is_(t.branch_id) if t.branch_id is None else WAECCertTemplate.branch_id == t.branch_id)
     .update({'is_default': False}, synchronize_session=False))


@results_bp.route('/waec/certificate/templates/<int:tpl_id>/edit', methods=['POST'])
@admin_required
def waec_cert_edit_template(tpl_id):
    t = db.session.get(WAECCertTemplate, tpl_id) or abort(404)
    require_branch_access(t.branch_id)   # no cross-branch template edits (IDOR guard)
    t.name = (request.form.get('name') or t.name).strip()
    t.description = (request.form.get('description') or '').strip() or None
    if request.form.get('base_layout') in W.TEMPLATES:
        t.base_layout = request.form.get('base_layout')
    t.year = request.form.get('year', type=int)
    t.branch_id = request.form.get('branch_id', type=int)
    t.is_default = request.form.get('is_default') == 'on'
    opts = _tpl_options_from_form()
    if opts:
        t.options_json = json.dumps(opts)
    t.version = (t.version or 1) + 1
    if t.is_default:
        _clear_other_defaults(t)
    db.session.commit()
    log_action('results.waec_cert_template_edit', detail=f'{t.name} (v{t.version})')
    flash('Template updated.', 'success')
    return redirect(url_for('results.waec_cert_templates'))


@results_bp.route('/waec/certificate/templates/<int:tpl_id>/duplicate', methods=['POST'])
@admin_required
def waec_cert_duplicate_template(tpl_id):
    t = db.session.get(WAECCertTemplate, tpl_id) or abort(404)
    require_branch_access(t.branch_id)   # no cross-branch template access (IDOR guard)
    d = WAECCertTemplate(name=f'{t.name} (copy)', description=t.description,
                         base_layout=t.base_layout, exam_type=t.exam_type, year=t.year,
                         branch_id=t.branch_id, is_default=False, status='active', version=1,
                         options_json=t.options_json, created_by=session.get('username') or 'admin')
    db.session.add(d); db.session.commit()
    flash('Template duplicated.', 'success')
    return redirect(url_for('results.waec_cert_templates'))


@results_bp.route('/waec/certificate/templates/<int:tpl_id>/status', methods=['POST'])
@admin_required
def waec_cert_template_status(tpl_id):
    t = db.session.get(WAECCertTemplate, tpl_id) or abort(404)
    require_branch_access(t.branch_id)   # no cross-branch status changes (IDOR guard)
    t.status = 'archived' if t.status == 'active' else 'active'
    if t.status == 'archived':
        t.is_default = False
    db.session.commit()
    flash(f'Template {t.status}.', 'success')
    return redirect(url_for('results.waec_cert_templates'))


@results_bp.route('/waec/certificate/templates/<int:tpl_id>/default', methods=['POST'])
@admin_required
def waec_cert_template_default(tpl_id):
    t = db.session.get(WAECCertTemplate, tpl_id) or abort(404)
    require_branch_access(t.branch_id)   # no cross-branch default changes (IDOR guard)
    t.is_default = True; t.status = 'active'
    _clear_other_defaults(t)
    db.session.commit()
    flash(f'“{t.name}” is now the default for its scope.', 'success')
    return redirect(url_for('results.waec_cert_templates'))


@results_bp.route('/waec/certificate/templates/<int:tpl_id>/delete', methods=['POST'])
@admin_required
def waec_cert_delete_template(tpl_id):
    t = db.session.get(WAECCertTemplate, tpl_id) or abort(404)
    require_branch_access(t.branch_id)   # no cross-branch template deletes (IDOR guard)
    db.session.delete(t); db.session.commit()
    flash('Template deleted.', 'success')
    return redirect(url_for('results.waec_cert_templates'))


# --------------------------------------------------------------------------- #
#  bulk generation → ZIP                                                       #
# --------------------------------------------------------------------------- #
@results_bp.route('/waec/certificate/bulk', methods=['GET'])
@admin_required
def waec_cert_bulk():
    years = [y[0] for y in db.session.query(WAECResult.exam_year).distinct()
             .order_by(WAECResult.exam_year.desc()).all()]
    year = resolve_exam_year(request.args.get('year', type=int), years)
    q = (request.args.get('q') or '').strip()
    students = []
    if year:
        base = scope_query(db.session.query(Student).join(WAECResult)
                           .filter(WAECResult.exam_year == year), Student).distinct()
        if q:
            term = like_term(q)
            base = base.filter(db.or_(Student.first_name.ilike(term, escape='\\'),
                                      Student.surname.ilike(term, escape='\\'),
                                      Student.student_id.ilike(term, escape='\\')))
        students = base.order_by(Student.surname).all()
    return render_template('results/waec_cert_bulk.html', years=years, year=year, q=q,
                           students=students, templates=W.list_templates(),
                           default_template=W.DEFAULT_TEMPLATE, presets=_all_presets(),
                           groups=W.available_components(W.build_context(students[0], year)) if students else [])


@results_bp.route('/waec/certificate/bulk', methods=['POST'])
@admin_required
def waec_cert_bulk_generate():
    year = request.form.get('year', type=int)
    template = request.form.get('template') or W.DEFAULT_TEMPLATE
    fmt = (request.form.get('format') or 'pdf').lower()
    preset = request.form.get('preset')
    comp_raw = request.form.get('c')
    ids = request.form.getlist('student_ids')
    if not year or not ids:
        flash('Choose a year and at least one student.', 'error')
        return redirect(url_for('results.waec_cert_bulk', year=year))
    ids = [int(i) for i in ids if i.isdigit()][:400]     # sane cap

    mem = io.BytesIO()
    used = set(); n = 0
    with zipfile.ZipFile(mem, 'w', zipfile.ZIP_DEFLATED) as zf:
        for sid in ids:
            s = db.session.get(Student, sid)
            if not s or not can_access_branch(s.branch_id):
                continue
            scope = None
            try:
                from utils.access_control import exam_student_scope
                scope = exam_student_scope()
            except Exception:
                scope = None
            if scope is not None and s.id not in scope:
                continue
            ctx = W.build_context(s, year)
            if not ctx['results']:
                continue
            if comp_raw is not None:
                enabled = {k for k in comp_raw.split(',') if k}
                show = W.resolve_show(ctx, {k: (k in enabled) for k in W._ALL_COMPONENTS})
            elif preset:
                show = W.preset_show(ctx, preset)
            else:
                show = W.default_show(ctx)
            code = _record_issue(s, year, template, fmt, show)
            ctx['verify_code'] = code
            data, _mt, ext = W.render(ctx, template, show, {}, fmt=fmt,
                                      verify_url=_verify_url_for(code), scale=2.5)
            safe = ''.join(ch if ch.isalnum() else '_' for ch in (s.full_name or f'student_{sid}')).strip('_')
            fn = f"WAEC_{year}_{safe}.{ext}"
            if fn in used:
                fn = f"WAEC_{year}_{safe}_{sid}.{ext}"
            used.add(fn)
            zf.writestr(fn, data)
            n += 1
    if not n:
        flash('No results could be generated for the selected students.', 'warning')
        return redirect(url_for('results.waec_cert_bulk', year=year))
    log_action('results.waec_cert_bulk', detail=f'WAEC {year} · {template} · {fmt} · {n} students')
    mem.seek(0)
    return send_file(mem, mimetype='application/zip', as_attachment=True,
                     download_name=f'WAEC_{year}_results_{n}.zip')


# --------------------------------------------------------------------------- #
#  public QR verification                                                      #
# --------------------------------------------------------------------------- #
@results_bp.route('/waec/verify')
@results_bp.route('/waec/verify/<code>')
def waec_cert_verify(code=None):
    """Public: confirm a generated result document by its verification code."""
    code = (code or request.args.get('code') or '').strip().upper()
    rec = WAECCertIssue.query.filter_by(code=code).first() if code else None
    data = None
    if rec and not rec.revoked:
        student = db.session.get(Student, rec.student_id)
        if student:
            from utils.school import school_profile
            data = {
                'school': school_profile().get('name'),
                'student': student.full_name,
                'exam': 'WAEC',
                'year': rec.exam_year,
                'issued_at': rec.issued_at,
                'code': rec.code,
            }
    return render_template('results/waec_cert_verify.html', code=code, data=data,
                           found=bool(data), revoked=bool(rec and rec.revoked))
