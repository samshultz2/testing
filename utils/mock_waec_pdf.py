"""Server-side PDFs for Mock WAEC — the broadsheet and student result slips.

Rendered with reportlab (no headless browser needed) so they preview/print
identically. School identity (name, address, …) comes from SchoolSettings, and
the bold "COMPETENCE RESULT" banner is optional.
"""
import io

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                Spacer, PageBreak)

_BLACK = colors.black
_HEAD = colors.HexColor('#d9d9d9')
_FOOT = colors.HexColor('#eeeeee')

_S = {}


def _styles():
    if _S:
        return _S
    base = getSampleStyleSheet()
    _S['school'] = ParagraphStyle('sch', parent=base['Title'], fontSize=18, leading=20,
                                  alignment=TA_CENTER, spaceAfter=0, textColor=_BLACK)
    _S['addr'] = ParagraphStyle('addr', parent=base['Normal'], fontSize=9,
                                alignment=TA_CENTER, spaceAfter=0)
    _S['comp'] = ParagraphStyle('comp', parent=base['Normal'], fontSize=14,
                                alignment=TA_CENTER, spaceBefore=4, spaceAfter=2,
                                fontName='Helvetica-Bold')
    _S['exam'] = ParagraphStyle('exam', parent=base['Normal'], fontSize=11,
                                alignment=TA_CENTER, spaceAfter=6, fontName='Helvetica-Bold')
    _S['colhead'] = ParagraphStyle('ch', parent=base['Normal'], fontSize=7.5, leading=8.5,
                                   alignment=TA_CENTER, fontName='Helvetica-Bold')
    _S['name'] = ParagraphStyle('nm', parent=base['Normal'], fontSize=8.5, leading=9.5,
                                fontName='Helvetica-Bold')
    _S['h'] = ParagraphStyle('h', parent=base['Normal'], fontSize=11, spaceBefore=8,
                             spaceAfter=4, fontName='Helvetica-Bold')
    _S['cell'] = ParagraphStyle('c', parent=base['Normal'], fontSize=10)
    return _S


def _school_header(e, school, show_title, subtitle):
    """School identity block + optional COMPETENCE RESULT banner + a subtitle."""
    _styles()
    if school.get('name'):
        e.append(Paragraph((school['name'] or '').upper(), _S['school']))
    line = ' · '.join(x for x in (school.get('address'), school.get('phone'),
                                  school.get('email')) if x)
    if line:
        e.append(Paragraph(line, _S['addr']))
    if school.get('motto'):
        e.append(Paragraph('<i>%s</i>' % school['motto'], _S['addr']))
    if show_title:
        e.append(Paragraph('COMPETENCE RESULT', _S['comp']))
    if subtitle:
        e.append(Paragraph(subtitle, _S['exam']))


def broadsheet_pdf(bs, exam, school, show_title=True, per=8):
    """Full score+grade matrix. Wide subject sets split across pages (``per``
    columns each) so the print stays bold and readable; no admission numbers."""
    _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=8 * mm,
                            bottomMargin=8 * mm, leftMargin=8 * mm, rightMargin=8 * mm,
                            title=f'Broadsheet — {exam.display_name}')
    subs = bs['subjects']
    groups = ([subs[i:i + per] for i in range(0, len(subs), per)]
              if per and len(subs) > per else [subs])
    ss = bs['subject_summary']
    nrows = len(bs['rows'])
    usable = landscape(A4)[0] - 16 * mm
    e = []
    for gi, group in enumerate(groups):
        last = gi == len(groups) - 1
        sub = f'{exam.display_name} — Broadsheet'
        if len(groups) > 1:
            sub += f' (Sheet {gi + 1} of {len(groups)})'
        _school_header(e, school, show_title, sub)

        sn_w, name_w = 9 * mm, 52 * mm
        tail = 2 if last else 0
        sub_w = (usable - sn_w - name_w) / (len(group) + tail)

        header = [Paragraph('S/N', _S['colhead']), Paragraph('Name of Student', _S['colhead'])]
        header += [Paragraph(s, _S['colhead']) for s in group]
        if last:
            header += [Paragraph('Cr', _S['colhead']), Paragraph('Avg%', _S['colhead'])]
        data = [header]
        for i, row in enumerate(bs['rows'], 1):
            line = [str(i), Paragraph(row['student'].full_name, _S['name'])]
            for s in group:
                r = row['cells'].get(s)
                line.append(f'{r.score} {r.grade}' if (r and r.score is not None) else '')
            if last:
                line += [str(row['credits']),
                         (str(row['average_score']) if row['average_score'] is not None else '')]
            data.append(line)
        for label, fn in (('No. offered', lambda d: d['offered']),
                          ('No. passed (C6+)', lambda d: d['passed']),
                          ('No. failed', lambda d: d['failed']),
                          ('Average score %', lambda d: d['avg_score'] if d['avg_score'] is not None else '—'),
                          ('Average grade', lambda d: d['avg_grade'])):
            rr = ['', label] + [str(fn(ss[s])) for s in group]
            if last:
                rr += ['', '']
            data.append(rr)

        widths = [sn_w, name_w] + [sub_w] * (len(group) + tail)
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.9, _BLACK),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 1), (-1, nrows), 9.5),
            ('FONTSIZE', (0, nrows + 1), (-1, -1), 8.5),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (-1, 0), _HEAD),
            ('BACKGROUND', (0, nrows + 1), (-1, -1), _FOOT),
            ('TOPPADDING', (0, 0), (-1, -1), 2.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ]))
        e.append(t)
        if not last:
            e.append(PageBreak())
    doc.build(e)
    buf.seek(0)
    return buf


def result_slips_pdf(slips, exam, school, show_title=True):
    """One A4 "Statement of Result" per student."""
    _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=12 * mm, bottomMargin=12 * mm,
                            leftMargin=14 * mm, rightMargin=14 * mm,
                            title=f'Results — {exam.display_name}')
    e = []
    session = exam.session.name if exam.session else ''
    for idx, slip in enumerate(slips):
        student, s = slip['student'], slip['summary']
        sub = f'{exam.display_name} — Statement of Result'
        if session:
            sub += f' · {session}'
        _school_header(e, school, show_title, sub)

        meta = [
            [Paragraph(f'<b>Name:</b> {student.full_name}', _S['cell']),
             Paragraph(f'<b>Adm. No:</b> {student.student_id}', _S['cell'])],
            [Paragraph(f"<b>Stream:</b> {student.stream or '—'}", _S['cell']),
             Paragraph(f'<b>Gender:</b> {student.gender or "—"}', _S['cell'])],
        ]
        mt = Table(meta, colWidths=[95 * mm, 87 * mm])
        mt.setStyle(TableStyle([('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
        e.append(mt)
        e.append(Spacer(1, 4))

        if s and s.get('results'):
            data = [['#', 'Subject', 'Score', 'Grade', 'Remark']]
            for i, r in enumerate(s['results'], 1):
                data.append([str(i), r.subject,
                             '' if r.score is None else str(r.score),
                             r.grade or '—', 'Credit' if r.is_pass else 'Fail'])
            t = Table(data, colWidths=[10 * mm, 92 * mm, 24 * mm, 24 * mm, 32 * mm], repeatRows=1)
            t.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.7, _BLACK),
                ('BACKGROUND', (0, 0), (-1, 0), _HEAD),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (3, 1), (3, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9.5),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            for ri, r in enumerate(s['results'], 1):
                t.setStyle(TableStyle([('TEXTCOLOR', (4, ri), (4, ri),
                    colors.HexColor('#047857') if r.is_pass else colors.HexColor('#b91c1c'))]))
            e.append(t)
            e.append(Spacer(1, 6))

            core = ', '.join(s.get('missing_core') or []) or 'None'
            summ = [
                [Paragraph(f"<b>Subjects:</b> {s['subjects']}", _S['cell']),
                 Paragraph(f"<b>Credits (C6+):</b> {s['credits']}", _S['cell'])],
                [Paragraph(f"<b>Distinctions (A1–B3):</b> {s['distinctions']}", _S['cell']),
                 Paragraph(f"<b>Average:</b> {s['average_score'] if s['average_score'] is not None else '—'}%", _S['cell'])],
                [Paragraph(f"<b>5 credits incl. English &amp; Maths:</b> {'YES' if s['has_5_incl_core'] else 'NO'}", _S['cell']),
                 Paragraph(f"<b>Missing core:</b> {core}", _S['cell'])],
            ]
            st = Table(summ, colWidths=[95 * mm, 87 * mm])
            st.setStyle(TableStyle([
                ('BOX', (0, 0), (-1, -1), 0.7, _BLACK),
                ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#cccccc')),
                ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ]))
            e.append(st)
        else:
            e.append(Paragraph('No results recorded for this student.', _S['cell']))

        e.append(Spacer(1, 22))
        sign = Table([[Paragraph('_______________________<br/>Class Teacher', _S['cell']),
                       Paragraph('_______________________<br/>Principal', _S['cell'])]],
                     colWidths=[91 * mm, 91 * mm])
        sign.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
        e.append(sign)
        if idx != len(slips) - 1:
            e.append(PageBreak())
    if not slips:
        e.append(Paragraph('No results to print.', _S['cell']))
    doc.build(e)
    buf.seek(0)
    return buf
