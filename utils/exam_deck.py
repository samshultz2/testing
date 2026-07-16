"""Generate an editable PowerPoint (.pptx) deck of a school's external-exam
performance — for administration/parent/board meetings.

Data-driven from the same WAEC/JAMB analytics as the board-pack PDF, and framed
to lead with the school's strengths. Aggregate figures only (plus optional
anonymous distribution counts) — no student records. The deck is a normal .pptx
the school can open in PowerPoint/Keynote/Google Slides and tweak."""
import io

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

# 16:9 canvas
_W = Inches(13.333)
_H = Inches(7.5)

_INK = RGBColor(0x14, 0x21, 0x1C)
_PRIMARY = RGBColor(0x0D, 0x6A, 0x4E)
_ACCENT = RGBColor(0xC9, 0xA2, 0x27)
_MUTED = RGBColor(0x6B, 0x7A, 0x74)
_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
_LIGHT = RGBColor(0xF4, 0xF7, 0xF5)


def _blank(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])   # blank layout


def _box(slide, l, t, w, h):
    tb = slide.shapes.add_textbox(l, t, w, h)
    tb.text_frame.word_wrap = True
    return tb.text_frame


def _rect(slide, l, t, w, h, fill):
    from pptx.enum.shapes import MSO_SHAPE
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, l, t, w, h)
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def _set(p, text, size, color, bold=False, align=PP_ALIGN.LEFT):
    p.text = str(text)
    p.alignment = align
    r = p.runs[0]
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.color.rgb = color
    return p


def _num(v, suffix=''):
    if v is None:
        return '—'
    try:
        f = float(v)
        return (f'{f:g}' if f != int(f) else f'{int(f)}') + suffix
    except (TypeError, ValueError):
        return str(v)


def _title_slide(prs, school, year, subtitle, generated):
    s = _blank(prs)
    _rect(s, 0, 0, _W, _H, _PRIMARY)
    _rect(s, 0, Inches(5.0), _W, Inches(0.12), _ACCENT)
    tf = _box(s, Inches(0.9), Inches(2.1), Inches(11.5), Inches(2.6))
    _set(tf.paragraphs[0], school, 40, _WHITE, bold=True)
    _set(tf.add_paragraph(), f'External Examination Performance · {year}', 26, _WHITE)
    if subtitle:
        _set(tf.add_paragraph(), subtitle, 18, RGBColor(0xE6, 0xEF, 0xEA))
    ft = _box(s, Inches(0.9), Inches(6.6), Inches(11.5), Inches(0.5))
    _set(ft.paragraphs[0], f'Prepared {generated}', 12, RGBColor(0xCF, 0xDD, 0xD7))


def _section_header(slide, title, subtitle=None):
    _rect(slide, 0, 0, _W, Inches(1.15), _PRIMARY)
    tf = _box(slide, Inches(0.6), Inches(0.18), Inches(12), Inches(0.9))
    _set(tf.paragraphs[0], title, 28, _WHITE, bold=True)
    if subtitle:
        st = _box(slide, Inches(0.6), Inches(1.25), Inches(12.1), Inches(0.5))
        _set(st.paragraphs[0], subtitle, 14, _MUTED)


def _stat_card(slide, l, t, w, value, label):
    _rect(slide, l, t, w, Inches(1.9), _LIGHT)
    _rect(slide, l, t, w, Inches(0.10), _ACCENT)
    vf = _box(slide, l, t + Inches(0.35), w, Inches(1.0))
    vf.vertical_anchor = MSO_ANCHOR.MIDDLE
    _set(vf.paragraphs[0], value, 40, _PRIMARY, bold=True, align=PP_ALIGN.CENTER)
    lf = _box(slide, l, t + Inches(1.35), w, Inches(0.5))
    _set(lf.paragraphs[0], label, 12, _MUTED, align=PP_ALIGN.CENTER)


def _kpi_slide(prs, waec, jamb, cutoff):
    s = _blank(prs)
    _section_header(s, 'Performance at a glance', 'Headline outcomes for the year')
    cards = []
    if waec:
        cards.append((_num(waec.get('overall_pass_rate'), '%'), 'WAEC pass rate'))
        cards.append((_num(waec.get('overall_distinction_rate'), '%'), 'WAEC distinctions'))
    if jamb:
        cards.append((_num(jamb.get('mean_score')), 'JAMB mean score'))
    if cutoff:
        cards.append((_num(cutoff.get('eligible_200_pct'), '%'), 'JAMB ≥ 200'))
    cards = cards[:4] or [('—', 'No data')]
    n = len(cards)
    gap = Inches(0.4)
    total_w = _W - Inches(1.2) - gap * (n - 1)
    w = Emu(int(total_w / n))
    x = Inches(0.6)
    for value, label in cards:
        _stat_card(s, x, Inches(2.4), w, value, label)
        x = Emu(int(x) + int(w) + int(gap))


def _table_slide(prs, title, subtitle, headers, rows):
    s = _blank(prs)
    _section_header(s, title, subtitle)
    if not rows:
        _set(_box(s, Inches(0.6), Inches(2.5), Inches(11), Inches(1)).paragraphs[0],
             'No data available for this section.', 16, _MUTED)
        return s
    rows = rows[:9]
    nrows, ncols = len(rows) + 1, len(headers)
    gt = s.shapes.add_table(nrows, ncols, Inches(0.6), Inches(1.6),
                            _W - Inches(1.2), Inches(0.5) * nrows).table
    for c, h in enumerate(headers):
        cell = gt.cell(0, c)
        cell.text = str(h)
        cell.fill.solid(); cell.fill.fore_color.rgb = _PRIMARY
        p = cell.text_frame.paragraphs[0]; p.runs[0].font.color.rgb = _WHITE
        p.runs[0].font.bold = True; p.runs[0].font.size = Pt(14)
    for r, row in enumerate(rows, start=1):
        for c, val in enumerate(row):
            cell = gt.cell(r, c)
            cell.text = str(val)
            p = cell.text_frame.paragraphs[0]
            p.runs[0].font.size = Pt(13); p.runs[0].font.color.rgb = _INK
            if r % 2 == 0:
                cell.fill.solid(); cell.fill.fore_color.rgb = _LIGHT
    return s


def _insights_slide(prs, insights):
    s = _blank(prs)
    _section_header(s, 'Key takeaways', 'What the results tell us')
    tf = _box(s, Inches(0.7), Inches(1.7), Inches(12), Inches(5.2))
    first = True
    for i in (insights or [])[:6]:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        _set(p, '•  ' + i.get('title', ''), 18, _PRIMARY, bold=True)
        detail = (i.get('detail') or '')
        if detail:
            dp = tf.add_paragraph()
            _set(dp, '     ' + detail, 13, _MUTED)
    if first:
        _set(tf.paragraphs[0], 'Results are being compiled.', 16, _MUTED)


def _closing_slide(prs, school):
    s = _blank(prs)
    _rect(s, 0, 0, _W, _H, _PRIMARY)
    tf = _box(s, Inches(0.9), Inches(3.0), Inches(11.5), Inches(1.5))
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    _set(tf.paragraphs[0], 'Thank you', 40, _WHITE, bold=True, align=PP_ALIGN.CENTER)
    _set(tf.add_paragraph(), school, 20, RGBColor(0xE6, 0xEF, 0xEA), align=PP_ALIGN.CENTER)


def build_deck(*, year, school_name, generated, branch_label=None,
               waec_stats=None, jamb_stats=None, cutoff=None, correlation=None, insights=None):
    """Return the .pptx bytes for the external-exam results deck."""
    prs = Presentation()
    prs.slide_width = _W
    prs.slide_height = _H

    subtitle = branch_label or 'All branches'
    _title_slide(prs, school_name or 'Our School', year, subtitle, generated)
    _kpi_slide(prs, waec_stats, jamb_stats, cutoff)

    if waec_stats and waec_stats.get('subject_analysis'):
        rows = [(s['subject'], _num(s.get('pass_rate'), '%'))
                for s in sorted(waec_stats['subject_analysis'],
                                key=lambda x: x.get('pass_rate') or 0, reverse=True)]
        _table_slide(prs, 'WAEC — strongest subjects', 'Subject pass rates, best first',
                     ['Subject', 'Pass rate'], rows)

    if jamb_stats:
        jrows = [('Candidates', _num(jamb_stats.get('total_students'))),
                 ('Mean score', _num(jamb_stats.get('mean_score'))),
                 ('Highest score', _num(jamb_stats.get('max_score'))),
                 ('Scored ≥ 200', _num(jamb_stats.get('above_200'))),
                 ('Scored ≥ 250', _num(jamb_stats.get('above_250'))),
                 ('Scored ≥ 300', _num(jamb_stats.get('above_300')))]
        _table_slide(prs, 'JAMB — overview', 'Cohort performance', ['Metric', 'Value'], jrows)

    if cutoff:
        crows = [('University-admissible (≥ 200)', _num(cutoff.get('eligible_200_pct'), '%')),
                 ('Competitive (≥ 250)', _num(cutoff.get('competitive_250_pct'), '%')),
                 ('Elite (≥ 300)', _num(cutoff.get('elite_300_pct'), '%'))]
        _table_slide(prs, 'University readiness', 'Share of JAMB candidates by band',
                     ['Band', 'Share'], crows)

    _insights_slide(prs, insights)
    _closing_slide(prs, school_name or 'Our School')

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
