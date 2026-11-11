"""Multi-format export (PDF, Word, Excel, HD PNG) for the Subject-Wise Grade
Breakdown report (routes.results.analytics.subject_branch_breakdown) —
a navy masthead + two-tier colour-coded header, matching the school's own
printed grade-analysis-sheet template. The on-screen A1-F9 / score-band
colour ramp (CSS color-mix(), no equivalent outside a browser) is hand-kept
in sync with the .gb-1..gb-9 rules in templates/results/subject_branch_breakdown.html:
header cells use the base hue at full strength, body cells a light tint.
The PDF doesn't use that ramp: it has its own design (Inter, an indigo hero,
ranking cards, single-hue grade chips) — see grade_breakdown_pdf.
"""
import io
import os

from utils.broadsheet_export import _school_name, _NEUTRAL_RGB, zip_pngs
from utils.web_exports import pdf_escape

NAVY_HEX = '#173A63'
NAVY_RGB = (23, 58, 99)

_BAND_BASE = ['#16a34a', '#22c55e', '#4ade80', '#eab308', '#f59e0b',
             '#f97316', '#ef4444', '#dc2626', '#9333ea']
_BAND_ALPHA = [.30, .26, .22, .26, .22, .26, .20, .26, .24]


def _blend(hex_color, alpha, base=(255, 255, 255)):
    hex_color = hex_color.lstrip('#')
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(round(c * alpha + base[i] * (1 - alpha)) for i, c in enumerate((r, g, b)))


def band_rgb(index, header=False):
    """0-based band index -> (r,g,b). ``header=True`` is the vivid, near-full-
    strength swatch used on the colour-coded header cells; the default is the
    light print-safe tint used on the data cells beneath it."""
    i = index % len(_BAND_BASE)
    if header:
        hexc = _BAND_BASE[i].lstrip('#')
        return tuple(int(hexc[j:j + 2], 16) for j in (0, 2, 4))
    return _blend(_BAND_BASE[i], _BAND_ALPHA[i])


def band_hex(index, header=False):
    r, g, b = band_rgb(index, header)
    return '#%02X%02X%02X' % (r, g, b)


def _text_on(rgb):
    """Black or white — whichever reads better on this background."""
    r, g, b = rgb
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return (255, 255, 255) if luminance < 0.62 else (15, 23, 42)


STAR = '\u2605'


def _best(result, subj):
    """The subject's best branch — the same rule as the on-screen page
    (highest credit/pass rate, then better grades, then entries; <5 entries
    can't win; exact ties highlight no one). Computed once in
    routes.results.analytics._branch_grade_breakdown."""
    return ((result.get('subject_overall') or {}).get(subj) or {}).get('best')


def top_note(result, subj):
    """'Top grades: Upper 1 — 3 of 3 A1 (small group)' or None."""
    t = ((result.get('subject_overall') or {}).get(subj) or {}).get('top_small')
    return f"Top grades: {t['branch']} — {t['text']} (small group)" if t else None


def top_notes(result):
    return [(s, top_note(result, s)) for s in result['subjects'] if top_note(result, s)]


def best_legend(band_label):
    word = 'credit' if band_label == 'Grade' else 'pass'
    return (f'{STAR} Best branch for the subject: highest {word} rate; if tied, better grades; '
            f'branches with fewer than 5 entries can\'t be best unless all are that small.')


def _main_headers(bands):
    return ['Subject', 'Branch', 'Candidates (N)'] + [f'{b} (%)' for b in bands]


def _summary_headers(bands, pass_label):
    return ['Branch', 'Total Subject Entries (N)'] + [f'{b} (%)' for b in bands] + [pass_label]


def _main_text_rows(result):
    bands = result['bands']
    rows = []
    for subj in result['subjects']:
        for bi, br in enumerate(result['branches']):
            cell = result['table'][subj][br]
            br = f'{STAR} {br}' if br == _best(result, subj) else br
            if cell is None:
                rows.append([subj if bi == 0 else '', br, 'Not Offered'] + [''] * len(bands))
            else:
                rows.append([subj if bi == 0 else '', br, str(cell['n'])]
                            + [f"{cell['pct'][b]}%" for b in bands])
    return rows


def _summary_text_rows(result, pass_label):
    bands = result['bands']
    rows = []
    for br in result['branches']:
        s = result['summary'][br]
        rows.append([br, str(s['n'])] + [f"{s['pct'][b]}%" for b in bands]
                    + [f"{s['pass_pct']}% ({s['pass_n']})"])
    return rows


def _docx_col_widths(name_lens, name_headers, name_caps, extra_header, avail_cm, n_band_cols, tail_label=None):
    """Column widths (cm) for a docx table: name-ish columns sized to their
    content (capped), band columns splitting whatever's left evenly — never
    letting Subject/Branch balloon out to fill the page like Word's default
    equal-split would."""
    from docx.shared import Cm
    widths = []
    for lens, header, cap in zip(name_lens, name_headers, name_caps):
        w = min(max(max(lens, default=8), len(header)) * 0.22 + 0.6, cap)
        widths.append(w)
    n_cm = len(extra_header) * 0.16 + 0.5
    widths.append(n_cm)
    tail_cm = min(len(tail_label) * 0.16 + 0.6, 5.5) if tail_label else 0
    band_cm = (avail_cm - sum(widths) - tail_cm) / n_band_cols
    widths += [band_cm] * n_band_cols
    if tail_label:
        widths.append(tail_cm)
    return [Cm(w) for w in widths]


def _apply_docx_col_widths(table, widths):
    table.autofit = False
    for i, w in enumerate(widths):
        table.columns[i].width = w
    for row in table.rows:
        for i, cell in enumerate(row.cells):
            if i < len(widths):
                cell.width = widths[i]


# --------------------------------------------------------------------------- #
# PDF (reportlab, landscape A4)
# --------------------------------------------------------------------------- #

# ---- PDF design system (Inter, indigo/violet accent) ------------------------
_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'fonts')
_PDF_FONTS = {}


def _pdf_fonts():
    """Register Inter (bundled TTFs, SIL OFL) once; fall back to Helvetica."""
    if _PDF_FONTS:
        return _PDF_FONTS
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    names = {'reg': 'Helvetica', 'med': 'Helvetica', 'semi': 'Helvetica-Bold', 'bold': 'Helvetica-Bold'}
    try:
        for key, fname in (('reg', 'Inter-Regular'), ('med', 'Inter-Medium'),
                           ('semi', 'Inter-SemiBold'), ('bold', 'Inter-Bold')):
            path = os.path.join(_FONT_DIR, fname + '.ttf')
            if fname not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(fname, path))
            names[key] = fname
        pdfmetrics.registerFontFamily('Inter', normal='Inter-Regular', bold='Inter-Bold',
                                      italic='Inter-Regular', boldItalic='Inter-Bold')
    except Exception:
        names = {'reg': 'Helvetica', 'med': 'Helvetica', 'semi': 'Helvetica-Bold', 'bold': 'Helvetica-Bold'}
    _PDF_FONTS.update(names)
    return _PDF_FONTS


_P = {  # palette
    'ink': '#0B1220', 'body': '#3D4659', 'muted': '#7A8399', 'faint': '#C9CFDB', 'line': '#E8EBF2',
    'soft': '#F5F6FB', 'ac': '#5B4FF5', 'ac_soft': '#EDE9FE',
    'good': '#0F9F6E', 'good_bg': '#E7F8F1', 'ok': '#C77D05', 'ok_bg': '#FFF4DD',
    'weak': '#E5484D', 'weak_bg': '#FFECED', 'warn': '#B45309',
    'grad': ['#3B2FD9', '#6D4CF2', '#A35CF0'],
    'groups': ['#4338CA', '#818CF8', '#C7D2FE', '#FB7185'],
}


def _tone(pct):
    return 'good' if pct >= 80 else ('ok' if pct >= 60 else 'weak')


def _band_groups(bands, pass_bands, band_label):
    """Fold the 9 grades / score bands into 4 readable groups: top 3, the rest
    of the passing bands, the other non-passing bands, and the lowest band."""
    top = list(bands[:3])
    passing = [b for b in bands[3:] if b in pass_bands]
    lowest = [bands[-1]] if len(bands) > 3 and bands[-1] not in top + passing else []
    other = [b for b in bands if b not in top + passing + lowest]
    raw = [top, passing, other, lowest]
    if band_label == 'Grade':
        names = ['Distinction', 'Credit', 'Pass', 'Fail']
    else:
        def rng(g):
            try:
                return f"{g[-1].split('-')[0]}–{g[0].split('-')[1]}"
            except Exception:
                return g[0] if len(g) == 1 else f'{g[-1]}–{g[0]}'
        names = [rng(g) if g else '' for g in raw]
    return [(n, g, _P['groups'][i]) for i, (n, g) in enumerate(zip(names, raw)) if g]


def _group_shares(pct, groups):
    return [round(sum(pct.get(b, 0) for b in g), 1) for _n, g, _c in groups]


def _insights(result, band_label):
    """Short, data-driven sentences for the 'Key takeaways' strip."""
    so = result.get('subject_overall') or {}
    word = 'credit' if band_label == 'Grade' else 'pass'
    subs = [s for s in result['subjects'] if (so.get(s) or {}).get('n', 0) >= 5]
    out = []
    if len(subs) > 1:
        weak = min(subs, key=lambda s: so[s]['pass_pct'])
        strong = max(subs, key=lambda s: so[s]['pass_pct'])
        out.append(('weak', '!', f'<b>{pdf_escape(weak)}</b> is the weakest subject at {so[weak]["pass_pct"]}% {word}.'))
        out.append(('good', '↑', f'<b>{pdf_escape(strong)}</b> is the strongest at {so[strong]["pass_pct"]}% {word}.'))
    gaps = []
    for s in result['subjects']:
        rows = [(br, c) for br, c in result['table'][s].items() if c and c['n'] >= 5]
        if len(rows) > 1:
            hi = max(rows, key=lambda x: x[1]['pass_pct']); lo = min(rows, key=lambda x: x[1]['pass_pct'])
            gaps.append((hi[1]['pass_pct'] - lo[1]['pass_pct'], s, hi[0], lo[0]))
    if gaps:
        g, s, hi, lo = max(gaps)
        if g >= 5:
            out.insert(1, ('ok', '↕', f'<b>{pdf_escape(s)}</b> has the widest branch gap — {g:.1f} pts '
                                           f'({pdf_escape(hi)} vs {pdf_escape(lo)}).'))
    below = [s for s in subs if so[s]['pass_pct'] < 70]
    if len(out) < 3 and subs:
        out.append(('weak' if below else 'good', str(len(below)),
                    f'<b>{len(below)} of {len(subs)}</b> subjects are below 70% {word}.'))
    return out[:3]


def grade_breakdown_pdf(meta, result, band_label, pass_label, _header_only=False):
    """Landscape A4 report: gradient hero with headline figures, branch ranking
    cards (credit ring, GPA, grade mix), key takeaways, then a subject table
    (tinted grade chips, grade-mix bar, credit pill) and the full branch
    ranking table with its criteria."""
    import os as _os
    from datetime import date
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
                                    Flowable, CondPageBreak, KeepTogether)
    from reportlab.pdfbase.pdfmetrics import stringWidth

    F = _pdf_fonts()
    C = colors.HexColor
    P = {k: (C(v) if isinstance(v, str) else v) for k, v in _P.items()}
    school_name = (meta.get('school_name') or _school_name() or '').strip()
    subtitle = (meta.get('subtitle') or '').strip()
    bands = result['bands']
    pass_set = set(result.get('pass_bands') or [])
    groups = _band_groups(bands, pass_set, band_label)
    so = result.get('subject_overall') or {}
    word = 'Credit' if band_label == 'Grade' else 'Pass'
    rc = result.get('ranking_criteria') or {}
    top3_label = (rc.get('top3_col') or '').replace(' %', '') or 'Top bands'
    if band_label != 'Grade' and len(bands) >= 3:
        try:
            top3_label = f"{bands[2].split('-')[0]}\u2013{bands[0].split('-')[1]}"
        except Exception:
            pass
    multi = len(result['branches']) > 1

    page = landscape(A4)
    side = 10 * mm
    avail = page[0] - 2 * side - 12   # frame keeps 6pt padding each side
    today = date.today().strftime('%d %b %Y')
    report_title = 'Subject-Wise Grade Breakdown'

    def fit(text, font, size, width):
        text = str(text)
        if stringWidth(text, font, size) <= width:
            return text
        while text and stringWidth(text + '…', font, size) > width:
            text = text[:-1]
        return text.rstrip() + '…'

    def fit_size(text, font, size, width, min_size):
        while size > min_size and stringWidth(str(text), font, size) > width:
            size -= 0.5
        return size

    def blend(hexc, a):
        r, g, b = (int(hexc.lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4))
        return colors.Color(1 - a * (1 - r), 1 - a * (1 - g), 1 - a * (1 - b))

    def ps(name, size=8, font=None, color=None, align=0, leading=None):
        return ParagraphStyle(name, fontName=font or F['reg'], fontSize=size, leading=leading or size * 1.35,
                              textColor=color or P['body'], alignment=align)

    # ------------------------------------------------------------------ flowables
    class Box(Flowable):
        def __init__(self, w, h, draw):
            super().__init__(); self.width, self.height, self._draw = w, h, draw

        def wrap(self, *_a):
            return self.width, self.height

        def draw(self):
            self._draw(self.canv, self.width, self.height)

    def rrect(c, x, y, w, h, r, fill=None, stroke=None, sw=0.6):
        c.saveState()
        if fill is not None:
            c.setFillColor(fill)
        if stroke is not None:
            c.setStrokeColor(stroke); c.setLineWidth(sw)
        c.roundRect(x, y, w, h, r, stroke=1 if stroke is not None else 0, fill=1 if fill is not None else 0)
        c.restoreState()

    def pill(c, x, y, text, fg, bg, size=6, font=None, padx=1.8 * mm, h=3.6 * mm):
        font = font or F['bold']
        w = stringWidth(text, font, size) + 2 * padx
        rrect(c, x, y, w, h, h / 2, fill=bg)
        c.setFillColor(fg); c.setFont(font, size)
        c.drawString(x + padx, y + (h - size * 0.72) / 2, text)
        return w

    def mix_bar(c, x, y, w, h, shares):
        c.saveState()
        p = c.beginPath(); p.roundRect(x, y, w, h, h / 2)
        c.clipPath(p, stroke=0, fill=0)
        c.setFillColor(P['soft']); c.rect(x, y, w, h, stroke=0, fill=1)
        cx = x
        for (_n, _g, col), v in zip(groups, shares):
            sw_ = w * v / 100
            if sw_ > 0:
                c.setFillColor(C(col)); c.rect(cx, y, sw_ + 0.2, h, stroke=0, fill=1)
            cx += sw_
        c.restoreState()

    def ring(c, cx, cy, r, pct, col, width):
        c.saveState()
        c.setLineWidth(width); c.setLineCap(1)
        c.setStrokeColor(C('#EEF0F6')); c.circle(cx, cy, r, stroke=1, fill=0)
        if pct > 0:
            c.setStrokeColor(col)
            ext = -min(pct, 99.9) * 3.6
            c.arc(cx - r, cy - r, cx + r, cy + r, 90, ext)
        c.restoreState()

    # ------------------------------------------------------------------ data
    O = result.get('overall') or {}
    ranking = result.get('ranking') or []
    ranked = [r for r in ranking if not r.get('small')]
    top = ranked[0] if ranked else (ranking[0] if ranking else None)
    subs5 = [s for s in result['subjects'] if (so.get(s) or {}).get('n', 0) >= 5]
    strong = max(subs5, key=lambda s: so[s]['pass_pct']) if len(subs5) > 1 else None
    weak = min(subs5, key=lambda s: so[s]['pass_pct']) if len(subs5) > 1 else None
    dist = round(sum((O.get('pct') or {}).get(b, 0) for b in bands[:3]), 1)

    # ------------------------------------------------------------------ hero
    logo = meta.get('logo_path')
    logo = logo if logo and _os.path.isfile(str(logo)) else None
    kpis = [('Credit pass' if band_label == 'Grade' else 'Pass rate', f"{O.get('pass_pct', 0)}%", f"{O.get('pass_n', 0)} of {O.get('n', 0)}"),
            (f'Top bands ({top3_label})', f'{dist}%', 'of all entries')]
    if top and multi:
        kpis.append(('Top branch', top['branch'], f"GPA {top['gpa']:.2f}"))
    elif top:
        kpis.append(('Weighted GPA', f"{top['gpa']:.2f}", f"{O.get('n', 0)} subject entries"))
    if strong:
        kpis.append(('Strongest subject', strong, f"{so[strong]['pass_pct']}% {word.lower()}"))
    if weak:
        kpis.append(('Needs attention', weak, f"{so[weak]['pass_pct']}% {word.lower()}"))

    def draw_hero(c, w, h):
        r = 5 * mm
        c.saveState()
        p = c.beginPath(); p.roundRect(0, 0, w, h, r)
        c.clipPath(p, stroke=0, fill=0)
        g = [C(x) for x in P['grad']]
        c.linearGradient(0, h, w, 0, g, positions=[0, 0.55, 1], extend=True)
        c.setFillColor(colors.white); c.setFillAlpha(0.07)
        c.circle(w - 18 * mm, h + 8 * mm, 52 * mm, stroke=0, fill=1)
        c.setFillAlpha(0.06); c.circle(w - 95 * mm, -34 * mm, 44 * mm, stroke=0, fill=1)
        c.restoreState()
        pad = 7 * mm
        top_y = h - pad
        # school tag pill
        tag = fit(school_name or 'Grade analysis', F['semi'], 7, 120 * mm)
        c.saveState(); c.setFillColor(colors.white); c.setFillAlpha(0.16)
        tw = stringWidth(tag, F['semi'], 7) + 7.5 * mm
        c.roundRect(pad, top_y - 4.6 * mm, tw, 4.6 * mm, 2.3 * mm, stroke=0, fill=1); c.restoreState()
        c.setFillColor(colors.white); c.circle(pad + 2.6 * mm, top_y - 2.3 * mm, 0.7 * mm, stroke=0, fill=1)
        c.setFont(F['semi'], 7); c.drawString(pad + 4.4 * mm, top_y - 3.2 * mm, tag)
        # title + subtitle
        c.setFont(F['bold'], 21); c.drawString(pad, top_y - 13.5 * mm, report_title)
        c.setFillColor(colors.Color(1, 1, 1, 0.82)); c.setFont(F['reg'], 9)
        sub = ' · '.join(x for x in (subtitle, f"{len(result['subjects'])} subject{'s' if len(result['subjects']) != 1 else ''} across "
                                                    f"{len(result['branches'])} branch{'es' if len(result['branches']) != 1 else ''}") if x)
        c.drawString(pad, top_y - 19 * mm, sub)
        # logo
        if logo:
            try:
                from reportlab.lib.utils import ImageReader
                ir = ImageReader(logo); iw, ih = ir.getSize()
                bh = 15 * mm; bw = bh
                rrect(c, w - pad - bw, h - pad - bh, bw, bh, 3 * mm, fill=colors.white)
                s_ = min((bw - 3 * mm) / iw, (bh - 3 * mm) / ih)
                c.drawImage(ir, w - pad - bw / 2 - iw * s_ / 2, h - pad - bh / 2 - ih * s_ / 2, iw * s_, ih * s_, mask='auto')
            except Exception:
                pass
        # KPI row
        n = len(kpis)
        x = pad
        colw = (w - 2 * pad) / n
        y_lab = 16.5 * mm
        for i, (lab, val, small) in enumerate(kpis):
            if i:
                c.saveState(); c.setStrokeColor(colors.white); c.setStrokeAlpha(0.18); c.setLineWidth(0.6)
                c.line(x - 4 * mm, 5 * mm, x - 4 * mm, y_lab + 2.5 * mm); c.restoreState()
            room = colw - 8 * mm
            c.setFillColor(colors.Color(1, 1, 1, 0.72)); c.setFont(F['semi'], 6.4)
            c.drawString(x, y_lab, fit(lab.upper(), F['semi'], 6.4, room))
            size = fit_size(val, F['bold'], 15, room, 10.5)
            c.setFillColor(colors.white); c.setFont(F['bold'], size)
            c.drawString(x, 9.6 * mm, fit(val, F['bold'], size, room))
            c.setFillColor(colors.Color(1, 1, 1, 0.72)); c.setFont(F['med'], 7)
            c.drawString(x, 5 * mm, fit(small, F['med'], 7, room))
            x += colw

    # ------------------------------------------------------------------ section heads
    def section(title, caption='', legend=False):
        def d(c, w, h):
            c.setFillColor(P['ink']); c.setFont(F['bold'], 12.5); c.drawString(0, 1.4 * mm, title)
            x = w
            c.setFont(F['reg'], 7.2)
            if caption:
                x -= stringWidth(caption, F['reg'], 7.2)
                c.setFillColor(P['muted']); c.drawString(x, 1.6 * mm, caption); x -= 5 * mm
            if legend:
                for name, _g, col in reversed(groups):
                    tw = stringWidth(name, F['med'], 7)
                    x -= tw; c.setFillColor(P['muted']); c.setFont(F['med'], 7); c.drawString(x, 1.6 * mm, name)
                    x -= 3.6 * mm; rrect(c, x, 1.4 * mm, 2.5 * mm, 2.5 * mm, 0.8 * mm, fill=C(col)); x -= 3.5 * mm
        return Box(avail, 7 * mm, d)

    # ------------------------------------------------------------------ ranking cards
    def card_grid():
        cards = ranking[:6]   # the full list is in the ranking table
        per = len(cards) if len(cards) <= 4 else 3
        rows_ = [cards[i:i + per] for i in range(0, len(cards), per)] or [[]]
        gap = 4 * mm
        cw = (avail - gap * (per - 1)) / per
        ch = 27 * mm
        h = len(rows_) * ch + (len(rows_) - 1) * gap

        def d(c, w, _h):
            for ri, row in enumerate(rows_):
                y = _h - (ri + 1) * ch - ri * gap
                for ci, r in enumerate(row):
                    x = ci * (cw + gap)
                    small = r.get('small')
                    first = r.get('rank') == 1
                    rrect(c, x, y, cw, ch, 3.5 * mm, fill=colors.white, stroke=P['ac'] if first else P['line'],
                          sw=1.1 if first else 0.6)
                    col = P['faint'] if small else P[_tone(r['pass_pct'])]
                    rr = 8.2 * mm
                    cx, cy = x + 4.5 * mm + rr, y + ch / 2
                    ring(c, cx, cy, rr, r['pass_pct'], col, 2.2 * mm)
                    c.setFillColor(P['ink']); c.setFont(F['bold'], 10.5)
                    c.drawCentredString(cx, cy - 0.2 * mm, f"{r['pass_pct']:.0f}%")
                    c.setFillColor(P['muted']); c.setFont(F['med'], 5.6)
                    c.drawCentredString(cx, cy - 3.6 * mm, word.lower())
                    tx = cx + rr + 5 * mm
                    tw = x + cw - tx - 4 * mm
                    badge = 'Not ranked' if small else f"#{r['rank']}"
                    bw_ = stringWidth(badge, F['bold'], 6.2) + 3.6 * mm
                    name = fit(r['branch'], F['bold'], 10.5, tw - bw_ - 2 * mm)
                    c.setFillColor(P['ink']); c.setFont(F['bold'], 10.5); c.drawString(tx, y + ch - 8 * mm, name)
                    bx = tx + stringWidth(name, F['bold'], 10.5) + 2 * mm
                    if small:
                        pill(c, bx, y + ch - 8.9 * mm, badge, P['warn'], P['ok_bg'], size=6.2)
                    else:
                        pill(c, bx, y + ch - 8.9 * mm, badge, colors.white if first else P['body'],
                             P['ac'] if first else P['soft'], size=6.2)
                    c.setFillColor(P['muted']); c.setFont(F['reg'], 7)
                    c.drawString(tx, y + ch - 12 * mm, f"{r['n']} subject entries"
                                 + (' · under 5, listed unranked' if small else ''))
                    sx = tx
                    for lab, val in (('GPA', f"{r['gpa']:.2f}"), (top3_label, f"{r['top3_pct']}%")):
                        c.setFillColor(P['muted']); c.setFont(F['semi'], 5.8); c.drawString(sx, y + 9.2 * mm, lab.upper())
                        c.setFillColor(P['ink']); c.setFont(F['bold'], 11); c.drawString(sx, y + 4.6 * mm, val)
                        sx += max(stringWidth(val, F['bold'], 11), stringWidth(lab.upper(), F['semi'], 5.8)) + 6 * mm
                    bar_x = sx + 1 * mm
                    if x + cw - 4 * mm - bar_x > 14 * mm:
                        sm_ = (result.get('summary') or {}).get(r['branch'])
                        if sm_:
                            mix_bar(c, bar_x, y + 5.6 * mm, x + cw - 4.5 * mm - bar_x, 2.2 * mm,
                                    _group_shares(sm_['pct'], groups))
                            c.setFillColor(P['muted']); c.setFont(F['semi'], 5.8)
                            c.drawString(bar_x, y + 9.2 * mm, 'GRADE MIX' if band_label == 'Grade' else 'SCORE MIX')
        return Box(avail, h, d)

    # ------------------------------------------------------------------ takeaways
    def takeaways(items):
        if not items:
            return None
        gap = 4 * mm
        n = len(items)
        cw = (avail - gap * (n - 1)) / n
        tstyle = ps('tk', 7.8, F['reg'], P['body'], leading=10.4)
        paras = [Paragraph(t.replace('<b>', f'<font name="{F["semi"]}" color="{_P["ink"]}">').replace('</b>', '</font>'), tstyle)
                 for _k, _i, t in items]
        hs = [p.wrap(cw - 16 * mm, 100)[1] for p in paras]
        ch = max(hs) + 7 * mm

        def d(c, w, h):
            for i, ((kind, icon, _t), para, ph) in enumerate(zip(items, paras, hs)):
                x = i * (cw + gap)
                rrect(c, x, 0, cw, h, 3 * mm, fill=P['soft'])
                bg, fg = P[kind + '_bg'], P[kind]
                rrect(c, x + 3.5 * mm, h / 2 - 3.2 * mm, 6.4 * mm, 6.4 * mm, 1.8 * mm, fill=bg)
                c.setFillColor(fg); c.setFont(F['bold'], 8.5); c.drawCentredString(x + 6.7 * mm, h / 2 - 1.3 * mm, icon)
                para.drawOn(c, x + 12.5 * mm, h / 2 - ph / 2)
        return Box(avail, ch, d)

    # ------------------------------------------------------------------ table cells
    class Cell(Flowable):
        def __init__(self, w, h, draw):
            super().__init__(); self.w_, self.h_, self._d = w, h, draw

        def wrap(self, aw, ah):
            self.aw = aw
            return aw, self.h_

        def draw(self):
            self._d(self.canv, self.aw, self.h_)

    CH = 4.4 * mm

    def chip(v):
        def d(c, w, h):
            if not v:
                c.setFillColor(P['faint']); c.setFont(F['reg'], 7.5); c.drawCentredString(w / 2, 1.3 * mm, '–'); return
            a = min(v, 100) / 100 * 0.40
            cw_ = min(w, 11.5 * mm)
            rrect(c, w / 2 - cw_ / 2, 0, cw_, h, 1.4 * mm, fill=blend(_P['ac'], max(a, 0.05)))
            txt = '<1%' if v < 1 else f'{v:.0f}%'
            c.setFillColor(C('#1E1B4B') if v >= 45 else P['body']); c.setFont(F['semi'] if v >= 45 else F['med'], 7.4)
            c.drawCentredString(w / 2, 1.35 * mm, txt)
        return Cell(None, CH, d)

    def cpill(v, bold=True):
        def d(c, w, h):
            t = _tone(v)
            txt = f'{v}%'
            pw = stringWidth(txt, F['bold'], 7.6) + 6.4 * mm
            x0 = w / 2 - pw / 2
            rrect(c, x0, 0, pw, h, h / 2, fill=P[t + '_bg'])
            c.setFillColor(P[t]); c.circle(x0 + 2.6 * mm, h / 2, 0.75 * mm, stroke=0, fill=1)
            c.setFont(F['bold'], 7.6); c.drawString(x0 + 4.2 * mm, 1.35 * mm, txt)
        return Cell(None, CH, d)

    def mixcell(pct):
        sh = _group_shares(pct, groups)
        return Cell(None, CH, lambda c, w, h: mix_bar(c, 1 * mm, h / 2 - 1.1 * mm, w - 2 * mm, 2.2 * mm, sh))

    def branchcell(name, best, note=None):
        def d(c, w, h):
            room = w - (12 * mm if best else 0)
            t = fit(name, F['med'] if not best else F['semi'], 7.9, room)
            c.setFillColor(P['ink'] if best else P['body']); c.setFont(F['semi'] if best else F['med'], 7.9)
            c.drawString(0, 1.35 * mm, t)
            if best:
                x = stringWidth(t, F['semi'], 7.9) + 1.6 * mm
                c.saveState()
                pw = stringWidth('BEST', F['bold'], 5.6) + 3 * mm
                p = c.beginPath(); p.roundRect(x, 0.55 * mm, pw, 3.3 * mm, 1.65 * mm)
                c.clipPath(p, stroke=0, fill=0)
                c.linearGradient(x, 0, x + pw, 0, [C(P['grad'][0]), C(P['grad'][2])], extend=True)
                c.restoreState()
                c.setFillColor(colors.white); c.setFont(F['bold'], 5.6); c.drawString(x + 1.5 * mm, 1.55 * mm, 'BEST')
        return Cell(None, CH, d)

    head = ps('th', 6.4, F['semi'], P['muted'], align=1)
    headl = ps('thl', 6.4, F['semi'], P['muted'])
    subj_st = ps('sj', 8.2, F['semi'], P['ink'], leading=10)
    note_st = ps('nt', 6.3, F['reg'], P['muted'], leading=8)
    num = ps('num', 7.9, F['med'], P['body'], align=1)

    def base_table_style():
        return [
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (-1, 0), P['soft']),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, P['line']),
            ('TOPPADDING', (0, 0), (-1, 0), 2.6 * mm), ('BOTTOMPADDING', (0, 0), (-1, 0), 2.6 * mm),
            ('TOPPADDING', (0, 1), (-1, -1), 1.3 * mm), ('BOTTOMPADDING', (0, 1), (-1, -1), 1.3 * mm),
            ('LEFTPADDING', (0, 0), (-1, -1), 1.2 * mm), ('RIGHTPADDING', (0, 0), (-1, -1), 1.2 * mm),
            ('LEFTPADDING', (0, 0), (0, -1), 4 * mm),
            ('BOX', (0, 0), (-1, -1), 0.6, P['line']),
            ('ROUNDEDCORNERS', [3.5 * mm, 3.5 * mm, 3.5 * mm, 3.5 * mm]),
        ]

    # ---- subject breakdown table
    mix_w, cr_w, n_w = 27 * mm, 22 * mm, 9 * mm
    subj_w = min(max(stringWidth(s, F['semi'], 8.2) for s in result['subjects']) + 9 * mm, 46 * mm) \
        if result['subjects'] else 30 * mm
    br_w = min(max(stringWidth(b, F['semi'], 7.9) for b in result['branches']) + 16 * mm, 50 * mm)
    band_w = (avail - subj_w - br_w - n_w - mix_w - cr_w) / len(bands)
    widths = [subj_w, br_w, n_w] + [band_w] * len(bands) + [mix_w, cr_w]
    data = [[Paragraph('SUBJECT', headl), Paragraph('BRANCH', headl), Paragraph('N', head)]
            + [Paragraph(pdf_escape(b), head) for b in bands]
            + [Paragraph('GRADE MIX' if band_label == 'Grade' else 'SCORE MIX', head),
               Paragraph(word.upper() + ' RATE', head)]]
    st = base_table_style()
    ri = 1
    for si, subj in enumerate(result['subjects']):
        offered = [(br, result['table'][subj][br]) for br in result['branches'] if result['table'][subj][br]]
        missing = [br for br in result['branches'] if not result['table'][subj][br]]
        if not offered:
            continue
        best = _best(result, subj)
        start = ri
        for bi, (br, c_) in enumerate(offered):
            if bi == 0:
                first = [Paragraph(pdf_escape(subj), subj_st)]
                if missing:
                    first.append(Paragraph('Not offered: ' + pdf_escape(', '.join(missing)), note_st))
            else:
                first = ''
            data.append([first, branchcell(br, br == best), Paragraph(str(c_['n']), num)]
                        + [chip(c_['pct'][b]) for b in bands] + [mixcell(c_['pct']), cpill(c_['pass_pct'])])
            if bi:
                st.append(('LINEABOVE', (1, ri), (-1, ri), 0.4, P['line']))
            ri += 1
        # No SPAN on the subject column: a spanned block can't split across
        # pages, and a subject offered by many branches must be able to.
        if len(offered) > 1 or missing:
            st.append(('VALIGN', (0, start), (0, ri - 1), 'TOP'))
            st.append(('TOPPADDING', (0, start), (0, start), 2 * mm))
        if start > 1:
            st.append(('LINEABOVE', (0, start), (-1, start), 0.7, C('#DCE0EA')))
    subj_table = Table(data, colWidths=widths, repeatRows=1)
    subj_table.setStyle(TableStyle(st))

    # ---- branch ranking table
    rank_table = None
    if ranking:
        summ = result.get('summary') or {}
        g_w = 20 * mm
        rw = [16 * mm, None, 16 * mm] + [g_w] * len(groups) + [34 * mm, 22 * mm, 24 * mm]
        rw[1] = avail - sum(x for x in rw if x)
        rdata = [[Paragraph('RANK', head), Paragraph('BRANCH', headl), Paragraph('ENTRIES', head)]
                 + [Paragraph(pdf_escape(n.upper()), head) for n, _g, _c in groups]
                 + [Paragraph('GRADE MIX' if band_label == 'Grade' else 'SCORE MIX', head),
                    Paragraph('WEIGHTED GPA', head),
                    Paragraph(word.upper() + ' RATE', head)]]
        rst = base_table_style()
        rst += [('TOPPADDING', (0, 1), (-1, -1), 2 * mm), ('BOTTOMPADDING', (0, 1), (-1, -1), 2 * mm)]

        def rank_badge(r):
            def d(c, w, h):
                small = r.get('small')
                first = r.get('rank') == 1
                cx = w / 2 - 1.5 * mm
                c.setFillColor(P['ac'] if first else (colors.white if small else P['soft']))
                c.circle(cx, h / 2, 2.9 * mm, stroke=0, fill=1)
                c.setFillColor(colors.white if first else (P['faint'] if small else P['ink']))
                c.setFont(F['bold'], 8); c.drawCentredString(cx, h / 2 - 1 * mm, str(r['rank']))
            return Cell(None, 6 * mm, d)

        def rank_name(r):
            def d(c, w, h):
                c.setFillColor(P['ink']); c.setFont(F['semi'], 8.6)
                if r.get('small'):
                    c.drawString(0, h / 2 + 0.3 * mm, fit(r['branch'], F['semi'], 8.6, w))
                    c.setFillColor(P['warn']); c.setFont(F['med'], 6.4)
                    c.drawString(0, h / 2 - 2.8 * mm, f'Not ranked · under {5} entries')
                else:
                    c.drawString(0, h / 2 - 1.1 * mm, fit(r['branch'], F['semi'], 8.6, w))
            return Cell(None, 6 * mm, d)

        for k, r in enumerate(ranking, 1):
            sm_ = summ.get(r['branch']) or {'pct': {b: 0 for b in bands}}
            shares = _group_shares(sm_['pct'], groups)
            rdata.append([rank_badge(r), rank_name(r), Paragraph(str(r['n']), num)]
                         + [Paragraph(f'{v}%' if v else f'<font color="{_P["faint"]}">\u2013</font>', num) for v in shares]
                         + [mixcell(sm_['pct']),
                            Paragraph(f'<font name="{F["bold"]}" color="{_P["ink"]}" size="9">{r["gpa"]:.2f}</font>', num),
                            cpill(r['pass_pct'])])
            if k > 1:
                rst.append(('LINEABOVE', (0, k), (-1, k), 0.4, P['line']))
            if r.get('rank') == 1:
                rst.append(('BACKGROUND', (0, k), (-1, k), C('#F7F5FF')))
        rank_table = Table(rdata, colWidths=rw, repeatRows=1)
        rank_table.setStyle(TableStyle(rst))

    # ------------------------------------------------------------------ assemble
    buf = io.BytesIO()

    def footer(c, _doc):
        c.saveState()
        c.setFont(F['reg'], 6.8); c.setFillColor(P['muted'])
        c.drawString(side + 6, 6.5 * mm, ' · '.join(x for x in (school_name, report_title, subtitle) if x))
        c.drawRightString(page[0] - side - 6, 6.5 * mm, f'Generated {today} · Page {c.getPageNumber()}')
        c.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=page, topMargin=11 * mm, bottomMargin=13 * mm,
                            leftMargin=side, rightMargin=side, title=report_title,
                            author=school_name or report_title)
    elems = [Box(avail, 49 * mm, draw_hero)]
    if ranking and multi:
        cap = f'ranked by weighted GPA · ring = {word.lower()} rate'
        if len(ranking) > 6:
            cap = f'top 6 of {len(ranking)} · full list in the ranking table · ' + cap
        elems += [Spacer(1, 5 * mm), section('Branch ranking', cap),
                  Spacer(1, 2.5 * mm), card_grid()]
    if _header_only:
        # Just the hero + ranking cards on a page cut to fit — rasterised for
        # the Word export, where gradients and rings can't be drawn natively.
        hh = sum(f.wrap(avail, 10000)[1] for f in elems) + 2
        doc = SimpleDocTemplate(buf, pagesize=(avail + 12, hh + 12), topMargin=0, bottomMargin=0,
                                leftMargin=0, rightMargin=0)
        doc.build(elems)
        return buf.getvalue()
    tk = takeaways(_insights(result, band_label))
    if tk:
        elems += [Spacer(1, 5 * mm), section('Key takeaways'), Spacer(1, 2.5 * mm), tk]
    elems += [Spacer(1, 6 * mm), CondPageBreak(55 * mm),
              section('Subject breakdown', '· darker cell = larger share', legend=True),
              Spacer(1, 2.5 * mm), subj_table]
    nst = ps('fn', 6.9, F['reg'], P['muted'], leading=10)
    notes = [Paragraph(f'<font name="{F["bold"]}" color="{_P["ac"]}">BEST</font> &nbsp;highest {word.lower()} rate for '
                       f'the subject; if tied, better {band_label.lower()}s; branches with fewer than 5 entries can’t '
                       f'be best unless all are that small. Branches that don’t offer a subject are listed under it.', nst)]
    for _s, _n in top_notes(result):
        notes.append(Paragraph(f'<font name="{F["semi"]}" color="{_P["warn"]}">{pdf_escape(_s)}</font> — '
                               f'{pdf_escape(_n)}; fewer than 5 entries, so not ranked best.', nst))
    elems += [Spacer(1, 2.5 * mm)] + notes
    if rank_table is not None:
        bullets = [Paragraph(f'<font name="{F["semi"]}" color="{_P["ink"]}">How the ranking works</font>',
                             ps('ch', 8, F['reg'], P['body']))]
        bullets += [Paragraph('•&nbsp; ' + pdf_escape(b), ps('cb%d' % i, 7.2, F['reg'], P['body'], leading=10.2))
                    for i, b in enumerate(rc.get('bullets') or [])]
        crit = Table([[b] for b in bullets], colWidths=[avail])
        crit.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), P['soft']),
                                  ('ROUNDEDCORNERS', [3 * mm] * 4),
                                  ('LEFTPADDING', (0, 0), (-1, -1), 4.5 * mm), ('RIGHTPADDING', (0, 0), (-1, -1), 4.5 * mm),
                                  ('TOPPADDING', (0, 0), (-1, -1), 0.6 * mm), ('BOTTOMPADDING', (0, 0), (-1, -1), 0.6 * mm),
                                  ('TOPPADDING', (0, 0), (-1, 0), 3 * mm), ('BOTTOMPADDING', (0, -1), (-1, -1), 3 * mm)]))
        elems += [Spacer(1, 7 * mm), CondPageBreak(60 * mm),
                  section('Branch ranking & summary' if multi else 'Overall summary', f'all subjects combined · % of entries'),
                  Spacer(1, 2.5 * mm), rank_table, Spacer(1, 4 * mm), KeepTogether([crit])]
    doc.build(elems, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Word (.docx)
# --------------------------------------------------------------------------- #

def _mix_bar_png(shares, groups, w=300, h=26):
    """A rounded grade-mix bar as a small PNG (for the Word export)."""
    from PIL import Image, ImageDraw
    k = 4
    W, H = w * k, h * k
    img = Image.new('RGBA', (W, H), (255, 255, 255, 0))
    mask = Image.new('L', (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, H - 1], radius=H // 2, fill=255)
    bar = Image.new('RGBA', (W, H), _hex_rgb(_P['soft']) + (255,))
    d = ImageDraw.Draw(bar)
    x = 0
    for (_n, _g, col), v in zip(groups, shares):
        sw = W * v / 100
        if sw > 0:
            d.rectangle([x, 0, x + sw + 1, H], fill=_hex_rgb(col) + (255,))
        x += sw
    img.paste(bar, (0, 0), mask)
    img = img.resize((w, h), Image.LANCZOS)
    out = io.BytesIO(); img.save(out, 'PNG')
    return out.getvalue()


def _hex_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _header_png(meta, result, band_label, pass_label, zoom=3):
    import pymupdf as fitz
    pdf = grade_breakdown_pdf(meta, result, band_label, pass_label, _header_only=True)
    d = fitz.open(stream=pdf, filetype='pdf')
    return d[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes('png')


def grade_breakdown_docx(meta, result, band_label, pass_label):
    """Word version of the PDF design: the gradient header and ranking cards
    as one crisp picture (Word cells can't draw gradients or rings), then
    editable native tables styled the same way — tinted grade cells, grade-mix
    bars, coloured credit cells, the BEST tag and the ranking table."""
    import html as _html
    import re as _re
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
    from docx.oxml.ns import nsdecls, qn
    from docx.oxml import parse_xml
    from docx.enum.section import WD_ORIENT

    FONT = 'Segoe UI'
    school_name = (meta.get('school_name') or _school_name() or '').strip()
    subtitle = (meta.get('subtitle') or '').strip()
    bands = result['bands']
    groups = _band_groups(bands, set(result.get('pass_bands') or []), band_label)
    word = 'Credit' if band_label == 'Grade' else 'Pass'
    mix_word = 'GRADE MIX' if band_label == 'Grade' else 'SCORE MIX'
    multi = len(result['branches']) > 1
    rgb = lambda h: RGBColor(*_hex_rgb(h))

    doc = Document()
    st = doc.styles['Normal']
    st.font.name = FONT; st.font.size = Pt(8.5); st.font.color.rgb = rgb(_P['body'])
    st.element.rPr.rFonts.set(qn('w:eastAsia'), FONT)
    st.paragraph_format.space_after = Pt(0)
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = sec.page_height, sec.page_width
    sec.left_margin = sec.right_margin = Cm(1.2)
    sec.top_margin = Cm(1.1); sec.bottom_margin = Cm(1.2)
    sec.footer_distance = Cm(0.6)
    avail_cm = sec.page_width.cm - sec.left_margin.cm - sec.right_margin.cm

    def shade(cell, hexcolor):
        cell._tc.get_or_add_tcPr().append(parse_xml(f'<w:shd {nsdecls("w")} w:val="clear" w:fill="{hexcolor.lstrip("#")}"/>'))

    def run(par, text, size=8.5, bold=False, color=None, shade_hex=None):
        r = par.add_run(text)
        r.font.size = Pt(size); r.bold = bold
        if color:
            r.font.color.rgb = rgb(color)
        if shade_hex:
            r._r.get_or_add_rPr().append(parse_xml(f'<w:shd {nsdecls("w")} w:val="clear" w:fill="{shade_hex.lstrip("#")}"/>'))
        return r

    def cell_text(cell, text, size=8.5, bold=False, color=None, align=WD_ALIGN_PARAGRAPH.CENTER):
        p = cell.paragraphs[0]; p.alignment = align
        run(p, str(text), size, bold, color)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        return p

    def table_look(t, cell_spacing=None, outer=True):
        tblPr = t._tbl.tblPr
        b = 'E8EBF2'
        edge = 'single' if outer else 'nil'
        tblPr.append(parse_xml(
            f'<w:tblBorders {nsdecls("w")}><w:top w:val="{edge}" w:sz="6" w:color="{b}"/><w:left w:val="{edge}" w:sz="6" w:color="{b}"/>'
            f'<w:bottom w:val="{edge}" w:sz="6" w:color="{b}"/><w:right w:val="{edge}" w:sz="6" w:color="{b}"/>'
            f'<w:insideH w:val="{"single" if outer else "nil"}" w:sz="4" w:color="{b}"/><w:insideV w:val="nil"/></w:tblBorders>'))
        tblPr.append(parse_xml(f'<w:tblCellMar {nsdecls("w")}><w:top w:w="70" w:type="dxa"/><w:left w:w="90" w:type="dxa"/>'
                               f'<w:bottom w:w="70" w:type="dxa"/><w:right w:w="90" w:type="dxa"/></w:tblCellMar>'))
        if cell_spacing:
            tblPr.append(parse_xml(f'<w:tblCellSpacing {nsdecls("w")} w:w="{cell_spacing}" w:type="dxa"/>'))
        t.alignment = WD_TABLE_ALIGNMENT.CENTER

    def widths(t, cms):
        """Fixed layout + grid widths (Word and LibreOffice both honour these)
        and rows that never split across a page."""
        t.autofit = False
        tblPr = t._tbl.tblPr
        tblPr.append(parse_xml(f'<w:tblLayout {nsdecls("w")} w:type="fixed"/>'))
        tw = [int(Cm(c).twips) for c in cms]
        for el in tblPr.findall(qn('w:tblW')):
            tblPr.remove(el)
        tblPr.append(parse_xml(f'<w:tblW {nsdecls("w")} w:w="{sum(tw)}" w:type="dxa"/>'))
        for gc, w in zip(t._tbl.tblGrid.findall(qn('w:gridCol')), tw):
            gc.set(qn('w:w'), str(w))
        for row in t.rows:
            row._tr.get_or_add_trPr().append(parse_xml(f'<w:cantSplit {nsdecls("w")}/>'))
            for i, c in enumerate(row.cells):
                if i < len(cms):
                    c.width = Cm(cms[i])

    def repeat_header(row):
        row._tr.get_or_add_trPr().append(parse_xml(f'<w:tblHeader {nsdecls("w")}/>'))

    def top_rule(row, color='DCE0EA', sz=10):
        for c in row.cells:
            c._tc.get_or_add_tcPr().append(parse_xml(
                f'<w:tcBorders {nsdecls("w")}><w:top w:val="single" w:sz="{sz}" w:color="{color}"/></w:tcBorders>'))

    def heading(title, caption=''):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(12); p.paragraph_format.space_after = Pt(5)
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.tab_stops.add_tab_stop(Cm(avail_cm), WD_TAB_ALIGNMENT.RIGHT)
        run(p, title, 13, True, _P['ink'])
        if caption:
            run(p, '\t' + caption, 7.5, False, _P['muted'])

    def rich(par, text, size=8.5, color=None):
        """Insights carry <b>…</b> and PDF escapes; turn them into runs."""
        for k, part in enumerate(_re.split(r'</?b>', text)):
            if part:
                run(par, _html.unescape(part), size, k % 2 == 1, _P['ink'] if k % 2 else color)

    # ---- header picture (hero + ranking cards) -----------------------------
    try:
        doc.add_picture(io.BytesIO(_header_png(meta, result, band_label, pass_label)), width=Cm(avail_cm))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    except Exception:
        t = doc.add_table(rows=1, cols=1); table_look(t, outer=False)
        c = t.rows[0].cells[0]; shade(c, _P['ac'])
        p = c.paragraphs[0]
        run(p, (school_name + '\n') if school_name else '', 8, True, '#FFFFFF')
        run(p, 'Subject-Wise Grade Breakdown', 20, True, '#FFFFFF')
        if subtitle:
            run(p, '\n' + subtitle, 9, False, '#FFFFFF')

    # ---- key takeaways ------------------------------------------------------
    items = _insights(result, band_label)
    if items:
        heading('Key takeaways')
        t = doc.add_table(rows=1, cols=len(items)); table_look(t, outer=False)
        for k, (c, (kind, icon, text)) in enumerate(zip(t.rows[0].cells, items)):
            shade(c, _P['soft'])
            if k:   # a white gutter between the cards
                c._tc.get_or_add_tcPr().append(parse_xml(
                    f'<w:tcBorders {nsdecls("w")}><w:left w:val="single" w:sz="48" w:color="FFFFFF"/></w:tcBorders>'))
            c.paragraphs[0].paragraph_format.space_before = Pt(4)
            c.paragraphs[0].paragraph_format.space_after = Pt(4)
            p = c.paragraphs[0]
            run(p, f' {icon} ', 9, True, _P[kind], shade_hex=_P[kind + '_bg'])
            run(p, '  ')
            rich(p, text, 8.5, _P['body'])
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        widths(t, [avail_cm / len(items)] * len(items))

    # ---- subject breakdown -------------------------------------------------
    heading('Subject breakdown', ' · '.join(n for n, _g, _c in groups) + ' · darker cell = larger share')
    mix_cm, cr_cm, n_cm, subj_cm, br_cm = 2.7, 2.3, 1.0, 3.9, 4.6
    band_cm = (avail_cm - mix_cm - cr_cm - n_cm - subj_cm - br_cm) / len(bands)
    cols = [subj_cm, br_cm, n_cm] + [band_cm] * len(bands) + [mix_cm, cr_cm]
    t = doc.add_table(rows=1, cols=len(cols)); table_look(t)
    hdr = ['SUBJECT', 'BRANCH', 'N'] + list(bands) + [mix_word, word.upper() + ' RATE']
    for i, (c, h) in enumerate(zip(t.rows[0].cells, hdr)):
        shade(c, _P['soft'])
        cell_text(c, h, 7, True, _P['muted'], WD_ALIGN_PARAGRAPH.LEFT if i < 2 else WD_ALIGN_PARAGRAPH.CENTER)
    repeat_header(t.rows[0])
    for subj in result['subjects']:
        offered = [(br, result['table'][subj][br]) for br in result['branches'] if result['table'][subj][br]]
        missing = [br for br in result['branches'] if not result['table'][subj][br]]
        if not offered:
            continue
        best = _best(result, subj)
        first_row = None
        for bi, (br, c_) in enumerate(offered):
            row = t.add_row(); cells = row.cells
            if bi == 0:
                first_row = row
                top_rule(row)
                p = cell_text(cells[0], subj, 9, True, _P['ink'], WD_ALIGN_PARAGRAPH.LEFT)
                if missing:
                    p2 = cells[0].add_paragraph()
                    run(p2, 'Not offered: ' + ', '.join(missing), 6.5, False, _P['muted'])
                cells[0].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
            p = cell_text(cells[1], br, 8.5, br == best, _P['ink'] if br == best else _P['body'], WD_ALIGN_PARAGRAPH.LEFT)
            if br == best:
                run(p, ' ')
                run(p, ' BEST ', 6, True, '#FFFFFF', shade_hex=_P['ac'])
            cell_text(cells[2], c_['n'])
            for bx, b in enumerate(bands):
                v = c_['pct'][b]
                cc = cells[3 + bx]
                if not v:
                    cell_text(cc, '–', 8, False, _P['faint'])
                    continue
                r_, g_, b_ = _hex_rgb(_P['ac'])
                a = max(min(v, 100) / 100 * 0.40, 0.05)
                shade(cc, '%02X%02X%02X' % tuple(round(255 - a * (255 - x)) for x in (r_, g_, b_)))
                cell_text(cc, '<1%' if v < 1 else f'{v:.0f}%', 8, v >= 45, '#1E1B4B' if v >= 45 else _P['body'])
            pm = cells[-2].paragraphs[0]; pm.alignment = WD_ALIGN_PARAGRAPH.CENTER
            pm.add_run().add_picture(io.BytesIO(_mix_bar_png(_group_shares(c_['pct'], groups), groups)), width=Cm(2.3))
            cells[-2].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tone = _tone(c_['pass_pct'])
            shade(cells[-1], _P[tone + '_bg'])
            cell_text(cells[-1], f"● {c_['pass_pct']}%", 8.5, True, _P[tone])
        if len(offered) > 1:
            first_row.cells[0].merge(t.rows[-1].cells[0])
    widths(t, cols)

    note = doc.add_paragraph(); note.paragraph_format.space_before = Pt(5)
    run(note, 'BEST  ', 7.5, True, _P['ac'])
    run(note, f'highest {word.lower()} rate for the subject; if tied, better {band_label.lower()}s; branches with fewer '
              f'than 5 entries can’t be best unless all are that small. Branches that don’t offer a subject '
              f'are listed under it.', 7.5, False, _P['muted'])
    for _s, _n in top_notes(result):
        p = doc.add_paragraph()
        run(p, _s, 7.5, True, _P['warn'])
        run(p, f' — {_n}; fewer than 5 entries, so not ranked best.', 7.5, False, _P['muted'])

    # ---- branch ranking & summary -----------------------------------------
    ranking = result.get('ranking') or []
    if ranking:
        summ = result.get('summary') or {}
        heading('Branch ranking & summary' if multi else 'Overall summary', 'all subjects combined · % of entries')
        g_cm = 2.1
        rcols = [1.5, None, 1.7] + [g_cm] * len(groups) + [3.2, 2.4, 2.4]
        rcols[1] = avail_cm - sum(x for x in rcols if x)
        t = doc.add_table(rows=1, cols=len(rcols)); table_look(t)
        hdr = ['RANK', 'BRANCH', 'ENTRIES'] + [n.upper() for n, _g, _c in groups] + [mix_word, 'WEIGHTED GPA', word.upper() + ' RATE']
        for i, (c, h) in enumerate(zip(t.rows[0].cells, hdr)):
            shade(c, _P['soft'])
            cell_text(c, h, 7, True, _P['muted'], WD_ALIGN_PARAGRAPH.LEFT if i == 1 else WD_ALIGN_PARAGRAPH.CENTER)
        repeat_header(t.rows[0])
        for r in ranking:
            row = t.add_row(); cells = row.cells
            small, first = r.get('small'), r.get('rank') == 1
            if first:
                for c in cells:
                    shade(c, '#F7F5FF')
            cell_text(cells[0], r['rank'], 11 if first else 9.5, True,
                      _P['ac'] if first else (_P['faint'] if small else _P['ink']))
            cell_text(cells[1], r['branch'], 9.5, True, _P['ink'], WD_ALIGN_PARAGRAPH.LEFT)
            if small:
                run(cells[1].add_paragraph(), 'Not ranked · under 5 entries', 6.8, False, _P['warn'])
            cell_text(cells[2], r['n'])
            sm_ = summ.get(r['branch']) or {'pct': {b: 0 for b in bands}}
            shares = _group_shares(sm_['pct'], groups)
            for k, v in enumerate(shares):
                cell_text(cells[3 + k], f'{v}%' if v else '–', 8.5, False, _P['body'] if v else _P['faint'])
            pm = cells[3 + len(groups)].paragraphs[0]; pm.alignment = WD_ALIGN_PARAGRAPH.CENTER
            pm.add_run().add_picture(io.BytesIO(_mix_bar_png(shares, groups)), width=Cm(2.8))
            cells[3 + len(groups)].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            cell_text(cells[-2], f"{r['gpa']:.2f}", 10, True, _P['ink'])
            tone = _tone(r['pass_pct'])
            shade(cells[-1], _P[tone + '_bg'])
            cell_text(cells[-1], f"● {r['pass_pct']}%", 8.5, True, _P[tone])
        widths(t, rcols)

        bullets = (result.get('ranking_criteria') or {}).get('bullets') or []
        if bullets:
            doc.add_paragraph().paragraph_format.space_after = Pt(4)
            t = doc.add_table(rows=1, cols=1); table_look(t, outer=False)
            c = t.rows[0].cells[0]; shade(c, _P['soft'])
            run(c.paragraphs[0], 'How the ranking works', 9, True, _P['ink'])
            for b in bullets:
                p = c.add_paragraph(); p.paragraph_format.space_before = Pt(2)
                run(p, '•  ' + b, 7.8, False, _P['body'])
            widths(t, [avail_cm])

    # ---- footer -------------------------------------------------------------
    doc.styles['Footer'].paragraph_format.tab_stops.clear_all()
    fp = sec.footer.paragraphs[0]
    fp.paragraph_format.tab_stops.add_tab_stop(Cm(avail_cm), WD_TAB_ALIGNMENT.RIGHT)
    run(fp, ' · '.join(x for x in (school_name, 'Subject-Wise Grade Breakdown', subtitle) if x), 7, False, _P['muted'])
    run(fp, '\tPage ', 7, False, _P['muted'])
    fld = parse_xml(f'<w:fldSimple {nsdecls("w")} w:instr="PAGE"><w:r><w:rPr><w:sz w:val="14"/>'
                    f'<w:color w:val="{_P["muted"].lstrip("#")}"/></w:rPr><w:t>1</w:t></w:r></w:fldSimple>')
    fp._p.append(fld)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Excel (.xlsx)
# --------------------------------------------------------------------------- #

def grade_breakdown_xlsx(meta, result, band_label, pass_label):
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = 'Grade Breakdown'
    navy_fill = PatternFill('solid', fgColor=NAVY_HEX.lstrip('#'))
    white_font = Font(bold=True, color='FFFFFF')
    ctr = Alignment(horizontal='center', vertical='center', wrap_text=True)
    left = Alignment(horizontal='left', vertical='center')
    school_name = (meta.get('school_name') or _school_name() or '').strip()
    bands = result['bands']

    def band_font(bx):
        fg = _text_on(band_rgb(bx, header=True))
        return Font(bold=True, color='%02X%02X%02X' % fg)

    r = 1
    if school_name:
        c0 = ws.cell(row=r, column=1, value=school_name.upper())
        c0.font = Font(bold=True, size=14, color='FFFFFF')
        c0.fill = navy_fill; c0.alignment = ctr
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3 + len(bands))
        r += 1
    c1 = ws.cell(row=r, column=1, value='Subject-Wise Performance & Grade Percentage Breakdown'.upper())
    c1.font = Font(bold=True, size=12, color='FFFFFF')
    c1.fill = navy_fill; c1.alignment = ctr
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3 + len(bands))
    r += 2

    headers = _main_headers(bands)
    hrow = r
    for i, label in enumerate(('Subject', 'Branch', 'Candidates (N)')):
        c = ws.cell(row=hrow, column=i + 1, value=label.upper())
        c.font = white_font; c.fill = navy_fill; c.alignment = ctr
        ws.merge_cells(start_row=hrow, start_column=i + 1, end_row=hrow + 1, end_column=i + 1)
    span_cell = ws.cell(row=hrow, column=4, value=f'{band_label} Percentage Breakdown'.upper())
    span_cell.font = white_font; span_cell.fill = navy_fill; span_cell.alignment = ctr
    ws.merge_cells(start_row=hrow, start_column=4, end_row=hrow, end_column=3 + len(bands))
    for bx, b in enumerate(bands):
        c = ws.cell(row=hrow + 1, column=4 + bx, value=f'{b} (%)')
        c.font = band_font(bx); c.fill = PatternFill('solid', fgColor=band_hex(bx, header=True).lstrip('#'))
        c.alignment = ctr
    r = hrow + 2
    data_start = r
    for subj in result['subjects']:
        branches = result['branches']
        subj_start = r
        for br in branches:
            cell_ = result['table'][subj][br]
            isb = cell_ is not None and br == _best(result, subj)
            bc = ws.cell(row=r, column=2, value=f'{STAR} {br}' if isb else br)
            bc.alignment = left
            if isb:
                bc.font = Font(bold=True, color='15803D')
            if cell_ is None:
                nc = ws.cell(row=r, column=3, value='Not Offered')
                nc.alignment = ctr
                nc.font = Font(italic=True, color='94A3B8')
                ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=3 + len(bands))
            else:
                ws.cell(row=r, column=3, value=cell_['n']).alignment = ctr
                for bx, b in enumerate(bands):
                    c_ = ws.cell(row=r, column=4 + bx, value=cell_['pct'][b] / 100)
                    c_.number_format = '0.0%'
                    c_.alignment = ctr
                    c_.fill = PatternFill('solid', fgColor=band_hex(bx).lstrip('#'))
            r += 1
        subj_cell = ws.cell(row=subj_start, column=1, value=subj)
        subj_cell.alignment = left
        if len(branches) > 1:
            ws.merge_cells(start_row=subj_start, start_column=1, end_row=r - 1, end_column=1)
    ws.cell(row=r + 1, column=1, value='— Not Offered').font = Font(italic=True, color='94A3B8', size=9)
    ws.cell(row=r + 2, column=1, value=best_legend(band_label)).font = Font(italic=True, color='15803D', size=9)
    for _k, (_s, _n) in enumerate(top_notes(result)):
        ws.cell(row=r + 3 + _k, column=1, value=f'{_s} — {_n}; fewer than 5 entries, so not ranked best.').font = \
            Font(italic=True, color='B45309', size=9)
    ws.freeze_panes = ws.cell(row=data_start, column=1)
    # Content-tight columns — Subject/Branch/N stay as narrow as their actual
    # text (no dead whitespace), matching the reference layout; band columns
    # get a touch more room since they carry a "xx.x%" value under a header.
    subj_w = min(max((len(s) for s in result['subjects']), default=8) + 2, 26)
    br_w = min(max((len(b) for b in result['branches']), default=8) + 2, 18)
    ws.column_dimensions['A'].width = max(subj_w, len('Subject') + 2)
    ws.column_dimensions['B'].width = max(br_w, len('Branch') + 2)
    ws.column_dimensions['C'].width = len('Candidates (N)') + 1
    for c in range(4, len(headers) + 1):
        ws.column_dimensions[get_column_letter(c)].width = max(len(str(headers[c - 1])), 8) + 1
    ws.row_dimensions[hrow].height = 26

    ws2 = wb.create_sheet('Summary')
    r2 = 1
    c2 = ws2.cell(row=r2, column=1, value=f'Overall {band_label} Percentage Summary by Branch'.upper())
    c2.font = Font(bold=True, size=13, color='FFFFFF')
    c2.fill = navy_fill; c2.alignment = ctr
    sum_headers = _summary_headers(bands, pass_label)
    ws2.merge_cells(start_row=r2, start_column=1, end_row=r2, end_column=len(sum_headers))
    r2 += 2
    hrow2 = r2
    for i, label in enumerate(('Branch', 'Total Subject Entries (N)')):
        c = ws2.cell(row=hrow2, column=i + 1, value=label.upper())
        c.font = white_font; c.fill = navy_fill; c.alignment = ctr
        ws2.merge_cells(start_row=hrow2, start_column=i + 1, end_row=hrow2 + 1, end_column=i + 1)
    span2 = ws2.cell(row=hrow2, column=3, value=f'{band_label} Percentage'.upper())
    span2.font = white_font; span2.fill = navy_fill; span2.alignment = ctr
    ws2.merge_cells(start_row=hrow2, start_column=3, end_row=hrow2, end_column=2 + len(bands))
    passc = ws2.cell(row=hrow2, column=3 + len(bands), value=pass_label.upper())
    passc.font = white_font; passc.fill = navy_fill; passc.alignment = ctr
    ws2.merge_cells(start_row=hrow2, start_column=3 + len(bands), end_row=hrow2 + 1, end_column=3 + len(bands))
    for bx, b in enumerate(bands):
        c = ws2.cell(row=hrow2 + 1, column=3 + bx, value=f'{b} (%)')
        c.font = band_font(bx); c.fill = PatternFill('solid', fgColor=band_hex(bx, header=True).lstrip('#'))
        c.alignment = ctr
    r2 = hrow2 + 2
    for br in result['branches']:
        s = result['summary'][br]
        ws2.cell(row=r2, column=1, value=br).alignment = left
        ws2.cell(row=r2, column=2, value=s['n']).alignment = ctr
        for bx, b in enumerate(bands):
            c_ = ws2.cell(row=r2, column=3 + bx, value=s['pct'][b] / 100)
            c_.number_format = '0.0%'
            c_.alignment = ctr
            c_.fill = PatternFill('solid', fgColor=band_hex(bx).lstrip('#'))
        last = ws2.cell(row=r2, column=3 + len(bands), value=f"{s['pass_pct']}% ({s['pass_n']})")
        last.alignment = ctr
        last.font = Font(bold=True)
        r2 += 1
    br_w2 = min(max((len(b) for b in result['branches']), default=8) + 2, 18)
    ws2.column_dimensions['A'].width = max(br_w2, len('Branch') + 2)
    ws2.column_dimensions['B'].width = len('Total Subject Entries (N)') + 1
    for c in range(3, 2 + len(bands) + 1):
        ws2.column_dimensions[get_column_letter(c)].width = max(len(str(sum_headers[c - 1])), 8) + 1
    ws2.column_dimensions[get_column_letter(2 + len(bands) + 1)].width = len(pass_label) + 2
    ws2.row_dimensions[hrow2].height = 26

    # ---- Composite ranking: a second summary, by different criteria (a
    # weighted-GPA-style composite score) — its own sheet, own header. ----
    ranking = result.get('ranking')
    if ranking:
        rc = result['ranking_criteria']
        rank_headers = ['Rank', 'Branch', 'Total Entries (N)', 'Weighted GPA', rc['top3_col'], rc['pass_col']]
        ws3 = wb.create_sheet('Branch Ranking')
        crit_fill = PatternFill('solid', fgColor='F8FAFC')
        wrap_left = Alignment(horizontal='left', vertical='center', wrap_text=True)

        r3 = 1
        c3 = ws3.cell(row=r3, column=1, value=result['ranking_title'].upper())
        c3.font = Font(bold=True, size=13, color='FFFFFF')
        c3.fill = navy_fill; c3.alignment = ctr
        ws3.merge_cells(start_row=r3, start_column=1, end_row=r3, end_column=len(rank_headers))
        r3 += 2

        title_c = ws3.cell(row=r3, column=1, value='CRITERIA & WEIGHTING SYSTEM')
        title_c.font = Font(bold=True, size=9, color='64748B'); title_c.fill = crit_fill; title_c.alignment = left
        ws3.merge_cells(start_row=r3, start_column=1, end_row=r3, end_column=len(rank_headers))
        r3 += 1
        for b in rc['bullets']:
            bc = ws3.cell(row=r3, column=1, value='• ' + b)
            bc.font = Font(size=10, color='334155'); bc.fill = crit_fill; bc.alignment = wrap_left
            ws3.merge_cells(start_row=r3, start_column=1, end_row=r3, end_column=len(rank_headers))
            ws3.row_dimensions[r3].height = 24
            r3 += 1
        r3 += 1

        hrow3 = r3
        for i, label in enumerate(rank_headers):
            c = ws3.cell(row=hrow3, column=i + 1, value=label.upper())
            c.font = white_font; c.fill = navy_fill; c.alignment = ctr
        r3 = hrow3 + 1
        for rk in ranking:
            ws3.cell(row=r3, column=1, value=rk['rank']).alignment = ctr
            ws3.cell(row=r3, column=2, value=rk['branch']).alignment = left
            ws3.cell(row=r3, column=3, value=rk['n']).alignment = ctr
            gpa_c = ws3.cell(row=r3, column=4, value=rk['gpa']); gpa_c.alignment = ctr; gpa_c.font = Font(bold=True)
            top3_c = ws3.cell(row=r3, column=5, value=rk['top3_pct'] / 100)
            top3_c.number_format = '0.0%'; top3_c.alignment = ctr
            pass_c = ws3.cell(row=r3, column=6, value=rk['pass_pct'] / 100)
            pass_c.number_format = '0.0%'; pass_c.alignment = ctr
            r3 += 1

        ws3.column_dimensions['A'].width = len('Rank') + 4
        ws3.column_dimensions['B'].width = max((len(rk['branch']) for rk in ranking), default=8) + 4
        ws3.column_dimensions['C'].width = len('Total Entries (N)') + 2
        ws3.column_dimensions['D'].width = len('Weighted GPA') + 2
        ws3.column_dimensions['E'].width = max(len(rank_headers[4]), 10) + 2
        ws3.column_dimensions['F'].width = max(len(rank_headers[5]), 10) + 2
        ws3.row_dimensions[hrow3].height = 26

    return wb


# --------------------------------------------------------------------------- #
# HD PNG (the PDF rasterised with PyMuPDF) — bundled into a zip when >1 page
# --------------------------------------------------------------------------- #

def grade_breakdown_png_pages(meta, result, band_label, pass_label, zoom=2.5):
    """HD PNG pages — the PDF design rasterised page by page, so the image
    export always matches the PDF exactly."""
    import pymupdf as fitz
    pdf = grade_breakdown_pdf(meta, result, band_label, pass_label)
    d = fitz.open(stream=pdf, filetype='pdf')
    return [p.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes('png') for p in d]


def grade_breakdown_image_export(meta, result, band_label, pass_label):
    """Returns (bytes, mimetype, ext) — a single HD PNG, or a zip of pages."""
    pages = grade_breakdown_png_pages(meta, result, band_label, pass_label)
    if len(pages) == 1:
        return pages[0], 'image/png', 'png'
    return zip_pngs(pages, base='grade_breakdown'), 'application/zip', 'zip'
