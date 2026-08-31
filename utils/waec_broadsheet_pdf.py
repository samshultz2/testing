"""Server-side PDF for the real WAEC broadsheet — the full grade matrix for an
exam year, one column per subject (grade only; WAEC reports no scores), with the
per-subject offered/passed/failed/average-grade summary beneath. Reuses the
mock-WAEC broadsheet primitives (vertical headers, school letterhead, grade key,
column fitting) so the two sheets look identical.
"""
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                Spacer, PageBreak)
from utils.web_exports import pdf_escape
from utils.mock_waec_pdf import (
    _styles, _S, _opt, _school_header, _groups, _pagesize,
    _grade_key_table, _fit_per, _VHead, _EXTRA_ROWS, _BLACK,
)

# Grade-only summary (no "Average score %" — WAEC carries no scores).
_WAEC_SUMMARY = ['No. offered', 'No. passed (C6+)', 'No. failed', 'Average grade']


def _bs_name(st):
    """Surname + first name for the name column. ``st`` is the plain dict the
    broadsheet builder emits (surname/first_name/full_name)."""
    parts = [st.get('surname') or '', st.get('first_name') or '']
    return ' '.join(p for p in parts if p).strip() or st.get('full_name') or ''


def waec_broadsheet_pdf(bs, year, school, opts=None, per=8, orient='landscape'):
    """Full grade matrix for a WAEC exam year. Wide subject sets split across
    pages (``per`` columns each). ``opts['summary']`` toggles the per-subject
    offered/passed/failed/average-grade rows; ``orient`` is landscape or
    portrait A4 with an 8mm margin."""
    _styles()
    page = _pagesize(orient)
    import io
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=page, topMargin=8 * mm,
                            bottomMargin=8 * mm, leftMargin=8 * mm, rightMargin=8 * mm,
                            title=f'WAEC Broadsheet — {year}')
    usable = page[0] - 16 * mm
    sn_w, name_w = 9 * mm, 52 * mm
    per = _fit_per(usable, sn_w, name_w, 24 * mm, 11 * mm, per, len(bs['subjects']))
    groups = _groups(bs['subjects'], per)
    ss = bs['subject_summary']
    nrows = len(bs['rows'])
    show_summary = _opt(opts, 'summary')
    e = []
    for gi, group in enumerate(groups):
        last = gi == len(groups) - 1
        sub = f'WAEC / WASSCE {year} — Broadsheet'
        if len(groups) > 1:
            sub += f' (Sheet {gi + 1} of {len(groups)})'
        _school_header(e, school, opts, sub)

        tail = 2 if last else 0
        sub_w = (usable - sn_w - name_w) / (len(group) + tail)

        header = [Paragraph('S/N', _S['colhead']), Paragraph('Name of Student', _S['colhead'])]
        header += [_VHead(s) for s in group]
        if last:
            header += [_VHead('Credits'), _VHead('Avg grade')]
        data = [header]
        for i, row in enumerate(bs['rows'], 1):
            line = [str(i), Paragraph(pdf_escape(_bs_name(row['student'])), _S['name'])]
            for s in group:
                line.append(row['cells'].get(s, ''))
            if last:
                line += [str(row['credits']), row['avg_grade']]
            data.append(line)

        ncols = 2 + len(group) + tail
        for _ in range(_EXTRA_ROWS):
            data.append([''] * ncols)

        sum0 = nrows + 1 + _EXTRA_ROWS
        if show_summary:
            for label, fn in (('No. offered', lambda d: d['offered']),
                              ('No. passed (C6+)', lambda d: d['passed']),
                              ('No. failed', lambda d: d['failed']),
                              ('Average grade', lambda d: d['avg_grade'])):
                rr = ['', label] + [str(fn(ss[s])) for s in group]
                if last:
                    rr += ['', '']
                data.append(rr)

        widths = [sn_w, name_w] + [sub_w] * (len(group) + tail)
        heights = ([None] + [None] * nrows + [7.5 * mm] * _EXTRA_ROWS
                   + ([None] * len(_WAEC_SUMMARY) if show_summary else []))
        t = Table(data, colWidths=widths, repeatRows=0, rowHeights=heights)
        style = [
            ('GRID', (0, 0), (-1, -1), 0.9, _BLACK),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 1), (-1, nrows), 9.5),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('VALIGN', (0, 0), (-1, 0), 'BOTTOM'),
            ('TOPPADDING', (0, 0), (-1, -1), 2.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ]
        if show_summary:
            style.append(('FONTSIZE', (0, sum0), (-1, -1), 8.5))
            style.append(('LINEABOVE', (0, sum0), (-1, sum0), 1.3, _BLACK))
        t.setStyle(TableStyle(style))
        e.append(t)
        if _opt(opts, 'grades'):
            e.append(Spacer(1, 6))
            e.append(_grade_key_table(usable))
        if not last:
            e.append(PageBreak())
    doc.build(e)
    buf.seek(0)
    return buf
