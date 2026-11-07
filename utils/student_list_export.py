"""Branded student-list documents (Students page → Export).

One description of the list (``spec``) is rendered to every format so they look
the same: PDF (reportlab), image (the PDF rasterised with PyMuPDF and cropped
to its content), Word (python-docx) and Excel (openpyxl).

Design: school letterhead (logo, name, motto, address · phone · email) over a
thin bar in the school's colours; a title with a subtitle and count boxes;
students grouped by class arm, each group headed with its count and boys/girls
split; a light, readable table (surname in bold, gender as a coloured dot,
missing exam numbers flagged); optional signature lines and blank marking
columns; and a footer with the preparer, a confidentiality note and
"Page n of N".

``spec`` keys::

    title, subtitle, doc_tag              str
    columns   [{'key', 'label', 'kind'}]  kind: id | name | gender | date | phone
                                          | exam | wrap | text | num | photo
    groups    [{'name': str|None, 'rows': [{key: value, ...}]}]
              a 'name' value is (surname, rest); 'gender' is 'Male'/'Female';
              'photo' is image bytes or None; 'date' a date or None
    stats     [(value, label, tone)]      tone: None | 'male' | 'female' | 'warn'
    orientation 'auto' | 'portrait' | 'landscape';  size 's' | 'm' | 'l'
    signatures bool;  blank_cols int;  prepared_by str;  generated datetime
    school    utils.school.school_profile();  colors  see colors_for()
"""
import io
import os
from datetime import date, datetime

# --------------------------------------------------------------------------- #
# Fonts & colours
# --------------------------------------------------------------------------- #
_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'fonts')
FONT_FILES = {
    'Body': 'DMSans-Regular.ttf', 'BodySemi': 'DMSans-SemiBold.ttf',
    'BodyBold': 'DMSans-Bold.ttf', 'Display': 'PlusJakartaSans-ExtraBold.ttf',
}
_registered = False


def _register_fonts():
    """Register the document fonts with reportlab once (falls back to
    Helvetica if a file is missing, so an export never fails on fonts)."""
    global _registered, F
    if _registered:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    ok = {}
    for name, fn in FONT_FILES.items():
        p = os.path.join(_FONT_DIR, fn)
        try:
            pdfmetrics.registerFont(TTFont('SL-' + name, p))
            ok[name] = 'SL-' + name
        except Exception:
            ok[name] = 'Helvetica-Bold' if name != 'Body' else 'Helvetica'
    F = ok
    _registered = True


F = {'Body': 'Helvetica', 'BodySemi': 'Helvetica-Bold', 'BodyBold': 'Helvetica-Bold', 'Display': 'Helvetica-Bold'}

DEFAULT_PRIMARY = '#0d6a4e'
DEFAULT_ACCENT = '#b7791f'
INK, INK2, MUTED = '#0f172a', '#334155', '#64748b'
LINE, LINE2, BG, ZEBRA = '#e2e8f0', '#eef2f6', '#f6f8fb', '#fbfcfd'
MALE, FEMALE, WARN = '#2563eb', '#db2777', '#b7791f'


def _hex(h):
    h = (h or '').strip().lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def _mix(h, other, t):
    a, b = _hex(h), _hex(other)
    return '#%02x%02x%02x' % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def colors_for(branding=None):
    """The school's document colours (Settings → document branding), with the
    app's green / gold as defaults."""
    b = branding or {}
    primary = b.get('primary_color') if _hex(b.get('primary_color')) else DEFAULT_PRIMARY
    accent = b.get('accent_color') if _hex(b.get('accent_color')) else DEFAULT_ACCENT
    return {'primary': primary, 'primary2': _mix(primary, '#ffffff', .25),
            'soft': _mix(primary, '#ffffff', .9), 'accent': accent,
            'dark': _mix(primary, '#000000', .25)}


SIZES = {'s': 8.6, 'm': 9.6, 'l': 11.0}


def initials(name):
    words = [w for w in (name or 'School').replace('.', ' ').split() if w[:1].isalpha()]
    return ''.join(w[0] for w in words[:2]).upper() or 'S'


def fmt_date(v):
    if isinstance(v, (date, datetime)):
        return v.strftime('%d %b %Y')
    return v or ''


def _contact_line(school):
    return ' · '.join(x for x in (school.get('address'), school.get('phone'), school.get('email')) if x)


def _cell_text(col, v):
    """Plain-text value of a cell (for measuring, Word and CSV-like uses)."""
    k = col['kind']
    if k == 'name':
        s, rest = v if isinstance(v, (tuple, list)) else (v or '', '')
        return (s + ' ' + rest).strip()
    if k == 'date':
        return fmt_date(v)
    if k == 'photo':
        return ''
    return '' if v is None else str(v)


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def _page_size(spec, avail_by_orient):
    from reportlab.lib.pagesizes import A4, landscape
    o = spec.get('orientation') or 'auto'
    if o == 'landscape':
        return landscape(A4)
    if o == 'portrait':
        return A4
    return landscape(A4) if avail_by_orient['portrait'] < spec['_natural_w'] else A4


def _natural_widths(spec, fs):
    """Comfortable width per column (points) at font size ``fs``."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    pad = 14
    rows = [r for g in spec['groups'] for r in g['rows']]
    widths = []
    for c in spec['columns']:
        k = c['kind']
        head = stringWidth(c['label'].upper(), F['BodyBold'], fs * .78) * 1.12 + pad
        if k == 'photo':
            widths.append(max(head, fs * 2.6 + pad))
            continue
        if k == 'gender':
            widths.append(max(head, stringWidth('Female', F['BodySemi'], fs * .92) + fs + pad))
            continue
        font = F['BodyBold'] if k == 'name' else F['Body']
        vals = [_cell_text(c, r.get(c['key'])) for r in rows] or ['']
        if k == 'exam':
            vals.append('— missing')
        longest = max(stringWidth(v, font, fs) for v in vals) + pad
        if k == 'wrap':
            longest = min(longest, fs * 22)
        widths.append(max(head, longest))
    return widths


def _fit_widths(natural, avail, kinds, blank_cols, fs):
    sn = fs * 2.6
    blank_w = fs * 4.2
    need = sum(natural) + sn + blank_cols * blank_w
    widths = list(natural)
    if need > avail:
        # Shrink wrap-able text first (names / addresses wrap), then everything.
        over = need - avail
        flex = [i for i, k in enumerate(kinds) if k in ('wrap', 'name', 'text')]
        room = sum(max(0, widths[i] - fs * 6) for i in flex)
        if room:
            take = min(over, room)
            for i in flex:
                widths[i] -= take * max(0, widths[i] - fs * 6) / room
            over -= take
        if over > 0:
            scale = (avail - sn - blank_cols * blank_w) / sum(widths)
            widths = [w * scale for w in widths]
    else:
        extra = avail - need
        grow = [i for i, k in enumerate(kinds) if k not in ('gender', 'photo', 'num')] or list(range(len(kinds)))
        tot = sum(widths[i] for i in grow) or 1
        for i in grow:
            widths[i] += extra * widths[i] / tot
    return [sn] + widths + [blank_w] * blank_cols


def render_pdf(spec):
    """Bytes of the branded A4 PDF."""
    _register_fonts()
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph, Table,
                                    TableStyle, Spacer, Flowable, KeepTogether, Image)
    from reportlab.pdfbase.pdfmetrics import stringWidth

    C = spec['colors']
    school = spec['school']
    fs = SIZES.get(spec.get('size') or 'm', 9.6)
    margin = 34
    spec['_natural_w'] = (sum(_natural_widths(spec, fs)) + fs * 2.6
                          + spec.get('blank_cols', 0) * fs * 4.2)
    avail = {'portrait': A4[0] - 2 * margin}
    PW, PH = _page_size(spec, avail)
    spec['_orientation'] = 'landscape' if PW > PH else 'portrait'
    avail_w = PW - 2 * margin
    kinds = [c['kind'] for c in spec['columns']]
    col_w = _fit_widths(_natural_widths(spec, fs), avail_w, kinds, spec.get('blank_cols', 0), fs)

    head_h = 112      # first-page letterhead
    head2_h = 46      # later pages
    foot_h = 40
    title = spec.get('title') or 'Student List'
    gen = spec.get('generated') or datetime.now()

    # ---- canvas: letterhead, later-page header, footer with "Page n of N" ----
    logo = None
    if school.get('logo_path') and os.path.exists(school['logo_path']):
        try:
            logo = ImageReader(school['logo_path'])
        except Exception:
            logo = None

    def letterhead(cv):
        top = PH - 30
        x = margin
        s = 50
        if logo:
            iw, ih = logo.getSize()
            r = min(s / iw, s / ih)
            cv.drawImage(logo, x, top - s + (s - ih * r) / 2, iw * r, ih * r, mask='auto')
        else:
            cv.setFillColor(colors.HexColor(C['primary']))
            cv.roundRect(x, top - s, s, s, 12, stroke=0, fill=1)
            cv.setFillColor(colors.white)
            cv.setFont(F['Display'], 18)
            cv.drawCentredString(x + s / 2, top - s / 2 - 6.3, initials(school.get('name')))
        tx = x + s + 14
        cv.setFillColor(colors.HexColor(INK))
        name = school.get('name') or 'School'
        nsz = 17
        right_reserve = 150
        while nsz > 11 and stringWidth(name, F['Display'], nsz) > PW - margin - tx - right_reserve:
            nsz -= .5
        cv.setFont(F['Display'], nsz)
        cv.drawString(tx, top - 17, name)
        y = top - 31
        if school.get('motto'):
            cv.setFillColor(colors.HexColor(C['primary']))
            cv.setFont(F['BodyBold'], 7.6)
            cv.drawString(tx, y, school['motto'].upper()[:120], charSpace=.9)
            y -= 12
        line = _contact_line(school)
        if line:
            cv.setFillColor(colors.HexColor(MUTED))
            cv.setFont(F['Body'], 7.8)
            cv.drawString(tx, y, line[:160])
        # doc tag + generated
        tag = (spec.get('doc_tag') or 'STUDENT LIST').upper()
        cv.setFont(F['BodyBold'], 7)
        tw = stringWidth(tag, F['BodyBold'], 7) + len(tag) * 1.2 + 16
        cv.setFillColor(colors.HexColor(C['soft']))
        cv.roundRect(PW - margin - tw, top - 18, tw, 15, 7.5, stroke=0, fill=1)
        cv.setFillColor(colors.HexColor(C['primary']))
        cv.drawString(PW - margin - tw + 8, top - 13.2, tag, charSpace=1.2)
        cv.setFillColor(colors.HexColor(MUTED))
        cv.setFont(F['Body'], 7.8)
        cv.drawRightString(PW - margin, top - 31, gen.strftime('Generated %d %b %Y, %H:%M'))
        # accent bar in the school's colours
        by = PH - head_h + 22
        cv.saveState()
        p = cv.beginPath(); p.roundRect(margin, by, PW - 2 * margin, 3, 1.5)
        cv.clipPath(p, stroke=0, fill=0)
        cv.linearGradient(margin, by, PW - margin, by,
                          (colors.HexColor(C['primary']), colors.HexColor(C['primary2']), colors.HexColor(C['accent'])),
                          (0, .6, 1), extend=True)
        cv.restoreState()

    def small_header(cv):
        y = PH - 28
        cv.setFillColor(colors.HexColor(INK))
        cv.setFont(F['BodyBold'], 8.5)
        cv.drawString(margin, y, school.get('name') or 'School')
        cv.setFillColor(colors.HexColor(MUTED))
        cv.setFont(F['Body'], 8.5)
        cv.drawRightString(PW - margin, y, title + (' · ' + spec['subtitle'] if spec.get('subtitle') else ''))
        cv.setFillColor(colors.HexColor(C['primary']))
        cv.rect(margin, y - 9, PW - 2 * margin, 1.6, stroke=0, fill=1)

    def footer(cv, page, total):
        y = 24
        cv.setStrokeColor(colors.HexColor(LINE)); cv.setLineWidth(.6)
        cv.line(margin, y + 14, PW - margin, y + 14)
        cv.setFont(F['BodyBold'], 7.4); cv.setFillColor(colors.HexColor(INK2))
        nm = school.get('name') or 'School'
        cv.drawString(margin, y, nm)
        cv.setFont(F['Body'], 7.4); cv.setFillColor(colors.HexColor(MUTED))
        rest = ' · ' + title + (' · prepared by ' + spec['prepared_by'] if spec.get('prepared_by') else '')
        cv.drawString(margin + stringWidth(nm, F['BodyBold'], 7.4), y, rest)
        note = 'Contains personal data — handle confidentially'
        left_end = margin + stringWidth(nm + rest, F['Body'], 7.4) + 20
        nw = stringWidth(note, F['Body'], 7.4)
        if left_end + nw + 90 < PW - margin:
            cv.drawRightString(PW - margin - 78, y, note)
        label = 'Page %d of %d' % (page, total)
        w = stringWidth(label, F['BodyBold'], 7.4) + 16
        cv.setFillColor(colors.HexColor(BG)); cv.setStrokeColor(colors.HexColor(LINE))
        cv.roundRect(PW - margin - w, y - 4.5, w, 14, 7, stroke=1, fill=1)
        cv.setFillColor(colors.HexColor(INK2)); cv.setFont(F['BodyBold'], 7.4)
        cv.drawCentredString(PW - margin - w / 2, y, label)

    class NumberedCanvas(rl_canvas.Canvas):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._saved = []

        def showPage(self):
            self._saved.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved)
            for st in self._saved:
                self.__dict__.update(st)
                (letterhead if self._pageNumber == 1 else small_header)(self)
                footer(self, self._pageNumber, total)
                super().showPage()
            super().save()

    # ---- styles -------------------------------------------------------------
    st_title = ParagraphStyle('t', fontName=F['Display'], fontSize=20, leading=24, textColor=colors.HexColor(INK))
    st_sub = ParagraphStyle('s', fontName=F['Body'], fontSize=9.6, leading=13, textColor=colors.HexColor(INK2))
    st_cell = ParagraphStyle('c', fontName=F['Body'], fontSize=fs, leading=fs * 1.3, textColor=colors.HexColor(INK2))
    st_name = ParagraphStyle('n', parent=st_cell, textColor=colors.HexColor(INK2))
    st_head = ParagraphStyle('h', fontName=F['BodyBold'], fontSize=fs * .78, leading=fs * 1.0,
                             textColor=colors.HexColor(MUTED))
    st_sn = ParagraphStyle('sn', parent=st_cell, textColor=colors.HexColor('#94a3b8'))

    class Stat(Flowable):
        def __init__(self, value, label, tone):
            super().__init__()
            self.v, self.l, self.tone = str(value), label.upper(), tone
            self.w = max(58, stringWidth(self.l, F['BodyBold'], 6.4) * 1.1 + 20,
                         stringWidth(self.v, F['Display'], 15) + 20)

        def wrap(self, aw, ah):
            return self.w, 42

        def draw(self):
            cv = self.canv
            cv.setStrokeColor(colors.HexColor(LINE)); cv.setFillColor(colors.white); cv.setLineWidth(.8)
            cv.roundRect(0, 0, self.w, 42, 9, stroke=1, fill=1)
            col = {'male': MALE, 'female': FEMALE, 'warn': WARN}.get(self.tone, INK)
            cv.setFillColor(colors.HexColor(col)); cv.setFont(F['Display'], 15)
            cv.drawString(10, 21, self.v)
            cv.setFillColor(colors.HexColor(MUTED)); cv.setFont(F['BodyBold'], 6.4)
            cv.drawString(10, 9, self.l, charSpace=.5)

    class GroupHead(Flowable):
        def __init__(self, name, count, split, width):
            super().__init__()
            self.name, self.count, self.split, self.width = name, count, split, width

        def wrap(self, aw, ah):
            return self.width, 26

        def draw(self):
            cv = self.canv
            y = 8
            cv.setFillColor(colors.HexColor(INK)); cv.setFont(F['Display'], 11)
            cv.drawString(0, y, self.name)
            x = stringWidth(self.name, F['Display'], 11) + 9
            pill = self.count
            pw = stringWidth(pill, F['Body'], 8) + 14
            cv.setFillColor(colors.HexColor(BG)); cv.setStrokeColor(colors.HexColor(LINE)); cv.setLineWidth(.7)
            cv.roundRect(x, y - 3.5, pw, 14, 7, stroke=1, fill=1)
            cv.setFillColor(colors.HexColor(MUTED)); cv.setFont(F['Body'], 8)
            cv.drawString(x + 7, y, pill)
            x += pw + 8
            if self.split:
                cv.drawString(x, y, self.split)
                x += stringWidth(self.split, F['Body'], 8) + 10
            cv.setStrokeColor(colors.HexColor(LINE)); cv.line(x, y + 3, self.width, y + 3)

    class Gender(Flowable):
        def __init__(self, text):
            super().__init__()
            self.t = text or ''

        def wrap(self, aw, ah):
            return aw, fs * 1.3

        def draw(self):
            if not self.t:
                return
            col = colors.HexColor(FEMALE if self.t.lower().startswith('f') else MALE)
            cv = self.canv
            cv.setFillColor(col)
            cv.circle(fs * .3, fs * .66, fs * .27, stroke=0, fill=1)
            cv.setFont(F['BodySemi'], fs * .92)
            cv.drawString(fs * .85, fs * .36, self.t)

    def photo_flowable(data):
        if not data:
            return ''
        try:
            from PIL import Image as PI, ImageDraw
            im = PI.open(io.BytesIO(data)).convert('RGB')
            s = min(im.size)
            im = im.crop(((im.width - s) // 2, (im.height - s) // 2, (im.width + s) // 2, (im.height + s) // 2)).resize((96, 96))
            mask = PI.new('L', (96, 96), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, 95, 95), fill=255)
            out = PI.new('RGBA', (96, 96)); out.paste(im, (0, 0), mask)
            b = io.BytesIO(); out.save(b, 'PNG'); b.seek(0)
            return Image(b, width=fs * 2.2, height=fs * 2.2)
        except Exception:
            return ''

    def cell(col, v):
        k = col['kind']
        if k == 'name':
            s, rest = v if isinstance(v, (tuple, list)) else (v or '', '')
            return Paragraph('<font name="%s" color="%s">%s</font> %s' % (F['BodyBold'], INK, _esc(s), _esc(rest)), st_name)
        if k == 'gender':
            return Gender(v)
        if k == 'photo':
            return photo_flowable(v)
        if k == 'exam' and not (v or '').strip():
            return Paragraph('<font name="%s" color="%s">— missing</font>' % (F['BodyBold'], WARN), st_cell)
        return Paragraph(_esc(_cell_text(col, v)), st_cell)

    head_row = [Paragraph('#', st_head)] + [Paragraph(_esc(c['label'].upper()), st_head) for c in spec['columns']] \
        + [Paragraph('', st_head) for _ in range(spec.get('blank_cols', 0))]

    def table_for(rows):
        data = [head_row]
        for i, r in enumerate(rows, 1):
            data.append([Paragraph(str(i), st_sn)] + [cell(c, r.get(c['key'])) for c in spec['columns']]
                        + ['' for _ in range(spec.get('blank_cols', 0))])
        t = Table(data, colWidths=col_w, repeatRows=1)
        style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(BG)),
            ('LINEABOVE', (0, 0), (-1, 0), .7, colors.HexColor(LINE)),
            ('LINEBELOW', (0, 0), (-1, 0), .7, colors.HexColor(LINE)),
            ('LINEBELOW', (0, 1), (-1, -1), .5, colors.HexColor(LINE2)),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, 0), 6), ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('TOPPADDING', (0, 1), (-1, -1), fs * .42), ('BOTTOMPADDING', (0, 1), (-1, -1), fs * .42),
            ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]
        for i in range(2, len(data), 2):
            style.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor(ZEBRA)))
        nb = spec.get('blank_cols', 0)
        if nb:
            style.append(('LINEBEFORE', (len(head_row) - nb, 0), (-1, -1), .5, colors.HexColor(LINE)))
            style.append(('GRID', (len(head_row) - nb, 1), (-1, -1), .5, colors.HexColor(LINE)))
        t.setStyle(TableStyle(style))
        return t

    def signatures():
        gap = 28
        w = (avail_w - 2 * gap) / 3
        cells = [['', '', '', '', ''], ['Class teacher', '', 'Principal', '', 'Date']]
        t = Table(cells, colWidths=[w, gap, w, gap, w], rowHeights=[26, 14])
        t.setStyle(TableStyle([
            ('LINEABOVE', (0, 1), (0, 1), .8, colors.HexColor(INK2)),
            ('LINEABOVE', (2, 1), (2, 1), .8, colors.HexColor(INK2)),
            ('LINEABOVE', (4, 1), (4, 1), .8, colors.HexColor(INK2)),
            ('FONT', (0, 1), (-1, 1), F['Body'], 8), ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor(MUTED)),
            ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        return t

    # ---- story --------------------------------------------------------------
    story = []
    stats = [Stat(*s) for s in spec.get('stats') or []]
    left = [Paragraph(_esc(title), st_title)]
    if spec.get('subtitle'):
        left.append(Spacer(1, 2)); left.append(Paragraph(_esc(spec['subtitle']), st_sub))
    if stats:
        sw = sum(s.w for s in stats) + 6 * (len(stats) - 1)
        stat_row = Table([stats], colWidths=[s.w + 6 for s in stats[:-1]] + [stats[-1].w], rowHeights=[42])
        sw = sum(s.w for s in stats) + 6 * (len(stats) - 1)
        stat_row.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                                      ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
        hb = Table([[left, stat_row]], colWidths=[avail_w - sw - 4, sw + 4])
    else:
        hb = Table([[left]], colWidths=[avail_w])
    hb.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'BOTTOM'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                            ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
    story += [hb, Spacer(1, 8)]

    for g in spec['groups']:
        rows = g['rows']
        if g.get('name'):
            m = sum(1 for r in rows if (r.get('_gender') or '').lower().startswith('m'))
            f = sum(1 for r in rows if (r.get('_gender') or '').lower().startswith('f'))
            noun = spec.get('noun') or 'students'
            split = ('%d M · %d F' % (m, f)) if (m or f) else ''
            story.append(KeepTogether([Spacer(1, 6), GroupHead(g['name'], '%d %s' % (len(rows), noun if len(rows) != 1 else noun.rstrip('s')), split, avail_w)]))
        story.append(table_for(rows))
        if spec.get('signatures') and g.get('name'):
            story += [Spacer(1, 14), signatures()]
    if spec.get('signatures') and not any(g.get('name') for g in spec['groups']):
        story += [Spacer(1, 18), signatures()]

    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=(PW, PH), leftMargin=margin, rightMargin=margin,
                          topMargin=margin, bottomMargin=margin, title=title,
                          author=school.get('name') or '', creator='Student export')
    first = Frame(margin, foot_h + 14, avail_w, PH - head_h - foot_h - 14, id='f1',
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    later = Frame(margin, foot_h + 14, avail_w, PH - head2_h - foot_h - 14, id='f2',
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    from reportlab.platypus import NextPageTemplate
    doc.addPageTemplates([PageTemplate('first', [first]), PageTemplate('later', [later])])
    story.insert(0, NextPageTemplate('later'))
    doc.build(story, canvasmaker=NumberedCanvas)
    return buf.getvalue()


def _esc(s):
    return (str(s or '')).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


# --------------------------------------------------------------------------- #
# Image: the PDF, rasterised, with the empty band above the footer removed
# --------------------------------------------------------------------------- #
def render_images(spec, zoom=2.0, only_page=None):
    """PNG bytes per page — the same design as the PDF, cropped to content.
    With ``only_page`` returns ``([that page], total_pages)``."""
    import fitz
    from PIL import Image as PI, ImageChops
    pdf = render_pdf(spec)
    doc = fitz.open(stream=pdf, filetype='pdf')
    total = doc.page_count
    out = []
    pages = [doc[min(only_page, total) - 1]] if only_page else list(doc)
    for page in pages:
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        im = PI.frombytes('RGB', (pix.width, pix.height), pix.samples)
        foot = int(58 * zoom)                     # footer band (see render_pdf)
        body = im.crop((0, 0, im.width, im.height - foot))
        bbox = ImageChops.difference(body, PI.new('RGB', body.size, 'white')).getbbox()
        if bbox and bbox[3] + int(24 * zoom) < body.height:
            cut = bbox[3] + int(18 * zoom)
            new = PI.new('RGB', (im.width, cut + foot), 'white')
            new.paste(body.crop((0, 0, im.width, cut)), (0, 0))
            new.paste(im.crop((0, im.height - foot, im.width, im.height)), (0, cut))
            im = new
        b = io.BytesIO()
        im.save(b, 'PNG', optimize=not only_page)
        out.append(b.getvalue())
    return (out, total) if only_page else out


# --------------------------------------------------------------------------- #
# Word
# --------------------------------------------------------------------------- #
def render_docx(spec):
    """Bytes of the Word version (same structure; Calibri so it opens the same
    everywhere)."""
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, Cm, RGBColor, Emu

    _register_fonts()
    C = spec['colors']
    school = spec['school']
    fs = SIZES.get(spec.get('size') or 'm', 9.6)
    from reportlab.lib.pagesizes import A4
    spec['_natural_w'] = (sum(_natural_widths(spec, fs)) + fs * 2.6 + spec.get('blank_cols', 0) * fs * 4.2)
    land = (spec.get('orientation') == 'landscape' or
            (spec.get('orientation', 'auto') == 'auto' and spec['_natural_w'] > A4[0] - 68))

    def rgb(h):
        r, g, b = _hex(h)
        return RGBColor(r, g, b)

    def shade(cell, hexcol):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement('w:shd')
        shd.set(qn('w:val'), 'clear'); shd.set(qn('w:color'), 'auto'); shd.set(qn('w:fill'), hexcol.lstrip('#'))
        tcPr.append(shd)

    def borders(cell, **sides):
        tcPr = cell._tc.get_or_add_tcPr()
        b = OxmlElement('w:tcBorders')
        for side in ('top', 'left', 'bottom', 'right'):
            el = OxmlElement('w:' + side)
            spec_ = sides.get(side)
            if spec_:
                el.set(qn('w:val'), 'single'); el.set(qn('w:sz'), str(spec_[0])); el.set(qn('w:color'), spec_[1].lstrip('#'))
            else:
                el.set(qn('w:val'), 'nil')
            b.append(el)
        tcPr.append(b)

    def run(p, text, size=None, bold=False, color=None, font='Calibri', spacing=None):
        r = p.add_run(text)
        r.font.name = font
        r._element.rPr.rFonts.set(qn('w:eastAsia'), font)
        if size:
            r.font.size = Pt(size)
        r.font.bold = bold
        if color:
            r.font.color.rgb = rgb(color)
        if spacing:
            rPr = r._element.get_or_add_rPr()
            sp = OxmlElement('w:spacing'); sp.set(qn('w:val'), str(spacing)); rPr.append(sp)
        return r

    def field(p, instr, size, color):
        r = p.add_run(); r.font.size = Pt(size); r.font.color.rgb = rgb(color); r.font.bold = True
        for kind, text in (('begin', None), (None, instr), ('end', None)):
            if kind:
                el = OxmlElement('w:fldChar'); el.set(qn('w:fldCharType'), kind); r._element.append(el)
            else:
                el = OxmlElement('w:instrText'); el.set(qn('xml:space'), 'preserve'); el.text = text; r._element.append(el)

    doc = Document()
    sec = doc.sections[0]
    if land:
        sec.orientation = WD_ORIENT.LANDSCAPE
        sec.page_width, sec.page_height = Cm(29.7), Cm(21.0)
    else:
        sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    for m in ('left_margin', 'right_margin'):
        setattr(sec, m, Cm(1.3))
    sec.top_margin, sec.bottom_margin = Cm(1.1), Cm(1.3)
    usable = sec.page_width - sec.left_margin - sec.right_margin
    st = doc.styles['Normal']; st.font.name = 'Calibri'; st.font.size = Pt(fs)

    # Letterhead: logo / crest | school | doc tag
    lh = doc.add_table(rows=1, cols=3)
    lh.alignment = WD_TABLE_ALIGNMENT.CENTER
    lh.autofit = False
    widths = [Cm(1.9), usable - Cm(1.9) - Cm(5.2), Cm(5.2)]
    for i, w in enumerate(widths):
        lh.columns[i].width = w
        lh.rows[0].cells[i].width = w
    c0, c1, c2 = lh.rows[0].cells
    p = c0.paragraphs[0]
    if school.get('logo_path') and os.path.exists(school['logo_path']):
        try:
            p.add_run().add_picture(school['logo_path'], width=Cm(1.6))
        except Exception:
            run(p, initials(school.get('name')), 20, True, C['primary'])
    else:
        shade(c0, C['primary'])
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run(p, initials(school.get('name')), 18, True, '#ffffff')
    p = c1.paragraphs[0]
    run(p, school.get('name') or 'School', 17, True, INK)
    if school.get('motto'):
        p2 = c1.add_paragraph(); run(p2, school['motto'].upper(), 7.5, True, C['primary'], spacing=20)
    if _contact_line(school):
        p3 = c1.add_paragraph(); run(p3, _contact_line(school), 7.5, False, MUTED)
    p = c2.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run(p, (spec.get('doc_tag') or 'STUDENT LIST').upper(), 7.5, True, C['primary'], spacing=24)
    p = c2.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run(p, (spec.get('generated') or datetime.now()).strftime('Generated %d %b %Y, %H:%M'), 7.5, False, MUTED)
    for c in (c0, c1, c2):
        for pp in c.paragraphs:
            pp.paragraph_format.space_after = Pt(1)
    # accent bar
    bar = doc.add_paragraph()
    pPr = bar._p.get_or_add_pPr()
    bdr = OxmlElement('w:pBdr'); bot = OxmlElement('w:bottom')
    bot.set(qn('w:val'), 'single'); bot.set(qn('w:sz'), '18'); bot.set(qn('w:color'), C['primary'].lstrip('#'))
    bdr.append(bot); pPr.append(bdr)
    bar.paragraph_format.space_after = Pt(8)

    # Title + stats
    p = doc.add_paragraph(); run(p, spec.get('title') or 'Student List', 20, True, INK)
    p.paragraph_format.space_after = Pt(0)
    if spec.get('subtitle'):
        p = doc.add_paragraph(); run(p, spec['subtitle'], 9.5, False, INK2)
    if spec.get('stats'):
        t = doc.add_table(rows=1, cols=len(spec['stats']))
        for i, (v, l, tone) in enumerate(spec['stats']):
            c = t.rows[0].cells[i]
            borders(c, top=(6, LINE), bottom=(6, LINE), left=(6, LINE), right=(6, LINE))
            pp = c.paragraphs[0]
            run(pp, str(v), 14, True, {'male': MALE, 'female': FEMALE, 'warn': WARN}.get(tone, INK))
            pp2 = c.add_paragraph(); run(pp2, l.upper(), 6.5, True, MUTED, spacing=10)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)

    cols = spec['columns']
    nb = spec.get('blank_cols', 0)
    nat = _natural_widths(spec, fs)
    pts = _fit_widths(nat, usable / 12700.0, [c['kind'] for c in cols], nb, fs)
    noun = spec.get('noun') or 'students'
    for g in spec['groups']:
        rows = g['rows']
        if g.get('name'):
            m = sum(1 for r in rows if (r.get('_gender') or '').lower().startswith('m'))
            f = sum(1 for r in rows if (r.get('_gender') or '').lower().startswith('f'))
            p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(8); p.paragraph_format.keep_with_next = True
            run(p, g['name'] + '   ', 11.5, True, INK)
            run(p, '%d %s' % (len(rows), noun), 8.5, False, MUTED)
            if m or f:
                run(p, '  ·  %d M · %d F' % (m, f), 8.5, False, MUTED)
        t = doc.add_table(rows=1, cols=1 + len(cols) + nb)
        t.autofit = False
        hdr = t.rows[0].cells
        labels = ['#'] + [c['label'].upper() for c in cols] + [''] * nb
        for i, lab in enumerate(labels):
            shade(hdr[i], BG); borders(hdr[i], top=(6, LINE), bottom=(6, LINE))
            run(hdr[i].paragraphs[0], lab, fs * .75, True, MUTED, spacing=12)
        trPr = t.rows[0]._tr.get_or_add_trPr(); th = OxmlElement('w:tblHeader'); th.set(qn('w:val'), 'true'); trPr.append(th)
        for i, r in enumerate(rows, 1):
            cells = t.add_row().cells
            run(cells[0].paragraphs[0], str(i), fs, False, '#94a3b8')
            for j, c in enumerate(cols, 1):
                v = r.get(c['key']); p = cells[j].paragraphs[0]
                if c['kind'] == 'name':
                    s, rest = v if isinstance(v, (tuple, list)) else (v or '', '')
                    run(p, s, fs, True, INK); run(p, (' ' + rest) if rest else '', fs, False, INK2)
                elif c['kind'] == 'gender' and v:
                    col = FEMALE if str(v).lower().startswith('f') else MALE
                    run(p, '● ', fs * .8, False, col); run(p, v, fs * .95, True, col)
                elif c['kind'] == 'photo':
                    if v:
                        try:
                            p.add_run().add_picture(io.BytesIO(v), width=Cm(0.9))
                        except Exception:
                            pass
                elif c['kind'] == 'exam' and not (v or '').strip():
                    run(p, '— missing', fs, True, WARN)
                else:
                    run(p, _cell_text(c, v), fs, False, INK2)
            for j, cc in enumerate(cells):
                if i % 2 == 0:
                    shade(cc, ZEBRA)
                if j > len(cols):
                    borders(cc, top=(4, LINE), bottom=(4, LINE), left=(4, LINE), right=(4, LINE))
                else:
                    borders(cc, bottom=(4, LINE2))
        for row in t.rows:
            for j, cc in enumerate(row.cells):
                cc.width = Emu(int(pts[j] * 12700))
        if spec.get('signatures') and g.get('name'):
            _docx_signatures(doc, run, borders)
    if spec.get('signatures') and not any(g.get('name') for g in spec['groups']):
        _docx_signatures(doc, run, borders)

    # footer: school · title · prepared by …   Page X of Y
    fp = sec.footer.paragraphs[0]
    run(fp, (school.get('name') or 'School'), 7.5, True, INK2)
    run(fp, ' · ' + (spec.get('title') or 'Student List')
        + (' · prepared by ' + spec['prepared_by'] if spec.get('prepared_by') else '')
        + '  ·  Contains personal data — handle confidentially      Page ', 7.5, False, MUTED)
    field(fp, 'PAGE', 7.5, INK2); run(fp, ' of ', 7.5, False, MUTED); field(fp, 'NUMPAGES', 7.5, INK2)
    buf = io.BytesIO(); doc.save(buf)
    return buf.getvalue()


def _docx_signatures(doc, run, borders):
    t = doc.add_table(rows=2, cols=3)
    for i, lab in enumerate(('Class teacher', 'Principal', 'Date')):
        top = t.rows[0].cells[i]; bot = t.rows[1].cells[i]
        top.paragraphs[0].add_run(' ')
        borders(bot, top=(8, INK2))
        run(bot.paragraphs[0], lab, 8, False, MUTED)


# --------------------------------------------------------------------------- #
# Excel
# --------------------------------------------------------------------------- #
def render_xlsx(spec, about=None):
    """openpyxl Workbook: a branded, filterable 'Students' sheet (frozen header,
    sized columns, real dates, phone numbers kept as text), a 'Summary' sheet
    (totals by class and gender) and 'About this export'."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from utils.web_exports import formula_guard

    C = spec['colors']
    school = spec['school']
    P = C['primary'].lstrip('#').upper()
    thin = Side(style='thin', color='E2E8F0')
    wb = Workbook()
    ws = wb.active
    ws.title = 'Students'

    # Columns: a name splits into Surname / Other names; a grouped export
    # without a Class column gets one (Excel stays one flat, filterable table).
    cols = []
    for c in spec['columns']:
        if c['kind'] == 'name':
            cols.append(('name_s', 'Surname', 'name_s'))
            cols.append(('name_r', 'Other names', 'text'))
        else:
            cols.append((c['key'], c['label'], c['kind']))
    grouped = any(g.get('name') for g in spec['groups'])
    if grouped and not any(k == 'current_class' for k, _, _ in cols):
        cols.append(('__group', 'Class', 'text'))
    nb = spec.get('blank_cols', 0)
    headers = ['#'] + [h for _, h, _ in cols] + [''] * nb
    ncol = len(headers)
    last = get_column_letter(ncol)

    title = '%s — %s' % (school.get('name') or 'School', spec.get('title') or 'Student List')
    ws['A1'] = formula_guard(title)
    ws['A1'].font = Font(name='Calibri', size=15, bold=True, color=P)
    ws.row_dimensions[1].height = 24
    sub = ' · '.join(x for x in (spec.get('subtitle'), _stats_line(spec),
                                 (spec.get('generated') or datetime.now()).strftime('generated %d %b %Y')) if x)
    ws['A2'] = formula_guard(sub)
    ws['A2'].font = Font(name='Calibri', size=10, color='64748B')
    ws.merge_cells('A1:%s1' % last)
    ws.merge_cells('A2:%s2' % last)

    hdr_row = 3
    for j, h in enumerate(headers, 1):
        c = ws.cell(row=hdr_row, column=j, value=h)
        c.font = Font(name='Calibri', bold=True, color='FFFFFF', size=10.5)
        c.fill = PatternFill('solid', start_color=P, end_color=P)
        c.alignment = Alignment(vertical='center', horizontal='center' if j == 1 else 'left')
        c.border = Border(bottom=Side(style='medium', color=C['dark'].lstrip('#').upper()))
    ws.row_dimensions[hdr_row].height = 22

    zebra = PatternFill('solid', start_color='F7FAF9', end_color='F7FAF9')
    warn = PatternFill('solid', start_color='FEF3C7', end_color='FEF3C7')
    widths = [len(h) + 4 for h in headers]
    r = hdr_row
    n = 0
    photos = []
    for g in spec['groups']:
        for row in g['rows']:
            r += 1
            n += 1
            vals = [n]
            for key, _, kind in cols:
                if key == 'name_s':
                    v = row.get('name')
                    vals.append(v[0] if isinstance(v, (tuple, list)) else (v or ''))
                elif key == 'name_r':
                    v = row.get('name')
                    vals.append(v[1] if isinstance(v, (tuple, list)) else '')
                elif key == '__group':
                    vals.append(g.get('name') or '')
                else:
                    vals.append(row.get(key))
            vals += [None] * nb
            for j, v in enumerate(vals, 1):
                kind = 'num' if j == 1 else (cols[j - 2][2] if j - 2 < len(cols) else 'blank')
                cell = ws.cell(row=r, column=j)
                if kind == 'photo':
                    if v:
                        photos.append((r, j, v))
                    continue
                if kind == 'date' and isinstance(v, (date, datetime)):
                    cell.value = v
                    cell.number_format = 'dd mmm yyyy'
                elif kind in ('phone', 'id', 'exam'):
                    cell.value = formula_guard(str(v)) if v not in (None, '') else None
                    cell.number_format = '@'
                elif kind == 'num':
                    cell.value = v
                else:
                    cell.value = formula_guard(str(v)) if v not in (None, '') else None
                cell.font = Font(name='Calibri', size=11,
                                 bold=(kind == 'name_s'),
                                 color=(('DB2777' if str(v).lower().startswith('f') else '2563EB')
                                        if kind == 'gender' and v else ('94A3B8' if j == 1 else '1F2937')))
                cell.alignment = Alignment(vertical='center', horizontal='center' if j == 1 else 'left',
                                           wrap_text=(kind == 'wrap'))
                cell.border = Border(bottom=thin, left=thin if kind == 'blank' else None,
                                     right=thin if kind == 'blank' else None)
                if kind == 'exam' and not v:
                    cell.fill = warn
                elif n % 2 == 0:
                    cell.fill = zebra
                text = (v.strftime('%d %b %Y') if isinstance(v, (date, datetime)) else str(v or ''))
                widths[j - 1] = max(widths[j - 1], min(len(text) + 3, 48))
            ws.row_dimensions[r].height = 30 if photos and photos[-1][0] == r else 18
    for j, w in enumerate(widths, 1):
        kind = 'num' if j == 1 else (cols[j - 2][2] if j - 2 < len(cols) else 'blank')
        ws.column_dimensions[get_column_letter(j)].width = 6 if j == 1 else (14 if kind == 'blank' else (7 if kind == 'photo' else w))
    if photos:
        try:
            from openpyxl.drawing.image import Image as XLImage
            from PIL import Image as PI
            for (rr, cc, data) in photos:
                im = PI.open(io.BytesIO(data)).convert('RGB')
                im.thumbnail((76, 76))
                b = io.BytesIO(); im.save(b, 'PNG'); b.seek(0)
                xi = XLImage(b); xi.width, xi.height = 36, 36
                ws.add_image(xi, '%s%d' % (get_column_letter(cc), rr))
        except Exception:
            pass

    ws.freeze_panes = 'B4'
    ws.auto_filter.ref = 'A%d:%s%d' % (hdr_row, last, max(r, hdr_row + 1))
    ws.print_title_rows = '3:3'
    ws.page_setup.orientation = 'landscape' if ncol > 7 else 'portrait'
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.sheet_view.showGridLines = False

    # ---- Summary ----
    sm = wb.create_sheet('Summary')
    sm['A1'] = formula_guard(title); sm['A1'].font = Font(size=14, bold=True, color=P)
    sm.append([])
    sm.append(['Class', 'Students', 'Male', 'Female'])
    for j in range(1, 5):
        c = sm.cell(row=3, column=j)
        c.font = Font(bold=True, color='FFFFFF'); c.fill = PatternFill('solid', start_color=P, end_color=P)
    by = {}
    for g in spec['groups']:
        for row in g['rows']:
            k = g.get('name') or row.get('current_class') or '—'
            d = by.setdefault(k, [0, 0, 0])
            d[0] += 1
            gg = (row.get('_gender') or '').lower()
            d[1] += gg.startswith('m'); d[2] += gg.startswith('f')
    for k, (t, m, f) in by.items():
        sm.append([formula_guard(k), t, m, f])
    tot = [sum(v[i] for v in by.values()) for i in range(3)]
    sm.append(['Total'] + tot)
    for c in sm[sm.max_row]:
        c.font = Font(bold=True)
        c.border = Border(top=Side(style='thin', color='1F2937'))
    sm.column_dimensions['A'].width = 26
    for col in 'BCD':
        sm.column_dimensions[col].width = 12

    # ---- About ----
    ab = wb.create_sheet('About this export')
    info = [('School', school.get('name') or ''), ('List', spec.get('title') or ''),
            ('Details', spec.get('subtitle') or ''),
            ('Generated', (spec.get('generated') or datetime.now()).strftime('%d %b %Y, %H:%M')),
            ('Prepared by', spec.get('prepared_by') or ''), ('Students', str(n)),
            ('Columns', ', '.join(h for _, h, _ in cols))]
    info += list(about or [])
    for k, v in info:
        ab.append([k, formula_guard(str(v))])
        ab.cell(row=ab.max_row, column=1).font = Font(bold=True, color='64748B')
    ab.append([])
    ab.append(['Note', 'Contains personal data — handle confidentially.'])
    ab.column_dimensions['A'].width = 16
    ab.column_dimensions['B'].width = 80
    return wb


def _stats_line(spec):
    bits = []
    for v, l, _ in spec.get('stats') or []:
        bits.append('%s %s' % (v, l.lower()))
    return ', '.join(bits[:3])
