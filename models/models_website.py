"""Website Builder — a school's public, component-driven website.

Two rows types make up a site, both living in the school's own tenant DB (so a
site is isolated exactly like every other record):

* :class:`SiteSettings` — one row per school: the theme tokens (palette, fonts,
  radius, button style…) that make two schools look different without code, the
  global publish switch, nav config and SEO defaults.
* :class:`SitePage` — one row per public page; its ``blocks`` is an ordered JSON
  list of ``{type, variant, enabled, props}`` component instances. The public
  renderer turns each block into HTML via the block registry, pulling live data
  (news, events, branding) from the rest of the SIS so nothing is duplicated.

Nothing here stores student PII; data-backed blocks read only published,
non-personal content through ``utils.site_data``.
"""
from models.models import db, local_now


class SiteSettings(db.Model):
    __tablename__ = 'site_settings'

    id = db.Column(db.Integer, primary_key=True)
    # Global publish switch: while False the public site 404s (draft mode).
    published = db.Column(db.Boolean, default=False, nullable=False)
    # Theme tokens applied as CSS custom properties by the public shell — this is
    # what lets two schools look genuinely different from the same components.
    # {preset, primary, accent, ink, surface, font_head, font_body, radius,
    #  button, shadow, nav_style}
    theme = db.Column(db.JSON, default=dict)
    # SEO / social defaults (per-page values override these).
    seo_title = db.Column(db.String(70))
    seo_description = db.Column(db.String(180))
    # Extra nav links a school adds by hand: [{label, href, external}].
    nav_extra = db.Column(db.JSON, default=list)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

    @staticmethod
    def get():
        """The singleton settings row for this school, created on first use."""
        row = SiteSettings.query.first()
        if row is None:
            row = SiteSettings(published=False, theme={}, nav_extra=[])
            db.session.add(row)
            db.session.commit()
        return row


class SiteMedia(db.Model):
    """An image for the public site, stored IN the school's own tenant database
    (not a shared filesystem) so it is isolated exactly like every other record
    and survives ephemeral containers. Served — resized and optimised — through
    a cached route. Deliberately small: uploads are capped and downscaled."""
    __tablename__ = 'site_media'

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(160))
    mime = db.Column(db.String(40), nullable=False)
    # Where the bytes live: 'db' keeps them here in `data`; 'local'/'s3' store
    # them elsewhere and keep only the `storage_key` reference.
    storage = db.Column(db.String(10), default='db', nullable=False)
    storage_key = db.Column(db.String(300))
    data = db.Column(db.LargeBinary)                 # populated only for storage='db'
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    bytes = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=local_now)

    @property
    def url(self):
        """A direct CDN/bucket URL when one is configured (best performance),
        else the app's cached, publish-gated serving route."""
        from utils import media_storage
        pub = media_storage.public_url(self)
        if pub:
            return pub
        from flask import url_for
        return url_for('website.media', media_id=self.id)


class SitePage(db.Model):
    __tablename__ = 'site_pages'

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    title = db.Column(db.String(120), nullable=False)
    # Ordered component instances: [{type, variant, enabled, props}].
    blocks = db.Column(db.JSON, default=list)
    is_published = db.Column(db.Boolean, default=True, nullable=False)
    show_in_nav = db.Column(db.Boolean, default=True, nullable=False)
    nav_order = db.Column(db.Integer, default=100)
    meta_description = db.Column(db.String(180))
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

    HOME_SLUG = 'home'

    def __repr__(self):
        return f'<SitePage {self.slug!r}>'


class SiteViewDaily(db.Model):
    """Privacy-friendly, first-party traffic: one aggregated row per (day, path)
    holding a page-view count. No cookies, no third-party trackers, no raw IPs —
    just server-side counters, so a school gets useful numbers without shipping
    visitor data to anyone."""
    __tablename__ = 'site_view_daily'

    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.Date, nullable=False, index=True)
    path = db.Column(db.String(200), nullable=False)
    views = db.Column(db.Integer, default=0, nullable=False)
    __table_args__ = (db.UniqueConstraint('day', 'path', name='uq_site_view_daily'),)


class SiteReferrerDaily(db.Model):
    """Aggregated referrer breakdown: one row per (day, source) where source is
    the referring host (e.g. ``google.com``) or ``'direct'``."""
    __tablename__ = 'site_referrer_daily'

    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.Date, nullable=False, index=True)
    source = db.Column(db.String(120), nullable=False)
    views = db.Column(db.Integer, default=0, nullable=False)
    __table_args__ = (db.UniqueConstraint('day', 'source', name='uq_site_referrer_daily'),)


class SiteVisitorDaily(db.Model):
    """Unique-visitor counting without identifying anyone: one row per (day,
    visitor_hash), where the hash is a per-day, salted, non-reversible digest of
    IP+user-agent. Rows count distinct visitors for a day and are safe to purge."""
    __tablename__ = 'site_visitor_daily'

    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.Date, nullable=False, index=True)
    visitor_hash = db.Column(db.String(64), nullable=False)
    __table_args__ = (db.UniqueConstraint('day', 'visitor_hash', name='uq_site_visitor_daily'),)
