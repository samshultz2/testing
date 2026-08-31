"""One-page executive "board pack" PDF for the external-exams analytics hub.

Turns the same numbers the analytics hub renders (JAMB/WAEC school statistics,
university-cut-off readiness, WAEC<->JAMB correlation, top performers) plus the
ranked Smart Insights into a board-ready summary a head/proprietor can print or
email — the paper twin of the on-screen Executive Summary.

Pure formatting: it receives the already-computed dicts and returns PDF bytes, so
it runs no queries of its own.
"""
import io
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                Spacer)

_PRIMARY = colors.HexColor('#0d6a4e')
_LIGHT = colors.HexColor('#e8f5f1')
_LEVEL_COLOR = {'critical': colors.HexColor('#dc2626'),
                'warn': colors.HexColor('#d97706'),
                'good': colors.HexColor('#16a34a'),
                'info': colors.HexColor('#4f46e5')}
_LEVEL_LABEL = {'critical': 'ACTION', 'warn': 'WATCH', 'good': 'GOOD', 'info': 'NOTE'}

_S = {}


def _esc(v):
    return _xml_escape('' if v is None else str(v))


def _styles():
    if _S:
        return _S
    base = getSampleStyleSheet()
    _S['title'] = ParagraphStyle('t', parent=base['Title'], fontSize=17,
                                 textColor=_PRIMARY, spaceAfter=2)
    _S['sub'] = ParagraphStyle('s', parent=base['Normal'], alignment=TA_CENTER,
                               fontSize=10, textColor=colors.grey, spaceAfter=10)
    _S['h'] = ParagraphStyle('h', parent=base['Heading4'], textColor=_PRIMARY,
                             spaceBefore=10, spaceAfter=4)
    _S['cell'] = ParagraphStyle('c', parent=base['Normal'], fontSize=8.5, leading=11)
    _S['ins'] = ParagraphStyle('i', parent=base['Normal'], fontSize=8.5, leading=11.5)
    _S['kpi_v'] = ParagraphStyle('kv', parent=base['Normal'], fontSize=15,
                                 alignment=TA_CENTER, leading=17)
    _S['kpi_l'] = ParagraphStyle('kl', parent=base['Normal'], fontSize=7,
                                 alignment=TA_CENTER, textColor=colors.grey, leading=8)
    _S['small'] = ParagraphStyle('sm', parent=base['Normal'], fontSize=7.5,
                                 textColor=colors.grey)
    return _S


def _kpi_band(kpis):
    """A row of value/label cells (list of ``(value, label, hex_color)``)."""
    S = _styles()
    top = [Paragraph(f'<font color="{c}"><b>{_esc(v)}</b></font>', S['kpi_v'])
           for v, _, c in kpis]
    bot = [Paragraph(_esc(l), S['kpi_l']) for _, l, _ in kpis]
    t = Table([top, bot], colWidths=[(180 * mm) / len(kpis)] * len(kpis))
    t.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor('#d0d7de')),
        ('INNERGRID', (0, 0), (-1, 0), 0.6, colors.HexColor('#d0d7de')),
        ('LINEBEFORE', (1, 0), (-1, -1), 0.6, colors.HexColor('#d0d7de')),
        ('BACKGROUND', (0, 0), (-1, -1), _LIGHT),
        ('TOPPADDING', (0, 0), (-1, 0), 7), ('BOTTOMPADDING', (0, 1), (-1, 1), 7),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return t


def _stat_table(title, pairs):
    S = _styles()
    rows = [[Paragraph(f'<b>{_esc(title)}</b>', S['cell']), '']]
    for k, v in pairs:
        rows.append([Paragraph(_esc(k), S['cell']),
                     Paragraph(f'<b>{_esc(v)}</b>', S['cell'])])
    t = Table(rows, colWidths=[58 * mm, 30 * mm])
    t.setStyle(TableStyle([
        ('SPAN', (0, 0), (1, 0)),
        ('BACKGROUND', (0, 0), (-1, 0), _PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('LINEBELOW', (0, 1), (-1, -1), 0.4, colors.HexColor('#e5e7eb')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f6f8fa')]),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    return t


def board_pack_pdf(*, year, school_name, generated, insights=None, jamb_stats=None,
                   waec_stats=None, cutoff=None, correlation=None, branch_label=None):
    """Render the board pack and return PDF ``bytes``."""
    S = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=14 * mm, bottomMargin=14 * mm,
                            leftMargin=14 * mm, rightMargin=14 * mm,
                            title=f'Exam Board Pack {year}')
    flow = [Paragraph(_esc(school_name or 'School'), S['title'])]
    sub = f'External Examinations — Executive Summary · {year}'
    if branch_label:
        sub += f' · {branch_label}'
    flow.append(Paragraph(sub, S['sub']))

    # --- KPI band --------------------------------------------------------- #
    def tone(ok, mid, val):
        if val is None:
            return colors.grey
        return (_LEVEL_COLOR['good'] if val >= ok
                else _LEVEL_COLOR['warn'] if val >= mid else _LEVEL_COLOR['critical'])
    kpis = []
    jmean = jamb_stats['mean_score'] if jamb_stats else None
    kpis.append((jmean if jmean is not None else '—', 'JAMB mean',
                 tone(200, 150, jmean).hexval() if jmean is not None else '#6b7280'))
    upct = cutoff['eligible_200_pct'] if cutoff else None
    kpis.append((f'{upct}%' if upct is not None else '—', 'University-ready (≥200)',
                 tone(65, 40, upct).hexval() if upct is not None else '#6b7280'))
    wpr = waec_stats['overall_pass_rate'] if waec_stats else None
    kpis.append((f'{wpr}%' if wpr is not None else '—', 'WAEC pass rate',
                 tone(75, 60, wpr).hexval() if wpr is not None else '#6b7280'))
    r = correlation.get('correlation_coefficient') if (correlation and not correlation.get('error')) else None
    kpis.append((r if r is not None else '—', 'WAEC↔JAMB link',
                 tone(0.5, 0.3, r).hexval() if r is not None else '#6b7280'))
    flow.append(_kpi_band(kpis))

    # --- Smart insights --------------------------------------------------- #
    if insights:
        flow.append(Paragraph('Smart Insights', S['h']))
        for i in insights:
            col = _LEVEL_COLOR.get(i['level'], colors.grey)
            tag = _LEVEL_LABEL.get(i['level'], 'NOTE')
            flow.append(Paragraph(
                f'<font color="{col.hexval()}"><b>[{tag}]</b></font> '
                f'<b>{_esc(i["title"])}</b> — {_esc(i["detail"])}', S['ins']))
            flow.append(Spacer(1, 2))

    # --- JAMB + WAEC key stats side by side ------------------------------- #
    left, right = [], []
    if jamb_stats:
        jp = [('Candidates', jamb_stats['total_students']),
              ('Mean / Median', f"{jamb_stats['mean_score']} / {jamb_stats['median_score']}"),
              ('Highest / Lowest', f"{jamb_stats['max_score']} / {jamb_stats['min_score']}"),
              ('≥200 / ≥250 / ≥300',
               f"{jamb_stats['above_200']} / {jamb_stats['above_250']} / {jamb_stats['above_300']}")]
        left.append(_stat_table('JAMB', jp))
    if cutoff:
        left.append(Spacer(1, 6))
        left.append(_stat_table('University readiness', [
            ('Admissible (≥200)', f"{cutoff['eligible_200']} ({cutoff['eligible_200_pct']}%)"),
            ('Competitive (≥250)', f"{cutoff['competitive_250']} ({cutoff['competitive_250_pct']}%)"),
            ('Elite (≥300)', f"{cutoff['elite_300']} ({cutoff['elite_300_pct']}%)")]))
    if waec_stats:
        wp = [('Students', waec_stats['unique_students']),
              ('Subject entries', waec_stats['total_results']),
              ('Pass rate', f"{waec_stats['overall_pass_rate']}%"),
              ('Distinction rate', f"{waec_stats['overall_distinction_rate']}%")]
        right.append(_stat_table('WAEC', wp))
        worst = waec_stats.get('most_failed_subjects') or []
        if worst:
            right.append(Spacer(1, 6))
            right.append(_stat_table('Most-failed WAEC subjects',
                                     [(s['subject'], f"{s['fail_rate']}% fail") for s in worst[:5]]))

    if left or right:
        flow.append(Paragraph('Key statistics', S['h']))
        body = Table([[left or '', right or '']], colWidths=[90 * mm, 90 * mm])
        body.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                  ('LEFTPADDING', (0, 0), (0, 0), 0),
                                  ('RIGHTPADDING', (1, 0), (1, 0), 0)]))
        flow.append(body)

    # --- Top performers --------------------------------------------------- #
    if jamb_stats and jamb_stats.get('top_10'):
        flow.append(Paragraph('Top JAMB candidates', S['h']))
        rows = [[Paragraph('<b>#</b>', S['cell']), Paragraph('<b>Student</b>', S['cell']),
                 Paragraph('<b>Score</b>', S['cell'])]]
        for n, t in enumerate(jamb_stats['top_10'][:10], 1):
            rows.append([Paragraph(str(n), S['cell']),
                         Paragraph(_esc(t['student_name']), S['cell']),
                         Paragraph(f"<b>{_esc(t['score'])}</b>", S['cell'])])
        tt = Table(rows, colWidths=[12 * mm, 138 * mm, 30 * mm])
        tt.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), _LIGHT),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f6f8fa')]),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        flow.append(tt)

    flow.append(Spacer(1, 10))
    flow.append(Paragraph(f'Generated {_esc(generated)} · EduSyncra', S['small']))
    doc.build(flow)
    return buf.getvalue()
