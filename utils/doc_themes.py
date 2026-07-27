"""Document design *collections* (themes) — the scalable foundation of the
Academic Documents & Publishing system.

A **collection** is a named visual identity (palette + typography + border art +
seal style). One generic renderer, driven by a collection, produces a fully
distinct-looking, security-grade document — cream/paper ground, microtext
security border, watermark, tinted section & field tables, serial number, gold
certified seal, rubber stamp and barcode — so every document type instantly
gains the whole library of collections without hand-authoring each combination.
"""
import math

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT, TA_LEFT
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.graphics.shapes import Drawing, Circle, String, Polygon, Line


def _c(v):
    return colors.HexColor(v)


def _esc(v):
    from utils.web_exports import pdf_escape
    return pdf_escape(str(v if v is not None else ''))


# ---------------------------------------------------------------------------
# collection registry — palette + fonts + border art + seal style
# ---------------------------------------------------------------------------
COLLECTIONS = {
    'classic':        {'name': 'Classic',        'primary': '#0e3a2f', 'accent': '#0e8a64', 'gold': '#b7791f', 'border': 'double',      'serif': True},
    'modern':         {'name': 'Modern',         'primary': '#1e3a8a', 'accent': '#0ea5e9', 'gold': '#c99700', 'border': 'corners',     'serif': False},
    'premium':        {'name': 'Premium',        'primary': '#4c1d95', 'accent': '#7c3aed', 'gold': '#b7791f', 'border': 'gold_double', 'serif': True},
    'executive':      {'name': 'Executive',      'primary': '#111827', 'accent': '#374151', 'gold': '#9a7b3f', 'border': 'keyline',     'serif': False},
    'luxury':         {'name': 'Luxury',         'primary': '#3b0764', 'accent': '#a21caf', 'gold': '#d4af37', 'border': 'deco',        'serif': True},
    'government':     {'name': 'Government',      'primary': '#14532d', 'accent': '#166534', 'gold': '#b45309', 'border': 'double',      'serif': True},
    'british':        {'name': 'British School',  'primary': '#7f1d1d', 'accent': '#991b1b', 'gold': '#b7791f', 'border': 'floral',      'serif': True},
    'american':       {'name': 'American High',   'primary': '#1e3a8a', 'accent': '#b91c1c', 'gold': '#c99700', 'border': 'ribbon',      'serif': False},
    'international':   {'name': 'International',   'primary': '#0f766e', 'accent': '#0891b2', 'gold': '#b7791f', 'border': 'corners',     'serif': False},
    'scandinavian':   {'name': 'Scandinavian',   'primary': '#0f172a', 'accent': '#64748b', 'gold': '#94a3b8', 'border': 'plain',       'serif': False},
    'contemporary':   {'name': 'Contemporary',   'primary': '#0369a1', 'accent': '#06b6d4', 'gold': '#c07f0a', 'border': 'keyline',     'serif': False},
    'minimalist':     {'name': 'Minimalist',     'primary': '#111827', 'accent': '#6b7280', 'gold': '#9ca3af', 'border': 'plain',       'serif': False},
    'elegant':        {'name': 'Elegant',        'primary': '#14532d', 'accent': '#b7791f', 'gold': '#d4af37', 'border': 'ribbon',      'serif': True},
    'traditional':    {'name': 'Traditional',    'primary': '#7c2d12', 'accent': '#9a3412', 'gold': '#b45309', 'border': 'floral',      'serif': True},
    'academic':       {'name': 'Academic',       'primary': '#1e293b', 'accent': '#334155', 'gold': '#b7791f', 'border': 'double',      'serif': True},
    'prestige':       {'name': 'Prestige',       'primary': '#422006', 'accent': '#713f12', 'gold': '#d4af37', 'border': 'gold_double', 'serif': True},
    'royal':          {'name': 'Royal',          'primary': '#1e1b4b', 'accent': '#4338ca', 'gold': '#d4af37', 'border': 'deco',        'serif': True},
    'heritage':       {'name': 'Heritage',       'primary': '#713f12', 'accent': '#92400e', 'gold': '#b45309', 'border': 'floral',      'serif': True},
    'platinum':       {'name': 'Platinum',       'primary': '#334155', 'accent': '#475569', 'gold': '#8a93a3', 'border': 'keyline',     'serif': False},
    'gold':           {'name': 'Gold',           'primary': '#713f12', 'accent': '#b7791f', 'gold': '#d4af37', 'border': 'gold_double', 'serif': True},
    'green_heritage': {'name': 'Green Heritage',  'primary': '#14532d', 'accent': '#15803d', 'gold': '#b7791f', 'border': 'double',      'serif': True},
    'corporate':      {'name': 'Corporate',      'primary': '#0c4a6e', 'accent': '#0369a1', 'gold': '#7c8a99', 'border': 'ribbon',      'serif': False},
    'creative':       {'name': 'Creative',       'primary': '#9d174d', 'accent': '#db2777', 'gold': '#c07f0a', 'border': 'corners',     'serif': False},
    'sapphire':       {'name': 'Sapphire',       'primary': '#172554', 'accent': '#2563eb', 'gold': '#c99700', 'border': 'deco',        'serif': False},
}
DEFAULT_COLLECTION = 'classic'


def resolve(key, branding=None):
    """The theme for ``key`` + a derived paper tint, with optional per-school
    ``branding`` colour overrides layered on top."""
    t = dict(COLLECTIONS.get(key) or COLLECTIONS[DEFAULT_COLLECTION])
    t['paper'] = '#fbf7ee' if t.get('serif') else '#f7f8fb'      # cream vs cool paper
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
    if theme.get('serif'):
        return 'Times-Bold', 'Times-Roman', 'Times-BoldItalic'
    return 'Helvetica-Bold', 'Helvetica', 'Helvetica-Bold'


# ---------------------------------------------------------------------------
# canvas art: paper, borders, microtext, watermark
# ---------------------------------------------------------------------------
def _poly(canvas, pts):
    p = canvas.beginPath()
    p.moveTo(*pts[0])
    for x, y in pts[1:]:
        p.lineTo(x, y)
    p.close()
    return p


def _paper(canvas, w, h, tint):
    canvas.setFillColor(tint)
    canvas.rect(0, 0, w, h, fill=1, stroke=0)


def _double(canvas, w, h, primary, gold):
    canvas.setStrokeColor(primary); canvas.setLineWidth(4)
    canvas.rect(9 * mm, 9 * mm, w - 18 * mm, h - 18 * mm, stroke=1, fill=0)
    canvas.setStrokeColor(gold); canvas.setLineWidth(1)
    canvas.rect(12 * mm, 12 * mm, w - 24 * mm, h - 24 * mm, stroke=1, fill=0)


def _gold_double(canvas, w, h, primary, gold):
    canvas.setStrokeColor(gold); canvas.setLineWidth(4.5)
    canvas.rect(8.5 * mm, 8.5 * mm, w - 17 * mm, h - 17 * mm, stroke=1, fill=0)
    canvas.setLineWidth(1.2)
    canvas.rect(12 * mm, 12 * mm, w - 24 * mm, h - 24 * mm, stroke=1, fill=0)


def _keyline(canvas, w, h, primary, gold):
    canvas.setStrokeColor(primary); canvas.setLineWidth(1.4)
    canvas.rect(11 * mm, 11 * mm, w - 22 * mm, h - 22 * mm, stroke=1, fill=0)


def _plain(canvas, w, h, primary, gold):
    canvas.setStrokeColor(gold); canvas.setLineWidth(0.8)
    canvas.rect(10 * mm, 10 * mm, w - 20 * mm, h - 20 * mm, stroke=1, fill=0)


def _corners(canvas, w, h, primary, gold):
    canvas.setFillColor(primary)
    canvas.drawPath(_poly(canvas, [(0, h), (46 * mm, h), (0, h - 34 * mm)]), fill=1, stroke=0)
    canvas.drawPath(_poly(canvas, [(w, 0), (w - 46 * mm, 0), (w, 34 * mm)]), fill=1, stroke=0)
    canvas.setFillColor(gold)
    canvas.drawPath(_poly(canvas, [(0, h), (30 * mm, h), (0, h - 22 * mm)]), fill=1, stroke=0)
    canvas.drawPath(_poly(canvas, [(w, 0), (w - 30 * mm, 0), (w, 22 * mm)]), fill=1, stroke=0)
    canvas.setStrokeColor(primary); canvas.setLineWidth(2)
    canvas.rect(9 * mm, 9 * mm, w - 18 * mm, h - 18 * mm, stroke=1, fill=0)
    canvas.setStrokeColor(gold); canvas.setLineWidth(0.8)
    canvas.rect(11.5 * mm, 11.5 * mm, w - 23 * mm, h - 23 * mm, stroke=1, fill=0)


def _deco(canvas, w, h, primary, gold):
    canvas.setStrokeColor(primary); canvas.setLineWidth(2.2)
    canvas.rect(10 * mm, 10 * mm, w - 20 * mm, h - 20 * mm, stroke=1, fill=0)
    canvas.setStrokeColor(gold); canvas.setLineWidth(2)
    L = 26 * mm
    for cx, cy, dx, dy in ((14 * mm, 14 * mm, 1, 1), (w - 14 * mm, 14 * mm, -1, 1),
                           (14 * mm, h - 14 * mm, 1, -1), (w - 14 * mm, h - 14 * mm, -1, -1)):
        canvas.line(cx, cy, cx + dx * L, cy)
        canvas.line(cx, cy, cx, cy + dy * L)


def _ribbon(canvas, w, h, primary, gold):
    canvas.setFillColor(primary); canvas.rect(0, h - 26 * mm, w, 26 * mm, fill=1, stroke=0)
    canvas.setFillColor(gold); canvas.rect(0, h - 29 * mm, w, 3 * mm, fill=1, stroke=0)
    canvas.setStrokeColor(primary); canvas.setLineWidth(1)
    canvas.rect(9 * mm, 9 * mm, w - 18 * mm, h - 18 * mm, stroke=1, fill=0)


def _floral(canvas, w, h, primary, gold):
    canvas.setStrokeColor(primary); canvas.setLineWidth(3)
    canvas.rect(10 * mm, 10 * mm, w - 20 * mm, h - 20 * mm, stroke=1, fill=0)
    canvas.setLineWidth(1)
    canvas.rect(13 * mm, 13 * mm, w - 26 * mm, h - 26 * mm, stroke=1, fill=0)
    canvas.setFillColor(gold)
    step, x = 12 * mm, 16 * mm
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


def _microtext(canvas, w, h, phrase, color, margin):
    """A repeating micro-printed security line just inside the page edge."""
    if not phrase:
        return
    phrase = (phrase + '  ') * 60
    canvas.setFillColor(color)
    canvas.setFont('Helvetica', 3.1)
    canvas.drawString(margin, h - margin + 1.2 * mm, phrase[:int((w - 2 * margin) / (1.55))])
    canvas.drawString(margin, margin - 2.4 * mm, phrase[:int((w - 2 * margin) / (1.55))])
    canvas.saveState()
    canvas.translate(margin - 2.4 * mm, margin)
    canvas.rotate(90)
    canvas.drawString(0, 0, phrase[:int((h - 2 * margin) / 1.55)])
    canvas.restoreState()
    canvas.saveState()
    canvas.translate(w - margin + 1.2 * mm, margin)
    canvas.rotate(90)
    canvas.drawString(0, 0, phrase[:int((h - 2 * margin) / 1.55)])
    canvas.restoreState()


def _watermark(canvas, w, h, text, color):
    """A faint diagonal school-name watermark + a light guilloché seal ring."""
    canvas.saveState()
    canvas.translate(w / 2, h / 2)
    canvas.setStrokeColor(color)
    canvas.setLineWidth(0.4)
    for r in (26 * mm, 30 * mm, 34 * mm):
        canvas.circle(0, 0, r, stroke=1, fill=0)
    canvas.rotate(30)
    canvas.setFillColor(color)
    canvas.setFont('Helvetica-Bold', 46)
    canvas.drawCentredString(0, -8, (text or 'OFFICIAL').upper()[:22])
    canvas.restoreState()


def _decorator(key, branding=None, microtext=None, watermark_text=None, letter=False):
    theme = resolve(key, branding)
    primary, gold, paper = _c(theme['primary']), _c(theme['gold']), _c(theme['paper'])
    paint = _PAINTERS.get(theme['border'], _double)
    micro_col = colors.Color(*primary.rgb(), alpha=0.30)
    wm_col = colors.Color(*primary.rgb(), alpha=0.05)

    def draw(canvas, doc):
        w, h = doc.pagesize
        canvas.saveState()
        try:
            _paper(canvas, w, h, paper)
            if watermark_text:
                _watermark(canvas, w, h, watermark_text, wm_col)
            if letter:
                canvas.setFillColor(primary)
                canvas.rect(0, h - 7 * mm, w, 7 * mm, fill=1, stroke=0)
                canvas.setFillColor(gold)
                canvas.rect(0, h - 9 * mm, w, 2 * mm, fill=1, stroke=0)
                canvas.setStrokeColor(gold); canvas.setLineWidth(1.1)
                canvas.rect(10 * mm, 10 * mm, w - 20 * mm, h - 22 * mm, stroke=1, fill=0)
            else:
                paint(canvas, w, h, primary, gold)
            _microtext(canvas, w, h, microtext, micro_col, 7 * mm if not letter else 6 * mm)
        finally:
            canvas.restoreState()
    return draw


def page_decorator(key, branding=None, microtext=None, watermark_text=None):
    return _decorator(key, branding, microtext, watermark_text, letter=False)


def letter_decorator(key, branding=None, microtext=None, watermark_text=None, style='frame'):
    """Letterhead page art for a letter. ``style`` distinguishes the layouts:
    'frame' (thin gold inner frame), 'band' (top colour band + frame), 'sidebar'
    (left colour bar), 'plain' (microtext + watermark only)."""
    theme = resolve(key, branding)
    primary, gold, paper = _c(theme['primary']), _c(theme['gold']), _c(theme['paper'])
    micro_col = colors.Color(*primary.rgb(), alpha=0.30)
    wm_col = colors.Color(*primary.rgb(), alpha=0.05)

    def draw(canvas, doc):
        w, h = doc.pagesize
        canvas.saveState()
        try:
            _paper(canvas, w, h, paper)
            if watermark_text:
                _watermark(canvas, w, h, watermark_text, wm_col)
            if style == 'band':
                canvas.setFillColor(primary)
                canvas.rect(0, h - 7 * mm, w, 7 * mm, fill=1, stroke=0)
                canvas.setFillColor(gold)
                canvas.rect(0, h - 9 * mm, w, 2 * mm, fill=1, stroke=0)
            elif style == 'sidebar':
                canvas.setFillColor(primary)
                canvas.rect(10 * mm, 10 * mm, 6 * mm, h - 20 * mm, fill=1, stroke=0)
                canvas.setFillColor(gold)
                canvas.rect(16 * mm, 10 * mm, 1.4 * mm, h - 20 * mm, fill=1, stroke=0)
            if style in ('frame', 'band'):
                canvas.setStrokeColor(gold)
                canvas.setLineWidth(1.1)
                canvas.rect(10 * mm, 10 * mm, w - 20 * mm, h - 22 * mm, stroke=1, fill=0)
            _microtext(canvas, w, h, microtext, micro_col, 6 * mm)
        finally:
            canvas.restoreState()
    return draw


# ---------------------------------------------------------------------------
# seals, stamps, barcodes
# ---------------------------------------------------------------------------
def gold_seal(theme, text='CERTIFIED', dia=24):
    """A gold, star-ringed 'certified' seal (the premium wax/foil seal look)."""
    d = Drawing(dia * mm, dia * mm)
    r = dia * mm / 2
    gold, dark = _c(theme['gold']), _c(theme['primary'])
    # rosette points
    pts = []
    for i in range(48):
        ang = 2 * math.pi * i / 48
        rr = r if i % 2 == 0 else r - 1.6
        pts += [r + rr * math.cos(ang), r + rr * math.sin(ang)]
    d.add(Polygon(points=pts, fillColor=gold, strokeColor=dark, strokeWidth=0.6))
    d.add(Circle(r, r, r - 3, fillColor=gold, strokeColor=colors.white, strokeWidth=1.2))
    d.add(Circle(r, r, r - 5.4, fillColor=None, strokeColor=dark, strokeWidth=0.7))
    d.add(String(r, r + 1.5, text[:11], textAnchor='middle', fontSize=4.6,
                 fillColor=dark, fontName='Helvetica-Bold'))
    d.add(String(r, r - 4.4, 'OFFICIAL', textAnchor='middle', fontSize=3.0,
                 fillColor=dark, fontName='Helvetica'))
    return d


def rubber_stamp(theme, top='OFFICIAL', mid='SEAL', bottom='', dia=24):
    """A round rubber-ink stamp (concentric rings + stacked text)."""
    d = Drawing(dia * mm, dia * mm)
    r = dia * mm / 2
    ink = _c(theme['accent'])
    d.add(Circle(r, r, r - 0.6, fillColor=None, strokeColor=ink, strokeWidth=1.4))
    d.add(Circle(r, r, r - 3.2, fillColor=None, strokeColor=ink, strokeWidth=0.7))
    d.add(String(r, r + 3.2, top[:16], textAnchor='middle', fontSize=3.2, fillColor=ink, fontName='Helvetica-Bold'))
    d.add(Line(r - (r - 4), r, r + (r - 4), r, strokeColor=ink, strokeWidth=0.5))
    d.add(String(r, r - 1.2, mid[:14], textAnchor='middle', fontSize=4.0, fillColor=ink, fontName='Helvetica-Bold'))
    if bottom:
        d.add(String(r, r - 5.6, bottom[:16], textAnchor='middle', fontSize=2.8, fillColor=ink, fontName='Helvetica'))
    return d


def barcode(value):
    try:
        from reportlab.graphics.barcode import code128
        return code128.Code128(str(value or '0'), barHeight=8 * mm, barWidth=0.3 * mm,
                               humanReadable=False)
    except Exception:
        return None


def qr(value, size=20):
    """A QR-code image flowable for the verification value (school prefers QR to
    a barcode). Returns None when the qrcode library is unavailable."""
    try:
        import io
        import qrcode
        from reportlab.platypus import Image as RLImage
        img = qrcode.make(str(value or ''))
        buf = io.BytesIO()
        img.save(buf, 'PNG')
        buf.seek(0)
        return RLImage(buf, width=size * mm, height=size * mm)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# shared field / section helpers
# ---------------------------------------------------------------------------
def field_table(pairs, theme, width, label_w=None, tint=True):
    """A boxed label/value table with tinted rows (bio blocks etc.)."""
    _h, bfont, _n = fonts(theme)
    primary = _c(theme['primary'])
    soft = colors.Color(*primary.rgb(), alpha=0.07)
    lab = ParagraphStyle('fl', fontName=_h, fontSize=9.5, leading=12, textColor=primary)
    val = ParagraphStyle('fv', fontName=bfont, fontSize=9.5, leading=12)
    rows = [[Paragraph(_esc(k), lab), Paragraph(_esc(v), val)] for k, v in pairs if v]
    if not rows:
        return None
    label_w = label_w or width * 0.42
    t = Table(rows, colWidths=[label_w, width - label_w])
    style = [('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
             ('BOX', (0, 0), (-1, -1), 0.6, primary),
             ('LINEBELOW', (0, 0), (-1, -2), 0.3, colors.Color(*primary.rgb(), alpha=0.25)),
             ('LINEAFTER', (0, 0), (0, -1), 0.3, colors.Color(*primary.rgb(), alpha=0.25)),
             ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
             ('LEFTPADDING', (0, 0), (-1, -1), 6)]
    if tint:
        style.append(('ROWBACKGROUNDS', (0, 0), (0, -1), [soft, soft]))
    t.setStyle(TableStyle(style))
    return t


def section_bar(title, theme, width):
    """A tinted section header bar (STUDENT INFORMATION, etc.)."""
    hfont, _b, _n = fonts(theme)
    primary = _c(theme['primary'])
    t = Table([[Paragraph(_esc(title).upper(),
                          ParagraphStyle('sb', fontName=hfont, fontSize=9.5, textColor=colors.white))]],
              colWidths=[width])
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), primary),
                           ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                           ('LEFTPADDING', (0, 0), (-1, -1), 6)]))
    return t


# ---------------------------------------------------------------------------
# generic certificate body (landscape, page-filling)
# ---------------------------------------------------------------------------
L_W = 261 * mm
_L_BODY_H = 210 * mm - 30 * mm - 34 * mm         # landscape page - margins - footer reserve
P_W = 170 * mm


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
    """Page-filling flowables for a certificate-style document."""
    theme = resolve(key, branding)
    hfont, bfont, nfont = fonts(theme)
    primary, accent, gold = _c(theme['primary']), _c(theme['accent']), _c(theme['gold'])
    cen = ParagraphStyle('c', alignment=TA_CENTER, fontName=bfont, fontSize=11, leading=16)

    head = []
    if content.get('serial'):
        sn = Table([[Paragraph(f"<b>S/N:</b> {_esc(content['serial'])}",
                               ParagraphStyle('sn', fontName=bfont, fontSize=8.5,
                                              alignment=TA_RIGHT, textColor=_c('#b91c1c')))]],
                   colWidths=[L_W - 2 * side])
        sn.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
        head.append(sn)
    lg = _logo()
    if lg is not None:
        head += [lg, Spacer(1, 3)]
    if content.get('kicker'):
        head.append(Paragraph(content['kicker'].upper(), ParagraphStyle(
            'k', parent=cen, fontName=hfont, fontSize=13, textColor=gold, leading=16, spaceAfter=1)))
    if content.get('motto'):
        head.append(Paragraph(f"<i>{_esc(content['motto'])}</i>", ParagraphStyle(
            'mt', parent=cen, fontName=bfont, fontSize=8.5, textColor=accent, spaceAfter=2)))
    head.append(Paragraph(content['title'].upper(), ParagraphStyle(
        'ti', parent=cen, fontName=hfont, fontSize=25, leading=29, textColor=primary)))

    mid = []
    if content.get('lead'):
        mid.append(Paragraph(content['lead'], ParagraphStyle('l', parent=cen, fontSize=11.5, spaceAfter=3)))
    mid.append(Paragraph(content['recipient'], ParagraphStyle(
        'nm', parent=cen, fontName=nfont, fontSize=28, leading=33, textColor=accent, spaceBefore=6, spaceAfter=4)))
    mid.append(HRFlowable(width='58%', thickness=0.8, color=gold))
    for para in (content.get('body') or []):
        mid.append(Paragraph(para, ParagraphStyle('b', parent=cen, fontSize=11.5, leading=17, spaceBefore=6)))
    if content.get('meta'):
        mid.append(Spacer(1, 6))
        mid.append(Paragraph(content['meta'], ParagraphStyle('m', parent=cen, fontSize=10, textColor=accent)))

    foot = _signature_row(content.get('signatures') or ['Principal', 'Registrar'],
                          bfont, theme, seal_text=content.get('seal_text'),
                          barcode_value=content.get('serial'))

    t = Table([[head], [mid], [foot]], colWidths=[L_W - 2 * side],
              rowHeights=[avail * 0.30, avail * 0.44, avail * 0.26], hAlign='CENTER')
    t.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                           ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                           ('VALIGN', (0, 0), (0, 0), 'MIDDLE'), ('VALIGN', (0, 1), (0, 1), 'MIDDLE'),
                           ('VALIGN', (0, 2), (0, 2), 'BOTTOM')]))
    return [t]


def _signature_row(labels, bfont, theme, width=L_W - 60 * mm, seal_text=None, barcode_value=None):
    small = ParagraphStyle('s', fontName=bfont, fontSize=8.5, alignment=TA_CENTER, textColor=_c('#334155'))
    line = ParagraphStyle('ln', fontName=bfont, fontSize=10.5, alignment=TA_CENTER)
    stamp = rubber_stamp(theme, top=(seal_text or 'OFFICIAL'), mid='SEAL')
    gseal = gold_seal(theme)
    if len(labels) == 2:
        cells = [[stamp, Paragraph('_' * 20, line), gseal, Paragraph('_' * 20, line)],
                 ['', Paragraph(f'<b>{labels[0]}</b>', small), '', Paragraph(f'<b>{labels[1]}</b>', small)]]
        colw = [26 * mm, (width - 52 * mm) / 2, 26 * mm, (width - 52 * mm) / 2]
    else:
        cells = [[Paragraph('_' * 20, line) for _ in labels] + [gseal],
                 [Paragraph(f'<b>{x}</b>', small) for x in labels] + ['']]
        colw = [(width - 26 * mm) / len(labels)] * len(labels) + [26 * mm]
    t = Table(cells, colWidths=colw)
    t.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                           ('TOPPADDING', (0, 1), (-1, 1), 2)]))
    bc = barcode(barcode_value) if barcode_value else None
    if bc is not None:
        strip = Table([[bc]], colWidths=[width])
        strip.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                   ('TOPPADDING', (0, 0), (-1, -1), 6)]))
        return [t, strip]
    return t


def render_letter(key, content, branding=None):
    """Portrait flowables for a formal letter (letterhead + bio table + body +
    security signature block)."""
    theme = resolve(key, branding)
    hfont, bfont, nfont = fonts(theme)
    primary, accent, gold = _c(theme['primary']), _c(theme['accent']), _c(theme['gold'])
    school = content.get('school') or {}

    body_st = ParagraphStyle('lb', fontName=bfont, fontSize=11, leading=17, alignment=TA_JUSTIFY, spaceAfter=8)
    left = ParagraphStyle('ll', fontName=bfont, fontSize=10, leading=14)
    right = ParagraphStyle('lr', parent=left, alignment=TA_RIGHT)

    el = []
    lg = _logo(max_h=17, max_w=30)
    name_p = Paragraph(_esc(school.get('name') or 'School'), ParagraphStyle(
        'ln', fontName=hfont, fontSize=18, leading=21, textColor=primary))
    sub_ps = []
    if content.get('motto'):
        sub_ps.append(Paragraph(f"<i>{_esc(content['motto'])}</i>", ParagraphStyle(
            'lm', fontSize=8.5, textColor=gold)))
    addr_bits = [school.get('address'),
                 ' · '.join([x for x in [school.get('phone'), school.get('email'),
                                         school.get('website')] if x])]
    for b in addr_bits:
        if b:
            sub_ps.append(Paragraph(_esc(b), ParagraphStyle('ls', fontSize=8.5, textColor=_c('#475569'))))
    text_col = [name_p] + sub_ps
    if lg is not None:
        head = Table([[lg, text_col]], colWidths=[32 * mm, P_W - 32 * mm])
        head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
        el.append(head)
    else:
        el += text_col
    el += [Spacer(1, 4), HRFlowable(width='100%', thickness=1.2, color=gold), Spacer(1, 8)]

    ref, dt = _esc(content.get('ref') or ''), _esc(content.get('date') or '')
    meta = Table([[Paragraph(f"<b>Ref:</b> {ref}" if ref else '', left),
                   Paragraph(f"<b>Date:</b> {dt}" if dt else '', right)]],
                 colWidths=[P_W / 2, P_W / 2])
    meta.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
    el += [meta, Spacer(1, 8)]

    el.append(Paragraph(content['title'].upper(), ParagraphStyle(
        'lt', alignment=TA_CENTER, fontName=hfont, fontSize=14, textColor=primary, spaceAfter=10)))
    if content.get('salutation'):
        el.append(Paragraph(content['salutation'], body_st))
    if content.get('fields'):
        ft = field_table(content['fields'], theme, P_W)
        if ft is not None:
            el += [ft, Spacer(1, 8)]
    for para in (content.get('body') or []):
        el.append(Paragraph(para, body_st))
    if content.get('closing'):
        el += [Spacer(1, 6), Paragraph(content['closing'], body_st)]

    sig = _signature_row(content.get('signatures') or ['Principal', 'Registrar'],
                         bfont, theme, width=P_W - 18 * mm,
                         seal_text=content.get('seal_text'), barcode_value=content.get('serial'))
    el += [Spacer(1, 16)] + (sig if isinstance(sig, list) else [sig])
    return el
