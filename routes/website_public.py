"""Public, unauthenticated rendering of a school's Website-Builder site.

Served from the school's own tenant, so it is isolated exactly like the rest of
that school's data. It renders ONLY published pages of a published site (drafts
404 for the public), and every data-backed block reads through the PII-safe
``utils.site_data`` provider — no student/parent/staff record is ever exposed.
Logged-in admins may preview an unpublished site (with a Draft banner).
"""
import json

from flask import Blueprint, render_template, abort, request, session, Response, url_for, redirect

from models import db, SiteSettings, SitePage, SiteMedia
from utils.security import rate_limited
from utils.site_themes import theme_css_vars, resolve_theme, google_fonts_href
from utils.site_data import public_context

website_bp = Blueprint('website', __name__, url_prefix='/site')


def _is_admin_preview():
    from utils.access_control import is_admin
    return bool(session.get('logged_in') and is_admin())


def _nav_links():
    """Public nav: published, in-nav pages ordered by nav_order, plus any
    hand-added external links from settings."""
    pages = (SitePage.query.filter_by(is_published=True, show_in_nav=True)
             .order_by(SitePage.nav_order.asc(), SitePage.title.asc()).all())
    links = [{'label': p.title,
              'href': url_for('website.home') if p.slug == SitePage.HOME_SLUG
              else url_for('website.page', slug=p.slug)}
             for p in pages]
    for extra in (SiteSettings.get().nav_extra or []):
        if extra.get('label') and extra.get('href'):
            links.append({'label': extra['label'], 'href': extra['href']})
    return links


def _jsonld(branding, origin):
    data = {'@context': 'https://schema.org', '@type': 'School',
            'name': branding['name'], 'url': origin}
    if branding['logo_url']:
        data['logo'] = origin + branding['logo_url']
    if branding['address']:
        data['address'] = branding['address']
    if branding['phone']:
        data['telephone'] = branding['phone']
    if branding['email']:
        data['email'] = branding['email']
    return json.dumps(data)


def _render(page, settings):
    ctx = public_context()
    branding = ctx['branding']
    origin = request.url_root.rstrip('/')
    theme = resolve_theme(settings.theme)
    seo = {
        'title': (page.title + ' · ' + branding['name']) if page.slug != SitePage.HOME_SLUG
                 else (settings.seo_title or branding['name']),
        'description': (page.meta_description or settings.seo_description
                        or branding['motto'] or f"Welcome to {branding['name']}."),
        'canonical': origin + request.path,
        'origin': origin,
        'jsonld': _jsonld(branding, origin),
    }
    return render_template('website/public_page.html',
                           page=page, blocks=[b for b in (page.blocks or []) if b.get('enabled', True)],
                           ctx=ctx, branding=branding, nav=_nav_links(),
                           theme=theme, theme_vars=theme_css_vars(settings.theme),
                           fonts_href=google_fonts_href(settings.theme),
                           seo=seo, draft_banner=(not settings.published),
                           now_year=__import__('datetime').date.today().year)


def _load(slug):
    settings = SiteSettings.get()
    if not settings.published and not _is_admin_preview():
        abort(404)                            # draft site is invisible to the public
    page = SitePage.query.filter_by(slug=slug).first()
    if page is None or (not page.is_published and not _is_admin_preview()):
        abort(404)
    return page, settings


def _track(settings):
    """Count a public page view — never for an admin previewing a draft, and
    never in a way that can break the page being served."""
    if not settings.published or _is_admin_preview():
        return
    try:
        from utils import site_analytics
        site_analytics.record(request.path, request)
    except Exception:
        pass


@website_bp.route('/')
def home():
    page, settings = _load(SitePage.HOME_SLUG)
    html = _render(page, settings)
    _track(settings)
    return html


_RESERVED_SLUGS = {'sitemap.xml', 'robots.txt', 'media', 'apply', 'assignments'}


@website_bp.route('/assignments/<int:aid>/download')
def assignment_download(aid):
    """Serve a published holiday-assignment document for download. Gated behind a
    published site (or admin preview) and the assignment's own publish flag."""
    from models import HolidayAssignment
    settings = SiteSettings.get()
    if not settings.published and not _is_admin_preview():
        abort(404)
    a = db.session.get(HolidayAssignment, aid)
    if a is None or (not a.is_published and not _is_admin_preview()) or a.data is None:
        abort(404)
    fname = (a.filename or f'assignment-{a.id}').replace('"', '')
    resp = Response(a.data, mimetype=a.mime or 'application/octet-stream')
    resp.headers['Content-Disposition'] = f'attachment; filename="{fname}"'
    resp.headers['Content-Length'] = str(a.bytes or len(a.data))
    return resp


@website_bp.route('/<slug>')
def page(slug):
    if slug in _RESERVED_SLUGS:                    # handled by their own routes
        abort(404)
    page, settings = _load(slug)
    html = _render(page, settings)
    _track(settings)
    return html


# --- public admissions application -----------------------------------------
def _chrome_ctx(page_title, page_desc, extra=None):
    """Themed page chrome (branding, theme, fonts, nav, seo) for standalone pages
    that aren't block-rendered (apply flow, news articles)."""
    from utils.site_themes import theme_css_vars, resolve_theme
    from utils.site_data import public_context
    s = SiteSettings.get()
    branding = public_context()['branding']
    origin = request.url_root.rstrip('/')
    seo = {'title': f"{page_title} · {branding['name']}",
           'description': page_desc or f"{branding['name']}.",
           'canonical': origin + request.path, 'origin': origin,
           'jsonld': _jsonld(branding, origin)}
    base = {'branding': branding, 'nav': _nav_links(),
            'theme': resolve_theme(s.theme), 'theme_vars': theme_css_vars(s.theme),
            'fonts_href': google_fonts_href(s.theme),
            'now_year': __import__('datetime').date.today().year,
            'draft_banner': (not s.published), 'seo': seo}
    base.update(extra or {})
    return base


def _apply_ctx(extra=None):
    """Themed context for the standalone admissions pages."""
    branding_name = SiteSettings.get()  # noqa: F841 (kept for clarity)
    title = (extra or {}).get('page_title') or 'Apply'
    from utils.site_data import public_branding
    desc = f"Apply for admission to {public_branding()['name']}."
    return _chrome_ctx(title, desc, extra)


@website_bp.route('/news/<slug>')
def news_article(slug):
    """A single published news/blog article."""
    from models import NewsPost
    settings = SiteSettings.get()
    if not settings.published and not _is_admin_preview():
        abort(404)
    post = NewsPost.query.filter_by(slug=slug).first()
    if post is None or (not post.is_published and not _is_admin_preview()):
        abort(404)
    return render_template('website/news_article.html',
                           **_chrome_ctx(post.title, (post.excerpt or ''), {'post': post}))


def _apply_available():
    """(settings_row, adm_cfg) if the public may apply now, else (None, None)."""
    from utils import site_admissions
    s = SiteSettings.get()
    if not s.published and not _is_admin_preview():
        return None, None
    return s, site_admissions.settings()


@website_bp.route('/apply', methods=['GET', 'POST'])
@rate_limited('site_apply', max_requests=30, window_minutes=15)
def apply():
    from utils import site_admissions, payments
    s, cfg = _apply_available()
    if s is None:
        abort(404)
    fee = cfg['fee']
    render_kwargs = dict(cfg=cfg, fee=fee, classes=site_admissions.class_choices(),
                         pay_configured=payments.is_configured(), errors={}, form={})
    if request.method == 'POST':
        if not cfg['open']:
            abort(404)
        if (request.form.get('website') or '').strip():      # honeypot — silently drop bots
            return render_template('website/apply_done.html', **_apply_ctx({'app_no': None, 'bot': True}))
        clean, errors = site_admissions.validate(request.form)
        if errors:
            render_kwargs.update(errors=errors, form=request.form)
            return render_template('website/apply.html', **_apply_ctx(render_kwargs))
        # Fee due and payments live → pay first, create on verified callback.
        if fee > 0 and payments.is_configured():
            ref = payments.new_reference('APP')
            session['apply_pending'] = {'ref': ref, 'fee': fee, 'data': _jsonable(clean)}
            res = payments.initialize(
                email=(clean['parent_email'] or 'applicant@example.com'),
                amount_naira=fee, reference=ref,
                callback_url=url_for('website.apply_callback', _external=True),
                metadata={'purpose': 'application_fee'})
            if res.get('ok') and res.get('authorization_url'):
                return redirect(res['authorization_url'])
            render_kwargs.update(errors={'_': res.get('error') or 'Could not start payment.'},
                                 form=request.form)
            return render_template('website/apply.html', **_apply_ctx(render_kwargs))
        # Free (or offline-fee) → create immediately.
        a = site_admissions.create_applicant(clean)
        return render_template('website/apply_done.html',
                               **_apply_ctx({'app_no': a.application_no, 'fee_note':
                                             (fee > 0 and not payments.is_configured())}))
    return render_template('website/apply.html', **_apply_ctx(render_kwargs))


@website_bp.route('/apply/callback')
def apply_callback():
    from utils import site_admissions, payments
    pending = session.get('apply_pending') or {}
    ref = request.args.get('reference') or request.args.get('trxref')
    if not ref or ref != pending.get('ref'):
        return render_template('website/apply_done.html',
                               **_apply_ctx({'app_no': None, 'error': 'We could not match that payment.'}))
    res = payments.verify(ref)
    session.pop('apply_pending', None)             # consume so a replay can't double-create
    if not res.get('ok'):
        return render_template('website/apply_done.html',
                               **_apply_ctx({'app_no': None, 'error':
                                             'Payment was not completed. Please try again.'}))
    clean = _from_jsonable(pending['data'])
    a = site_admissions.create_applicant(clean, fee_paid=pending.get('fee') or 0, fee_reference=ref)
    return render_template('website/apply_done.html',
                           **_apply_ctx({'app_no': a.application_no, 'paid': True}))


@website_bp.route('/apply/track', methods=['GET', 'POST'])
@rate_limited('site_track', max_requests=40, window_minutes=15)
def apply_track():
    from utils import site_admissions
    s = SiteSettings.get()
    if not s.published and not _is_admin_preview():
        abort(404)
    result = None
    searched = False
    if request.method == 'POST':
        searched = True
        result = site_admissions.find_application(
            request.form.get('application_no', ''), request.form.get('surname', ''))
    return render_template('website/apply_track.html',
                           **_apply_ctx({'result': result, 'searched': searched}))


def _jsonable(clean):
    d = dict(clean)
    if d.get('date_of_birth'):
        d['date_of_birth'] = d['date_of_birth'].isoformat()
    return d


def _from_jsonable(d):
    from datetime import date as _d
    d = dict(d or {})
    if d.get('date_of_birth'):
        try:
            d['date_of_birth'] = _d.fromisoformat(d['date_of_birth'])
        except (ValueError, TypeError):
            d['date_of_birth'] = None
    return d


@website_bp.route('/media/<int:media_id>')
def media(media_id):
    """Serve a site image from the tenant DB. Public once the site is published
    (or to an admin previewing a draft). Long-cached + ETag'd — the bytes for a
    given id never change (edits create a new row)."""
    settings = SiteSettings.get()
    if not settings.published and not _is_admin_preview():
        abort(404)
    row = db.session.get(SiteMedia, media_id)
    if row is None:
        abort(404)
    # If a public CDN/bucket URL exists, send the visitor straight there.
    from utils import media_storage
    pub = media_storage.public_url(row)
    if pub:
        return redirect(pub, code=302)
    etag = 'sm-%d-%d' % (row.id, row.bytes or 0)
    if request.headers.get('If-None-Match') == etag:
        return Response(status=304)
    try:
        data = media_storage.load(row)
    except Exception:
        abort(404)
    resp = Response(data, mimetype=row.mime)
    resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    resp.headers['ETag'] = etag
    return resp


@website_bp.route('/sitemap.xml')
def sitemap():
    settings = SiteSettings.get()
    if not settings.published:
        abort(404)
    origin = request.url_root.rstrip('/')
    pages = SitePage.query.filter_by(is_published=True).all()
    urls = []
    for p in pages:
        loc = origin + (url_for('website.home') if p.slug == SitePage.HOME_SLUG
                        else url_for('website.page', slug=p.slug))
        lastmod = (p.updated_at or p.created_at)
        urls.append('<url><loc>{}</loc>{}</url>'.format(
            loc, ('<lastmod>%s</lastmod>' % lastmod.date().isoformat()) if lastmod else ''))
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           + ''.join(urls) + '</urlset>')
    return Response(xml, mimetype='application/xml')


@website_bp.route('/robots.txt')
def robots():
    settings = SiteSettings.get()
    origin = request.url_root.rstrip('/')
    if not settings.published:
        return Response('User-agent: *\nDisallow: /\n', mimetype='text/plain')
    body = ('User-agent: *\nAllow: /site\n'
            f'Sitemap: {origin}{url_for("website.sitemap")}\n')
    return Response(body, mimetype='text/plain')
