"""Website-Builder admin — authenticated, admin-only editing of the school's
public site: publish switch, theme, pages, and each page's component blocks.

All content is school-authored and rendered through Jinja autoescaping on the
public side; here we validate block types/variants against the registry and keep
props as plain JSON. Every change is audit-logged.
"""
import copy
import re

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, abort, jsonify)
from sqlalchemy.orm.attributes import flag_modified

from models import db, SiteSettings, SitePage, SiteMedia
from utils.access_control import admin_required, login_required, module_required
from utils.audit import log_action
from utils.site_themes import preset_choices, PRESETS
from utils import site_blocks
from utils import site_media
from utils import site_admissions
from utils.spa import wants_json, render_or_json
from utils import website_editor as wed

website_admin_bp = Blueprint('website_admin', __name__, url_prefix='/website')


def _slugify(text):
    s = re.sub(r'[^a-z0-9]+', '-', (text or '').lower()).strip('-')
    return s or 'page'


def _seed_if_empty():
    """Ensure a settings row and a starter home page exist the first time the
    admin opens the builder — so they land on something real, not a blank."""
    settings = SiteSettings.get()
    if SitePage.query.filter_by(slug=SitePage.HOME_SLUG).first() is None:
        db.session.add(SitePage(slug=SitePage.HOME_SLUG, title='Home',
                                blocks=site_blocks.default_home_blocks(),
                                show_in_nav=True, nav_order=0))
        db.session.commit()
    return settings


def _done(msg, url, **extra):
    """Finish an action: JSON for the app, flash + redirect for a plain form."""
    if wants_json():
        return jsonify(ok=True, message=msg, **extra)
    if msg:
        flash(msg, 'success')
    return redirect(url)


def _fail(msg, url, status=400):
    if wants_json():
        return jsonify(ok=False, error=msg), status
    flash(msg, 'error')
    return redirect(url)


def _nav():
    return {k: url_for('website_admin.' + e) for k, e in (
        ('home', 'index'), ('news', 'news'), ('media', 'media_library'),
        ('assignments', 'assignments'), ('analytics', 'analytics'))}


def _payload(page, **data):
    from utils import site_ai
    settings = SiteSettings.get()
    data.update(page=page, nav=_nav(), public_home=url_for('website.home'),
                published=bool(settings.published), ai_available=site_ai.is_available(),
                site_name=_site_name())
    return render_or_json('website/app.html', 'web_json', data)


def _site_name():
    try:
        from utils.site_data import public_branding
        return (public_branding() or {}).get('name') or 'Your school'
    except Exception:
        return 'Your school'


def _page_row(p):
    return {'id': p.id, 'title': p.title, 'slug': p.slug, 'is_home': p.slug == SitePage.HOME_SLUG,
            'address': '/site' + ('' if p.slug == SitePage.HOME_SLUG else '/' + p.slug),
            'published': bool(p.is_published), 'in_nav': bool(p.show_in_nav),
            'sections': len(p.blocks or []), 'edit': url_for('website_admin.edit_page', page_id=p.id),
            'public': (url_for('website.home') if p.slug == SitePage.HOME_SLUG
                       else url_for('website.page', slug=p.slug))}


@website_admin_bp.route('/')
@login_required
@module_required('website')
def index():
    settings = _seed_if_empty()
    pages = SitePage.query.order_by(SitePage.nav_order.asc(), SitePage.title.asc()).all()
    from models import AcademicSession, NewsPost, HolidayAssignment
    try:
        sessions = AcademicSession.query.order_by(AcademicSession.name.desc()).all()
    except Exception:
        sessions = []
    theme = dict(settings.theme or {})
    preset = theme.get('preset') if theme.get('preset') in PRESETS else 'emerald'
    views = None
    try:
        from utils import site_analytics
        views = site_analytics.summary(days=7)['total_views']
    except Exception:
        db.session.rollback()
    adm = site_admissions.settings()
    return _payload(
        'home',
        pages=[_page_row(p) for p in pages],
        theme={'preset': preset, 'primary': theme.get('primary') or '', 'accent': theme.get('accent') or '',
               'seo_title': settings.seo_title or '', 'seo_description': settings.seo_description or ''},
        presets=[{'key': k, 'label': v['label'].split(' (')[0],
                  'mood': (v['label'].split(' (')[1].rstrip(')') if ' (' in v['label'] else ''),
                  'primary': v['primary'], 'accent': v['accent'], 'ink': v['ink'], 'muted': v['muted'],
                  'font': v['font_head'].split(',')[0].strip('"'), 'radius': v['radius']}
                 for k, v in PRESETS.items()],
        adm={'open': bool(adm.get('open')), 'intro': adm.get('intro') or '', 'fee': adm.get('fee') or 0,
             'session_id': adm.get('session_id') or ''},
        sessions=[{'id': s.id, 'name': s.name} for s in sessions],
        pay_configured=_payments_configured(), apply_url=url_for('website.apply'),
        counts={'posts': NewsPost.query.count(),
                'drafts': NewsPost.query.filter_by(is_published=False).count(),
                'media': SiteMedia.query.count(), 'assignments': HolidayAssignment.query.count(),
                'views7': views},
        urls={'publish': url_for('website_admin.publish'), 'theme': url_for('website_admin.theme'),
              'admissions': url_for('website_admin.admissions_settings'),
              'generate': url_for('website_admin.generate_site'),
              'new_page': url_for('website_admin.new_page'),
              'reorder': url_for('website_admin.reorder_pages')})


def _payments_configured():
    try:
        from utils import payments
        return payments.is_configured()
    except Exception:
        return False


@website_admin_bp.route('/admissions', methods=['POST'])
@login_required
@module_required('website')
def admissions_settings():
    site_admissions.save_settings(
        is_open=(request.form.get('web_admissions_open') == 'on'),
        intro=request.form.get('intro'),
        fee=request.form.get('fee'),
        session_id=request.form.get('session_id'))
    log_action('website.admissions_settings')
    return _done('Online admissions settings saved.', url_for('website_admin.index'))


@website_admin_bp.route('/generate', methods=['POST'])
@login_required
@module_required('website')
def generate_site():
    """Build a complete, uniquely-styled site in one click. Replaces existing
    pages, so it's a deliberate action from the overview (with confirmation)."""
    from utils import site_generator, site_ai
    # 'salt' lets the admin ask for a different look without changing anything else.
    salt = (request.form.get('salt') or '').strip()
    use_ai = (request.form.get('use_ai') == 'on') and site_ai.is_available()
    try:
        n = site_generator.generate(salt=salt, use_ai=use_ai)
    except Exception:
        db.session.rollback()
        return _fail('Sorry — the site could not be generated. Please try again.',
                     url_for('website_admin.index'), 500)
    log_action('website.generate', detail=f'{n} pages, ai={use_ai}')
    return _done(f'Your website has been built — {n} pages ready to review and edit. '
                 'Publish it when you’re happy.', url_for('website_admin.index'))


@website_admin_bp.route('/publish', methods=['POST'])
@login_required
@module_required('website')
def publish():
    settings = SiteSettings.get()
    settings.published = (request.form.get('published') == 'on')
    db.session.commit()
    log_action('website.publish', detail=str(settings.published))
    return _done('Your website is live.' if settings.published else 'Your website is now a private draft.',
                 url_for('website_admin.index'), published=bool(settings.published))


@website_admin_bp.route('/theme', methods=['POST'])
@login_required
@module_required('website')
def theme():
    settings = SiteSettings.get()
    preset = request.form.get('preset')
    theme = dict(settings.theme or {})
    if preset in PRESETS:
        theme['preset'] = preset
    # Optional colour overrides. A colour picker always submits a value, so the
    # old "blank = use the preset" rule never fired and a saved colour stuck
    # forever (picking a new preset kept the old colours). Overrides now apply
    # only when "custom colours" is on, and must be real #rrggbb values.
    custom = request.form.get('custom_colors')
    for key in ('primary', 'accent'):
        val = (request.form.get(key) or '').strip()
        keep = (custom == 'on') if custom is not None else bool(val)
        if keep and re.fullmatch(r'#[0-9a-fA-F]{6}', val):
            theme[key] = val.lower()
        else:
            theme.pop(key, None)
    settings.theme = theme
    settings.seo_title = (request.form.get('seo_title') or '').strip()[:70] or None
    settings.seo_description = (request.form.get('seo_description') or '').strip()[:180] or None
    db.session.commit()
    log_action('website.theme', detail=theme.get('preset'))
    return _done('Look and search details saved.', url_for('website_admin.index'))


@website_admin_bp.route('/pages/new', methods=['POST'])
@login_required
@module_required('website')
def new_page():
    title = (request.form.get('title') or '').strip() or 'New page'
    slug = _slugify(request.form.get('slug') or title)
    if slug in _RESERVED or SitePage.query.filter_by(slug=slug).first():
        return _fail('A page with that address already exists — try a different title.',
                     url_for('website_admin.index'))
    last = db.session.query(db.func.max(SitePage.nav_order)).scalar() or 0
    pg = SitePage(slug=slug, title=title[:120], blocks=site_blocks.default_page_blocks(slug, title),
                  nav_order=last + 1)
    db.session.add(pg); db.session.commit()
    log_action('website.page_create', target=pg)
    url = url_for('website_admin.edit_page', page_id=pg.id)
    if wants_json():
        return jsonify(ok=True, message='Page created.', redirect=url)
    return redirect(url)


# Addresses the public site already uses for its own routes.
_RESERVED = {SitePage.HOME_SLUG, 'apply', 'media', 'assignments', 'sitemap.xml', 'robots.txt'}


@website_admin_bp.route('/pages/reorder', methods=['POST'])
@login_required
@module_required('website')
def reorder_pages():
    ids = [int(x) for x in (request.form.get('order') or '').split(',') if x.strip().isdigit()]
    pages = {p.id: p for p in SitePage.query.filter(SitePage.id.in_(ids)).all()} if ids else {}
    for i, pid in enumerate(ids):
        if pid in pages:
            pages[pid].nav_order = i
    db.session.commit()
    log_action('website.page_reorder')
    return _done('Menu order saved.', url_for('website_admin.index'))


def _page_payload(pg):
    from utils import site_ai
    ai = site_ai.is_available()
    public_url = (url_for('website.home') if pg.slug == SitePage.HOME_SLUG
                  else url_for('website.page', slug=pg.slug))
    base = '/website/pages/%d' % pg.id
    return dict(pg=dict(_page_row(pg), meta_description=pg.meta_description or ''),
                blocks=[wed.serialize_block(b, i, ai) for i, b in enumerate(pg.blocks or [])],
                catalogue=wed.catalogue(), public_url=public_url,
                pages_for_links=[{'title': p.title, 'address': '/site' + ('/' if p.slug == SitePage.HOME_SLUG else '/' + p.slug)}
                                 for p in SitePage.query.order_by(SitePage.nav_order.asc()).all()
                                 if p.slug != SitePage.HOME_SLUG],
                urls={'meta': url_for('website_admin.save_page_meta', page_id=pg.id),
                      'add': url_for('website_admin.add_block', page_id=pg.id),
                      'delete': url_for('website_admin.delete_page', page_id=pg.id),
                      'base': base, 'upload': url_for('website_admin.media_upload'),
                      'library': url_for('website_admin.media_library')})


@website_admin_bp.route('/pages/<int:page_id>')
@login_required
@module_required('website')
def edit_page(page_id):
    pg = db.get_or_404(SitePage, page_id)
    return _payload('page', **_page_payload(pg))


@website_admin_bp.route('/pages/<int:page_id>/meta', methods=['POST'])
@login_required
@module_required('website')
def save_page_meta(page_id):
    pg = db.get_or_404(SitePage, page_id)
    back = url_for('website_admin.edit_page', page_id=pg.id)
    pg.title = ((request.form.get('title') or '').strip() or pg.title)[:120]
    pg.meta_description = (request.form.get('meta_description') or '').strip()[:180] or None
    pg.show_in_nav = (request.form.get('show_in_nav') == 'on')
    # The home page is always published — hiding it would take the whole site down.
    pg.is_published = True if pg.slug == SitePage.HOME_SLUG else (request.form.get('is_published') == 'on')
    try:
        pg.nav_order = int(request.form.get('nav_order') or pg.nav_order)
    except (TypeError, ValueError):
        pass
    raw_slug = (request.form.get('slug') or '').strip()
    if raw_slug and pg.slug != SitePage.HOME_SLUG:
        slug = _slugify(raw_slug)
        if slug != pg.slug:
            if slug in _RESERVED or SitePage.query.filter(SitePage.slug == slug, SitePage.id != pg.id).first():
                db.session.rollback()
                return _fail('That address is already used — pick another.', back)
            pg.slug = slug
    db.session.commit()
    log_action('website.page_meta', target=pg)
    return _done('Page settings saved.', back, page=_page_payload(pg))


def _blocks(pg):
    """A deep copy of the page's blocks to edit safely.

    A shallow ``list(pg.blocks)`` shares the nested dicts with the ORM's
    committed value, so mutating a block in place (text, variant, enabled…)
    would also mutate the snapshot SQLAlchemy compares against — the change
    would look like a no-op and never persist. Deep-copying (plus
    ``flag_modified`` on save) guarantees in-place edits are written."""
    return copy.deepcopy(pg.blocks or [])


def _save_blocks(pg, blocks):
    """Assign edited blocks back and force the JSON column to be flushed."""
    pg.blocks = blocks
    flag_modified(pg, 'blocks')
    db.session.commit()


@website_admin_bp.route('/pages/<int:page_id>/block/add', methods=['POST'])
@login_required
@module_required('website')
def add_block(page_id):
    pg = db.get_or_404(SitePage, page_id)
    btype = request.form.get('type')
    if not site_blocks.valid_type(btype):
        abort(400)
    blocks = _blocks(pg)
    new = site_blocks.block_defaults(btype)
    # Keep the footer last: a section added after it would sit below the footer.
    at = len(blocks)
    if btype != 'footer' and blocks and blocks[-1].get('type') == 'footer':
        at -= 1
    blocks.insert(at, new)
    _save_blocks(pg, blocks)
    log_action('website.block_add', detail=btype, target=pg)
    if wants_json():
        return jsonify(ok=True, message='Section added.', page=_page_payload(pg), selected=at)
    return redirect(url_for('website_admin.edit_page', page_id=pg.id, _anchor='b%d' % at))


@website_admin_bp.route('/pages/<int:page_id>/block/<int:idx>/op', methods=['POST'])
@login_required
@module_required('website')
def block_op(page_id, idx):
    pg = db.get_or_404(SitePage, page_id)
    blocks = _blocks(pg)
    if not (0 <= idx < len(blocks)):
        abort(404)
    if not _same_block(blocks, idx):
        return _stale(pg)
    op = request.form.get('op')
    if op == 'up' and idx > 0:
        blocks[idx - 1], blocks[idx] = blocks[idx], blocks[idx - 1]
    elif op == 'down' and idx < len(blocks) - 1:
        blocks[idx + 1], blocks[idx] = blocks[idx], blocks[idx + 1]
    elif op == 'delete':
        blocks.pop(idx)
    elif op == 'duplicate':
        blocks.insert(idx + 1, copy.deepcopy(blocks[idx]))
    elif op == 'toggle':
        blocks[idx]['enabled'] = not blocks[idx].get('enabled', True)
    elif op == 'variant':
        variant = request.form.get('variant')
        if site_blocks.valid_variant(blocks[idx]['type'], variant):
            blocks[idx]['variant'] = variant
    _save_blocks(pg, blocks)
    log_action('website.block_op', detail=op, target=pg)
    if wants_json():
        sel = {'up': idx - 1, 'down': idx + 1, 'duplicate': idx + 1, 'delete': min(idx, len(blocks) - 1)}.get(op, idx)
        return jsonify(ok=True, page=_page_payload(pg), selected=max(0, min(sel, len(blocks) - 1)),
                       message={'delete': 'Section removed.', 'duplicate': 'Section copied.'}.get(op))
    return redirect(url_for('website_admin.edit_page', page_id=pg.id, _anchor='b%d' % min(idx, len(blocks) - 1) if blocks else None))


def _same_block(blocks, idx):
    """The app sends the section type it is editing; if the page changed in
    another tab, the index may now point at a different section."""
    want = request.form.get('expect') or ((request.get_json(silent=True) or {}).get('expect') if request.is_json else None)
    return not want or blocks[idx].get('type') == want


def _stale(pg):
    if wants_json():
        return jsonify(ok=False, stale=True, page=_page_payload(pg),
                       error='This page was changed somewhere else — it has been reloaded. Please try again.'), 409
    abort(409)


@website_admin_bp.route('/pages/<int:page_id>/block/<int:idx>/save', methods=['POST'])
@login_required
@module_required('website')
def block_save(page_id, idx):
    """Save a whole section from the app in one go: its content, design and
    visibility. Content is checked against the block registry."""
    pg = db.get_or_404(SitePage, page_id)
    blocks = _blocks(pg)
    if not (0 <= idx < len(blocks)):
        abort(404)
    body = request.get_json(silent=True) or {}
    if not _same_block(blocks, idx):
        return _stale(pg)
    blk = blocks[idx]
    try:
        blk['props'] = wed.clean_props(blk['type'], blk.get('props') or {}, body.get('props') or {})
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400
    variant = body.get('variant')
    if variant and site_blocks.valid_variant(blk['type'], variant):
        blk['variant'] = variant
    if 'enabled' in body:
        blk['enabled'] = bool(body.get('enabled'))
    _save_blocks(pg, blocks)
    log_action('website.block_content', target=pg)
    return jsonify(ok=True, message='Saved.', page=_page_payload(pg), selected=idx)


@website_admin_bp.route('/pages/<int:page_id>/block/<int:idx>/content', methods=['POST'])
@login_required
@module_required('website')
def block_content(page_id, idx):
    pg = db.get_or_404(SitePage, page_id)
    blocks = _blocks(pg)
    if not (0 <= idx < len(blocks)):
        abort(404)
    btype = blocks[idx]['type']
    img_keys = site_blocks.image_props(btype)
    list_key = site_blocks.image_list_prop(btype)
    props = dict(blocks[idx].get('props') or {})
    for key, val in props.items():
        if key in img_keys:
            # single-image prop: an uploaded file replaces it; a clear box empties it.
            up = request.files.get('file__' + key)
            if up and up.filename:
                try:
                    props[key] = site_media.store_upload(up).url
                    # make sure the block's design actually shows this image
                    switch = site_blocks.variant_for_image(btype, key, blocks[idx].get('variant'))
                    if switch:
                        blocks[idx]['variant'] = switch
                except ValueError as e:
                    flash(str(e), 'error')
            elif request.form.get('clear__' + key):
                props[key] = ''
        elif key == list_key and isinstance(val, list):
            # gallery: drop removed images, then append newly-uploaded ones.
            removed = set(request.form.getlist('remove__' + key))
            kept = [u for u in val if u not in removed]
            for up in request.files.getlist('file__' + key):
                if up and up.filename:
                    try:
                        kept.append(site_media.store_upload(up).url)
                    except ValueError as e:
                        flash(str(e), 'error')
            props[key] = kept
        elif isinstance(val, (list, dict)):
            raw = request.form.get('prop__' + key)
            if raw is not None:
                import json
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, type(val)):
                        props[key] = parsed
                except (ValueError, TypeError):
                    flash(f'Could not parse "{key}" — leave it as valid JSON.', 'error')
        else:
            if ('prop__' + key) in request.form:
                props[key] = request.form.get('prop__' + key)
    blocks[idx]['props'] = props
    _save_blocks(pg, blocks)
    log_action('website.block_content', target=pg)
    flash('Content saved.', 'success')
    return redirect(url_for('website_admin.edit_page', page_id=pg.id, _anchor='b%d' % idx))


@website_admin_bp.route('/pages/<int:page_id>/block/<int:idx>/ai', methods=['POST'])
@login_required
@module_required('website')
def block_ai(page_id, idx):
    """Draft copy for a section with AI. The generated text is written into the
    block's props but must still be reviewed and saved by the admin (they land in
    the Edit-content form fields), so nothing goes live automatically."""
    from utils import site_ai, site_blocks
    pg = db.get_or_404(SitePage, page_id)
    blocks = _blocks(pg)
    if not (0 <= idx < len(blocks)):
        abort(404)
    if not site_ai.is_available():
        return _fail('AI writing isn’t set up on this site.',
                     url_for('website_admin.edit_page', page_id=pg.id, _anchor='b%d' % idx))
    block = blocks[idx]
    props = dict(block.get('props') or {})
    fields = site_ai.copy_fields(props)
    if not fields:
        return _fail('This section has no text to write.',
                     url_for('website_admin.edit_page', page_id=pg.id, _anchor='b%d' % idx))
    spec = site_blocks.REGISTRY.get(block['type']) or {}
    from utils.site_data import public_context
    branding = public_context()['branding']
    suggestions = site_ai.suggest_block_copy(
        spec.get('label', block['type']), fields, props, branding=branding,
        tone=(request.form.get('tone') or '').strip()[:60],
        keywords=(request.form.get('keywords') or '').strip()[:200])
    if not suggestions:
        return _fail('AI couldn’t write anything just now — please try again.',
                     url_for('website_admin.edit_page', page_id=pg.id, _anchor='b%d' % idx), 502)
    if wants_json():
        # The app drops the draft into the fields; nothing is saved (or goes
        # live) until the person reviews it and taps Save.
        log_action('website.block_ai', detail=block['type'], target=pg)
        return jsonify(ok=True, suggestions={k: v for k, v in suggestions.items() if k in fields},
                       message='Draft written — check the wording, then Save.')
    props.update(suggestions)
    block['props'] = props
    _save_blocks(pg, blocks)
    log_action('website.block_ai', detail=block['type'], target=pg)
    flash('AI draft added — review the wording below and click Save content to publish it.', 'success')
    return redirect(url_for('website_admin.edit_page', page_id=pg.id, _anchor='b%d' % idx))


@website_admin_bp.route('/pages/<int:page_id>/delete', methods=['POST'])
@login_required
@module_required('website')
def delete_page(page_id):
    pg = db.get_or_404(SitePage, page_id)
    if pg.slug == SitePage.HOME_SLUG:
        return _fail('The home page cannot be deleted.', url_for('website_admin.edit_page', page_id=pg.id))
    name = pg.title
    db.session.delete(pg); db.session.commit()
    log_action('website.page_delete', detail=name)
    return _done(f'Page “{name}” deleted.', url_for('website_admin.index'), redirect=url_for('website_admin.index'))


# --- media library ---------------------------------------------------------
def _media_row(m):
    return {'id': m.id, 'url': m.url, 'name': m.filename or 'Image', 'w': m.width, 'h': m.height,
            'kb': round((m.bytes or 0) / 1024), 'date': m.created_at.strftime('%d %b %Y') if m.created_at else '',
            'delete': url_for('website_admin.media_delete', media_id=m.id)}


def _media_used():
    """Every image URL a page or post currently uses, so the library can warn
    before deleting an image that is still on the site."""
    used = set()

    def walk(v):
        if isinstance(v, str):
            if v.startswith('/site/media/') or v.startswith('http'):
                used.add(v)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
    for p in SitePage.query.all():
        walk(p.blocks or [])
    try:
        from models import NewsPost
        for n in NewsPost.query.filter(NewsPost.cover_image.isnot(None)).all():
            used.add(n.cover_image)
    except Exception:
        db.session.rollback()
    return used


@website_admin_bp.route('/media')
@login_required
@module_required('website')
def media_library():
    items = SiteMedia.query.order_by(SiteMedia.created_at.desc(), SiteMedia.id.desc()).all()
    total = sum(m.bytes or 0 for m in items)
    from utils import media_storage
    labels = {'db': 'this school’s database', 'local': 'a filesystem volume', 's3': 'object storage (S3/R2)'}
    where = labels.get(media_storage.backend(), media_storage.backend())
    used = _media_used()
    rows = []
    for m in items:
        r = _media_row(m)
        r['used'] = m.url in used
        rows.append(r)
    return _payload('media', items=rows, total_mb=round(total / 1024 / 1024, 2), storage_where=where,
                    urls={'upload': url_for('website_admin.media_upload')})


@website_admin_bp.route('/media/upload', methods=['POST'])
@login_required
@module_required('website')
def media_upload():
    done, errors = [], []
    for up in request.files.getlist('file'):
        if up and up.filename:
            try:
                m = site_media.store_upload(up)
                done.append(m)
                log_action('website.media_upload', detail='%dx%d' % (m.width or 0, m.height or 0))
            except ValueError as e:
                errors.append(f'{up.filename}: {e}')
    if wants_json():
        if not done:
            return jsonify(ok=False, error=errors[0] if errors else 'Choose an image to upload.'), 400
        return jsonify(ok=True, items=[_media_row(m) for m in done], errors=errors,
                       message=f'{len(done)} image{"s" if len(done) != 1 else ""} uploaded.')
    # Only claim success for what actually uploaded (it used to say "uploaded"
    # even when every file was rejected).
    for e in errors:
        flash(e, 'error')
    if done:
        flash(f'{len(done)} image{"s" if len(done) != 1 else ""} uploaded.', 'success')
    elif not errors:
        flash('Choose an image to upload.', 'error')
    return redirect(url_for('website_admin.media_library'))


@website_admin_bp.route('/media/<int:media_id>/delete', methods=['POST'])
@login_required
@module_required('website')
def media_delete(media_id):
    m = db.get_or_404(SiteMedia, media_id)
    from utils import media_storage
    media_storage.delete(m)                    # remove filesystem/object bytes too
    db.session.delete(m); db.session.commit()
    log_action('website.media_delete', detail=str(media_id))
    return _done('Image deleted.', url_for('website_admin.media_library'))


# --- holiday assignments ---------------------------------------------------
_ASSIGN_EXT = {'pdf': 'application/pdf', 'doc': 'application/msword',
               'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}
_ASSIGN_MAX = 20 * 1024 * 1024        # 20 MB per document


def _class_choices():
    from models import SchoolClass
    try:
        return [(c.id, c.name) for c in SchoolClass.query.order_by(SchoolClass.level).all()]
    except Exception:
        return []


def _assignment_row(a):
    return {'id': a.id, 'class_id': a.class_id, 'class_label': a.class_label, 'title': a.title,
            'session_label': a.session_label or '', 'filename': a.filename, 'ext': (a.ext or '').upper(),
            'icon': a.icon, 'size': a.size_human, 'published': bool(a.is_published),
            'date': a.created_at.strftime('%d %b %Y') if a.created_at else '',
            'download': url_for('website.assignment_download', aid=a.id),
            'toggle': url_for('website_admin.assignment_toggle', aid=a.id),
            'delete': url_for('website_admin.assignment_delete', aid=a.id)}


@website_admin_bp.route('/assignments')
@login_required
@module_required('website')
def assignments():
    from models import HolidayAssignment
    items = HolidayAssignment.query.order_by(HolidayAssignment.class_label.asc(),
                                             HolidayAssignment.created_at.desc()).all()
    return _payload('assignments', items=[_assignment_row(a) for a in items],
                    classes=[{'id': cid, 'name': n} for cid, n in _class_choices()],
                    urls={'upload': url_for('website_admin.assignment_upload')})


@website_admin_bp.route('/assignments/upload', methods=['POST'])
@login_required
@module_required('website')
def assignment_upload():
    from models import HolidayAssignment, SchoolClass
    back = url_for('website_admin.assignments')
    up = request.files.get('file')
    title = (request.form.get('title') or '').strip()[:200]
    session_label = (request.form.get('session_label') or '').strip()[:60]
    if not up or not up.filename or not title:
        return _fail('Please give it a title and choose a file.', back)
    ext = up.filename.rsplit('.', 1)[-1].lower() if '.' in up.filename else ''
    if ext not in _ASSIGN_EXT:
        return _fail('Only PDF and Word (.doc/.docx) files are allowed.', back)
    data = up.read()
    if not data or len(data) > _ASSIGN_MAX:
        return _fail('That file is empty or larger than 20 MB.', back)
    # resolve the class label (denormalised, survives class edits/deletes)
    cid = request.form.get('class_id')
    cid = int(cid) if (cid and str(cid).isdigit()) else None
    label = 'General'
    if cid:
        c = db.session.get(SchoolClass, cid)
        label = c.name if c else 'General'
        if not c:
            cid = None
    a = HolidayAssignment(class_id=cid, class_label=label, title=title,
                          session_label=session_label or None, filename=up.filename[:200],
                          mime=_ASSIGN_EXT[ext], bytes=len(data), data=data, is_published=True)
    db.session.add(a); db.session.commit()
    log_action('website.assignment_upload', detail=f'{label}: {title}', target=a)
    return _done('Assignment uploaded.', back, item=_assignment_row(a))


@website_admin_bp.route('/assignments/<int:aid>/toggle', methods=['POST'])
@login_required
@module_required('website')
def assignment_toggle(aid):
    from models import HolidayAssignment
    a = db.get_or_404(HolidayAssignment, aid)
    a.is_published = not a.is_published
    db.session.commit()
    log_action('website.assignment_toggle', detail=str(a.is_published), target=a)
    return _done(None if not wants_json() else ('Now on the website.' if a.is_published else 'Hidden from the website.'),
                 url_for('website_admin.assignments'), item=_assignment_row(a))


@website_admin_bp.route('/assignments/<int:aid>/delete', methods=['POST'])
@login_required
@module_required('website')
def assignment_delete(aid):
    from models import HolidayAssignment
    a = db.get_or_404(HolidayAssignment, aid)
    db.session.delete(a); db.session.commit()
    log_action('website.assignment_delete', detail=str(aid))
    return _done('Assignment deleted.', url_for('website_admin.assignments'))


# --- news / blog -----------------------------------------------------------
def _unique_news_slug(title, exclude_id=None):
    from models import NewsPost
    base = _slugify(title) or 'post'
    slug, i = base, 2
    while True:
        row = NewsPost.query.filter_by(slug=slug).first()
        if row is None or row.id == exclude_id:
            return slug
        slug = f'{base}-{i}'; i += 1


def _post_row(p):
    return {'id': p.id, 'title': p.title, 'slug': p.slug, 'excerpt': p.excerpt or '', 'body': p.body or '',
            'category': p.category or '', 'author': p.author or '', 'published': bool(p.is_published),
            'date': p.published_at.isoformat() if p.published_at else '',
            'date_label': p.published_at.strftime('%d %b %Y') if p.published_at else '',
            'cover': p.cover_image or '',
            'words': len((p.body or '').split()),
            'edit': url_for('website_admin.news_edit', post_id=p.id),
            'public': url_for('website.news_article', slug=p.slug)}


@website_admin_bp.route('/news')
@login_required
@module_required('website')
def news():
    from models import NewsPost
    posts = NewsPost.query.order_by(NewsPost.published_at.desc(), NewsPost.id.desc()).all()
    return _payload('news', posts=[_post_row(p) for p in posts],
                    urls={'new': url_for('website_admin.news_new')})


@website_admin_bp.route('/news/new', methods=['POST'])
@login_required
@module_required('website')
def news_new():
    from models import NewsPost
    title = (request.form.get('title') or 'Untitled post').strip()[:200]
    p = NewsPost(slug=_unique_news_slug(title), title=title, is_published=False,
                 body='', excerpt='')
    db.session.add(p); db.session.commit()
    log_action('website.news_create', target=p)
    url = url_for('website_admin.news_edit', post_id=p.id)
    if wants_json():
        return jsonify(ok=True, redirect=url)
    return redirect(url)


@website_admin_bp.route('/news/<int:post_id>')
@login_required
@module_required('website')
def news_edit(post_id):
    from models import NewsPost
    p = db.get_or_404(NewsPost, post_id)
    cats = sorted({c for (c,) in db.session.query(NewsPost.category).filter(NewsPost.category.isnot(None)).all() if c})
    return _payload('post', post=_post_row(p), categories=cats,
                    urls={'save': url_for('website_admin.news_save', post_id=p.id),
                          'delete': url_for('website_admin.news_delete', post_id=p.id),
                          'upload': url_for('website_admin.media_upload'),
                          'library': url_for('website_admin.media_library')})


@website_admin_bp.route('/news/<int:post_id>/save', methods=['POST'])
@login_required
@module_required('website')
def news_save(post_id):
    from models import NewsPost
    from datetime import datetime
    p = db.get_or_404(NewsPost, post_id)
    back = url_for('website_admin.news_edit', post_id=p.id)
    new_title = ((request.form.get('title') or '').strip() or p.title)[:200]
    if _slugify(new_title) != _slugify(p.title):
        p.slug = _unique_news_slug(new_title, exclude_id=p.id)
    p.title = new_title
    p.excerpt = (request.form.get('excerpt') or '').strip()[:400] or None
    p.body = request.form.get('body') or ''
    p.category = (request.form.get('category') or '').strip()[:60] or None
    p.author = (request.form.get('author') or '').strip()[:120] or None
    p.is_published = (request.form.get('is_published') == 'on')
    pub = (request.form.get('published_at') or '').strip()
    if pub:
        try:
            p.published_at = datetime.strptime(pub, '%Y-%m-%d').date()
        except ValueError:
            pass
    elif p.is_published and not p.published_at:
        from models import local_now
        p.published_at = local_now().date()
    up = request.files.get('cover_file')
    if up and up.filename:
        try:
            p.cover_image = site_media.store_upload(up).url
        except ValueError as e:
            db.session.rollback()
            return _fail(str(e), back)
    elif request.form.get('clear_cover'):
        p.cover_image = None
    elif (request.form.get('cover_url') or '').strip():
        p.cover_image = request.form.get('cover_url').strip()[:400]
    db.session.commit()
    log_action('website.news_save', target=p)
    return _done('Post published.' if p.is_published else 'Draft saved.', back, post=_post_row(p))


@website_admin_bp.route('/news/<int:post_id>/delete', methods=['POST'])
@login_required
@module_required('website')
def news_delete(post_id):
    from models import NewsPost
    p = db.get_or_404(NewsPost, post_id)
    name = p.title
    db.session.delete(p); db.session.commit()
    log_action('website.news_delete', detail=name)
    return _done(f'Post “{name}” deleted.', url_for('website_admin.news'), redirect=url_for('website_admin.news'))


# --- analytics -------------------------------------------------------------
def _days():
    try:
        return min(90, max(7, int(request.args.get('days', 30))))
    except (TypeError, ValueError):
        return 30


@website_admin_bp.route('/analytics')
@login_required
@module_required('website')
def analytics():
    from utils import site_analytics
    days = _days()
    data = site_analytics.summary(days=days)
    peak = max((p['views'] for p in data['series']), default=0)
    busiest = max(data['series'], key=lambda p: p['views'], default=None)
    half = len(data['series']) // 2
    first = sum(p['views'] for p in data['series'][:half])
    second = sum(p['views'] for p in data['series'][half:])
    return _payload('analytics', days=days,
                    start=data['start'].strftime('%d %b'), end=data['end'].strftime('%d %b %Y'),
                    total=data['total_views'], unique=data['unique_visitors'], peak=peak,
                    busiest=(busiest['day'].strftime('%a %d %b') if busiest and peak else ''),
                    trend=(None if not first else round((second - first) / first * 100)),
                    series=[{'day': p['day'].isoformat(), 'label': p['day'].strftime('%a %d %b'),
                             'short': p['day'].strftime('%d %b'), 'views': p['views']} for p in data['series']],
                    top_pages=data['top_pages'], top_referrers=data['top_referrers'],
                    urls={'csv': url_for('website_admin.analytics_export', days=days)})


@website_admin_bp.route('/analytics/export')
@login_required
@module_required('website')
def analytics_export():
    import csv
    import io
    from utils import site_analytics
    from utils.web_exports import csv_response, formula_guard
    days = _days()
    data = site_analytics.summary(days=days)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Date', 'Page views'])
    for p in data['series']:
        w.writerow([p['day'].isoformat(), p['views']])
    w.writerow([])
    w.writerow(['Top page', 'Views'])
    for p in data['top_pages']:
        w.writerow([formula_guard(p['path']), p['views']])
    w.writerow([])
    w.writerow(['Referrer', 'Views'])
    for r in data['top_referrers']:
        w.writerow([formula_guard(r['source']), r['views']])
    log_action('website.analytics_export', detail=f'{days}d')
    return csv_response(buf.getvalue(), f'website-analytics-{days}d.csv')
