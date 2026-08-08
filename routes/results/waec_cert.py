"""WAEC result certificate generator — routes.

Workflow: pick student → year → template → toggle components → LIVE preview →
generate PNG / JPEG / PDF. Rendering is deterministic (ReportLab + PyMuPDF) via
utils.waec_result_gen; every generation is audited.
"""
import json

from flask import send_file, abort

from routes.results import *  # noqa: F401,F403  (results_bp, db, Student, request, etc.)
from utils import waec_result_gen as W
from utils.search import like_term


def _load_student(student_id):
    s = db.session.get(Student, student_id) if student_id else None
    if not s:
        abort(404)
    require_branch_access(s.branch_id)
    _assert_exam_student(s.id)
    return s


def _requested_show(ctx):
    """Build the requested on/off map from the request.

    ``c`` (comma-separated enabled keys) is the primary channel used by the live
    preview <img>; falling back to per-key form fields for the generate POST."""
    raw = request.values.get('c')
    if raw is not None:
        enabled = {k for k in raw.split(',') if k}
        return W.resolve_show(ctx, {k: (k in enabled) for k in W._ALL_COMPONENTS})
    # per-key fields (checkbox names) — absent means off
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


def _verify_url(student, year):
    """A best-effort verification URL for the optional QR/code component."""
    try:
        return url_for('results.waec_cert_generator', student_id=student.id, year=year, _external=True)
    except Exception:
        return ''


@results_bp.route('/waec/certificate')
@login_required
def waec_cert_generator():
    """The generator UI. With ?student_id it opens configured for that student;
    otherwise it shows a searchable picker of students who have WAEC results."""
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
        return render_template('results/waec_cert.html', student=None, students=students, q=q)

    student = _load_student(student_id)
    years = W.available_years(student)
    year = request.args.get('year', type=int) or (years[0] if years else None)
    ctx = W.build_context(student, year) if year else None
    groups = W.available_components(ctx) if ctx else []
    show = W.default_show(ctx) if ctx else {}
    warnings = W.missing_warnings(ctx, show) if ctx else []
    return render_template(
        'results/waec_cert.html', student=student, years=years, year=year,
        templates=W.list_templates(), default_template=W.DEFAULT_TEMPLATE,
        groups=groups, show=show, warnings=warnings,
        presets=[{'key': k, 'label': v['label']} for k, v in W.PRESETS.items()],
        preview_url=url_for('results.waec_cert_preview', student_id=student.id, year=year),
        generate_url=url_for('results.waec_cert_generate'))


@results_bp.route('/waec/certificate/preview')
@login_required
def waec_cert_preview():
    """A rendered PNG of the current configuration (drives the live preview)."""
    student = _load_student(request.args.get('student_id', type=int))
    year = request.args.get('year', type=int)
    if not year:
        abort(400)
    ctx = W.build_context(student, year)
    template = request.args.get('template') or W.DEFAULT_TEMPLATE
    preset = request.args.get('preset')
    if preset:
        show = W.preset_show(ctx, preset)
    else:
        show = _requested_show(ctx)
    cfg = _requested_cfg()
    png = W.render_image(W.render_pdf(ctx, template, show, cfg, _verify_url(student, year)),
                         'png', scale=float(request.args.get('scale', 2.0)))
    from io import BytesIO
    resp = send_file(BytesIO(png), mimetype='image/png')
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@results_bp.route('/waec/certificate/generate', methods=['POST'])
@admin_required
def waec_cert_generate():
    """Produce the final downloadable file (PNG / JPEG / PDF) and audit it."""
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
    data, mimetype, ext = W.render(ctx, template, show, cfg, fmt=fmt,
                                   verify_url=_verify_url(student, year), scale=3.0)
    enabled = [k for k, v in show.items() if v]
    log_action('results.waec_cert_generate', target=student,
               detail=f"{ctx['exam']['short']} {year} · {template} · {fmt} · {len(enabled)} components")
    safe = ''.join(ch if ch.isalnum() else '_' for ch in (student.full_name or 'student')).strip('_')
    fname = f"{ctx['exam']['short']}_{year}_{safe}.{ext}"
    from io import BytesIO
    return send_file(BytesIO(data), mimetype=mimetype, as_attachment=True, download_name=fname)
