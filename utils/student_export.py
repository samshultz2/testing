"""Polished, A4-fitting student-list exports (PDF, image, Word).

A shared visual design — a large branded masthead (school logo, name, address/
phone/email, motto) with a bold info panel (date, total, format), a navy table
with zebra rows and gender glyphs, and a footer with "Page X of Y" and a
confidentiality note.

Layout rules the user asked for:
* fonts are large enough to read without zooming;
* columns take the width of their content (no wasted space), EXCEPT the address /
  hobbies columns, which are capped and wrap to the next line;
* everything fits the A4 width (shrinks to fit / wraps — no truncation) and
  paginates down the A4 length; the image export renders one A4 page per image.
"""
import io
import os
from utils import timeutil

NAVY = '#1E2A4A'
GOLD = '#B8862B'
INK = '#1F2937'
MUTED = '#6B7280'
ZEBRA = '#F4F6F9'
LINE = '#D8DEE9'
PANEL = '#F7F8FA'

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


def _is_wrap(h):
    k = (h or '').lower()
    return 'address' in k or 'hobb' in k


def _gender_glyph(value):
    v = (value or '').strip().lower()
    if v.startswith('m'):
        return '♂', '#1D4ED8'
    if v.startswith('f'):
        return '♀', '#BE185D'
    return '', MUTED


# --------------------------------------------------------------------------- #
# PDF (reportlab)
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
    from reportlab.pdfbase.pdfmetrics import stringWidth
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
    mast_h = 44 * mm
    foot_h = 14 * mm
    avail = PW - 2 * margin - 2 * mm

    fs = 11
    cell = ParagraphStyle('c', fontName=base, fontSize=fs, leading=fs + 3, textColor=colors.HexColor(INK))
    cellc = ParagraphStyle('cc', parent=cell, alignment=TA_CENTER)
    headp = ParagraphStyle('h', fontName=boldf, fontSize=fs, leading=fs + 2,
                           textColor=colors.white, alignment=TA_CENTER)

    ncol = len(headers)
    pad = 8 * mm
    # Content-based widths: each column fits its widest value; wrap columns are
    # capped (they wrap), other columns capped so one long value can't blow out.
    def _disp(j, v):
        if headers[j].lower() == 'gender':
            g, _c = _gender_glyph(v)
            return (g + ' ' + v).strip()
        return v

    def measure(j):
        w = stringWidth(short_header(headers[j]), boldf, fs)
        for r in rows:
            v = '' if j >= len(r) else ('' if r[j] is None else str(r[j]))
            w = max(w, stringWidth(_disp(j, v), base, fs))
        return w + pad
    col_w = []
    for j in range(ncol):
        w = measure(j)
        w = min(w, 60 * mm) if _is_wrap(headers[j]) else min(w, 46 * mm)
        col_w.append(max(w, 9 * mm))
    tot = sum(col_w)
    if tot > avail:
        wrap_idx = [j for j in range(ncol) if _is_wrap(headers[j])]
        slack = sum(max(0, col_w[j] - 24 * mm) for j in wrap_idx)
        over = tot - avail
        if slack > 0:
            take = min(over, slack)
            for j in wrap_idx:
                s = max(0, col_w[j] - 24 * mm)
                col_w[j] -= take * (s / slack) if slack else 0
            tot = sum(col_w); over = tot - avail
        if over > 0:
            f = avail / tot; col_w = [w * f for w in col_w]
    # Columns stay tight to their content (address/hobbies capped so they wrap);
    # a narrower-than-page table is centred rather than stretched.

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

    t = Table(data, colWidths=col_w, repeatRows=1, hAlign='CENTER')
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(NAVY)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW', (0, 0), (-1, -1), 0.4, colors.HexColor(LINE)),
        ('LINEAFTER', (0, 0), (-2, -1), 0.4, colors.HexColor(LINE)),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(ZEBRA)]),
        ('BOX', (0, 0), (-1, -1), 0.7, colors.HexColor(NAVY)),
    ]))

    buf = io.BytesIO()
    frame = Frame(margin + 1 * mm, margin + foot_h, avail, PH - mast_h - foot_h - margin,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    def paint(cv, doc):
        _draw_border(cv, PW, PH, margin)
        _draw_masthead(cv, PW, PH, margin, school, total, 'PDF', base, boldf, obl)
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
                self.setFont(base, 9.5); self.setFillColor(colors.HexColor(MUTED))
                self.drawCentredString(PW / 2, margin + 5 * mm, 'Page %d of %d' % (self._pageNumber, n))
                super().showPage()
            super().save()

    doc.build([t], canvasmaker=Numbered)
    return buf.getvalue()


def _draw_border(cv, PW, PH, margin):
    from reportlab.lib import colors
    cv.setStrokeColor(colors.HexColor(GOLD)); cv.setLineWidth(1.6)
    cv.roundRect(margin * 0.6, margin * 0.6, PW - 1.2 * margin, PH - 1.2 * margin, 9, stroke=1, fill=0)
    cv.setStrokeColor(colors.HexColor(LINE)); cv.setLineWidth(0.6)
    cv.roundRect(margin * 0.6 + 2.5, margin * 0.6 + 2.5, PW - 1.2 * margin - 5, PH - 1.2 * margin - 5, 8, stroke=1, fill=0)


def _draw_masthead(cv, PW, PH, margin, school, total, fmt, base, boldf, obl):
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    top = PH - margin - 3 * mm
    x = margin + 5 * mm
    logo = (school or {}).get('logo_path')
    lx = x
    if logo and os.path.exists(logo):
        try:
            from reportlab.lib.utils import ImageReader
            ir = ImageReader(logo); iw, ih = ir.getSize()
            h = 28 * mm; w = h * (iw / ih) if ih else 28 * mm
            cv.drawImage(ir, x, top - h, width=min(w, 30 * mm), height=h, mask='auto',
                         preserveAspectRatio=True)
            lx = x + min(w, 30 * mm) + 6 * mm
        except Exception:
            lx = x
    name = (school or {}).get('name') or 'School'
    cv.setFillColor(colors.HexColor(NAVY)); cv.setFont(boldf, 29)
    cv.drawString(lx, top - 9 * mm, name.upper()[:40])
    cv.setFillColor(colors.HexColor(INK)); cv.setFont(base, 11.5)
    addr = (school or {}).get('address') or ''
    if addr:
        cv.drawString(lx, top - 16 * mm, ('●  ' + addr)[:78])
    contact = '       '.join(p for p in [(school or {}).get('phone') or '', (school or {}).get('email') or ''] if p)
    if contact:
        cv.drawString(lx, top - 21.5 * mm, contact[:78])
    motto = (school or {}).get('motto') or ''
    if motto:
        cv.setFillColor(colors.HexColor(GOLD)); cv.setFont(obl, 12)
        cv.drawString(lx, top - 28 * mm, ('—  ' + motto + '  —')[:78])

    # Right info panel — large.
    pw = 118 * mm; ph = 28 * mm
    px = PW - margin - 5 * mm - pw; py = top - ph
    cv.setFillColor(colors.HexColor(PANEL)); cv.setStrokeColor(colors.HexColor(LINE)); cv.setLineWidth(0.8)
    cv.roundRect(px, py, pw, ph, 6, stroke=1, fill=1)
    cells = [('DATE GENERATED', timeutil.today().strftime('%d %b %Y')),
             ('TOTAL STUDENTS', str(total)), ('EXPORTED AS', fmt)]
    cwid = pw / 3
    for i, (lab, val) in enumerate(cells):
        cx = px + i * cwid + cwid / 2
        cv.setFillColor(colors.HexColor(MUTED)); cv.setFont(base, 8.5)
        cv.drawCentredString(cx, py + ph - 10 * mm, lab)
        cv.setFillColor(colors.HexColor(NAVY)); cv.setFont(boldf, 15)
        cv.drawCentredString(cx, py + 6 * mm, val)
        if i:
            cv.setStrokeColor(colors.HexColor(LINE)); cv.setLineWidth(0.6)
            cv.line(px + i * cwid, py + 4 * mm, px + i * cwid, py + ph - 4 * mm)


def _draw_footer(cv, PW, margin, foot_h, school, base, boldf, obl):
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    y = margin + 2.5 * mm
    cv.setStrokeColor(colors.HexColor(LINE)); cv.setLineWidth(0.6)
    cv.line(margin + 5 * mm, margin + foot_h, PW - margin - 5 * mm, margin + foot_h)
    name = (school or {}).get('name') or 'School'
    cv.setFillColor(colors.HexColor(NAVY)); cv.setFont(boldf, 9.5)
    cv.drawString(margin + 5 * mm, y + 1.5 * mm, name.upper()[:40])
    motto = (school or {}).get('motto') or ''
    if motto:
        cv.setFillColor(colors.HexColor(MUTED)); cv.setFont(obl, 8)
        cv.drawString(margin + 5 * mm, y - 2.5 * mm, motto[:50])
    cv.setFillColor(colors.HexColor(MUTED)); cv.setFont(obl, 8)
    cv.drawRightString(PW - margin - 5 * mm, y, 'This report is system-generated and confidential.')


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
    body, body_b = fnt(12), fnt(12, True)
    name_f, addr_f, motto_f = fnt(28, True), fnt(12), fnt(12)
    hdr_f, panel_lab, panel_val = fnt(12, True), fnt(9), fnt(15, True)
    foot_b, foot_s = fnt(11, True), fnt(9)
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

    def wrap(t, f, mw):
        """Word-wrap text to a max pixel width; returns a list of lines."""
        t = str(t)
        if tw(t, f) <= mw:
            return [t]
        words, lines, cur = t.split(' '), [], ''
        for w in words:
            trial = (cur + ' ' + w).strip()
            if tw(trial, f) <= mw or not cur:
                cur = trial
            else:
                lines.append(cur); cur = w
        if cur:
            lines.append(cur)
        return lines

    margin = 30 * S
    avail = PW * S - 2 * margin
    pad = 20 * S
    ncol = len(headers)

    def _disp(j, v):
        if headers[j].lower() == 'gender':
            g, _c = _gender_glyph(v)
            return (g + ' ' + v).strip()
        return v

    def measure(j):
        w = tw(short_header(headers[j]), hdr_f)
        for r in rows:
            v = '' if j >= len(r) else ('' if r[j] is None else str(r[j]))
            w = max(w, tw(_disp(j, v), body))
        return w + pad
    col_w = []
    for j in range(ncol):
        w = measure(j)
        w = min(w, int(300 * S)) if _is_wrap(headers[j]) else min(w, int(260 * S))
        col_w.append(max(w, int(56 * S)))
    tot = sum(col_w)
    if tot > avail:                        # shrink wrap columns first, then all
        wrap_idx = [j for j in range(ncol) if _is_wrap(headers[j])]
        slack = sum(max(0, col_w[j] - int(150 * S)) for j in wrap_idx)
        over = tot - avail
        if slack > 0:
            take = min(over, slack)
            for j in wrap_idx:
                s = max(0, col_w[j] - int(150 * S))
                col_w[j] -= int(take * (s / slack)) if slack else 0
            tot = sum(col_w); over = tot - avail
        if over > 0:
            f = avail / tot; col_w = [int(w * f) for w in col_w]
    table_w = sum(col_w)
    # Centre a table that is narrower than the page (columns stay tight).
    tx0 = margin + max(0, (avail - table_w) // 2)

    line_h = tmp.textbbox((0, 0), 'Ay', font=body)[3]
    cpx = 8 * S
    mast_h = 170 * S
    foot_h = 46 * S

    def row_lines(r):
        m = 1
        for j in range(ncol):
            v = '' if j >= len(r) else ('' if r[j] is None else str(r[j]))
            if _is_wrap(headers[j]):
                m = max(m, len(wrap(v, body, col_w[j] - 2 * cpx)))
        return m

    header_h = line_h + 18 * S
    # Paginate accounting for variable (wrapped) row heights.
    pages_rows, cur, cur_h = [], [], 0
    body_area = PH * S - margin - mast_h - header_h - foot_h
    for r in rows:
        rh = row_lines(r) * (line_h + 4 * S) + 12 * S
        if cur and cur_h + rh > body_area:
            pages_rows.append(cur); cur, cur_h = [], 0
        cur.append((r, rh)); cur_h += rh
    if cur or not pages_rows:
        pages_rows.append(cur)

    n = len(pages_rows)
    out_pages = []
    for pi, chunk in enumerate(pages_rows):
        img = Image.new('RGB', (PW * S, PH * S), C['white'])
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([int(margin * 0.6), int(margin * 0.6), PW * S - int(margin * 0.6), PH * S - int(margin * 0.6)],
                            radius=18, outline=C['gold'], width=4)
        _img_masthead(d, img, PW * S, margin, school, total, C, name_f, addr_f, motto_f,
                      panel_lab, panel_val, body, fit, tw)
        y0 = margin + mast_h
        d.rectangle([tx0, y0, tx0 + table_w, y0 + header_h], fill=C['navy'])
        x = tx0
        for j in range(ncol):
            d.text((x + cpx, y0 + (header_h - line_h) // 2), fit(short_header(headers[j]), hdr_f, col_w[j] - 2 * cpx),
                   fill=C['white'], font=hdr_f)
            x += col_w[j]
        yy = y0 + header_h
        for i, (r, rh) in enumerate(chunk):
            if i % 2:
                d.rectangle([tx0, yy, tx0 + table_w, yy + rh], fill=C['zebra'])
            x = tx0
            for j in range(ncol):
                v = '' if j >= len(r) else ('' if r[j] is None else str(r[j]))
                col = C['ink']
                if headers[j].lower() == 'gender':
                    g, _hex = _gender_glyph(v); v = (g + ' ' + v).strip()
                lines = wrap(v, body, col_w[j] - 2 * cpx) if _is_wrap(headers[j]) else [fit(v, body, col_w[j] - 2 * cpx)]
                ty = yy + 6 * S
                for ln in lines:
                    d.text((x + cpx, ty), ln, fill=col, font=body); ty += line_h + 4 * S
                x += col_w[j]
            d.line([tx0, yy, tx0 + table_w, yy], fill=C['line'], width=1)
            yy += rh
        d.rectangle([tx0, y0, tx0 + table_w, yy], outline=C['navy'], width=2)
        fy = PH * S - foot_h
        d.line([margin, fy, PW * S - margin, fy], fill=C['line'], width=1)
        d.text((margin, fy + 10 * S), ((school or {}).get('name') or 'School').upper(), fill=C['navy'], font=foot_b)
        conf = 'This report is system-generated and confidential.'
        d.text((PW * S - margin - tw(conf, foot_s), fy + 10 * S), conf, fill=C['muted'], font=foot_s)
        pnum = 'Page %d of %d' % (pi + 1, n)
        d.text((PW * S / 2 - tw(pnum, foot_s) / 2, fy + 10 * S), pnum, fill=C['muted'], font=foot_s)
        buf = io.BytesIO()
        img.resize((PW, PH), Image.LANCZOS).save(buf, format='PNG')
        out_pages.append(buf.getvalue())
    return out_pages


def _img_masthead(d, img, PW, margin, school, total, C, name_f, addr_f, motto_f,
                  panel_lab, panel_val, body, fit, tw):
    from PIL import Image
    x = margin + 10
    logo = (school or {}).get('logo_path')
    lx = x
    if logo and os.path.exists(logo):
        try:
            lg = Image.open(logo).convert('RGBA')
            h = 150; w = int(lg.width * h / lg.height)
            lg = lg.resize((min(w, 180), h), Image.LANCZOS)
            img.paste(lg, (x, margin + 8), lg)
            lx = x + min(w, 180) + 26
        except Exception:
            lx = x
    d.text((lx, margin + 10), ((school or {}).get('name') or 'School').upper(), fill=C['navy'], font=name_f)
    ty = margin + 10 + 64
    addr = (school or {}).get('address') or ''
    if addr:
        d.text((lx, ty), '●  ' + addr, fill=C['ink'], font=addr_f); ty += 32
    contact = '       '.join(p for p in [(school or {}).get('phone') or '', (school or {}).get('email') or ''] if p)
    if contact:
        d.text((lx, ty), contact, fill=C['ink'], font=addr_f); ty += 32
    motto = (school or {}).get('motto') or ''
    if motto:
        d.text((lx, ty), '—  ' + motto + '  —', fill=C['gold'], font=motto_f)
    # info panel — large
    pw = 560; ph = 130
    px = PW - margin - 10 - pw; py = margin + 8
    d.rounded_rectangle([px, py, px + pw, py + ph], radius=12, fill=C['panel'], outline=C['line'], width=2)
    cells = [('DATE GENERATED', timeutil.today().strftime('%d %b %Y')),
             ('TOTAL STUDENTS', str(total)), ('EXPORTED AS', 'IMAGE')]
    cwid = pw / 3
    for i, (lab, val) in enumerate(cells):
        cx = px + i * cwid + cwid / 2
        d.text((cx - tw(lab, panel_lab) / 2, py + 24), lab, fill=C['muted'], font=panel_lab)
        d.text((cx - tw(val, panel_val) / 2, py + 66), val, fill=C['navy'], font=panel_val)
        if i:
            d.line([px + i * cwid, py + 18, px + i * cwid, py + ph - 18], fill=C['line'], width=1)
