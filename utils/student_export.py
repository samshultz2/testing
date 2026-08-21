"""Polished, A4-fitting student-list exports (PDF, image, Word).

A shared visual design — a branded masthead (school logo, name, address/phone/
email, motto) with an info panel (date, total, format), a navy table with zebra
rows and gender glyphs, and a footer with a "Page X of Y" and a confidentiality
note. Everything fits the A4 width (columns are scaled and long text wraps — no
truncation) and paginates down the A4 length; the image export renders one A4
page per image so a long list downloads as several images.
"""
import io
import os


def _today():
    from utils.timeutil import today
    return today()

# Palette (navy / gold on light) — a formal, school-neutral look.
NAVY = '#1E2A4A'
NAVY_SOFT = '#2B3A5E'
GOLD = '#B8862B'
INK = '#1F2937'
MUTED = '#6B7280'
ZEBRA = '#F4F6F9'
LINE = '#D8DEE9'
PANEL = '#F7F8FA'

# Clear short forms for the widest headers (no truncation — real abbreviations).
_SHORT_HEADER = {
    'Date of Birth': 'DOB',
    'JAMB Profile Code': 'JAMB Profile',
    'JAMB Reg Number': 'JAMB Reg No',
    'WAEC Reg Number': 'WAEC Reg No',
    'Parent Phone': 'Phone',
}

_DEJAVU = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
_DEJAVU_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
_DEJAVU_OBL = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf'


def short_header(name):
    return _SHORT_HEADER.get(name, name)


def _gender_glyph(value):
    v = (value or '').strip().lower()
    if v.startswith('m'):
        return '♂', '#1D4ED8'      # ♂ blue
    if v.startswith('f'):
        return '♀', '#BE185D'      # ♀ pink
    return '', MUTED


# --------------------------------------------------------------------------- #
# PDF (reportlab) — landscape A4, branded masthead + footer, paginated.
# --------------------------------------------------------------------------- #
def students_pdf(rows, headers, school, total=None):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Table,
                                    TableStyle, Paragraph)
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas as _canvas

    base, boldf, obl = 'Helvetica', 'Helvetica-Bold', 'Helvetica-Oblique'
    try:
        if os.path.exists(_DEJAVU):
            pdfmetrics.registerFont(TTFont('DejaVu', _DEJAVU)); base = 'DejaVu'
        if os.path.exists(_DEJAVU_BOLD):
            pdfmetrics.registerFont(TTFont('DejaVu-Bold', _DEJAVU_BOLD)); boldf = 'DejaVu-Bold'
        if os.path.exists(_DEJAVU_OBL):
            pdfmetrics.registerFont(TTFont('DejaVu-Obl', _DEJAVU_OBL)); obl = 'DejaVu-Obl'
    except Exception:
        pass

    total = total if total is not None else len(rows)
    PW, PH = landscape(A4)
    margin = 8 * mm
    mast_h = 34 * mm
    foot_h = 13 * mm
    avail = PW - 2 * margin - 2 * mm

    cell = ParagraphStyle('c', fontName=base, fontSize=8.5, leading=10.5, textColor=colors.HexColor(INK))
    cellc = ParagraphStyle('cc', parent=cell, alignment=TA_CENTER)
    headp = ParagraphStyle('h', fontName=boldf, fontSize=8.8, leading=10.5,
                           textColor=colors.white, alignment=TA_CENTER)

    ncol = len(headers)
    # Column weight per header type — names/address wide, S/N narrow.
    def weight(h):
        k = h.lower()
        if k in ('s/n', 'sn', 'age'):
            return 0.5
        if 'address' in k or 'hobb' in k:
            return 3.0
        if 'name' in k:
            return 1.6
        if 'gender' in k:
            return 0.9
        return 1.2
    ws = [weight(h) for h in headers]
    tot_w = sum(ws) or 1
    col_w = [max(11 * mm, avail * (w / tot_w)) for w in ws]
    # Normalise to exactly avail.
    scale = avail / sum(col_w)
    col_w = [w * scale for w in col_w]

    data = [[Paragraph(short_header(h), headp) for h in headers]]
    for r in rows:
        line = []
        for j, h in enumerate(headers):
            v = '' if j >= len(r) else ('' if r[j] is None else str(r[j]))
            if h.lower() == 'gender':
                g, col = _gender_glyph(v)
                line.append(Paragraph(f'<font color="{col}">{g}</font> {v}'.strip(), cellc))
            elif h.lower() in ('s/n', 'sn', 'age'):
                line.append(Paragraph(v, cellc))
            else:
                line.append(Paragraph(v, cell))
        data.append(line)

    t = Table(data, colWidths=col_w, repeatRows=1)
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(NAVY)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW', (0, 0), (-1, -1), 0.4, colors.HexColor(LINE)),
        ('LINEAFTER', (0, 0), (-2, -1), 0.4, colors.HexColor(LINE)),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(ZEBRA)]),
        ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor(LINE)),
    ]
    t.setStyle(TableStyle(style))

    buf = io.BytesIO()
    frame = Frame(margin + 1 * mm, margin + foot_h, avail, PH - mast_h - foot_h - margin,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    def paint(cv, doc):
        _draw_border(cv, PW, PH, margin)
        _draw_masthead(cv, PW, PH, margin, mast_h, school, total, 'PDF', base, boldf, obl)
        _draw_footer(cv, PW, margin, foot_h, school, base, boldf, obl)

    doc = BaseDocTemplate(buf, pagesize=(PW, PH), leftMargin=margin, rightMargin=margin,
                          topMargin=margin, bottomMargin=margin)
    doc.addPageTemplates([PageTemplate(id='main', frames=[frame], onPage=paint)])

    class Numbered(_canvas.Canvas):
        def __init__(self, *a, **k):
            super().__init__(*a, **k); self._saved = []
        def showPage(self):
            self._saved.append(dict(self.__dict__)); self._startPage()
        def save(self):
            n = len(self._saved)
            for st in self._saved:
                self.__dict__.update(st)
                self.setFont(base, 8.5); self.setFillColor(colors.HexColor(MUTED))
                self.drawCentredString(PW / 2, margin + 4.5 * mm, 'Page %d of %d' % (self._pageNumber, n))
                super().showPage()
            super().save()

    doc.build([t], canvasmaker=Numbered)
    return buf.getvalue()


def _draw_border(cv, PW, PH, margin):
    from reportlab.lib import colors
    cv.setStrokeColor(colors.HexColor(GOLD)); cv.setLineWidth(1.4)
    cv.roundRect(margin * 0.6, margin * 0.6, PW - 1.2 * margin, PH - 1.2 * margin, 8, stroke=1, fill=0)
    cv.setStrokeColor(colors.HexColor(LINE)); cv.setLineWidth(0.6)
    cv.roundRect(margin * 0.6 + 2, margin * 0.6 + 2, PW - 1.2 * margin - 4, PH - 1.2 * margin - 4, 7, stroke=1, fill=0)


def _draw_masthead(cv, PW, PH, margin, mast_h, school, total, fmt, base, boldf, obl):
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    top = PH - margin - 2 * mm
    x = margin + 4 * mm
    logo = (school or {}).get('logo_path')
    lx = x
    if logo and os.path.exists(logo):
        try:
            from reportlab.lib.utils import ImageReader
            ir = ImageReader(logo); iw, ih = ir.getSize()
            h = 22 * mm; w = h * (iw / ih) if ih else 22 * mm
            cv.drawImage(ir, x, top - h, width=min(w, 26 * mm), height=h, mask='auto',
                         preserveAspectRatio=True)
            lx = x + min(w, 26 * mm) + 5 * mm
        except Exception:
            lx = x
    name = (school or {}).get('name') or 'School'
    cv.setFillColor(colors.HexColor(NAVY)); cv.setFont(boldf, 21)
    cv.drawString(lx, top - 8 * mm, name.upper()[:46])
    cv.setFillColor(colors.HexColor(INK)); cv.setFont(base, 9.5)
    addr = (school or {}).get('address') or ''
    if addr:
        cv.drawString(lx, top - 13.5 * mm, ('●  ' + addr)[:70])
    contact = '   '.join(p for p in [(school or {}).get('phone') or '', (school or {}).get('email') or ''] if p)
    if contact:
        cv.drawString(lx, top - 18 * mm, contact[:70])
    motto = (school or {}).get('motto') or ''
    if motto:
        cv.setFillColor(colors.HexColor(GOLD)); cv.setFont(obl, 10)
        cv.drawString(lx, top - 23.5 * mm, ('—  ' + motto + '  —')[:70])

    # Right info panel: Date generated / Total / Exported as.
    pw = 92 * mm; ph = 22 * mm
    px = PW - margin - 4 * mm - pw; py = top - ph
    cv.setFillColor(colors.HexColor(PANEL)); cv.setStrokeColor(colors.HexColor(LINE)); cv.setLineWidth(0.6)
    cv.roundRect(px, py, pw, ph, 5, stroke=1, fill=1)
    cells = [('DATE GENERATED', _today().strftime('%d %b %Y')),
             ('TOTAL STUDENTS', str(total)), ('EXPORTED AS', fmt)]
    cwid = pw / 3
    for i, (lab, val) in enumerate(cells):
        cx = px + i * cwid + cwid / 2
        cv.setFillColor(colors.HexColor(MUTED)); cv.setFont(base, 7)
        cv.drawCentredString(cx, py + ph - 8 * mm, lab)
        cv.setFillColor(colors.HexColor(NAVY)); cv.setFont(boldf, 11)
        cv.drawCentredString(cx, py + 5 * mm, val)
        if i:
            cv.setStrokeColor(colors.HexColor(LINE)); cv.setLineWidth(0.5)
            cv.line(px + i * cwid, py + 3 * mm, px + i * cwid, py + ph - 3 * mm)


def _draw_footer(cv, PW, margin, foot_h, school, base, boldf, obl):
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    y = margin + 2 * mm
    cv.setStrokeColor(colors.HexColor(LINE)); cv.setLineWidth(0.5)
    cv.line(margin + 4 * mm, margin + foot_h, PW - margin - 4 * mm, margin + foot_h)
    name = (school or {}).get('name') or 'School'
    cv.setFillColor(colors.HexColor(NAVY)); cv.setFont(boldf, 8.5)
    cv.drawString(margin + 4 * mm, y + 1.5 * mm, name.upper()[:40])
    motto = (school or {}).get('motto') or ''
    if motto:
        cv.setFillColor(colors.HexColor(MUTED)); cv.setFont(obl, 7.5)
        cv.drawString(margin + 4 * mm, y - 2 * mm, motto[:50])
    cv.setFillColor(colors.HexColor(MUTED)); cv.setFont(obl, 7.5)
    cv.drawRightString(PW - margin - 4 * mm, y, 'This report is system-generated and confidential.')


# --------------------------------------------------------------------------- #
# Image (PIL) — one landscape-A4 PNG per page.
# --------------------------------------------------------------------------- #
def students_image_pages(rows, headers, school, total=None):
    from PIL import Image, ImageDraw, ImageFont
    S = 2
    DPI = 150
    PW = int(round(297 / 25.4 * DPI)); PH = int(round(210 / 25.4 * DPI))
    total = total if total is not None else len(rows)

    def fnt(size, bold=False):
        p = _DEJAVU_BOLD if bold else _DEJAVU
        try:
            return ImageFont.truetype(p, int(size * S))
        except Exception:
            return ImageFont.load_default()

    C = {'navy': (30, 42, 74), 'gold': (184, 134, 43), 'ink': (31, 41, 55),
         'muted': (107, 114, 128), 'zebra': (244, 246, 249), 'line': (216, 222, 233),
         'white': (255, 255, 255), 'panel': (247, 248, 250)}
    body, body_b = fnt(10), fnt(10, True)
    name_f, sub_f, hdr_f = fnt(20, True), fnt(9), fnt(9, True)
    tmp = ImageDraw.Draw(Image.new('RGB', (1, 1)))

    def tw(t, f):
        b = tmp.textbbox((0, 0), str(t), font=f); return b[2] - b[0]

    def fit(t, f, mw):
        t = str(t)
        if tw(t, f) <= mw:
            return t
        while t and tw(t + '…', f) > mw:
            t = t[:-1]
        return (t + '…') if t else ''

    margin = 30 * S
    mast_h = 150 * S
    foot_h = 44 * S
    avail = PW * S - 2 * margin
    ncol = len(headers)

    def weight(h):
        k = h.lower()
        if k in ('s/n', 'sn', 'age'):
            return 0.5
        if 'address' in k or 'hobb' in k:
            return 3.0
        if 'name' in k:
            return 1.6
        if 'gender' in k:
            return 0.9
        return 1.2
    ws = [weight(h) for h in headers]
    col_w = [avail * (w / (sum(ws) or 1)) for w in ws]
    line_h = tmp.textbbox((0, 0), 'Ay', font=body)[3]
    row_h = line_h + 14 * S
    header_h = row_h + 6 * S
    rows_area = PH * S - margin - mast_h - header_h - foot_h
    per_page = max(1, int(rows_area // row_h))
    chunks = [rows[i:i + per_page] for i in range(0, len(rows), per_page)] or [[]]
    n = len(chunks)
    pages = []
    for pi, chunk in enumerate(chunks):
        img = Image.new('RGB', (PW * S, PH * S), C['white'])
        d = ImageDraw.Draw(img)
        # border
        d.rounded_rectangle([int(margin * 0.6), int(margin * 0.6), PW * S - int(margin * 0.6), PH * S - int(margin * 0.6)],
                            radius=16, outline=C['gold'], width=3)
        _img_masthead(d, img, PW * S, margin, school, total, C, name_f, sub_f, body, fit, tw)
        # table
        y0 = margin + mast_h
        d.rectangle([margin, y0, margin + sum(col_w), y0 + header_h], fill=C['navy'])
        x = margin
        for j in range(ncol):
            d.text((x + 8 * S, y0 + (header_h - line_h) // 2), fit(short_header(headers[j]), hdr_f, col_w[j] - 16 * S),
                   fill=C['white'], font=hdr_f)
            x += col_w[j]
        yy = y0 + header_h
        for i, r in enumerate(chunk):
            if i % 2:
                d.rectangle([margin, yy, margin + sum(col_w), yy + row_h], fill=C['zebra'])
            x = margin
            for j in range(ncol):
                v = '' if j >= len(r) else ('' if r[j] is None else str(r[j]))
                col = C['ink']
                if headers[j].lower() == 'gender':
                    g, hexcol = _gender_glyph(v)
                    v = (g + ' ' + v).strip()
                d.text((x + 8 * S, yy + (row_h - line_h) // 2), fit(v, body, col_w[j] - 16 * S), fill=col, font=body)
                x += col_w[j]
            d.line([margin, yy, margin + sum(col_w), yy], fill=C['line'], width=1)
            yy += row_h
        d.rectangle([margin, y0, margin + sum(col_w), yy], outline=C['line'], width=1)
        # footer
        fy = PH * S - foot_h
        d.line([margin, fy, PW * S - margin, fy], fill=C['line'], width=1)
        d.text((margin, fy + 8 * S), ((school or {}).get('name') or 'School').upper(), fill=C['navy'], font=hdr_f)
        d.text((PW * S - margin - tw('This report is system-generated and confidential.', sub_f), fy + 8 * S),
               'This report is system-generated and confidential.', fill=C['muted'], font=sub_f)
        pnum = 'Page %d of %d' % (pi + 1, n)
        d.text((PW * S / 2 - tw(pnum, sub_f) / 2, fy + 8 * S), pnum, fill=C['muted'], font=sub_f)
        out = io.BytesIO()
        img.resize((PW, PH), Image.LANCZOS).save(out, format='PNG')
        pages.append(out.getvalue())
    return pages


def _img_masthead(d, img, PW, margin, school, total, C, name_f, sub_f, body, fit, tw):
    from PIL import Image
    x = margin + 8
    logo = (school or {}).get('logo_path')
    lx = x
    if logo and os.path.exists(logo):
        try:
            lg = Image.open(logo).convert('RGBA')
            h = 108; w = int(lg.width * h / lg.height)
            lg = lg.resize((min(w, 130), h), Image.LANCZOS)
            img.paste(lg, (x, margin + 8), lg)
            lx = x + min(w, 130) + 20
        except Exception:
            lx = x
    d.text((lx, margin + 12), ((school or {}).get('name') or 'School').upper(), fill=C['navy'], font=name_f)
    ty = margin + 12 + 46
    addr = (school or {}).get('address') or ''
    if addr:
        d.text((lx, ty), '●  ' + addr, fill=C['ink'], font=body); ty += 26
    contact = '   '.join(p for p in [(school or {}).get('phone') or '', (school or {}).get('email') or ''] if p)
    if contact:
        d.text((lx, ty), contact, fill=C['ink'], font=body); ty += 26
    motto = (school or {}).get('motto') or ''
    if motto:
        d.text((lx, ty), '—  ' + motto + '  —', fill=C['gold'], font=body)
    # info panel
    pw = 470; ph = 104
    px = PW - margin - 8 - pw; py = margin + 10
    d.rounded_rectangle([px, py, px + pw, py + ph], radius=10, fill=C['panel'], outline=C['line'], width=2)
    cells = [('DATE GENERATED', _today().strftime('%d %b %Y')),
             ('TOTAL STUDENTS', str(total)), ('EXPORTED AS', 'IMAGE')]
    cwid = pw / 3
    for i, (lab, val) in enumerate(cells):
        cx = px + i * cwid + cwid / 2
        lab = fit(lab, sub_f, cwid - 14)
        d.text((cx - tw(lab, sub_f) / 2, py + 20), lab, fill=C['muted'], font=sub_f)
        d.text((cx - tw(val, body) / 2, py + 54), val, fill=C['navy'], font=body)
        if i:
            d.line([px + i * cwid, py + 14, px + i * cwid, py + ph - 14], fill=C['line'], width=1)
