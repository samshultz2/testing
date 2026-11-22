"""WAEC / NECO exam timetable — candidates, clashes and the exports.

Candidates are the school's SSS3 students (the external-exam cohort); a
candidate "sits" a paper when that subject is among the subjects on their
profile. Two papers clash when they overlap on the same day and at least one
candidate sits both.
"""
from __future__ import annotations

import datetime as dt
import io

from utils import student_list_export as SLE

KINDS = [('objective', 'Objective'), ('essay', 'Essay / Theory'), ('practical', 'Practical'),
         ('oral', 'Oral / Listening'), ('other', 'Other')]
KIND_LABEL = dict(KINDS)
SESSION_CUT = dt.time(12, 0)          # papers starting before noon are "morning"


def norm(s):
    return ' '.join((s or '').lower().replace('&', 'and').split())


def candidates(board):
    """The external-exam cohort with the subjects on each profile:
    [{id, name, student_id, reg_no, subjects:set(normalised), registered}]."""
    from utils.helpers import get_sss3_students
    out = []
    for s in get_sss3_students():
        reg = (s.neco_reg_number if board == 'neco' else s.waec_reg_number) or ''
        out.append({'id': s.id, 'name': s.full_name, 'student_id': s.student_id or '',
                    'reg_no': reg.strip(), 'registered': bool(reg.strip()),
                    'subjects': {norm(x) for x in (s.waec_subject_list or [])},
                    'subject_names': list(s.waec_subject_list or [])})
    out.sort(key=lambda c: c['name'].lower())
    return out


def minutes(a, b):
    return (b.hour * 60 + b.minute) - (a.hour * 60 + a.minute)


def fmt_dur(m):
    if m <= 0:
        return '—'
    h, mm = divmod(m, 60)
    return ('%dh' % h if h else '') + (' %02dm' % mm if h and mm else ('%dm' % mm if mm else ''))


def fmt_time(t):
    return t.strftime('%I:%M %p').lstrip('0') if t else ''


def analyse(tt, cands):
    """Everything the editor and exports show, from the papers + candidates."""
    papers = list(tt.papers)
    by_subject = {}
    for c in cands:
        for s in c['subjects']:
            by_subject.setdefault(s, []).append(c)
    rows = []
    for p in papers:
        who = by_subject.get(norm(p.subject), [])
        rows.append({'p': p, 'count': len(who), 'cands': who, 'minutes': minutes(p.start_time, p.end_time),
                     'session': 'Morning' if p.start_time < SESSION_CUT else 'Afternoon'})
    # clashes: overlapping papers on the same day that share candidates
    clashes = []
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            pa, pb = a['p'], b['p']
            if pa.exam_date != pb.exam_date or norm(pa.subject) == norm(pb.subject):
                continue
            if pa.start_time < pb.end_time and pb.start_time < pa.end_time:
                ids = {c['id'] for c in a['cands']} & {c['id'] for c in b['cands']}
                if ids:
                    clashes.append({'a': pa, 'b': pb, 'students': sorted(
                        (c['name'] for c in a['cands'] if c['id'] in ids), key=str.lower)})
    # days
    days = []
    for r in rows:
        if not days or days[-1]['date'] != r['p'].exam_date:
            days.append({'date': r['p'].exam_date, 'rows': []})
        days[-1]['rows'].append(r)
    # subjects candidates registered for but with no paper yet
    have = {norm(p.subject) for p in papers}
    names = {}
    for c in cands:
        for n in c['subject_names']:
            names.setdefault(norm(n), n)
    missing = sorted(((names[k], len(v)) for k, v in by_subject.items() if k not in have and k in names),
                     key=lambda x: (-x[1], x[0]))
    # heaviest days per candidate (3+ papers on one day)
    heavy = []
    for c in cands:
        per_day = {}
        for r in rows:
            if norm(r['p'].subject) in c['subjects']:
                per_day[r['p'].exam_date] = per_day.get(r['p'].exam_date, 0) + 1
        worst = max(per_day.values()) if per_day else 0
        if worst >= 3:
            heavy.append({'name': c['name'], 'papers': worst})
    dates = [r['p'].exam_date for r in rows]
    return {'rows': rows, 'days': days, 'clashes': clashes, 'missing': missing, 'heavy': heavy,
            'first': min(dates) if dates else None, 'last': max(dates) if dates else None,
            'subjects': len({norm(p.subject) for p in papers}),
            'candidates': len(cands), 'registered': sum(1 for c in cands if c['registered'])}


def personal(tt, cands, data):
    """[{candidate, rows}] — each candidate's own papers in order."""
    out = []
    for c in cands:
        mine = [r for r in data['rows'] if norm(r['p'].subject) in c['subjects']]
        if mine:
            out.append({'c': c, 'rows': mine})
    return out


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def render_pdf(tt, cands, data, per_student=False):
    SLE._register_fonts()
    F = SLE.F
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph, Table, TableStyle,
                                    Spacer, Flowable, KeepTogether)
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from utils.school import school_profile, document_branding
    from utils.access_control import get_current_user

    hx = colors.HexColor
    C = SLE.colors_for(document_branding())
    u = get_current_user()
    title = tt.title
    spec = {'school': school_profile() or {}, 'colors': C,
            'doc_tag': ('%s timetable' % tt.board_label) if not per_student else 'Candidate timetables',
            'subtitle': '', 'prepared_by': (getattr(u, 'full_name', None) or getattr(u, 'username', None) or '') if u else ''}
    PW, PH = A4
    margin, head_h = 34, 104
    canvas_cls = SLE.numbered_canvas(spec, PW, PH, margin, head_h, title,
                                     note_text='Check the official %s timetable for changes' % tt.board_label)
    avail = PW - 2 * margin
    esc = SLE._esc
    st = {
        'h1': ParagraphStyle('h1', fontName=F['Display'], fontSize=19, leading=23, textColor=hx(SLE.INK)),
        'sub': ParagraphStyle('sub', fontName=F['Body'], fontSize=9.4, leading=13, textColor=hx(SLE.MUTED)),
        'cell': ParagraphStyle('cell', fontName=F['Body'], fontSize=8.8, leading=11, textColor=hx(SLE.INK)),
        'cellb': ParagraphStyle('cellb', fontName=F['BodyBold'], fontSize=9.2, leading=11.5, textColor=hx(SLE.INK)),
        'small': ParagraphStyle('small', fontName=F['Body'], fontSize=7.6, leading=9.5, textColor=hx(SLE.MUTED)),
        'name': ParagraphStyle('name', fontName=F['Display'], fontSize=12.5, leading=15, textColor=hx(SLE.INK)),
    }

    class DayBand(Flowable):
        def __init__(self, d, n):
            super().__init__()
            self.d, self.n = d, n

        def wrap(self, aw, ah):
            self.w = aw
            return aw, 30

        def draw(self):
            cv = self.canv
            cv.setFillColor(hx(C['soft']))
            cv.roundRect(0, 0, self.w, 26, 8, stroke=0, fill=1)
            cv.setFillColor(hx(C['primary']))
            cv.roundRect(0, 0, 5, 26, 2.5, stroke=0, fill=1)
            cv.setFont(F['Display'], 11); cv.setFillColor(hx(SLE.INK))
            label = self.d.strftime('%A, %d %B %Y')
            cv.drawString(14, 8.6, label)
            cv.setFont(F['BodyBold'], 7.6); cv.setFillColor(hx(C['primary']))
            cv.drawRightString(self.w - 12, 9.4, ('%d PAPER%s' % (self.n, '' if self.n == 1 else 'S')), charSpace=.8)

    def paper_cell(p):
        bits = '<b>%s</b>' % esc(p.subject)
        if p.paper:
            bits += '<br/><font size="7.8" color="%s">%s</font>' % (SLE.MUTED, esc(p.paper))
        return Paragraph(bits, st['cellb'])

    def tbl(data_rows, widths, extra=None):
        t = Table(data_rows, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), F['BodyBold']), ('FONTSIZE', (0, 0), (-1, 0), 6.8),
            ('TEXTCOLOR', (0, 0), (-1, 0), hx(SLE.MUTED)),
            ('FONTNAME', (0, 1), (-1, -1), F['Body']), ('FONTSIZE', (0, 1), (-1, -1), 8.8),
            ('TEXTCOLOR', (0, 1), (-1, -1), hx(SLE.INK)),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LINEBELOW', (0, 0), (-1, -1), .5, hx(SLE.LINE2)),
            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ] + (extra or [])))
        return t

    story = [Paragraph(esc(title), st['h1'])]
    sub = []
    if data['first']:
        sub.append(data['first'].strftime('%d %b') + ' – ' + data['last'].strftime('%d %b %Y'))
    sub.append('%d papers · %d subjects' % (len(data['rows']), data['subjects']))
    story.append(Paragraph(esc(' · '.join(sub)), st['sub']))
    if tt.notes:
        story += [Spacer(1, 4), Paragraph(esc(tt.notes), st['small'])]
    story.append(Spacer(1, 12))

    if not per_student:
        w = [70, avail - 70 - 52 - 96 - 52, 52, 96, 52]
        for day in data['days']:
            rows = [['TIME', 'SUBJECT / PAPER', 'DURATION', 'VENUE', 'CANDIDATES']]
            for r in day['rows']:
                p = r['p']
                venue = esc(p.venue or '—')
                if p.invigilators:
                    venue += '<br/><font size="7" color="%s">%s</font>' % (SLE.MUTED, esc(p.invigilators))
                rows.append([Paragraph('<b>%s</b><br/><font size="7.4" color="%s">to %s</font>' % (
                    fmt_time(p.start_time), SLE.MUTED, fmt_time(p.end_time)), st['cell']),
                    paper_cell(p), fmt_dur(r['minutes']), Paragraph(venue, st['cell']), r['count'] or '–'])
            story.append(KeepTogether([DayBand(day['date'], len(day['rows'])), Spacer(1, 3),
                                       tbl(rows, w, [('ALIGN', (2, 0), (2, -1), 'CENTER'),
                                                     ('ALIGN', (4, 0), (4, -1), 'CENTER')])]))
            story.append(Spacer(1, 10))
        if data['clashes']:
            story.append(Paragraph('Clashes to resolve', ParagraphStyle(
                'ch', fontName=F['BodyBold'], fontSize=11, textColor=hx('#b91c1c'), spaceBefore=6, spaceAfter=5)))
            rows = [['DATE', 'PAPERS', 'CANDIDATES AFFECTED']]
            for c in data['clashes']:
                rows.append([c['a'].exam_date.strftime('%d %b'),
                             Paragraph('%s <font color="%s">and</font> %s' % (esc(c['a'].subject), SLE.MUTED,
                                                                             esc(c['b'].subject)), st['cell']),
                             Paragraph(esc(', '.join(c['students'][:12]) + (' …' if len(c['students']) > 12 else '')),
                                       st['small'])])
            story.append(tbl(rows, [50, 170, avail - 220]))
    else:
        for item in personal(tt, cands, data):
            c = item['c']
            rows = [['DATE', 'TIME', 'SUBJECT / PAPER', 'VENUE']]
            for r in item['rows']:
                p = r['p']
                rows.append([Paragraph('<b>%s</b><br/><font size="7.4" color="%s">%s</font>' % (
                    p.exam_date.strftime('%a %d %b'), SLE.MUTED, p.exam_date.strftime('%Y')), st['cell']),
                    '%s – %s' % (fmt_time(p.start_time), fmt_time(p.end_time)), paper_cell(p), p.venue or '—'])
            head = Table([[Paragraph(esc(c['name']), st['name']),
                           Paragraph('<font color="%s">%s%s</font>' % (
                               SLE.MUTED, esc(c['student_id']),
                               (' · Reg. no. ' + esc(c['reg_no'])) if c['reg_no'] else ''),
                               ParagraphStyle('r', parent=st['cell'], alignment=2))]],
                         colWidths=[avail * .55, avail * .45])
            head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'BOTTOM'), ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                                      ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                                      ('LINEBELOW', (0, 0), (-1, 0), 1.4, hx(C['primary'])),
                                      ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
            story.append(KeepTogether([head, Spacer(1, 4),
                                       tbl(rows, [70, 110, avail - 70 - 110 - 110, 110]), Spacer(1, 18)]))

    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=margin, rightMargin=margin,
                          topMargin=head_h, bottomMargin=54, title=title)
    doc.addPageTemplates([PageTemplate('first', [Frame(margin, 54, avail, PH - head_h - 54)],
                                       autoNextPageTemplate='later'),
                          PageTemplate('later', [Frame(margin, 54, avail, PH - 58 - 54)])])
    doc.build(story, canvasmaker=canvas_cls)
    return buf.getvalue()


def render_xlsx(tt, cands, data):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from utils.school import school_profile, document_branding
    from utils.web_exports import formula_guard

    C = SLE.colors_for(document_branding())
    prim = C['primary'].lstrip('#').upper()
    hf, hfill = Font(bold=True, color='FFFFFF'), PatternFill('solid', fgColor=prim)

    def sheet(ws, heads, rows, widths):
        ws.cell(row=1, column=1, value=(school_profile() or {}).get('name') or '').font = Font(bold=True, size=14)
        ws.cell(row=2, column=1, value=tt.title).font = Font(color='64748B')
        for i, h in enumerate(heads, 1):
            c = ws.cell(row=4, column=i, value=h)
            c.font, c.fill, c.alignment = hf, hfill, Alignment(horizontal='center')
        for r, row in enumerate(rows, 5):
            for i, v in enumerate(row, 1):
                ws.cell(row=r, column=i, value=formula_guard(v) if isinstance(v, str) else v)
        for i, w in enumerate(widths):
            ws.column_dimensions[chr(65 + i)].width = w
        ws.freeze_panes = 'A5'

    wb = Workbook()
    ws = wb.active
    ws.title = 'Timetable'
    sheet(ws, ['Date', 'Day', 'Start', 'End', 'Duration', 'Subject', 'Paper', 'Type', 'Venue', 'Invigilators',
               'Candidates'],
          [[r['p'].exam_date, r['p'].exam_date.strftime('%A'), fmt_time(r['p'].start_time), fmt_time(r['p'].end_time),
            fmt_dur(r['minutes']), r['p'].subject, r['p'].paper or '', KIND_LABEL.get(r['p'].kind, ''),
            r['p'].venue or '', r['p'].invigilators or '', r['count']] for r in data['rows']],
          [12, 11, 10, 10, 10, 28, 22, 14, 16, 26, 11])
    for row in ws.iter_rows(min_row=5, max_col=1):
        for c in row:
            c.number_format = 'DD MMM YYYY'
    ws2 = wb.create_sheet('By candidate')
    rows = []
    for item in personal(tt, cands, data):
        for r in item['rows']:
            rows.append([item['c']['name'], item['c']['student_id'], item['c']['reg_no'], r['p'].exam_date,
                         '%s – %s' % (fmt_time(r['p'].start_time), fmt_time(r['p'].end_time)),
                         r['p'].subject, r['p'].paper or '', r['p'].venue or ''])
    sheet(ws2, ['Candidate', 'Student ID', 'Reg. no.', 'Date', 'Time', 'Subject', 'Paper', 'Venue'], rows,
          [28, 14, 16, 12, 20, 28, 22, 16])
    for row in ws2.iter_rows(min_row=5, min_col=4, max_col=4):
        for c in row:
            c.number_format = 'DD MMM YYYY'
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
