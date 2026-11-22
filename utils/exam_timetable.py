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

KINDS = [('objective', 'Objective'), ('essay', 'Essay / Theory'), ('combined', 'Objective & Essay'),
         ('practical', 'Practical'), ('alt_practical', 'Alternative to Practical'),
         ('practical_physical', 'Practical & Physical'), ('objective_practical', 'Objective & Practical'),
         ('prose', 'Prose'), ('drama_poetry', 'Drama & Poetry'), ('objective_prose', 'Objective & Prose'),
         ('oral', 'Oral / Listening'), ('drawing', 'Drawing'), ('project', 'Project / Coursework'),
         ('other', 'Other')]
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
    """Exam-timetable style duration: 45mins, 1hr, 1hr 30mins, 2hrs 45mins."""
    if not m or m <= 0:
        return '—'
    h, mm = divmod(int(m), 60)
    parts = []
    if h:
        parts.append('%dhr%s' % (h, '' if h == 1 else 's'))
    if mm:
        parts.append('%dmin%s' % (mm, '' if mm == 1 else 's'))
    return ' '.join(parts)


# The sessions recent WAEC / NECO SSCE timetables use most: (start, end).
# WAEC: essays/practicals from 9:30am, objectives from 2:00pm (often followed by
# a short oral/listening paper). NECO: morning papers from 10:00am, afternoon
# papers from 2:00pm or 3:00pm.
COMMON_SESSIONS = {
    'waec': [('09:30', '12:30'), ('09:30', '12:00'), ('09:30', '11:30'), ('09:30', '11:00'),
             ('14:00', '15:30'), ('14:00', '15:00'), ('14:00', '17:00'), ('15:30', '16:15')],
    'neco': [('10:00', '13:00'), ('10:00', '12:45'), ('10:00', '12:30'), ('10:00', '12:00'),
             ('14:00', '16:30'), ('14:00', '16:00'), ('15:00', '16:30'), ('15:00', '16:00')],
}
DURATIONS = [45, 60, 90, 120, 150, 165, 180]


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


# --------------------------------------------------------------------------- #
# Paste import — rows copied from a chatbot / spreadsheet / the official PDF
# --------------------------------------------------------------------------- #
import re as _re

_MONTHS = {m: i for i, m in enumerate(
    ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'], 1)}
_WEEKDAY = _re.compile(r'\b(mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)[a-z]*\.?,?\s*', _re.I)


def parse_date(text, default_year=None):
    """2026-05-04 · 04/05/2026 (day first) · 4/5/26 · Monday, 4th May 2026 ·
    May 4, 2026 · 4 May (year from ``default_year``)."""
    t = (text or '').strip()
    if not t:
        return None
    m = _re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', t)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        t = _WEEKDAY.sub('', t).strip()
        t = _re.sub(r'(\d)(st|nd|rd|th)\b', r'\1', t, flags=_re.I).replace(',', ' ').replace('.', ' ')
        m = _re.match(r'^(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?$', t)
        if m:
            d, mo = int(m.group(1)), int(m.group(2))
            y = int(m.group(3)) if m.group(3) else default_year
        else:
            words = t.split()
            nums = [int(w) for w in words if w.isdigit()]
            mon = next((_MONTHS[w[:3].lower()] for w in words if w[:3].lower() in _MONTHS and not w.isdigit()), None)
            if not mon or not nums:
                return None
            mo = mon
            d = next((n for n in nums if n <= 31), None)
            y = next((n for n in nums if n > 31), default_year)
        if y is not None and y < 100:
            y += 2000
    try:
        return dt.date(int(y), int(mo), int(d)) if y and d else None
    except (TypeError, ValueError):
        return None


def parse_time(text):
    """9:30am · 9.30 a.m. · 14:00 · 2pm · 12 noon."""
    t = (text or '').strip().lower().replace(' ', '').replace('.', ':').replace('a:m:', 'am').replace('p:m:', 'pm')
    t = t.replace('a:m', 'am').replace('p:m', 'pm').rstrip(':')
    if t in ('noon', '12noon'):
        return dt.time(12, 0)
    m = _re.match(r'^(\d{1,2})(?::(\d{2}))?(am|pm|noon)?$', t)
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ap == 'pm' and h < 12:
        h += 12
    if ap == 'am' and h == 12:
        h = 0
    return dt.time(h, mi) if h < 24 and mi < 60 else None


def parse_duration(text):
    """1hr 30mins · 2 hrs · 45 mins · 1½ hrs · 1.5 hours · 90 → minutes."""
    t = (text or '').lower().replace('½', '.5').replace(' ', '')
    if not t or not _re.search(r'\d', t):
        return None
    if t.isdigit():
        return int(t)
    h = _re.search(r'(\d+(?:\.\d+)?)h', t)
    m = _re.search(r'(\d+)m', t)
    if not (h or m):
        return None
    return int(round(float(h.group(1)) * 60)) + (int(m.group(1)) if m else 0) if h else int(m.group(1))


_RANGE = _re.compile(r'^(.+?)\s*(?:-|–|—|to)\s*(.+)$', _re.I)


def _split(line):
    for sep in ('\t', '|', ';'):
        if sep in line:
            return [c.strip() for c in line.split(sep)]
    return [c.strip() for c in line.split(',')]


def parse_paste(text, subjects, papers_for, default_year=None):
    """Rows of ``date, start, end, subject, paper[, venue, invigilators]``.
    ``start, end`` may be one "9:30am - 12:30pm" cell, and ``end`` may be a
    duration (2hrs 30mins). Subjects are matched to the known list (case,
    '&'/'and', common short names). Returns [{line, raw, …, error}]."""
    known = {norm(s): s for s in subjects}
    alias = {'eng': 'english language', 'english': 'english language', 'maths': 'mathematics',
             'math': 'mathematics', 'gen maths': 'mathematics', 'general mathematics': 'mathematics',
             'further maths': 'further mathematics', 'f/maths': 'further mathematics',
             'lit': 'literature in english', 'literature': 'literature in english',
             'literature-in-english': 'literature in english', 'crs': 'christian religious studies',
             'crk': 'christian religious studies', 'irs': 'islamic religious studies',
             'irk': 'islamic religious studies', 'agric': 'agricultural science',
             'agricultural science': 'agricultural science', 'govt': 'government', 'econs': 'economics',
             'geo': 'geography', 'bio': 'biology', 'chem': 'chemistry', 'phy': 'physics', 'physics': 'physics',
             'civic': 'civic education', 'comm': 'commerce', 'accounts': 'financial accounting',
             'computer': 'computer studies', 'data processing': 'data processing', 'tech drawing': 'technical drawing',
             'td': 'technical drawing', 'visual art': 'visual arts', 'fine art': 'visual arts'}
    out = []
    for n, raw in enumerate((text or '').splitlines(), 1):
        line = raw.strip().strip('`')
        if not line or line.lower().startswith(('date', '#', '//')):
            continue
        cols = _split(line)
        row = {'line': n, 'raw': line, 'error': None}
        # date may have been split at its own comma ("Monday, 4 May 2026")
        if len(cols) > 1 and _WEEKDAY.fullmatch(cols[0] + ' ') and parse_date(cols[1], default_year):
            cols = [cols[0] + ' ' + cols[1]] + cols[2:]
        if len(cols) > 1 and not parse_time(cols[1]) and _RANGE.match(cols[1] or ''):
            a, b = _RANGE.match(cols[1]).groups()
            if parse_time(a) and (parse_time(b) or parse_duration(b)):
                cols = [cols[0], a, b] + cols[2:]
        while len(cols) < 7:
            cols.append('')
        d, st = parse_date(cols[0], default_year), parse_time(cols[1])
        en = parse_time(cols[2])
        if st and not en:
            mins = parse_duration(cols[2])
            if mins:
                tot = st.hour * 60 + st.minute + mins
                en = dt.time(tot // 60 % 24, tot % 60)
        subj_in = cols[3]
        key = norm(subj_in).replace('-', ' ')
        key = alias.get(norm(subj_in), alias.get(key, key))
        subject = known.get(key) or known.get(norm(subj_in)) or subj_in.strip()
        paper = cols[4].strip()
        kinds = dict(papers_for(subject))
        kind = kinds.get(paper) or _guess_kind(paper)
        row.update(date=d, start=st, end=en, subject=subject, paper=paper or None, kind=kind,
                   venue=cols[5] or None, invigilators=cols[6] or None,
                   known=bool(known.get(key) or known.get(norm(subj_in))))
        if not d:
            row['error'] = 'Date not understood: “%s”' % cols[0]
        elif not st:
            row['error'] = 'Start time not understood: “%s”' % cols[1]
        elif not en:
            row['error'] = 'End time / duration not understood: “%s”' % cols[2]
        elif en <= st:
            row['error'] = 'Ends before it starts'
        elif not subject:
            row['error'] = 'No subject'
        out.append(row)
    return out


def _guess_kind(paper):
    p = norm(paper)
    has = lambda *w: all(x in p for x in w)
    for test, kind in ((has('drama', 'poetry'), 'drama_poetry'), (has('objective', 'prose'), 'objective_prose'),
                       (has('objective', 'practical'), 'objective_practical'),
                       (has('practical', 'physical'), 'practical_physical'),
                       (has('objective', 'essay'), 'combined'), (has('alternative'), 'alt_practical'),
                       (has('prose'), 'prose'), (has('practical'), 'practical'), (has('oral'), 'oral'),
                       (has('listening'), 'oral'), (has('drawing'), 'drawing'), (has('project'), 'project'),
                       (has('objective'), 'objective'), (has('essay'), 'essay'), (has('theory'), 'essay')):
        if test:
            return kind
    return None
