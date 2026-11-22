"""Exam hall allocation documents — the PDF and Excel exports.

PDF (A4 portrait, school letterhead and colours):
  page 1  overview: totals, a hall × class matrix (how many SSS1, SSS2… sit in
          each hall), gender per hall and how widely each class/arm is spread;
  then    one page per hall for the door / invigilator: hall header, class
          breakdown, the seating chart (front of hall at the top) and the
          attendance roster with a signature column.

Excel: a Summary sheet (the same matrix) plus one sheet per hall.

Both take the ``result`` dict built by routes/exam_halls (live or a saved
plan's snapshot) — halls carry ``by_class`` and ``seating``; ``classes`` lists
the class names in school order.
"""
from __future__ import annotations

import io

from utils import student_list_export as SLE

CLASS_INKS = ['#0d6a4e', '#2563eb', '#b45309', '#7c3aed', '#db2777', '#0891b2', '#65a30d', '#dc2626',
              '#4f46e5', '#c2410c']


def class_colors(classes):
    return {c: CLASS_INKS[i % len(CLASS_INKS)] for i, c in enumerate(classes)}


def _label(s):
    return ((s.get('class_name') or '') + (' ' + s['arm'] if s.get('arm') else '')).strip()


def _seats(hall):
    """[(seat number, student)] in seat order (falls back to list order)."""
    rows = (hall.get('seating') or {}).get('rows') or []
    cells = [c for row in rows for c in row if c]
    if cells:
        return sorted(((c['seat'], c['student']) for c in cells), key=lambda x: x[0])
    return list(enumerate(hall.get('students') or [], 1))


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def render_pdf(result, title='Exam hall allocation', subtitle=''):
    SLE._register_fonts()
    F = SLE.F
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph, Table, TableStyle,
                                    Spacer, PageBreak, Flowable, KeepTogether)
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from utils.school import school_profile, document_branding
    from utils.access_control import get_current_user

    hx = colors.HexColor
    C = SLE.colors_for(document_branding())
    school = school_profile() or {}
    u = get_current_user()
    spec = {'school': school, 'colors': C, 'doc_tag': 'Exam halls', 'subtitle': subtitle,
            'prepared_by': (getattr(u, 'full_name', None) or getattr(u, 'username', None) or '') if u else ''}
    PW, PH = A4
    margin, head_h = 34, 104
    canvas_cls = SLE.numbered_canvas(spec, PW, PH, margin, head_h, title,
                                     note_text='Confidential — for exam officers')
    avail = PW - 2 * margin
    classes = result.get('classes') or []
    inks = class_colors(classes)
    esc = SLE._esc

    st = {
        'h1': ParagraphStyle('h1', fontName=F['Display'], fontSize=19, leading=23, textColor=hx(SLE.INK)),
        'sub': ParagraphStyle('sub', fontName=F['Body'], fontSize=9.4, leading=13, textColor=hx(SLE.MUTED)),
        'h2': ParagraphStyle('h2', fontName=F['BodyBold'], fontSize=11, leading=14, textColor=hx(SLE.INK),
                             spaceBefore=12, spaceAfter=6),
        'note': ParagraphStyle('note', fontName=F['Body'], fontSize=7.8, leading=10.5, textColor=hx(SLE.MUTED)),
        'cell': ParagraphStyle('cell', fontName=F['Body'], fontSize=8.6, leading=10.5, textColor=hx(SLE.INK)),
        'cellb': ParagraphStyle('cellb', fontName=F['BodyBold'], fontSize=8.6, leading=10.5, textColor=hx(SLE.INK)),
    }

    class Tiles(Flowable):
        """A row of stat tiles: [(label, value, note)]."""
        def __init__(self, items, h=50):
            super().__init__()
            self.items, self.h = items, h

        def wrap(self, aw, ah):
            self.w = aw
            return aw, self.h

        def draw(self):
            cv, n, gap = self.canv, len(self.items), 8
            w = (self.w - gap * (n - 1)) / n
            for i, (lab, val, note) in enumerate(self.items):
                x = i * (w + gap)
                cv.setFillColor(hx(SLE.BG)); cv.setStrokeColor(hx(SLE.LINE)); cv.setLineWidth(.6)
                cv.roundRect(x, 0, w, self.h, 8, stroke=1, fill=1)
                cv.setFillColor(hx(SLE.MUTED)); cv.setFont(F['BodyBold'], 6.6)
                cv.drawString(x + 10, self.h - 15, lab.upper(), charSpace=.7)
                cv.setFillColor(hx(SLE.INK)); cv.setFont(F['Display'], 17)
                cv.drawString(x + 10, self.h - 35, str(val))
                if note:
                    cv.setFillColor(hx(SLE.MUTED)); cv.setFont(F['Body'], 7)
                    cv.drawString(x + 10 + stringWidth(str(val), F['Display'], 17) + 6, self.h - 35, note)

    class HallHead(Flowable):
        """The band at the top of each hall page."""
        def __init__(self, hall, idx, total):
            super().__init__()
            self.hall, self.idx, self.total = hall, idx, total

        def wrap(self, aw, ah):
            self.w = aw
            return aw, 74

        def draw(self):
            cv, h, hall = self.canv, 74, self.hall
            cv.setFillColor(hx(C['dark'] if hall.get('is_main') else C['primary']))
            cv.roundRect(0, 0, self.w, h, 12, stroke=0, fill=1)
            cv.setFillColor(hx('#ffffff'))
            cv.setFont(F['BodyBold'], 7.2)
            tag = ('MAIN HALL · ' if hall.get('is_main') else '') + 'HALL %d OF %d' % (self.idx, self.total)
            cv.drawString(18, h - 20, tag, charSpace=1.1)
            name = hall.get('name') or 'Hall'
            size = 24
            while size > 13 and stringWidth(name, F['Display'], size) > self.w - 210:
                size -= 1
            cv.setFont(F['Display'], size)
            cv.drawString(18, 18, name)
            # right side: seats used + gender
            g = hall.get('gender') or {}
            cv.setFont(F['Display'], 22)
            seats = '%d' % hall.get('count', 0)
            cap = ' / %d seats' % hall.get('capacity', 0)
            right = self.w - 18
            cw = stringWidth(cap, F['Body'], 9.5)
            cv.setFont(F['Body'], 9.5)
            cv.drawRightString(right, 34, cap)
            cv.setFont(F['Display'], 22)
            cv.drawRightString(right - cw, 34, seats)
            cv.setFont(F['Body'], 8.4)
            gl = '%d female · %d male' % (g.get('Female', 0), g.get('Male', 0))
            if g.get('Other'):
                gl += ' · %d other' % g['Other']
            cv.drawRightString(right, 18, gl)

    class Chips(Flowable):
        """Class breakdown chips: coloured dot, class, count."""
        def __init__(self, counts):
            super().__init__()
            self.counts = [(c, n) for c, n in counts if n]

        def wrap(self, aw, ah):
            self.w = aw
            x, rows = 0, 1
            for c, n in self.counts:
                w = self._w(c, n)
                if x + w > aw:
                    x, rows = 0, rows + 1
                x += w + 6
            self.h = rows * 26
            return aw, self.h

        def _w(self, c, n):
            return 26 + stringWidth(c, F['BodySemi'], 8.6) + stringWidth(str(n), F['Display'], 10) + 12

        def draw(self):
            cv, x, y = self.canv, 0, self.h - 22
            for c, n in self.counts:
                w = self._w(c, n)
                if x + w > self.w:
                    x, y = 0, y - 26
                ink = inks.get(c, C['primary'])
                cv.setFillColor(hx(SLE._mix(ink, '#ffffff', .88))); cv.setStrokeColor(hx(SLE._mix(ink, '#ffffff', .6)))
                cv.setLineWidth(.6)
                cv.roundRect(x, y, w, 20, 10, stroke=1, fill=1)
                cv.setFillColor(hx(ink)); cv.circle(x + 11, y + 10, 3.2, stroke=0, fill=1)
                cv.setFillColor(hx(SLE.INK)); cv.setFont(F['BodySemi'], 8.6)
                cv.drawString(x + 20, y + 6.6, c)
                cv.setFont(F['Display'], 10); cv.setFillColor(hx(ink))
                cv.drawRightString(x + w - 9, y + 6, str(n))
                x += w + 6

    def table(data, widths, head_bg=None, align_from=1, zebra=True, extra=None):
        t = Table(data, colWidths=widths, repeatRows=1)
        style = [
            ('FONTNAME', (0, 0), (-1, 0), F['BodyBold']), ('FONTSIZE', (0, 0), (-1, 0), 7),
            ('TEXTCOLOR', (0, 0), (-1, 0), hx(head_bg and '#ffffff' or SLE.MUTED)),
            ('BACKGROUND', (0, 0), (-1, 0), hx(head_bg or SLE.BG)),
            ('FONTNAME', (0, 1), (-1, -1), F['Body']), ('FONTSIZE', (0, 1), (-1, -1), 8.6),
            ('TEXTCOLOR', (0, 1), (-1, -1), hx(SLE.INK)),
            ('ALIGN', (align_from, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LINEBELOW', (0, 0), (-1, -1), .5, hx(SLE.LINE2)),
            ('BOX', (0, 0), (-1, -1), .6, hx(SLE.LINE)),
            ('TOPPADDING', (0, 0), (-1, -1), 4.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5),
            ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]
        if zebra:
            style.append(('ROWBACKGROUNDS', (0, 1), (-1, -1), [hx('#ffffff'), hx(SLE.ZEBRA)]))
        t.setStyle(TableStyle(style + (extra or [])))
        return t

    halls = result.get('halls') or []
    used = [h for h in halls if h.get('count')] or halls
    story = []

    # ---- overview -------------------------------------------------------
    story.append(Paragraph(esc(title), st['h1']))
    term = result.get('term') or ''
    sub_bits = [b for b in [subtitle, '' if term and term in (subtitle or '') else term] if b]
    if sub_bits:
        story.append(Paragraph(esc(' · '.join(sub_bits)), st['sub']))
    story.append(Spacer(1, 12))
    fill = (round(100 * result.get('total_students', 0) / result['total_capacity'])
            if result.get('total_capacity') else 0)
    story.append(Tiles([('Candidates', result.get('total_students', 0), ''),
                        ('Halls', len(halls), ''),
                        ('Seats', result.get('total_capacity', 0), '%d%% filled' % fill),
                        ('Classes', len(classes), '%d class arms' % len(result.get('groups') or []))]))

    story.append(Paragraph('Candidates per hall, by class', st['h2']))
    head = ['Hall'] + classes + ['Female', 'Male', 'Total', 'Seats']
    data = [head]
    tot = {c: 0 for c in classes}
    tf = tm = 0
    for h in halls:
        bc = h.get('by_class') or {}
        g = h.get('gender') or {}
        for c in classes:
            tot[c] += bc.get(c, 0)
        tf += g.get('Female', 0); tm += g.get('Male', 0)
        data.append([Paragraph(esc(h['name']) + (' <font color="%s" size="6.5">MAIN</font>' % C['primary']
                                                  if h.get('is_main') else ''), st['cellb'])]
                    + [bc.get(c, 0) or '–' for c in classes]
                    + [g.get('Female', 0), g.get('Male', 0), h.get('count', 0), h.get('capacity', 0)])
    data.append(['Total'] + [tot[c] for c in classes] + [tf, tm, result.get('total_students', 0),
                                                        result.get('total_capacity', 0)])
    name_w = 120
    rest = (avail - name_w) / max(1, len(head) - 1)
    extra = [('FONTNAME', (0, -1), (-1, -1), F['BodyBold']), ('BACKGROUND', (0, -1), (-1, -1), hx(C['soft'])),
             ('FONTNAME', (-2, 1), (-2, -1), F['BodyBold'])]
    for i, c in enumerate(classes, 1):
        extra.append(('TEXTCOLOR', (i, 0), (i, 0), hx(inks[c])))
    story.append(table(data, [name_w] + [rest] * (len(head) - 1), extra=extra))

    groups = result.get('groups') or []
    if groups:
        story.append(Paragraph('How widely each class arm is spread', st['h2']))
        gd = [['Class / arm', 'Candidates', 'Halls used', 'Most in one hall']]
        for g in groups:
            gd.append([Paragraph(esc(g['key']), st['cell']), g['size'],
                       '%d of %d' % (g['halls_used'], len(halls)), g['max_in_hall']])
        story.append(table(gd, [avail * .4, avail * .2, avail * .2, avail * .2]))
        story.append(Spacer(1, 5))
        story.append(Paragraph('Lower “most in one hall” means classmates are spread more thinly — '
                               'fewer chances to copy.', st['note']))

    # ---- one page per hall ----------------------------------------------
    for i, h in enumerate(used, 1):
        story.append(PageBreak())
        story.append(HallHead(h, i, len(used)))
        story.append(Spacer(1, 10))
        bc = h.get('by_class') or {}
        story.append(Chips([(c, bc.get(c, 0)) for c in classes] +
                           [(c, n) for c, n in bc.items() if c not in classes]))
        seating = h.get('seating') or {}
        rows = seating.get('rows') or []
        if rows and seating.get('cols'):
            cols = seating['cols']
            cw = min(avail / cols, 82)
            grid = []
            for row in rows:
                line = []
                for cell in row:
                    if not cell:
                        line.append('')
                        continue
                    s = cell['student']
                    ink = inks.get(s.get('class_name'), C['primary'])
                    line.append(Paragraph(
                        '<font name="%s" size="9.5">%d</font><br/><font size="5.8" color="%s">%s</font><br/>'
                        '<font size="5.8" color="%s">%s</font>' % (
                            F['Display'], cell['seat'], SLE.MUTED, esc((s.get('student_id') or '')[:14]),
                            ink, esc(_label(s)[:16])),
                        ParagraphStyle('seat', fontName=F['BodyBold'], fontSize=6, leading=7.4,
                                       alignment=1, textColor=hx(SLE.INK))))
                grid.append(line)
            gs = [('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                  ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                  ('LEFTPADDING', (0, 0), (-1, -1), 2), ('RIGHTPADDING', (0, 0), (-1, -1), 2)]
            for r, row in enumerate(rows):
                for c, cell in enumerate(row):
                    if cell:
                        ink = inks.get(cell['student'].get('class_name'), C['primary'])
                        gs += [('BACKGROUND', (c, r), (c, r), hx(SLE._mix(ink, '#ffffff', .93))),
                               ('BOX', (c, r), (c, r), .7, hx(SLE._mix(ink, '#ffffff', .55)))]
            seat_tbl = Table(grid, colWidths=[cw] * cols, rowHeights=34, hAlign='CENTER')
            seat_tbl.setStyle(TableStyle(gs))
            story.append(Spacer(1, 8))
            story.append(KeepTogether([
                Paragraph('Seating plan <font color="%s" size="7.5">· front of hall at the top</font>' % SLE.MUTED,
                          st['h2']),
                seat_tbl]))
        story.append(Paragraph('Attendance roster', st['h2']))
        rd = [['Seat', 'Name', 'Student ID', 'Class', 'Sex', 'Signature']]
        for seat, s in _seats(h):
            g = (s.get('gender') or '')[:1].upper()
            rd.append([seat, Paragraph(esc(s.get('name') or ''), st['cellb']), s.get('student_id') or '',
                       _label(s), g, ''])
        story.append(table(rd, [32, avail - 32 - 82 - 70 - 30 - 92, 82, 70, 30, 92], align_from=0,
                           extra=[('ALIGN', (1, 0), (3, -1), 'LEFT')]))

    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=margin, rightMargin=margin,
                          topMargin=head_h, bottomMargin=54, title=title)
    first = Frame(margin, 54, avail, PH - head_h - 54, id='first', showBoundary=0)
    later = Frame(margin, 54, avail, PH - 58 - 54, id='later', showBoundary=0)
    doc.addPageTemplates([PageTemplate('first', [first], autoNextPageTemplate='later'),
                          PageTemplate('later', [later])])
    doc.build(story, canvasmaker=canvas_cls)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Excel
# --------------------------------------------------------------------------- #
def render_xlsx(result, title='Exam hall allocation', subtitle=''):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from utils.school import school_profile, document_branding
    from utils.web_exports import formula_guard

    C = SLE.colors_for(document_branding())
    prim = C['primary'].lstrip('#').upper()
    soft = C['soft'].lstrip('#').upper()
    school = (school_profile() or {}).get('name') or ''
    classes = result.get('classes') or []
    halls = result.get('halls') or []
    thin = Side(style='thin', color='E2E8F0')
    head_font, head_fill = Font(bold=True, color='FFFFFF'), PatternFill('solid', fgColor=prim)
    center = Alignment(horizontal='center', vertical='center')

    def header(ws, row, cols):
        for i, h in enumerate(cols, 1):
            c = ws.cell(row=row, column=i, value=h)
            c.font, c.fill, c.alignment = head_font, head_fill, center
            c.border = Border(bottom=thin)

    def top(ws, line):
        ws.cell(row=1, column=1, value=school).font = Font(bold=True, size=14)
        ws.cell(row=2, column=1, value=line).font = Font(color='64748B')

    wb = Workbook()
    ws = wb.active
    ws.title = 'Summary'
    top(ws, ' · '.join(b for b in [title, subtitle, result.get('term')] if b))
    cols = ['Hall'] + classes + ['Female', 'Male', 'Total', 'Seats']
    header(ws, 4, cols)
    r = 5
    for h in halls:
        bc, g = h.get('by_class') or {}, h.get('gender') or {}
        vals = [h['name'] + (' (Main)' if h.get('is_main') else '')] + [bc.get(c, 0) for c in classes] + \
               [g.get('Female', 0), g.get('Male', 0), h.get('count', 0), h.get('capacity', 0)]
        for i, v in enumerate(vals, 1):
            cell = ws.cell(row=r, column=i, value=formula_guard(v) if isinstance(v, str) else v)
            if i > 1:
                cell.alignment = center
        r += 1
    last = r - 1
    ws.cell(row=r, column=1, value='Total').font = Font(bold=True)
    for i in range(2, len(cols) + 1):
        L = get_column_letter(i)
        c = ws.cell(row=r, column=i, value='=SUM(%s5:%s%d)' % (L, L, last))
        c.font, c.alignment, c.fill = Font(bold=True), center, PatternFill('solid', fgColor=soft)
    ws.cell(row=r, column=1).fill = PatternFill('solid', fgColor=soft)
    ws.column_dimensions['A'].width = 24
    for i in range(2, len(cols) + 1):
        ws.column_dimensions[get_column_letter(i)].width = 11
    ws.freeze_panes = 'B5'

    groups = result.get('groups') or []
    if groups:
        r += 3
        ws.cell(row=r - 1, column=1, value='Spread per class arm').font = Font(bold=True)
        header(ws, r, ['Class / arm', 'Candidates', 'Halls used', 'Most in one hall'])
        for g in groups:
            r += 1
            for i, v in enumerate([g['key'], g['size'], g['halls_used'], g['max_in_hall']], 1):
                c = ws.cell(row=r, column=i, value=formula_guard(v) if isinstance(v, str) else v)
                if i > 1:
                    c.alignment = center

    used_names = set()
    for h in halls:
        if not h.get('count'):
            continue
        name = ''.join(ch for ch in h['name'] if ch not in '[]:*?/\\')[:28] or 'Hall'
        base, k = name, 2
        while name.lower() in used_names:
            name = '%s %d' % (base[:25], k); k += 1
        used_names.add(name.lower())
        hs = wb.create_sheet(name)
        bc = h.get('by_class') or {}
        top(hs, '%s · %d / %d seats · %s' % (h['name'], h.get('count', 0), h.get('capacity', 0),
                                             ', '.join('%s %d' % (c, bc[c]) for c in classes if bc.get(c))))
        header(hs, 4, ['Seat', 'Name', 'Student ID', 'Class', 'Arm', 'Gender', 'Signature'])
        rr = 5
        for seat, s in _seats(h):
            for i, v in enumerate([seat, s.get('name'), s.get('student_id'), s.get('class_name'), s.get('arm'),
                                   s.get('gender'), ''], 1):
                c = hs.cell(row=rr, column=i, value=formula_guard(v) if isinstance(v, str) else v)
                c.border = Border(bottom=thin)
                if i in (1, 6):
                    c.alignment = center
            rr += 1
        for col, w in zip('ABCDEFG', (7, 32, 16, 10, 10, 9, 22)):
            hs.column_dimensions[col].width = w
        hs.freeze_panes = 'A5'
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
