"""Website-Builder admin — authenticated, admin-only editing of the school's
public site: publish switch, theme, pages, and each page's component blocks.

All content is school-authored and rendered through Jinja autoescaping on the
public side; here we validate block types/variants against the registry and keep
props as plain JSON. Every change is audit-logged.
"""
import copy
import re

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, abort)
from sqlalchemy.orm.attributes import flag_modified

from models import db, SiteSettings, SitePage, SiteMedia
from utils.access_control import admin_required, login_required
from utils.audit import log_action
from utils.site_themes import preset_choices, PRESETS
from utils import site_blocks
from utils import site_media
from utils import site_admissions

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


@website_admin_bp.route('/')
@login_required
@admin_required
def index():
    settings = _seed_if_empty()
    pages = SitePage.query.order_by(SitePage.nav_order.asc(), SitePage.title.asc()).all()
    from models import AcademicSession
    try:
        sessions = AcademicSession.query.order_by(AcademicSession.name.desc()).all()
    except Exception:
        sessions = []
    from utils import site_ai
    return render_template('website/admin_overview.html', settings=settings, pages=pages,
                           presets=preset_choices(), public_home=url_for('website.home'),
                           adm=site_admissions.settings(), sessions=sessions,
                           pay_configured=_payments_configured(),
                           apply_url=url_for('website.apply'),
                           ai_available=site_ai.is_available())


def _payments_configured():
    try:
        from utils import payments
        return payments.is_configured()
    except Exception:
        return False


@website_admin_bp.route('/admissions', methods=['POST'])
@login_required
@admin_required
def admissions_settings():
    site_admissions.save_settings(
        is_open=(request.form.get('web_admissions_open') == 'on'),
        intro=request.form.get('intro'),
        fee=request.form.get('fee'),
        session_id=request.form.get('session_id'))
    log_action('website.admissions_settings')
    flash('Online admissions settings saved.', 'success')
    return redirect(url_for('website_admin.index'))


@website_admin_bp.route('/generate', methods=['POST'])
@login_required
@admin_required
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
        flash('Sorry — the site could not be generated. Please try again.', 'error')
        return redirect(url_for('website_admin.index'))
    log_action('website.generate', detail=f'{n} pages, ai={use_ai}')
    flash(f'Your website has been built — {n} pages ready to review and edit. '
          'Publish it when you’re happy.', 'success')
    return redirect(url_for('website_admin.index'))


@website_admin_bp.route('/publish', methods=['POST'])
@login_required
@admin_required
def publish():
    settings = SiteSettings.get()
    settings.published = (request.form.get('published') == 'on')
    db.session.commit()
    log_action('website.publish', detail=str(settings.published))
    flash('Website published.' if settings.published else 'Website unpublished (draft).', 'success')
    return redirect(url_for('website_admin.index'))


@website_admin_bp.route('/theme', methods=['POST'])
@login_required
@admin_required
def theme():
    settings = SiteSettings.get()
    preset = request.form.get('preset')
    theme = dict(settings.theme or {})
    if preset in PRESETS:
        theme['preset'] = preset
    # Optional individual overrides (colors) — blank clears to the preset value.
    for key in ('primary', 'accent'):
        val = (request.form.get(key) or '').strip()
        if val:
            theme[key] = val
        else:
            theme.pop(key, None)
    settings.theme = theme
    settings.seo_title = (request.form.get('seo_title') or '').strip()[:70] or None
    settings.seo_description = (request.form.get('seo_description') or '').strip()[:180] or None
    db.session.commit()
    log_action('website.theme', detail=theme.get('preset'))
    flash('Theme updated.', 'success')
    return redirect(url_for('website_admin.index'))


@website_admin_bp.route('/pages/new', methods=['POST'])
@login_required
@admin_required
def new_page():
    title = (request.form.get('title') or '').strip() or 'New page'
    slug = _slugify(request.form.get('slug') or title)
    if slug == SitePage.HOME_SLUG or SitePage.query.filter_by(slug=slug).first():
        flash('That page address is already taken.', 'error')
        return redirect(url_for('website_admin.index'))
    pg = SitePage(slug=slug, title=title, blocks=site_blocks.default_page_blocks(slug, title),
                  nav_order=(SitePage.query.count() + 1))
    db.session.add(pg); db.session.commit()
    log_action('website.page_create', target=pg)
    return redirect(url_for('website_admin.edit_page', page_id=pg.id))


@website_admin_bp.route('/pages/<int:page_id>')
@login_required
@admin_required
def edit_page(page_id):
    pg = db.get_or_404(SitePage, page_id)
    public_url = (url_for('website.home') if pg.slug == SitePage.HOME_SLUG
                  else url_for('website.page', slug=pg.slug))
    from utils import site_ai
    ai_available = site_ai.is_available()
    # which block indexes have editable text worth an AI draft
    ai_text_idx = {i for i, b in enumerate(pg.blocks or [])
                   if site_ai.copy_fields((b or {}).get('props'))} if ai_available else set()
    return render_template('website/admin_page.html', pg=pg,
                           blocks=pg.blocks or [], catalogue=site_blocks.catalogue(),
                           registry=site_blocks.REGISTRY, public_url=public_url,
                           ai_available=ai_available, ai_text_idx=ai_text_idx)


@website_admin_bp.route('/pages/<int:page_id>/meta', methods=['POST'])
@login_required
@admin_required
def save_page_meta(page_id):
    pg = db.get_or_404(SitePage, page_id)
    pg.title = (request.form.get('title') or pg.title).strip()[:120]
    pg.meta_description = (request.form.get('meta_description') or '').strip()[:180] or None
    pg.show_in_nav = (request.form.get('show_in_nav') == 'on')
    pg.is_published = (request.form.get('is_published') == 'on')
    try:
        pg.nav_order = int(request.form.get('nav_order') or pg.nav_order)
    except (TypeError, ValueError):
        pass
    db.session.commit()
    log_action('website.page_meta', target=pg)
    flash('Page settings saved.', 'success')
    return redirect(url_for('website_admin.edit_page', page_id=pg.id))


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
@admin_required
def add_block(page_id):
    pg = db.get_or_404(SitePage, page_id)
    btype = request.form.get('type')
    if not site_blocks.valid_type(btype):
        abort(400)
    blocks = _blocks(pg)
    blocks.append(site_blocks.block_defaults(btype))
    _save_blocks(pg, blocks)
    log_action('website.block_add', detail=btype, target=pg)
    return redirect(url_for('website_admin.edit_page', page_id=pg.id, _anchor='b%d' % (len(blocks) - 1)))


@website_admin_bp.route('/pages/<int:page_id>/block/<int:idx>/op', methods=['POST'])
@login_required
@admin_required
def block_op(page_id, idx):
    pg = db.get_or_404(SitePage, page_id)
    blocks = _blocks(pg)
    if not (0 <= idx < len(blocks)):
        abort(404)
    op = request.form.get('op')
    if op == 'up' and idx > 0:
        blocks[idx - 1], blocks[idx] = blocks[idx], blocks[idx - 1]
    elif op == 'down' and idx < len(blocks) - 1:
        blocks[idx + 1], blocks[idx] = blocks[idx], blocks[idx + 1]
    elif op == 'delete':
        blocks.pop(idx)
    elif op == 'duplicate':
        import copy
        blocks.insert(idx + 1, copy.deepcopy(blocks[idx]))
    elif op == 'toggle':
        blocks[idx]['enabled'] = not blocks[idx].get('enabled', True)
    elif op == 'variant':
        variant = request.form.get('variant')
        if site_blocks.valid_variant(blocks[idx]['type'], variant):
            blocks[idx]['variant'] = variant
    _save_blocks(pg, blocks)
    log_action('website.block_op', detail=op, target=pg)
    return redirect(url_for('website_admin.edit_page', page_id=pg.id, _anchor='b%d' % min(idx, len(blocks) - 1) if blocks else None))


@website_admin_bp.route('/pages/<int:page_id>/block/<int:idx>/content', methods=['POST'])
@login_required
@admin_required
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
@admin_required
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
        flash('AI copywriting isn’t set up on this site.', 'error')
        return redirect(url_for('website_admin.edit_page', page_id=pg.id, _anchor='b%d' % idx))
    block = blocks[idx]
    props = dict(block.get('props') or {})
    fields = site_ai.copy_fields(props)
    if not fields:
        flash('This section has no editable text to write.', 'error')
        return redirect(url_for('website_admin.edit_page', page_id=pg.id, _anchor='b%d' % idx))
    spec = site_blocks.REGISTRY.get(block['type']) or {}
    from utils.site_data import public_context
    branding = public_context()['branding']
    suggestions = site_ai.suggest_block_copy(
        spec.get('label', block['type']), fields, props, branding=branding,
        tone=(request.form.get('tone') or '').strip()[:60],
        keywords=(request.form.get('keywords') or '').strip()[:200])
    if not suggestions:
        flash('AI couldn’t generate copy just now — please try again.', 'error')
        return redirect(url_for('website_admin.edit_page', page_id=pg.id, _anchor='b%d' % idx))
    props.update(suggestions)
    block['props'] = props
    _save_blocks(pg, blocks)
    log_action('website.block_ai', detail=block['type'], target=pg)
    flash('AI draft added — review the wording below and click Save content to publish it.', 'success')
    return redirect(url_for('website_admin.edit_page', page_id=pg.id, _anchor='b%d' % idx))


@website_admin_bp.route('/pages/<int:page_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_page(page_id):
    pg = db.get_or_404(SitePage, page_id)
    if pg.slug == SitePage.HOME_SLUG:
        flash('The home page cannot be deleted.', 'error')
        return redirect(url_for('website_admin.edit_page', page_id=pg.id))
    name = pg.title
    db.session.delete(pg); db.session.commit()
    log_action('website.page_delete', detail=name)
    flash(f'Page “{name}” deleted.', 'success')
    return redirect(url_for('website_admin.index'))


# --- media library ---------------------------------------------------------
@website_admin_bp.route('/media')
@login_required
@admin_required
def media_library():
    items = SiteMedia.query.order_by(SiteMedia.created_at.desc()).all()
    total = sum(m.bytes or 0 for m in items)
    from utils import media_storage
    labels = {'db': 'this school’s database', 'local': 'a filesystem volume', 's3': 'object storage (S3/R2)'}
    where = labels.get(media_storage.backend(), media_storage.backend())
    return render_template('website/admin_media.html', items=items, total=total, storage_where=where)


@website_admin_bp.route('/media/upload', methods=['POST'])
@login_required
@admin_required
def media_upload():
    for up in request.files.getlist('file'):
        if up and up.filename:
            try:
                m = site_media.store_upload(up)
                log_action('website.media_upload', detail='%dx%d' % (m.width or 0, m.height or 0))
            except ValueError as e:
                flash(str(e), 'error')
    flash('Image(s) uploaded.', 'success')
    return redirect(url_for('website_admin.media_library'))


# --- analytics -------------------------------------------------------------
@website_admin_bp.route('/analytics')
@login_required
@admin_required
def analytics():
    from utils import site_analytics
    try:
        days = min(90, max(7, int(request.args.get('days', 30))))
    except (TypeError, ValueError):
        days = 30
    data = site_analytics.summary(days=days)
    peak = max((p['views'] for p in data['series']), default=0)
    return render_template('website/admin_analytics.html', data=data, peak=peak, days=days)


@website_admin_bp.route('/analytics/export')
@login_required
@admin_required
def analytics_export():
    import csv
    import io
    from utils import site_analytics
    from utils.web_exports import csv_response
    try:
        days = min(90, max(7, int(request.args.get('days', 30))))
    except (TypeError, ValueError):
        days = 30
    data = site_analytics.summary(days=days)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Date', 'Page views'])
    for p in data['series']:
        w.writerow([p['day'].isoformat(), p['views']])
    w.writerow([])
    w.writerow(['Top page', 'Views'])
    for p in data['top_pages']:
        w.writerow([p['path'], p['views']])
    w.writerow([])
    w.writerow(['Referrer', 'Views'])
    for r in data['top_referrers']:
        w.writerow([r['source'], r['views']])
    log_action('website.analytics_export', detail=f'{days}d')
    return csv_response(buf.getvalue(), f'website-analytics-{days}d.csv')


@website_admin_bp.route('/media/<int:media_id>/delete', methods=['POST'])
@login_required
@admin_required
def media_delete(media_id):
    m = db.get_or_404(SiteMedia, media_id)
    from utils import media_storage
    media_storage.delete(m)                    # remove filesystem/object bytes too
    db.session.delete(m); db.session.commit()
    log_action('website.media_delete', detail=str(media_id))
    flash('Image deleted.', 'success')
    return redirect(url_for('website_admin.media_library'))
