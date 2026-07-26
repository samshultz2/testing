"""Document design *collections* (themes) — the scalable foundation of the
Academic Documents & Publishing system.

A **collection** is a named visual identity (palette + typography + border art +
seal style). One generic renderer, driven by a collection, produces a fully
distinct-looking document — so every document type instantly gains the whole
library of collections (Classic, Modern, Premium, Executive, Luxury, Government,
…) without hand-authoring a bespoke layout for each combination.

This module owns:
  * ``COLLECTIONS`` — the theme registry (one entry per named collection).
  * ``page_decorator(key)`` — a canvas painter that draws that collection's
    border / background art on every page.
  * ``render_certificate(key, content, …)`` — a page-filling certificate body
    (used by the certificate/award/graduation document family).

Everything is data-driven; a school's own branding (colours, motto, logo) is
layered on top by the caller via ``branding_overrides``.
"""
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.graphics.shapes import Drawing, Circle, String, Polygon


def _c(v):
    return colors.HexColor(v)


# ---------------------------------------------------------------------------
# collection registry — each is (palette + fonts + border art + seal style)
# ---------------------------------------------------------------------------
# border: one of double | gold_double | corners | keyline | deco | ribbon |
#         floral | plain   (drawn by _PAINTERS below)
# serif : True → Times family (formal), False → Helvetica family (contemporary)
COLLECTIONS = {
    'classic':        {'name': 'Classic',        'primary': '#0e3a2f', 'accent': '#0e8a64', 'gold': '#b7791f', 'border': 'double',      'serif': True},
    'modern':         {'name': 'Modern',         'primary': '#1e3a8a', 'accent': '#0ea5e9', 'gold': '#c99700', 'border': 'corners',     'serif': False},
    'premium':        {'name': 'Premium',        'primary': '#4c1d95', 'accent': '#7c3aed', 'gold': '#b7791f', 'border': 'gold_double', 'serif': True},
    'executive':      {'name': 'Executive',      'primary': '#111827', 'accent': '#374151', 'gold': '#9ca3af', 'border': 'keyline',     'serif': False},
    'luxury':         {'name': 'Luxury',         'primary': '#3b0764', 'accent': '#a21caf', 'gold': '#d4af37', 'border': 'deco',        'serif': True},
    'government':     {'name': 'Government',      'primary': '#14532d', 'accent': '#166534', 'gold': '#b45309', 'border': 'double',      'serif': True},
    'british':        {'name': 'British School',  'primary': '#7f1d1d', 'accent': '#991b1b', 'gold': '#b7791f', 'border': 'floral',      'serif': True},
    'american':       {'name': 'American High',   'primary': '#1e3a8a', 'accent': '#b91c1c', 'gold': '#c99700', 'border': 'ribbon',      'serif': False},
    'international':   {'name': 'International',   'primary': '#0f766e', 'accent': '#0891b2', 'gold': '#b7791f', 'border': 'corners',     'serif': False},
    'scandinavian':   {'name': 'Scandinavian',   'primary': '#0f172a', 'accent': '#64748b', 'gold': '#94a3b8', 'border': 'plain',       'serif': False},
    'contemporary':   {'name': 'Contemporary',   'primary': '#0369a1', 'accent': '#06b6d4', 'gold': '#f59e0b', 'border': 'keyline',     'serif': False},
    'minimalist':     {'name': 'Minimalist',     'primary': '#111827', 'accent': '#6b7280', 'gold': '#9ca3af', 'border': 'plain',       'serif': False},
    'elegant':        {'name': 'Elegant',        'primary': '#14532d', 'accent': '#b7791f', 'gold': '#d4af37', 'border': 'ribbon',      'serif': True},
    'traditional':    {'name': 'Traditional',    'primary': '#7c2d12', 'accent': '#9a3412', 'gold': '#b45309', 'border': 'floral',      'serif': True},
    'academic':       {'name': 'Academic',       'primary': '#1e293b', 'accent': '#334155', 'gold': '#b7791f', 'border': 'double',      'serif': True},
    'prestige':       {'name': 'Prestige',       'primary': '#422006', 'accent': '#713f12', 'gold': '#d4af37', 'border': 'gold_double', 'serif': True},
    'royal':          {'name': 'Royal',          'primary': '#1e1b4b', 'accent': '#4338ca', 'gold': '#d4af37', 'border': 'deco',        'serif': True},
    'heritage':       {'name': 'Heritage',       'primary': '#713f12', 'accent': '#92400e', 'gold': '#b45309', 'border': 'floral',      'serif': True},
    'platinum':       {'name': 'Platinum',       'primary': '#334155', 'accent': '#475569', 'gold': '#94a3b8', 'border': 'keyline',     'serif': False},
    'gold':           {'name': 'Gold',           'primary': '#713f12', 'accent': '#b7791f', 'gold': '#d4af37', 'border': 'gold_double', 'serif': True},
    'green_heritage': {'name': 'Green Heritage',  'primary': '#14532d', 'accent': '#15803d', 'gold': '#b7791f', 'border': 'double',      'serif': True},
    'corporate':      {'name': 'Corporate',      'primary': '#0c4a6e', 'accent': '#0369a1', 'gold': '#64748b', 'border': 'ribbon',      'serif': False},
    'creative':       {'name': 'Creative',       'primary': '#9d174d', 'accent': '#db2777', 'gold': '#f59e0b', 'border': 'corners',     'serif': False},
    'sapphire':       {'name': 'Sapphire',       'primary': '#172554', 'accent': '#2563eb', 'gold': '#c99700', 'border': 'deco',        'serif': False},
}
DEFAULT_COLLECTION = 'classic'


def resolve(key, branding=None):
    """The theme for ``key`` (falls back to the default), with optional per-school
    ``branding`` overrides layered on top (custom primary/accent/gold colours)."""
    t = dict(COLLECTIONS.get(key) or COLLECTIONS[DEFAULT_COLLECTION])
    if branding:
        for src, dst in (('primary_color', 'primary'), ('accent_color', 'accent'),
                         ('secondary_color', 'gold')):
            v = (branding.get(src) or '').strip()
            if v.startswith('#') and len(v) in (4, 7):
                t[dst] = v
    return t


def list_collections():
    return [{'key': k, 'name': v['name']} for k, v in COLLECTIONS.items()]


def fonts(theme):
    """(heading, body, name) font names for a theme (standard PDF fonts only)."""
    if theme.get('serif'):
        return 'Times-Bold', 'Times-Roman', 'Times-BoldItalic'
    return 'Helvetica-Bold', 'Helvetica', 'Helvetica-Bold'


# ---------------------------------------------------------------------------
# border / background painters (drawn on the page canvas)
# ---------------------------------------------------------------------------
def _poly(canvas, pts):
    p = canvas.beginPath()
    p.moveTo(*pts[0])
    for x, y in pts[1:]:
        p.lineTo(x, y)
    p.close()
    return p


def _double(canvas, w, h, primary, gold):
    canvas.setStrokeColor(primary)
    canvas.setLineWidth(4)
    canvas.rect(9 * mm, 9 * mm, w - 18 * mm, h - 18 * mm, stroke=1, fill=0)
    canvas.setStrokeColor(gold)
    canvas.setLineWidth(1)
    canvas.rect(12 * mm, 12 * mm, w - 24 * mm, h - 24 * mm, stroke=1, fill=0)


def _gold_double(canvas, w, h, primary, gold):
    canvas.setStrokeColor(gold)
    canvas.setLineWidth(4.5)
    canvas.rect(8.5 * mm, 8.5 * mm, w - 17 * mm, h - 17 * mm, stroke=1, fill=0)
    canvas.setLineWidth(1.2)
    canvas.rect(12 * mm, 12 * mm, w - 24 * mm, h - 24 * mm, stroke=1, fill=0)


def _keyline(canvas, w, h, primary, gold):
    canvas.setStrokeColor(primary)
    canvas.setLineWidth(1.4)
    canvas.rect(11 * mm, 11 * mm, w - 22 * mm, h - 22 * mm, stroke=1, fill=0)


def _plain(canvas, w, h, primary, gold):
    canvas.setStrokeColor(gold)
    canvas.setLineWidth(0.8)
    canvas.rect(10 * mm, 10 * mm, w - 20 * mm, h - 20 * mm, stroke=1, fill=0)


def _corners(canvas, w, h, primary, gold):
    canvas.setFillColor(primary)
    canvas.drawPath(_poly(canvas, [(0, h), (46 * mm, h), (0, h - 34 * mm)]), fill=1, stroke=0)
    canvas.drawPath(_poly(canvas, [(w, 0), (w - 46 * mm, 0), (w, 34 * mm)]), fill=1, stroke=0)
    canvas.setFillColor(gold)
    canvas.drawPath(_poly(canvas, [(0, h), (30 * mm, h), (0, h - 22 * mm)]), fill=1, stroke=0)
    canvas.drawPath(_poly(canvas, [(w, 0), (w - 30 * mm, 0), (w, 22 * mm)]), fill=1, stroke=0)
    canvas.setStrokeColor(primary)
    canvas.setLineWidth(2)
    canvas.rect(9 * mm, 9 * mm, w - 18 * mm, h - 18 * mm, stroke=1, fill=0)
    canvas.setStrokeColor(gold)
    canvas.setLineWidth(0.8)
    canvas.rect(11.5 * mm, 11.5 * mm, w - 23 * mm, h - 23 * mm, stroke=1, fill=0)


def _deco(canvas, w, h, primary, gold):
    canvas.setStrokeColor(primary)
    canvas.setLineWidth(2.2)
    canvas.rect(10 * mm, 10 * mm, w - 20 * mm, h - 20 * mm, stroke=1, fill=0)
    canvas.setStrokeColor(gold)
    canvas.setLineWidth(2)
    L = 26 * mm
    for cx, cy, dx, dy in ((14 * mm, 14 * mm, 1, 1), (w - 14 * mm, 14 * mm, -1, 1),
                           (14 * mm, h - 14 * mm, 1, -1), (w - 14 * mm, h - 14 * mm, -1, -1)):
        canvas.line(cx, cy, cx + dx * L, cy)
        canvas.line(cx, cy, cx, cy + dy * L)


def _ribbon(canvas, w, h, primary, gold):
    canvas.setFillColor(primary)
    canvas.rect(0, h - 26 * mm, w, 26 * mm, fill=1, stroke=0)
    canvas.setFillColor(gold)
    canvas.rect(0, h - 29 * mm, w, 3 * mm, fill=1, stroke=0)
    canvas.setStrokeColor(primary)
    canvas.setLineWidth(1)
    canvas.rect(9 * mm, 9 * mm, w - 18 * mm, h - 18 * mm, stroke=1, fill=0)


def _floral(canvas, w, h, primary, gold):
    canvas.setStrokeColor(primary)
    canvas.setLineWidth(3)
    canvas.rect(10 * mm, 10 * mm, w - 20 * mm, h - 20 * mm, stroke=1, fill=0)
    canvas.setLineWidth(1)
    canvas.rect(13 * mm, 13 * mm, w - 26 * mm, h - 26 * mm, stroke=1, fill=0)
    canvas.setFillColor(gold)
    step = 12 * mm
    x = 16 * mm
    while x < w - 16 * mm:
        canvas.circle(x, 11.5 * mm, 1.1 * mm, fill=1, stroke=0)
        canvas.circle(x, h - 11.5 * mm, 1.1 * mm, fill=1, stroke=0)
        x += step
    y = 16 * mm
    while y < h - 16 * mm:
        canvas.circle(11.5 * mm, y, 1.1 * mm, fill=1, stroke=0)
        canvas.circle(w - 11.5 * mm, y, 1.1 * mm, fill=1, stroke=0)
        y += step


_PAINTERS = {'double': _double, 'gold_double': _gold_double, 'keyline': _keyline,
             'plain': _plain, 'corners': _corners, 'deco': _deco, 'ribbon': _ribbon,
             'floral': _floral}


def page_decorator(key, branding=None):
    """A canvas painter that draws this collection's border/background art."""
    theme = resolve(key, branding)
    paint = _PAINTERS.get(theme['border'], _double)
    primary, gold = _c(theme['primary']), _c(theme['gold'])

    def draw(canvas, doc):
        w, h = doc.pagesize
        canvas.saveState()
        try:
            paint(canvas, w, h, primary, gold)
        finally:
            canvas.restoreState()
    return draw


# ---------------------------------------------------------------------------
# seal
# ---------------------------------------------------------------------------
def seal(theme, text='OFFICIAL SEAL', dia=22):
    d = Drawing(dia * mm, dia * mm)
    r = dia * mm / 2
    gold, primary = _c(theme['gold']), _c(theme['primary'])
    d.add(Circle(r, r, r, fillColor=gold, strokeColor=primary, strokeWidth=1.5))
    d.add(Circle(r, r, r - 2.6, fillColor=None, strokeColor=colors.white, strokeWidth=0.9))
    pts = []
    import math
    for i in range(20):
        ang = math.pi * i / 10
        rr = (r - 1) if i % 2 == 0 else (r - 3.4)
        pts += [r + rr * math.cos(ang), r + rr * math.sin(ang)]
    d.add(Polygon(points=pts, fillColor=None, strokeColor=colors.white, strokeWidth=0.5))
    d.add(String(r, r - 2, text[:14], textAnchor='middle', fontSize=4.2,
                 fillColor=colors.white, fontName='Helvetica-Bold'))
    return d


# ---------------------------------------------------------------------------
# generic certificate body (landscape, page-filling)
# ---------------------------------------------------------------------------
L_W = 261 * mm                                  # landscape content width (A4 - margins)
_L_BODY_H = 210 * mm - 34 * mm - 46 * mm         # landscape page - margins - footer reserve


def _logo(max_h=15, max_w=40):
    try:
        from utils.school import logo_flowable
        img = logo_flowable(max_h_mm=max_h, max_w_mm=max_w)
    except Exception:
        img = None
    if img is not None:
        img.hAlign = 'CENTER'
    return img


def render_certificate(key, content, branding=None, avail=_L_BODY_H, side=30 * mm):
    """Return page-filling flowables for a certificate-style document.

    ``content`` keys: kicker (school name), title, lead, recipient, body (list of
    strings), meta (date/session line), signatures (list of labels), seal_text.
    """
    theme = resolve(key, branding)
    hfont, bfont, nfont = fonts(theme)
    primary, accent, gold = _c(theme['primary']), _c(theme['accent']), _c(theme['gold'])
    cen = ParagraphStyle('c', alignment=TA_CENTER, fontName=bfont, fontSize=11, leading=16)

    head = []
    lg = _logo()
    if lg is not None:
        head += [lg, Spacer(1, 3)]
    if content.get('kicker'):
        head.append(Paragraph(content['kicker'].upper(), ParagraphStyle(
            'k', parent=cen, fontName=hfont, fontSize=13, textColor=gold, leading=16, spaceAfter=2)))
    head.append(Paragraph(content['title'].upper(), ParagraphStyle(
        'ti', parent=cen, fontName=hfont, fontSize=24, leading=28, textColor=primary)))

    mid = []
    if content.get('lead'):
        mid.append(Paragraph(content['lead'], ParagraphStyle('l', parent=cen, fontSize=11.5, spaceAfter=4)))
    mid.append(Paragraph(content['recipient'], ParagraphStyle(
        'nm', parent=cen, fontName=nfont, fontSize=27, leading=32, textColor=accent, spaceBefore=6, spaceAfter=6)))
    mid.append(HRFlowable(width='55%', thickness=0.7, color=gold))
    for para in (content.get('body') or []):
        mid.append(Paragraph(para, ParagraphStyle('b', parent=cen, fontSize=11.5, leading=17, spaceBefore=6)))
    if content.get('meta'):
        mid.append(Spacer(1, 6))
        mid.append(Paragraph(content['meta'], ParagraphStyle('m', parent=cen, fontSize=10, textColor=accent)))

    foot = _signature_row(content.get('signatures') or ['Principal', 'Registrar'],
                          bfont, theme, seal_text=content.get('seal_text'))

    t = Table([[head], [mid], [foot]], colWidths=[L_W - 2 * side],
              rowHeights=[avail * 0.30, avail * 0.44, avail * 0.26], hAlign='CENTER')
    t.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                           ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                           ('VALIGN', (0, 0), (0, 0), 'MIDDLE'), ('VALIGN', (0, 1), (0, 1), 'MIDDLE'),
                           ('VALIGN', (0, 2), (0, 2), 'BOTTOM')]))
    return [t]


def _signature_row(labels, bfont, theme, width=L_W - 60 * mm, seal_text=None):
    small = ParagraphStyle('s', fontName=bfont, fontSize=8.5, alignment=TA_CENTER,
                           textColor=_c('#334155'))
    line = ParagraphStyle('ln', fontName=bfont, fontSize=10.5, alignment=TA_CENTER)
    if seal_text and len(labels) == 2:
        cells = [[Paragraph('_' * 22, line), seal(theme, seal_text), Paragraph('_' * 22, line)],
                 [Paragraph(f'<b>{labels[0]}</b>', small), '', Paragraph(f'<b>{labels[1]}</b>', small)]]
        colw = [(width - 26 * mm) / 2, 26 * mm, (width - 26 * mm) / 2]
    else:
        cells = [[Paragraph('_' * 22, line) for _ in labels],
                 [Paragraph(f'<b>{x}</b>', small) for x in labels]]
        colw = [width / len(labels)] * len(labels)
    t = Table(cells, colWidths=colw)
    t.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                           ('TOPPADDING', (0, 1), (-1, 1), 2)]))
    return t
