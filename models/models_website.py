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
