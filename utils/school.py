"""Shared school identity (name, contacts and the one school-wide logo).

A school uploads a single logo under Settings → School Info; it is resized once
and reused everywhere — the app shell header and every printout (term report
cards, Mock-WAEC slips & broadsheets, timetables, receipts). This module is the
single source of truth so each of those builders pulls the same profile.
"""
import os

from flask import current_app, url_for

from models import SchoolSettings

# Path (relative to static/) where the uploaded, resized logo is stored.
LOGO_REL = 'uploads/branding/logo.png'


def logo_rel():
    """The logo's static-relative path for THIS school.

    Multi-tenant: each customer school gets its own file
    (``uploads/branding/<subdomain>/logo.png``) so schools never share a logo.
    The owner school and single-tenant deployments keep the original shared path
    (so an already-uploaded logo isn't lost)."""
    try:
        from utils.tenant_runtime import current_tenant
        from utils import billing
        t = current_tenant()
        if t is not None and not billing.is_owner(t):
            return f'uploads/branding/{t.subdomain}/logo.png'
    except Exception:
        pass
    return LOGO_REL


def logo_path():
    """Absolute filesystem path of the uploaded logo, or None if not present.

    Authoritative check for reportlab / PIL builders — they need a real file."""
    try:
        p = os.path.join(current_app.root_path, 'static', logo_rel())
    except Exception:
        return None
    return p if os.path.exists(p) else None


def logo_url():
    """Cache-busted static URL of THIS school's uploaded logo, or '' if none.

    Built from the (per-school) logo path + its mtime, so it is always correct
    per tenant and never points at a missing or another school's image."""
    p = logo_path()
    if not p:
        return ''
    try:
        return url_for('static', filename=logo_rel()) + ('?v=%d' % int(os.path.getmtime(p)))
    except Exception:
        return ''


def school_profile():
    """School identity reused by the shell header and every printout.

    Returns ``{name, address, phone, email, motto, logo_url, logo_path}`` where
    ``logo_path`` is an absolute fs path (for reportlab/PIL) or None, and
    ``logo_url`` is a static URL (for templates) or ''."""
    g = SchoolSettings.get
    return {
        'name': g('school_name', '') or '',
        'address': g('school_address', '') or '',
        'phone': g('school_phone', '') or '',
        'email': g('school_email', '') or '',
        'motto': g('school_motto', '') or '',
        'logo_url': logo_url(),
        'logo_path': logo_path(),
    }


def logo_header_flowable(logo, items, gap_mm=4):
    """A centred letterhead row: the ``logo`` immediately to the left of a text
    block, with the whole logo+text unit centred on the page.

    ``items`` is a list of ``(paragraph, plain_text, font_name, font_size)`` — the
    paragraphs render in the block, while their plain text + font is used to size
    the text column (so the centred lines sit snug against the logo instead of
    being page-centred away from it). Returns a reportlab flowable, or None when
    there is no logo (callers then lay the plain block out themselves)."""
    block = [it[0] for it in items]
    if logo is None or not block:
        return None
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.lib.units import mm
    from reportlab.platypus import Table, TableStyle
    text_w = 0
    for _para, text, font_name, font_size in items:
        if text:
            text_w = max(text_w, stringWidth(text, font_name, font_size))
    text_w += 8                                  # a little slack so nothing wraps
    logo_col = getattr(logo, 'drawWidth', 0) + gap_mm * mm
    t = Table([[logo, block]], colWidths=[logo_col, text_w])
    t.hAlign = 'CENTER'
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return t


def logo_flowable(max_h_mm=18, max_w_mm=34, path=None):
    """A reportlab ``Image`` flowable for the school logo (aspect preserved), or
    None when no logo is available. ``path`` overrides the uploaded logo (used by
    builders that already resolved it via ``school_profile``); sized to fit within
    max_h × max_w (mm)."""
    p = path or logo_path()
    if not p or not os.path.exists(p):
        return None
    try:
        from reportlab.platypus import Image as RLImage
        from reportlab.lib.units import mm
        from PIL import Image as PILImage
        with PILImage.open(p) as im:
            iw, ih = im.size
        ratio = (iw / ih) if ih else 1.0
        h = max_h_mm * mm
        w = h * ratio
        if w > max_w_mm * mm:
            w = max_w_mm * mm
            h = w / ratio if ratio else h
        return RLImage(p, width=w, height=h)
    except Exception:
        return None
