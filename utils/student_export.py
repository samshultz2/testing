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

def _first_font(cands):
    for p in cands:
        if os.path.exists(p):
            return p
    return cands[-1]


# Prefer Work Sans — a modern, geometric humanist grotesque vendored with the
# app — then fall back to Liberation Sans and DejaVu if it is ever missing.
_FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'fonts')
_LIB = '/usr/share/fonts/truetype/liberation/'
_DV = '/usr/share/fonts/truetype/dejavu/'
_FONT_REG = _first_font([os.path.join(_FONTS, 'WorkSans-Regular.ttf'), _LIB + 'LiberationSans-Regular.ttf', _DV + 'DejaVuSans.ttf'])
_FONT_BOLD = _first_font([os.path.join(_FONTS, 'WorkSans-Bold.ttf'), _LIB + 'LiberationSans-Bold.ttf', _DV + 'DejaVuSans-Bold.ttf'])
_FONT_ITAL = _first_font([os.path.join(_FONTS, 'WorkSans-Italic.ttf'), _LIB + 'LiberationSans-Italic.ttf', _DV + 'DejaVuSans-Oblique.ttf'])
# Back-compat aliases (used by the image renderer helpers below).
_DEJAVU, _DEJAVU_BOLD, _DEJAVU_OBL = _FONT_REG, _FONT_BOLD, _FONT_ITAL


def short_header(name):
    return _SHORT_HEADER.get(name, name)


def _is_wrap(h):
    k = (h or '').lower()
    return 'address' in k or 'hobb' in k


def _hex_rgb(h):
    h = (h or '#000000').lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _gender_glyph(value):
    # A small colour-coded dot (blue = male, pink = female). We use ● rather
    # than ♂/♀ so it renders in the modern body font without a symbol fallback.
    v = (value or '').strip().lower()
    if v.startswith('m'):
        return '●', '#1D4ED8'
    if v.startswith('f'):
        return '●', '#BE185D'
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
                                    TableStyle, Paragraph, NextPageTemplate)
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas as _canvas

    base, boldf, obl = 'Helvetica', 'Helvetica-Bold', 'Helvetica-Oblique'
    try:
        pdfmetrics.registerFont(TTFont('Body', _FONT_REG)); base = 'Body'
        pdfmetrics.registerFont(TTFont('Body-Bold', _FONT_BOLD)); boldf = 'Body-Bold'
        pdfmetrics.registerFont(TTFont('Body-Obl', _FONT_ITAL)); obl = 'Body-Obl'
    except Exception:
        pass

    total = total if total is not None else len(rows)
    PW, PH = landscape(A4)
    margin = 8 * mm
    mast_h = 44 * mm
    foot_h = 14 * mm
    avail = PW - 2 * margin - 2 * mm

    fs = 16
    cell = ParagraphStyle('c', fontName=base, fontSize=fs, leading=fs + 3, textColor=colors.HexColor(INK))
    cellc = ParagraphStyle('cc', parent=cell, alignment=TA_CENTER)
    headp = ParagraphStyle('h', fontName=boldf, fontSize=fs, leading=fs + 2,
                           textColor=colors.white, alignment=TA_CENTER)

    ncol = len(headers)
    cell_pad = 6            # points of L/R padding inside each table cell
    pad = 6 * mm            # width budget per column; must exceed 2*cell_pad
    def _disp(j, v):
        if headers[j].lower() == 'gender':
            g, _c = _gender_glyph(v)
            return (g + ' ' + v).strip()
        return v

    def _hdr_word(j):
        # Longest word in the (possibly multi-word) header, so headers may wrap.
        return max([stringWidth(t, boldf, fs) for t in short_header(headers[j]).split()] or [0])

    def val_w(j):
        w = 0
        for r in rows:
            v = '' if j >= len(r) else ('' if r[j] is None else str(r[j]))
            w = max(w, stringWidth(_disp(j, v), base, fs))
        return w

    def word_floor(j):
        # Widest single token (value words or header words). A wrap column
        # narrower than this would break words character-by-character.
        w = _hdr_word(j)
        for r in rows:
            v = '' if j >= len(r) else ('' if r[j] is None else str(r[j]))
            for tok in str(v).split():
                w = max(w, stringWidth(tok, base, fs))
        return w + pad
    col_w, floors = [], {}
    for j in range(ncol):
        if _is_wrap(headers[j]):
            # Address / hobbies wrap onto several lines: keep them just wide
            # enough for the longest word so the table stays phone-narrow.
            fl = word_floor(j)
            floors[j] = fl
            w = max(min(val_w(j) + pad, 38 * mm), fl)
        else:
            # Non-wrap: fit the widest value and the longest header word (the
            # header itself may wrap); the value never wraps.
            w = min(max(val_w(j), _hdr_word(j)) + pad, 50 * mm)
        col_w.append(max(w, 9 * mm))
    tot = sum(col_w)
    if tot > avail:
        # Shrink wrap columns, but never below their longest word.
        wrap_idx = [j for j in range(ncol) if _is_wrap(headers[j])]
        slack = sum(max(0, col_w[j] - floors[j]) for j in wrap_idx)
        over = tot - avail
        if slack > 0:
            take = min(over, slack)
            for j in wrap_idx:
                s = max(0, col_w[j] - floors[j])
                col_w[j] -= take * (s / slack) if slack else 0
            tot = sum(col_w); over = tot - avail
        if over > 0:
            f = avail / tot; col_w = [w * f for w in col_w]
    elif tot < avail:
        # Fill the A4 width by growing the non-wrap text columns; the wrap
        # columns stay narrow so address/hobbies keep wrapping.
        grow = [j for j in range(ncol) if not _is_wrap(headers[j])
                and headers[j].lower() not in ('s/n', 'sn', 'age', 'gender')]
        if not grow:
            grow = [j for j in range(ncol) if not _is_wrap(headers[j])] or list(range(ncol))
        base_sum = sum(col_w[j] for j in grow) or 1
        left = avail - tot
        for j in grow:
            col_w[j] += left * (col_w[j] / base_sum)

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

    # Modern, minimal table: a solid navy header, roomy rows, soft zebra and
    # horizontal hairlines only — no vertical gridlines or heavy outer box.
    t = Table(data, colWidths=col_w, repeatRows=1, hAlign='LEFT')
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(NAVY)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, 0), 9), ('BOTTOMPADDING', (0, 0), (-1, 0), 9),
        ('TOPPADDING', (0, 1), (-1, -1), 7), ('BOTTOMPADDING', (0, 1), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), cell_pad), ('RIGHTPADDING', (0, 0), (-1, -1), cell_pad),
        ('LINEBELOW', (0, 1), (-1, -1), 0.5, colors.HexColor(LINE)),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(ZEBRA)]),
        ('LINEBELOW', (0, 0), (-1, 0), 1.2, colors.HexColor(GOLD)),
    ]))

    buf = io.BytesIO()
    # The masthead is drawn on the first page only; later pages use the full
    # height (below a small top gap) so the table keeps flowing.
    frame_first = Frame(margin + 1 * mm, margin + foot_h, avail, PH - mast_h - foot_h - margin,
                        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    frame_later = Frame(margin + 1 * mm, margin + foot_h, avail, PH - foot_h - margin - 12 * mm,
                        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    def paint_first(cv, doc):
        _draw_border(cv, PW, PH, margin)
        _draw_masthead(cv, PW, PH, margin, school, total, 'PDF', base, boldf, obl)
        _draw_footer(cv, PW, margin, foot_h, school, base, boldf, obl)

    def paint_later(cv, doc):
        _draw_border(cv, PW, PH, margin)
        _draw_footer(cv, PW, margin, foot_h, school, base, boldf, obl)

    doc = BaseDocTemplate(buf, pagesize=(PW, PH), leftMargin=margin, rightMargin=margin,
                          topMargin=margin, bottomMargin=margin)
    doc.addPageTemplates([
        PageTemplate(id='first', frames=[frame_first], onPage=paint_first),
        PageTemplate(id='later', frames=[frame_later], onPage=paint_later),
    ])

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

    doc.build([NextPageTemplate('later'), t], canvasmaker=Numbered)
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
    from reportlab.pdfbase.pdfmetrics import stringWidth

    def _fit(s, font, size, maxw):
        s = str(s)
        if stringWidth(s, font, size) <= maxw:
            return s
        while s and stringWidth(s + '…', font, size) > maxw:
            s = s[:-1]
        return (s + '…') if s else ''

    top = PH - margin - 3 * mm
    x = margin + 5 * mm

    # Right info panel — geometry first so the left block keeps a gutter.
    pw = 118 * mm; ph = 28 * mm
    px = PW - margin - 5 * mm - pw; py = top - ph
    right_limit = px - 8 * mm  # gutter between the left details and the panel

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
    avail_l = right_limit - lx
    name = ((school or {}).get('name') or 'School').upper()
    nsize = 29
    while nsize > 16 and stringWidth(name, boldf, nsize) > avail_l:
        nsize -= 1
    cv.setFillColor(colors.HexColor(NAVY)); cv.setFont(boldf, nsize)
    cv.drawString(lx, top - 9 * mm, _fit(name, boldf, nsize, avail_l))
    cv.setFillColor(colors.HexColor(INK)); cv.setFont(base, 11.5)
    addr = (school or {}).get('address') or ''
    if addr:
        cv.drawString(lx, top - 16 * mm, _fit('●  ' + addr, base, 11.5, avail_l))
    contact = '       '.join(p for p in [(school or {}).get('phone') or '', (school or {}).get('email') or ''] if p)
    if contact:
        cv.drawString(lx, top - 21.5 * mm, _fit(contact, base, 11.5, avail_l))
    motto = (school or {}).get('motto') or ''
    if motto:
        cv.setFillColor(colors.HexColor(GOLD)); cv.setFont(obl, 12)
        cv.drawString(lx, top - 28 * mm, _fit('—  ' + motto + '  —', obl, 12, avail_l))

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
    body, body_b = fnt(18), fnt(18, True)
    name_f, addr_f, motto_f = fnt(42, True), fnt(17), fnt(17)
    hdr_f, panel_lab, panel_val = fnt(18, True), fnt(12), fnt(22, True)
    foot_b, foot_s = fnt(13, True), fnt(11)
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
    pad = 34 * S            # must exceed 2*cpx (per-cell L/R padding) so nothing clips
    ncol = len(headers)

    def _disp(j, v):
        if headers[j].lower() == 'gender':
            g, _c = _gender_glyph(v)
            return (g + ' ' + v).strip()
        return v

    def _hdr_word(j):
        return max([tw(t, hdr_f) for t in short_header(headers[j]).split()] or [0])

    def val_w(j):
        w = 0
        for r in rows:
            v = '' if j >= len(r) else ('' if r[j] is None else str(r[j]))
            w = max(w, tw(_disp(j, v), body))
        return w

    def word_floor(j):
        w = _hdr_word(j)
        for r in rows:
            v = '' if j >= len(r) else ('' if r[j] is None else str(r[j]))
            for tok in str(v).split():
                w = max(w, tw(tok, body))
        return w + pad
    col_w, floors = [], {}
    for j in range(ncol):
        if _is_wrap(headers[j]):
            # Keep address / hobbies just wide enough for the longest word so
            # they wrap onto several lines without breaking words apart.
            fl = word_floor(j)
            floors[j] = fl
            w = max(min(val_w(j) + pad, int(210 * S)), fl)
        else:
            # Non-wrap: fit widest value + longest header word (header may wrap).
            w = min(max(val_w(j), _hdr_word(j)) + pad, int(280 * S))
        col_w.append(max(w, int(56 * S)))
    tot = sum(col_w)
    if tot > avail:                        # shrink wrap columns, never below a word
        wrap_idx = [j for j in range(ncol) if _is_wrap(headers[j])]
        slack = sum(max(0, col_w[j] - floors[j]) for j in wrap_idx)
        over = tot - avail
        if slack > 0:
            take = min(over, slack)
            for j in wrap_idx:
                s = max(0, col_w[j] - floors[j])
                col_w[j] -= int(take * (s / slack)) if slack else 0
            tot = sum(col_w); over = tot - avail
        if over > 0:
            f = avail / tot; col_w = [int(w * f) for w in col_w]
    elif tot < avail:
        # Fill the A4 width by growing the non-wrap text columns; wrap columns
        # stay capped so address/hobbies keep wrapping.
        grow = [j for j in range(ncol) if not _is_wrap(headers[j])
                and headers[j].lower() not in ('s/n', 'sn', 'age', 'gender')]
        if not grow:
            grow = [j for j in range(ncol) if not _is_wrap(headers[j])] or list(range(ncol))
        base_sum = sum(col_w[j] for j in grow) or 1
        left = avail - tot
        for j in grow:
            col_w[j] += int(left * (col_w[j] / base_sum))
    table_w = sum(col_w)
    tx0 = margin  # full-width, left-aligned to the page margin

    line_h = tmp.textbbox((0, 0), 'Ay', font=body)[3]
    cpx = 12 * S
    mast_h = 200 * S
    foot_h = 46 * S

    def row_lines(r):
        m = 1
        for j in range(ncol):
            v = '' if j >= len(r) else ('' if r[j] is None else str(r[j]))
            if _is_wrap(headers[j]):
                m = max(m, len(wrap(v, body, col_w[j] - 2 * cpx)))
        return m

    header_h = line_h + 18 * S
    top_gap = 40 * S  # small top margin on later (masthead-free) pages
    # The masthead is on the first page only, so page 1 has less room for rows
    # than the rest — paginate with the right body height for each page.
    pages_rows, cur, cur_h = [], [], 0
    first_area = PH * S - margin - mast_h - header_h - foot_h
    rest_area = PH * S - margin - top_gap - header_h - foot_h
    for r in rows:
        rh = row_lines(r) * (line_h + 4 * S) + 12 * S
        area = first_area if not pages_rows else rest_area
        if cur and cur_h + rh > area:
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
        if pi == 0:
            _img_masthead(d, img, PW * S, margin, school, total, C, name_f, addr_f, motto_f,
                          panel_lab, panel_val, body, fit, tw)
            y0 = margin + mast_h
        else:
            y0 = margin + top_gap
        # Solid navy header band with a thin gold accent underline.
        d.rectangle([tx0, y0, tx0 + table_w, y0 + header_h], fill=C['navy'])
        d.rectangle([tx0, y0 + header_h - 3, tx0 + table_w, y0 + header_h], fill=C['gold'])
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
                ty = yy + 9 * S
                if headers[j].lower() == 'gender':
                    g, ghex = _gender_glyph(v)
                    gx = x + cpx
                    if g:
                        d.text((gx, ty), g, fill=_hex_rgb(ghex), font=body)
                        gx += tw(g + ' ', body)
                    d.text((gx, ty), fit(v, body, col_w[j] - 2 * cpx - (gx - x - cpx)), fill=C['ink'], font=body)
                    x += col_w[j]
                    continue
                lines = wrap(v, body, col_w[j] - 2 * cpx) if _is_wrap(headers[j]) else [fit(v, body, col_w[j] - 2 * cpx)]
                for ln in lines:
                    d.text((x + cpx, ty), ln, fill=C['ink'], font=body); ty += line_h + 4 * S
                x += col_w[j]
            # horizontal hairline only — no vertical gridlines (modern, minimal)
            d.line([tx0, yy + rh, tx0 + table_w, yy + rh], fill=C['line'], width=1)
            yy += rh
        # subtle closing rule instead of a boxed outline
        d.line([tx0, yy, tx0 + table_w, yy], fill=C['line'], width=1)
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
            h = 190; w = int(lg.width * h / lg.height)
            lg = lg.resize((min(w, 220), h), Image.LANCZOS)
            img.paste(lg, (x, margin + 10), lg)
            lx = x + min(w, 220) + 30
        except Exception:
            lx = x
    # info panel — large (defined first so left text keeps a gutter before it)
    pw = 780; ph = 176
    px = PW - margin - 12 - pw; py = margin + 10
    right_limit = px - 32
    d.rounded_rectangle([px, py, px + pw, py + ph], radius=14, fill=C['panel'], outline=C['line'], width=2)
    cells = [('DATE GENERATED', timeutil.today().strftime('%d %b %Y')),
             ('TOTAL STUDENTS', str(total)), ('EXPORTED AS', 'IMAGE')]
    cwid = pw / 3
    for i, (lab, val) in enumerate(cells):
        cx = px + i * cwid + cwid / 2
        d.text((cx - tw(lab, panel_lab) / 2, py + 34), lab, fill=C['muted'], font=panel_lab)
        d.text((cx - tw(val, panel_val) / 2, py + 92), val, fill=C['navy'], font=panel_val)
        if i:
            d.line([px + i * cwid, py + 24, px + i * cwid, py + ph - 24], fill=C['line'], width=1)
    # left: school identity — shrink the name to fit before the panel, don't clip.
    from PIL import ImageFont
    nm = ((school or {}).get('name') or 'School').upper()
    nf, nsz = name_f, 42
    while nsz > 22 and tw(nm, nf) > (right_limit - lx):
        nsz -= 2
        try:
            nf = ImageFont.truetype(_DEJAVU_BOLD, int(nsz * 2))
        except Exception:
            break
    name_top = margin + 14
    d.text((lx, name_top), fit(nm, nf, right_limit - lx), fill=C['navy'], font=nf)
    # start the details clear of the tall name glyphs
    ty = d.textbbox((lx, name_top), nm, font=nf)[3] + 22
    addr = (school or {}).get('address') or ''
    if addr:
        d.text((lx, ty), fit('●  ' + addr, addr_f, right_limit - lx), fill=C['ink'], font=addr_f); ty += 46
    contact = '       '.join(p for p in [(school or {}).get('phone') or '', (school or {}).get('email') or ''] if p)
    if contact:
        d.text((lx, ty), fit(contact, addr_f, right_limit - lx), fill=C['ink'], font=addr_f); ty += 46
    motto = (school or {}).get('motto') or ''
    if motto:
        d.text((lx, ty), fit('—  ' + motto + '  —', motto_f, right_limit - lx), fill=C['gold'], font=motto_f)
