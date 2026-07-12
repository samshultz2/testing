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
from utils.site_themes import theme_css_vars, resolve_theme
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


@website_bp.route('/')
def home():
    page, settings = _load(SitePage.HOME_SLUG)
    return _render(page, settings)


@website_bp.route('/<slug>')
def page(slug):
    if slug in ('sitemap.xml', 'robots.txt'):     # handled by their own routes
        abort(404)
    page, settings = _load(slug)
    return _render(page, settings)


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
