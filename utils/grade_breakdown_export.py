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


# ---- export options (the Export dialog on the page) -------------------------
GB_SECTIONS = [('hero', 'Header & headline figures'), ('cards', 'Branch ranking cards'),
               ('takeaways', 'Key takeaways'), ('subjects', 'Subject breakdown table'),
               ('notes', 'Notes under the table'), ('ranking', 'Branch ranking & summary table'),
               ('criteria', 'How the ranking works')]
GB_COLUMNS = [('n', 'Entries (N)', True), ('grades', 'Each grade (A1 \u2013 F9)', True),
              ('groups', 'Grade groups (Distinction, Credit, Pass, Fail)', False),
              ('mix', 'Grade-mix bar', True), ('rate', 'Credit rate', True)]
GB_SIZES = {'s': 1.0, 'm': 1.2, 'l': 1.42}   # table text scale; 's' = the previous size


def gb_options(size=None, sections=None, cols=None):
    """Normalise the Export dialog's choices. ``sections``/``cols`` are
    iterables of keys (None = defaults: every section, default columns)."""
    size = size if size in GB_SIZES else 'm'
    secs = {k for k, _l in GB_SECTIONS} if sections is None else {k for k in sections if k in dict(GB_SECTIONS)}
    cols = {k for k, _l, on in GB_COLUMNS if on} if cols is None else {k for k in cols if k in {c[0] for c in GB_COLUMNS}}
    return {'size': size, 'k': GB_SIZES[size], 'sections': secs, 'cols': cols}


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


def grade_breakdown_pdf(meta, result, band_label, pass_label, _header_only=False, opts=None):
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
    o = opts or gb_options()
    k = o['k']; secs = o['sections']; cols = o['cols']
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

    CH = 4.4 * mm * k
    BL = 1.35 * mm * k          # text baseline inside a cell

    def chip(v):
        def d(c, w, h):
            if not v:
                c.setFillColor(P['faint']); c.setFont(F['reg'], 7.5 * k); c.drawCentredString(w / 2, BL, '–'); return
            a = min(v, 100) / 100 * 0.40
            cw_ = min(w, 11.5 * mm * k)
            rrect(c, w / 2 - cw_ / 2, 0, cw_, h, 1.4 * mm * k, fill=blend(_P['ac'], max(a, 0.05)))
            txt = '<1%' if v < 1 else f'{v:.0f}%'
            fnt = F['semi'] if v >= 45 else F['med']
            fs_ = 7.4 * k
            while fs_ > 6 and stringWidth(txt, fnt, fs_) > cw_ - 1.2 * mm:   # never spill out of the chip
                fs_ -= 0.25
            c.setFillColor(C('#1E1B4B') if v >= 45 else P['body']); c.setFont(fnt, fs_)
            c.drawCentredString(w / 2, BL, txt)
        return Cell(None, CH, d)

    def cpill(v, bold=True):
        def d(c, w, h):
            t = _tone(v)
            txt = f'{v}%'
            fs_ = 7.6 * k
            pw = min(stringWidth(txt, F['bold'], fs_) + 6.4 * mm * k, w)
            x0 = w / 2 - pw / 2
            rrect(c, x0, 0, pw, h, h / 2, fill=P[t + '_bg'])
            c.setFillColor(P[t]); c.circle(x0 + 2.6 * mm * k, h / 2, 0.75 * mm * k, stroke=0, fill=1)
            c.setFont(F['bold'], fs_); c.drawString(x0 + 4.2 * mm * k, BL, txt)
        return Cell(None, CH, d)

    def pctcell(v):
        return Paragraph(f'{v}%' if v else f'<font color="{_P["faint"]}">–</font>', num)

    def mixcell(pct):
        sh = _group_shares(pct, groups)
        return Cell(None, CH, lambda c, w, h: mix_bar(c, 1 * mm, h / 2 - 1.1 * mm * k, w - 2 * mm, 2.2 * mm * k, sh))

    def branchcell(name, best, note=None):
        fs_ = 7.9 * k
        def d(c, w, h):
            room = w - (12 * mm * k if best else 0)
            t = fit(name, F['med'] if not best else F['semi'], fs_, room)
            c.setFillColor(P['ink'] if best else P['body']); c.setFont(F['semi'] if best else F['med'], fs_)
            c.drawString(0, BL, t)
            if best:
                x = stringWidth(t, F['semi'], fs_) + 1.6 * mm
                c.saveState()
                pw = stringWidth('BEST', F['bold'], 5.6 * k) + 3 * mm * k
                p = c.beginPath(); p.roundRect(x, 0.55 * mm * k, pw, 3.3 * mm * k, 1.65 * mm * k)
                c.clipPath(p, stroke=0, fill=0)
                c.linearGradient(x, 0, x + pw, 0, [C(P['grad'][0]), C(P['grad'][2])], extend=True)
                c.restoreState()
                c.setFillColor(colors.white); c.setFont(F['bold'], 5.6 * k); c.drawString(x + 1.5 * mm * k, 1.55 * mm * k, 'BEST')
        return Cell(None, CH, d)

    hk = min(k, 1.25)            # headers grow a little less than the body
    head = ps('th', 6.4 * hk, F['semi'], P['muted'], align=1)
    headl = ps('thl', 6.4 * hk, F['semi'], P['muted'])
    subj_st = ps('sj', 8.2 * k, F['semi'], P['ink'], leading=10 * k)
    note_st = ps('nt', 6.3 * k, F['reg'], P['muted'], leading=8 * k)
    num = ps('num', 7.9 * k, F['med'], P['body'], align=1)
    mix_label = 'GRADE MIX' if band_label == 'Grade' else 'SCORE MIX'

    def base_table_style():
        return [
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (-1, 0), P['soft']),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, P['line']),
            ('TOPPADDING', (0, 0), (-1, 0), 2.6 * mm), ('BOTTOMPADDING', (0, 0), (-1, 0), 2.6 * mm),
            ('TOPPADDING', (0, 1), (-1, -1), 1.3 * mm * k), ('BOTTOMPADDING', (0, 1), (-1, -1), 1.3 * mm * k),
            ('LEFTPADDING', (0, 0), (-1, -1), 1.2 * mm), ('RIGHTPADDING', (0, 0), (-1, -1), 1.2 * mm),
            ('LEFTPADDING', (0, 0), (0, -1), 4 * mm),
            ('BOX', (0, 0), (-1, -1), 0.6, P['line']),
            ('ROUNDEDCORNERS', [3.5 * mm, 3.5 * mm, 3.5 * mm, 3.5 * mm]),
        ]

    # ---- subject breakdown table (columns per the Export dialog) --------------
    show_n, show_grades, show_groups = 'n' in cols, 'grades' in cols, 'groups' in cols
    show_mix, show_rate = 'mix' in cols, 'rate' in cols
    subj_w = min(max(stringWidth(s_, F['semi'], 8.2 * k) for s_ in result['subjects']) + 9 * mm, 46 * mm) \
        if result['subjects'] else 30 * mm
    br_w = min(max(stringWidth(b, F['semi'], 7.9 * k) for b in result['branches']) + 16 * mm * k, 58 * mm)
    n_w, mix_w, cr_w, g_w = 9 * mm * k, (27 if k < 1.3 else 20) * mm, 22 * mm * k, 18 * mm * k
    fixed = subj_w + br_w + (n_w if show_n else 0) + (mix_w if show_mix else 0) + (cr_w if show_rate else 0) \
        + (g_w * len(groups) if show_groups else 0)
    spare = max(avail - fixed, 0)
    band_w = spare / len(bands) if show_grades else 0
    if not show_grades:          # hand the room to the next-best columns
        if show_groups:
            g_w += spare / len(groups)
        elif show_mix:
            mix_w += spare
        else:
            br_w += spare
    widths = [subj_w, br_w] + ([n_w] if show_n else []) + ([band_w] * len(bands) if show_grades else []) \
        + ([g_w] * len(groups) if show_groups else []) + ([mix_w] if show_mix else []) + ([cr_w] if show_rate else [])
    hdr = [Paragraph('SUBJECT', headl), Paragraph('BRANCH', headl)] + ([Paragraph('N', head)] if show_n else []) \
        + ([Paragraph(pdf_escape(b), head) for b in bands] if show_grades else []) \
        + ([Paragraph(pdf_escape(n.upper()), head) for n, _g, _c in groups] if show_groups else []) \
        + ([Paragraph(mix_label, head)] if show_mix else []) + ([Paragraph(word.upper() + ' RATE', head)] if show_rate else [])
    data = [hdr]
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
            row = [first, branchcell(br, br == best)]
            if show_n:
                row.append(Paragraph(str(c_['n']), num))
            if show_grades:
                row += [chip(c_['pct'][b]) for b in bands]
            if show_groups:
                row += [pctcell(v) for v in _group_shares(c_['pct'], groups)]
            if show_mix:
                row.append(mixcell(c_['pct']))
            if show_rate:
                row.append(cpill(c_['pass_pct']))
            data.append(row)
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
        RH = 6 * mm * k
        rw = [16 * mm, None, 16 * mm * k] + [20 * mm * k] * len(groups) + ([34 * mm] if show_mix else []) \
            + [22 * mm * k] + ([24 * mm * k] if show_rate else [])
        rw[1] = avail - sum(x for x in rw if x)
        rdata = [[Paragraph('RANK', head), Paragraph('BRANCH', headl), Paragraph('ENTRIES', head)]
                 + [Paragraph(pdf_escape(n.upper()), head) for n, _g, _c in groups]
                 + ([Paragraph(mix_label, head)] if show_mix else [])
                 + [Paragraph('WEIGHTED GPA', head)]
                 + ([Paragraph(word.upper() + ' RATE', head)] if show_rate else [])]
        rst = base_table_style()
        rst += [('TOPPADDING', (0, 1), (-1, -1), 2 * mm * k), ('BOTTOMPADDING', (0, 1), (-1, -1), 2 * mm * k)]

        def rank_badge(r):
            def d(c, w, h):
                small = r.get('small')
                first = r.get('rank') == 1
                cx = w / 2 - 1.5 * mm
                c.setFillColor(P['ac'] if first else (colors.white if small else P['soft']))
                c.circle(cx, h / 2, 2.9 * mm * k, stroke=0, fill=1)
                c.setFillColor(colors.white if first else (P['faint'] if small else P['ink']))
                c.setFont(F['bold'], 8 * k); c.drawCentredString(cx, h / 2 - 1 * mm * k, str(r['rank']))
            return Cell(None, RH, d)

        def rank_name(r):
            fs_ = 8.6 * k
            def d(c, w, h):
                c.setFillColor(P['ink']); c.setFont(F['semi'], fs_)
                if r.get('small'):
                    c.drawString(0, h / 2 + 0.3 * mm * k, fit(r['branch'], F['semi'], fs_, w))
                    c.setFillColor(P['warn']); c.setFont(F['med'], 6.4 * k)
                    c.drawString(0, h / 2 - 2.8 * mm * k, 'Not ranked · under 5 entries')
                else:
                    c.drawString(0, h / 2 - 1.1 * mm * k, fit(r['branch'], F['semi'], fs_, w))
            return Cell(None, RH, d)

        for kk, r in enumerate(ranking, 1):
            sm_ = summ.get(r['branch']) or {'pct': {b: 0 for b in bands}}
            row = [rank_badge(r), rank_name(r), Paragraph(str(r['n']), num)] \
                + [pctcell(v) for v in _group_shares(sm_['pct'], groups)]
            if show_mix:
                row.append(mixcell(sm_['pct']))
            row.append(Paragraph(f'<font name="{F["bold"]}" color="{_P["ink"]}" size="{9 * k:.1f}">{r["gpa"]:.2f}</font>', num))
            if show_rate:
                row.append(cpill(r['pass_pct']))
            rdata.append(row)
            if kk > 1:
                rst.append(('LINEABOVE', (0, kk), (-1, kk), 0.4, P['line']))
            if r.get('rank') == 1:
                rst.append(('BACKGROUND', (0, kk), (-1, kk), C('#F7F5FF')))
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

    def plain_title():
        """Used when the gradient header is left out: the report still needs a title."""
        def d(c, w, h):
            c.setFillColor(P['ac']); c.setFont(F['semi'], 8); c.drawString(0, h - 3 * mm, (school_name or '').upper())
            c.setFillColor(P['ink']); c.setFont(F['bold'], 16); c.drawString(0, h - 10.5 * mm, report_title)
            c.setFillColor(P['muted']); c.setFont(F['reg'], 8.5); c.drawString(0, 1 * mm, subtitle)
        return Box(avail, 17 * mm, d)

    doc = SimpleDocTemplate(buf, pagesize=page, topMargin=11 * mm, bottomMargin=13 * mm,
                            leftMargin=side, rightMargin=side, title=report_title,
                            author=school_name or report_title)
    elems = []
    if 'hero' in secs:
        elems.append(Box(avail, 49 * mm, draw_hero))
    elif not _header_only:
        elems.append(plain_title())
    if ranking and multi and 'cards' in secs:
        cap = f'ranked by weighted GPA · ring = {word.lower()} rate'
        if len(ranking) > 6:
            cap = f'top 6 of {len(ranking)} · full list in the ranking table · ' + cap
        elems += [Spacer(1, 5 * mm), section('Branch ranking', cap),
                  Spacer(1, 2.5 * mm), card_grid()]
    if _header_only:
        # Just the hero + ranking cards on a page cut to fit — rasterised for
        # the Word export, where gradients and rings can't be drawn natively.
        if not elems:
            return None
        hh = sum(f.wrap(avail, 10000)[1] for f in elems) + 2
        doc = SimpleDocTemplate(buf, pagesize=(avail + 12, hh + 12), topMargin=0, bottomMargin=0,
                                leftMargin=0, rightMargin=0)
        doc.build(elems)
        return buf.getvalue()
    tk = takeaways(_insights(result, band_label)) if 'takeaways' in secs else None
    if tk:
        elems += [Spacer(1, 5 * mm), section('Key takeaways'), Spacer(1, 2.5 * mm), tk]
    if 'subjects' in secs:
        elems += [Spacer(1, 6 * mm), CondPageBreak(55 * mm),
                  section('Subject breakdown', '· darker cell = larger share' if show_grades else '',
                          legend=show_mix or show_groups),
                  Spacer(1, 2.5 * mm), subj_table]
    if 'notes' in secs:
        nst = ps('fn', 6.9 * min(k, 1.2), F['reg'], P['muted'], leading=10 * min(k, 1.2))
        notes = [Paragraph(f'<font name="{F["bold"]}" color="{_P["ac"]}">BEST</font> &nbsp;highest {word.lower()} rate for '
                           f'the subject; if tied, better {band_label.lower()}s; branches with fewer than 5 entries can’t '
                           f'be best unless all are that small. Branches that don’t offer a subject are listed under it.', nst)]
        for _s, _n in top_notes(result):
            notes.append(Paragraph(f'<font name="{F["semi"]}" color="{_P["warn"]}">{pdf_escape(_s)}</font> — '
                                   f'{pdf_escape(_n)}; fewer than 5 entries, so not ranked best.', nst))
        elems += [Spacer(1, 2.5 * mm)] + notes
    if rank_table is not None and ('ranking' in secs or 'criteria' in secs):
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
        elems += [Spacer(1, 7 * mm), CondPageBreak(60 * mm)]
        if 'ranking' in secs:
            elems += [section('Branch ranking & summary' if multi else 'Overall summary', 'all subjects combined · % of entries'),
                      Spacer(1, 2.5 * mm), rank_table, Spacer(1, 4 * mm)]
        if 'criteria' in secs:
            elems.append(KeepTogether([crit]))
    if len(elems) == 1:          # everything switched off: say so rather than ship a blank page
        elems += [Spacer(1, 8 * mm), Paragraph('No sections were selected for this export.', ps('none', 10, F['med'], P['muted']))]
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


def _header_png(meta, result, band_label, pass_label, zoom=3, opts=None):
    import pymupdf as fitz
    pdf = grade_breakdown_pdf(meta, result, band_label, pass_label, _header_only=True, opts=opts)
    if not pdf:
        return None
    d = fitz.open(stream=pdf, filetype='pdf')
    return d[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes('png')


def grade_breakdown_docx(meta, result, band_label, pass_label, opts=None):
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

    o = opts or gb_options()
    k, secs, ocols = o['k'], o['sections'], o['cols']
    show_n, show_grades, show_groups = 'n' in ocols, 'grades' in ocols, 'groups' in ocols
    show_mix, show_rate = 'mix' in ocols, 'rate' in ocols
    T = lambda pt: round(pt * k * 2) / 2          # table text, scaled by the chosen size

    # ---- header picture (hero + ranking cards) -----------------------------
    pic = None
    if 'hero' in secs or ('cards' in secs and multi):
        try:
            pic = _header_png(meta, result, band_label, pass_label, opts=o)
        except Exception:
            pic = None
    if pic:
        doc.add_picture(io.BytesIO(pic), width=Cm(avail_cm))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    else:
        p = doc.paragraphs[0] if doc.paragraphs else doc.add_paragraph()
        if school_name:
            run(p, school_name.upper() + '\n', 8, True, _P['ac'])
        run(p, 'Subject-Wise Grade Breakdown', 18, True, _P['ink'])
        if subtitle:
            run(p, '\n' + subtitle, 9, False, _P['muted'])

    # ---- key takeaways ------------------------------------------------------
    items = _insights(result, band_label) if 'takeaways' in secs else []
    if items:
        heading('Key takeaways')
        t = doc.add_table(rows=1, cols=len(items)); table_look(t, outer=False)
        for i_, (c, (kind, icon, text)) in enumerate(zip(t.rows[0].cells, items)):
            shade(c, _P['soft'])
            if i_:   # a white gutter between the cards
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
    if 'subjects' in secs:
        heading('Subject breakdown', ' · '.join(n for n, _g, _c in groups)
                + (' · darker cell = larger share' if show_grades else ''))
        subj_cm, br_cm = 3.9 * min(k, 1.25), 4.6 * min(k, 1.25)
        n_cm, mix_cm, cr_cm, g_cm = 1.0 * k, 2.7, 2.3 * k, 2.0 * k
        fixed = subj_cm + br_cm + (n_cm if show_n else 0) + (mix_cm if show_mix else 0) \
            + (cr_cm if show_rate else 0) + (g_cm * len(groups) if show_groups else 0)
        spare = max(avail_cm - fixed, 0)
        band_cm = spare / len(bands) if show_grades else 0
        min_band = 0.42 + 0.66 * k        # room for "100%" at this size plus cell padding
        if show_grades and band_cm < min_band:
            need = (min_band - band_cm) * len(bands)
            if show_mix:
                take = min(need, mix_cm - 1.9); mix_cm -= take; need -= take
            for _ in range(2):            # then the subject/branch columns, which wrap gracefully
                if need <= 0:
                    break
                room = max(subj_cm - 2.8, 0) + max(br_cm - 3.0, 0)
                if room <= 0:
                    break
                cut = min(need, room)
                subj_cm -= cut * max(subj_cm - 2.8, 0) / room
                br_cm -= cut * max(br_cm - 3.0, 0) / room
                need -= cut
            band_cm = min_band - max(need, 0) / len(bands)
        if not show_grades:
            if show_groups:
                g_cm += spare / len(groups)
            elif show_mix:
                mix_cm += spare
            else:
                br_cm += spare
        cols = [subj_cm, br_cm] + ([n_cm] if show_n else []) + ([band_cm] * len(bands) if show_grades else []) \
            + ([g_cm] * len(groups) if show_groups else []) + ([mix_cm] if show_mix else []) + ([cr_cm] if show_rate else [])
        t = doc.add_table(rows=1, cols=len(cols)); table_look(t)
        hdr = ['SUBJECT', 'BRANCH'] + (['N'] if show_n else []) + (list(bands) if show_grades else []) \
            + ([n.upper() for n, _g, _c in groups] if show_groups else []) + ([mix_word] if show_mix else []) \
            + ([word.upper() + ' RATE'] if show_rate else [])
        for i, (c, h) in enumerate(zip(t.rows[0].cells, hdr)):
            shade(c, _P['soft'])
            cell_text(c, h, T(7) if k < 1.3 else 8.5, True, _P['muted'], WD_ALIGN_PARAGRAPH.LEFT if i < 2 else WD_ALIGN_PARAGRAPH.CENTER)
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
                    cell_text(cells[0], subj, T(9), True, _P['ink'], WD_ALIGN_PARAGRAPH.LEFT)
                    if missing:
                        run(cells[0].add_paragraph(), 'Not offered: ' + ', '.join(missing), T(6.5), False, _P['muted'])
                    cells[0].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
                p = cell_text(cells[1], br, T(8.5), br == best, _P['ink'] if br == best else _P['body'], WD_ALIGN_PARAGRAPH.LEFT)
                if br == best:
                    run(p, ' ')
                    run(p, ' BEST ', T(6), True, '#FFFFFF', shade_hex=_P['ac'])
                ci = 2
                if show_n:
                    cell_text(cells[ci], c_['n'], T(8.5)); ci += 1
                if show_grades:
                    for b in bands:
                        v = c_['pct'][b]
                        cc = cells[ci]; ci += 1
                        if not v:
                            cell_text(cc, '–', T(8), False, _P['faint'])
                            continue
                        r_, g_, b_ = _hex_rgb(_P['ac'])
                        a = max(min(v, 100) / 100 * 0.40, 0.05)
                        shade(cc, '%02X%02X%02X' % tuple(round(255 - a * (255 - x)) for x in (r_, g_, b_)))
                        cell_text(cc, '<1%' if v < 1 else f'{v:.0f}%', T(8), v >= 45, '#1E1B4B' if v >= 45 else _P['body'])
                if show_groups:
                    for v in _group_shares(c_['pct'], groups):
                        cell_text(cells[ci], f'{v}%' if v else '–', T(8.5), False, _P['body'] if v else _P['faint']); ci += 1
                if show_mix:
                    pm = cells[ci].paragraphs[0]; pm.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    pm.add_run().add_picture(io.BytesIO(_mix_bar_png(_group_shares(c_['pct'], groups), groups)),
                                             width=Cm(min(mix_cm - 0.4, 2.3 * k)))
                    cells[ci].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                    ci += 1
                if show_rate:
                    tone = _tone(c_['pass_pct'])
                    shade(cells[ci], _P[tone + '_bg'])
                    cell_text(cells[ci], f"● {c_['pass_pct']}%", T(8.5), True, _P[tone])
            if len(offered) > 1:
                first_row.cells[0].merge(t.rows[-1].cells[0])
        widths(t, cols)

    if 'notes' in secs:
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
    if ranking and 'ranking' in secs:
        summ = result.get('summary') or {}
        heading('Branch ranking & summary' if multi else 'Overall summary', 'all subjects combined · % of entries')
        rcols = [1.5, None, 1.7 * k] + [2.1 * k] * len(groups) + ([3.2] if show_mix else []) + [2.4 * k] \
            + ([2.4 * k] if show_rate else [])
        rcols[1] = avail_cm - sum(x for x in rcols if x)
        t = doc.add_table(rows=1, cols=len(rcols)); table_look(t)
        hdr = ['RANK', 'BRANCH', 'ENTRIES'] + [n.upper() for n, _g, _c in groups] + ([mix_word] if show_mix else []) \
            + ['WEIGHTED GPA'] + ([word.upper() + ' RATE'] if show_rate else [])
        for i, (c, h) in enumerate(zip(t.rows[0].cells, hdr)):
            shade(c, _P['soft'])
            cell_text(c, h, T(7) if k < 1.3 else 8.5, True, _P['muted'], WD_ALIGN_PARAGRAPH.LEFT if i == 1 else WD_ALIGN_PARAGRAPH.CENTER)
        repeat_header(t.rows[0])
        for r in ranking:
            row = t.add_row(); cells = row.cells
            small, first = r.get('small'), r.get('rank') == 1
            if first:
                for c in cells:
                    shade(c, '#F7F5FF')
            cell_text(cells[0], r['rank'], T(11 if first else 9.5), True,
                      _P['ac'] if first else (_P['faint'] if small else _P['ink']))
            cell_text(cells[1], r['branch'], T(9.5), True, _P['ink'], WD_ALIGN_PARAGRAPH.LEFT)
            if small:
                run(cells[1].add_paragraph(), 'Not ranked · under 5 entries', T(6.8), False, _P['warn'])
            cell_text(cells[2], r['n'], T(8.5))
            sm_ = summ.get(r['branch']) or {'pct': {b: 0 for b in bands}}
            shares = _group_shares(sm_['pct'], groups)
            ci = 3
            for v in shares:
                cell_text(cells[ci], f'{v}%' if v else '–', T(8.5), False, _P['body'] if v else _P['faint']); ci += 1
            if show_mix:
                pm = cells[ci].paragraphs[0]; pm.alignment = WD_ALIGN_PARAGRAPH.CENTER
                pm.add_run().add_picture(io.BytesIO(_mix_bar_png(shares, groups)), width=Cm(2.8))
                cells[ci].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                ci += 1
            cell_text(cells[ci], f"{r['gpa']:.2f}", T(10), True, _P['ink']); ci += 1
            if show_rate:
                tone = _tone(r['pass_pct'])
                shade(cells[ci], _P[tone + '_bg'])
                cell_text(cells[ci], f"● {r['pass_pct']}%", T(8.5), True, _P[tone])
        widths(t, rcols)

    bullets = (result.get('ranking_criteria') or {}).get('bullets') or []
    if ranking and bullets and 'criteria' in secs:
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

def grade_breakdown_xlsx(meta, result, band_label, pass_label, opts=None):
    """Excel in the PDF's design, keeping real numbers so it still sorts,
    filters and feeds formulas: an Overview sheet (the header picture, key
    takeaways, headline figures), then Grade Breakdown, Summary and Branch
    Ranking sheets with gradient title bars, tinted grade cells, coloured
    credit-rate cells, a BEST tag and data bars."""
    import html as _html
    import re as _re
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, GradientFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.formatting.rule import DataBarRule

    FONT = 'Segoe UI'
    school_name = (meta.get('school_name') or _school_name() or '').strip()
    subtitle = (meta.get('subtitle') or '').strip()
    bands = result['bands']
    groups = _band_groups(bands, set(result.get('pass_bands') or []), band_label)
    word = 'Credit' if band_label == 'Grade' else 'Pass'
    multi = len(result['branches']) > 1
    PCT = '0.0%;-0.0%;"–"'
    hx = lambda h: h.lstrip('#').upper()

    def font(size=10, bold=False, color=_P['body']):
        return Font(name=FONT, size=size, bold=bold, color=hx(color))

    def fill(h):
        return PatternFill('solid', start_color=hx(h), end_color=hx(h))

    def tint(v):
        a = max(min(v, 100) / 100 * 0.40, 0.05)
        return '%02X%02X%02X' % tuple(round(255 - a * (255 - x)) for x in _hex_rgb(_P['ac']))

    line = Side(style='thin', color=hx(_P['line']))
    group_line = Side(style='medium', color='DCE0EA')
    center = Alignment(horizontal='center', vertical='center')
    left = Alignment(horizontal='left', vertical='center', indent=1)
    wrap_left = Alignment(horizontal='left', vertical='center', wrap_text=True, indent=1)

    def setup(ws, ncols, title, caption):
        ws.sheet_view.showGridLines = False
        ws.page_setup.orientation = 'landscape'
        ws.page_setup.fitToWidth = 1; ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        last = get_column_letter(ncols)
        ws.merge_cells(f'A1:{last}1'); ws.merge_cells(f'A2:{last}2')
        ws.row_dimensions[1].height = 34; ws.row_dimensions[2].height = 20
        grad = GradientFill(type='linear', degree=0, stop=(hx(_P['grad'][0]), hx(_P['grad'][2])))
        for col in range(1, ncols + 1):
            ws.cell(row=1, column=col).fill = grad
            ws.cell(row=2, column=col).fill = grad
        c = ws['A1']; c.value = title
        c.font = Font(name=FONT, size=16, bold=True, color='FFFFFF'); c.alignment = Alignment(vertical='bottom', indent=1)
        c = ws['A2']; c.value = ' · '.join(x for x in (school_name, subtitle, caption) if x)
        c.font = Font(name=FONT, size=9, color='E6E3FF'); c.alignment = Alignment(vertical='top', indent=1)
        ws.row_dimensions[3].height = 10

    def header_row(ws, row, labels, left_cols=()):
        for i, h in enumerate(labels, 1):
            c = ws.cell(row=row, column=i, value=h)
            c.font = font(8.5, True, _P['muted']); c.fill = fill(_P['soft'])
            c.alignment = left if i in left_cols else Alignment(horizontal='center', vertical='center', wrap_text=True)
            c.border = Border(bottom=Side(style='thin', color='D5DAE5'))
        ws.row_dimensions[row].height = 26
        ws.freeze_panes = ws.cell(row=row + 1, column=1)

    o = opts or gb_options()
    zk, secs, ocols = o['k'], o['sections'], o['cols']
    TF = lambda pt: round(pt * zk * 2) / 2            # table text, scaled by the chosen size
    RH = lambda h: round(h * zk)                      # row heights follow the text

    def credit_cell(c, v):
        t = _tone(v)
        c.value = v / 100; c.number_format = '0.0%'
        c.font = font(TF(10), True, _P[t]); c.fill = fill(_P[t + '_bg']); c.alignment = center

    wb = Workbook()
    _first_sheet = [True]

    def new_sheet(title):
        if _first_sheet[0]:
            _first_sheet[0] = False
            w = wb.active; w.title = title
            return w
        return wb.create_sheet(title)

    # ---- Overview -----------------------------------------------------------
    O = result.get('overall') or {}
    so = result.get('subject_overall') or {}
    ranking = result.get('ranking') or []
    show_overview = bool(secs & {'hero', 'cards', 'takeaways'})
    ov = new_sheet('Overview') if show_overview else None
    if ov is not None:
        ov.sheet_view.showGridLines = False
        ov.page_setup.orientation = 'landscape'
        ov.page_setup.fitToWidth = 1; ov.page_setup.fitToHeight = 0
        ov.sheet_properties.pageSetUpPr.fitToPage = True
        for i in range(1, 13):
            ov.column_dimensions[get_column_letter(i)].width = 13
        row = 1
        try:
            from openpyxl.drawing.image import Image as XLImage
            png = _header_png(meta, result, band_label, pass_label, zoom=2, opts=o) if secs & {'hero', 'cards'} else None
            if not png:
                raise ValueError('no header picture')
            img = XLImage(io.BytesIO(png))
            scale = 1180 / img.width
            img.width, img.height = int(img.width * scale), int(img.height * scale)
            ov.add_image(img, 'A1')
            row = int(img.height / 20) + 3
        except Exception:
            setup(ov, 12, 'Subject-Wise Grade Breakdown', f"{len(result['subjects'])} subjects · {len(result['branches'])} branches")
            row = 5

        def ov_heading(r, text):
            c = ov.cell(row=r, column=1, value=text); c.font = font(14, True, _P['ink'])
            ov.row_dimensions[r].height = 24

        items = _insights(result, band_label) if 'takeaways' in secs else []
        if items:
            ov_heading(row, 'Key takeaways'); row += 1
            for kind, icon, text in items:
                ov.merge_cells(start_row=row, start_column=2, end_row=row, end_column=12)
                ic = ov.cell(row=row, column=1, value=icon)
                ic.font = font(12, True, _P[kind]); ic.fill = fill(_P[kind + '_bg']); ic.alignment = center
                tc = ov.cell(row=row, column=2, value=_html.unescape(_re.sub(r'</?b>', '', text)))
                tc.font = font(10.5, False, _P['ink']); tc.alignment = wrap_left
                for col in range(2, 13):
                    ov.cell(row=row, column=col).fill = fill(_P['soft'])
                ov.row_dimensions[row].height = 26
                row += 1
            row += 1

        ranked = [r for r in ranking if not r.get('small')]
        subs5 = [s for s in result['subjects'] if (so.get(s) or {}).get('n', 0) >= 5]
        figs = [(f'{word} pass rate', (O.get('pass_pct') or 0) / 100, '0.0%', f"{O.get('pass_n', 0)} of {O.get('n', 0)} subject entries"),
                ('Top-band share (' + ', '.join(bands[:3]) + ')',
                 sum((O.get('pct') or {}).get(b, 0) for b in bands[:3]) / 100, '0.0%', 'of all entries'),
                ('Subject entries', O.get('n', 0), '0', f"{len(result['subjects'])} subjects · {len(result['branches'])} branches")]
        if ranked and multi:
            figs.append(('Top branch', ranked[0]['branch'], '@', f"weighted GPA {ranked[0]['gpa']:.2f}"))
        if len(subs5) > 1:
            st_ = max(subs5, key=lambda s: so[s]['pass_pct']); wk = min(subs5, key=lambda s: so[s]['pass_pct'])
            figs.append(('Strongest subject', st_, '@', f"{so[st_]['pass_pct']}% {word.lower()}"))
            figs.append(('Needs attention', wk, '@', f"{so[wk]['pass_pct']}% {word.lower()}"))
        ov_heading(row, 'Headline figures'); row += 1
        for lab, val, fmt, note in figs:
            ov.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
            ov.merge_cells(start_row=row, start_column=4, end_row=row, end_column=6)
            ov.merge_cells(start_row=row, start_column=7, end_row=row, end_column=12)
            a = ov.cell(row=row, column=1, value=lab); a.font = font(10, True, _P['muted']); a.alignment = left
            b = ov.cell(row=row, column=4, value=val); b.number_format = fmt; b.font = font(12, True, _P['ink'])
            b.alignment = Alignment(horizontal='left', vertical='center')
            n = ov.cell(row=row, column=7, value=note); n.font = font(9.5, False, _P['muted']); n.alignment = left
            for col in range(1, 13):
                ov.cell(row=row, column=col).border = Border(bottom=line)
            ov.row_dimensions[row].height = 22
            row += 1
        ov.cell(row=row + 1, column=1, value='See the other sheets for the full subject breakdown, '
                                              'per-band summary and branch ranking.').font = font(9, False, _P['muted'])

    # ---- Grade Breakdown ----------------------------------------------------
    summ = result.get('summary') or {}
    if 'subjects' in secs:
        ws = new_sheet('Grade Breakdown')
        show_n, show_grades, show_groups, show_rate = 'n' in ocols, 'grades' in ocols, 'groups' in ocols, 'rate' in ocols
        labels = ['Subject', 'Branch', ''] + (['N'] if show_n else []) + (list(bands) if show_grades else []) \
            + ([n for n, _g, _c in groups] if show_groups else []) + ([f'{word} rate'] if show_rate else [])
        ncols = len(labels)
        setup(ws, ncols, 'Subject breakdown', f'% of entries per {band_label.lower()}'
              + (' · darker cell = larger share' if show_grades else ''))
        hr = 4
        header_row(ws, hr, labels + ['Not offered at'], left_cols=(1, 2, ncols + 1))
        r = hr + 1
        for subj in result['subjects']:
            offered = [(br, result['table'][subj][br]) for br in result['branches'] if result['table'][subj][br]]
            missing = [br for br in result['branches'] if not result['table'][subj][br]]
            best = _best(result, subj)
            for bi, (br, c_) in enumerate(offered):
                s_ = ws.cell(row=r, column=1, value=subj)   # repeated so filters/sorts keep context
                s_.font = font(TF(10.5), True, _P['ink']) if bi == 0 else font(TF(9), False, _P['faint'])
                s_.alignment = left
                b_ = ws.cell(row=r, column=2, value=br)
                b_.font = font(TF(10), br == best, _P['ink'] if br == best else _P['body']); b_.alignment = left
                if br == best:
                    t = ws.cell(row=r, column=3, value='BEST')
                    t.font = Font(name=FONT, size=TF(8), bold=True, color='FFFFFF'); t.fill = fill(_P['ac']); t.alignment = center
                col = 4
                if show_n:
                    n_ = ws.cell(row=r, column=col, value=c_['n']); n_.font = font(TF(10)); n_.alignment = center; col += 1
                if show_grades:
                    for b in bands:
                        v = c_['pct'][b]
                        cc = ws.cell(row=r, column=col, value=v / 100); col += 1
                        cc.number_format = PCT; cc.alignment = center
                        if v:
                            cc.fill = fill(tint(v)); cc.font = font(TF(10), v >= 45, '#1E1B4B' if v >= 45 else _P['body'])
                        else:
                            cc.font = font(TF(10), False, _P['faint'])
                if show_groups:
                    for gi, v in enumerate(_group_shares(c_['pct'], groups)):
                        cc = ws.cell(row=r, column=col, value=v / 100); col += 1
                        cc.number_format = PCT; cc.alignment = center
                        cc.font = font(TF(10), True, groups[0][2] if gi == 0 else (_P['ink'] if v else _P['faint']))
                if show_rate:
                    credit_cell(ws.cell(row=r, column=col), c_['pass_pct'])
                for cl in range(1, ncols + 1):
                    ws.cell(row=r, column=cl).border = Border(top=group_line if bi == 0 and r > hr + 1 else line)
                ws.row_dimensions[r].height = RH(20)
                r += 1
            if missing:
                m = ws.cell(row=r - 1 if offered else r, column=ncols + 1, value=', '.join(missing))
                m.font = font(TF(8.5), False, _P['muted']); m.alignment = Alignment(vertical='center')
                if not offered:
                    r += 1
        ws.auto_filter.ref = f'A{hr}:{get_column_letter(ncols + 1)}{r - 1}'
        if 'notes' in secs:
            note_r = r + 1
            for txt, colr in ([(f'BEST = highest {word.lower()} rate for the subject; if tied, better {band_label.lower()}s; '
                                'branches with fewer than 5 entries can’t be best unless all are that small.', _P['muted'])]
                              + [(f'{s_} — {n_}; fewer than 5 entries, so not ranked best.', _P['warn']) for s_, n_ in top_notes(result)]):
                ws.cell(row=note_r, column=1, value=txt).font = font(9, False, colr)
                note_r += 1
        ws.column_dimensions['A'].width = min(max([len(x) for x in result['subjects']] + [10]) * zk + 4, 46)
        ws.column_dimensions['B'].width = min(max([len(x) for x in result['branches']] + [10]) * zk + 4, 46)
        ws.column_dimensions['C'].width = 8
        for cl in range(4, ncols + 1):
            ws.column_dimensions[get_column_letter(cl)].width = round(9 * zk, 1)
        if show_groups:
            for cl in range(ncols - len(groups) - (1 if show_rate else 0) + 1, ncols - (1 if show_rate else 0) + 1):
                ws.column_dimensions[get_column_letter(cl)].width = round(13 * zk, 1)
        if show_rate:
            ws.column_dimensions[get_column_letter(ncols)].width = round(13 * zk, 1)
        ws.column_dimensions[get_column_letter(ncols + 1)].width = 36

    if 'ranking' in secs:
        # ---- Summary (per band, all subjects) -----------------------------------
        sm = new_sheet('Summary')
        ncols = 2 + len(bands) + len(groups) + 1
        setup(sm, ncols, f'Overall {band_label.lower()} summary by branch', 'all subjects combined · % of entries')
        header_row(sm, 4, ['Branch', 'Entries'] + list(bands) + [n for n, _g, _c in groups] + [f'{word} rate'], left_cols=(1,))
        r = 5
        for br in result['branches']:
            s_ = summ.get(br)
            if not s_:
                continue
            sm.cell(row=r, column=1, value=br).font = font(TF(10.5), True, _P['ink']); sm.cell(row=r, column=1).alignment = left
            e = sm.cell(row=r, column=2, value=s_['n']); e.font = font(TF(10)); e.alignment = center
            for bx, b in enumerate(bands):
                v = s_['pct'][b]
                cc = sm.cell(row=r, column=3 + bx, value=v / 100); cc.number_format = PCT; cc.alignment = center
                cc.font = font(TF(10), v >= 45, '#1E1B4B' if v >= 45 else (_P['body'] if v else _P['faint']))
                if v:
                    cc.fill = fill(tint(v))
            for gi, v in enumerate(_group_shares(s_['pct'], groups)):
                cc = sm.cell(row=r, column=3 + len(bands) + gi, value=v / 100); cc.number_format = PCT
                cc.alignment = center; cc.font = font(TF(10), True, groups[0][2] if gi == 0 else _P['ink'])
            credit_cell(sm.cell(row=r, column=ncols), s_['pass_pct'])
            for col in range(1, ncols + 1):
                sm.cell(row=r, column=col).border = Border(bottom=line)
            sm.row_dimensions[r].height = RH(22)
            r += 1
        sm.column_dimensions['A'].width = min(max([len(b) for b in result['branches']] + [10]) + 4, 40)
        sm.column_dimensions['B'].width = 10
        for col in range(3, ncols):
            sm.column_dimensions[get_column_letter(col)].width = 11 if col >= 3 + len(bands) else 9
        sm.column_dimensions[get_column_letter(ncols)].width = 13

        # ---- Branch Ranking -----------------------------------------------------
        rk = new_sheet('Branch Ranking')
        rc = result.get('ranking_criteria') or {}
        ncols = 3 + len(groups) + 2 + 1
        setup(rk, ncols, 'Branch ranking & summary' if multi else 'Overall summary',
              'ranked by weighted GPA · all subjects combined')
        header_row(rk, 4, ['Rank', 'Branch', 'Entries'] + [n for n, _g, _c in groups]
                   + ['Weighted GPA', f'{word} rate', 'Note'], left_cols=(2, ncols))
        r = 5
        for x in ranking:
            small, first = x.get('small'), x.get('rank') == 1
            a = rk.cell(row=r, column=1, value=x['rank']); a.alignment = center
            a.font = font(TF(13 if first else 11), True, _P['ac'] if first else (_P['faint'] if small else _P['ink']))
            b = rk.cell(row=r, column=2, value=x['branch']); b.font = font(TF(11), True, _P['ink']); b.alignment = left
            e = rk.cell(row=r, column=3, value=x['n']); e.font = font(TF(10)); e.alignment = center
            sm_ = summ.get(x['branch']) or {'pct': {bb: 0 for bb in bands}}
            for gi, v in enumerate(_group_shares(sm_['pct'], groups)):
                cc = rk.cell(row=r, column=4 + gi, value=v / 100); cc.number_format = PCT
                cc.alignment = center; cc.font = font(TF(10), False, _P['body'] if v else _P['faint'])
            g = rk.cell(row=r, column=4 + len(groups), value=x['gpa']); g.number_format = '0.00'
            g.font = font(TF(12), True, _P['ink']); g.alignment = center
            credit_cell(rk.cell(row=r, column=5 + len(groups)), x['pass_pct'])
            nt = rk.cell(row=r, column=ncols, value='Not ranked · under 5 entries' if small else ('Top branch' if first else ''))
            nt.font = font(9, small, _P['warn'] if small else _P['ac']); nt.alignment = left
            for col in range(1, ncols + 1):
                cl = rk.cell(row=r, column=col)
                cl.border = Border(bottom=line)
                if first and col != 5 + len(groups):   # keep the credit cell's own colour
                    cl.fill = fill('#F7F5FF')
            rk.row_dimensions[r].height = RH(24)
            r += 1
        if ranking:
            gcol = get_column_letter(4 + len(groups))   # GPA, on its 1..len(bands) scale
            rk.conditional_formatting.add(f'{gcol}5:{gcol}{r - 1}', DataBarRule(
                start_type='num', start_value=0, end_type='num', end_value=len(bands), color='C7D2FE'))
            if 'criteria' in secs:
                rk.cell(row=r + 1, column=1, value='How the ranking works').font = font(11, True, _P['ink'])
                for bi_, bl in enumerate(rc.get('bullets') or []):
                    rk.cell(row=r + 2 + bi_, column=1, value='•  ' + bl).font = font(9.5, False, _P['body'])
        rk.column_dimensions['A'].width = 8
        rk.column_dimensions['B'].width = min(max([len(b) for b in result['branches']] + [10]) + 4, 40)
        rk.column_dimensions['C'].width = 10
        for gi in range(len(groups)):
            rk.column_dimensions[get_column_letter(4 + gi)].width = round(13 * zk, 1)
        rk.column_dimensions[get_column_letter(4 + len(groups))].width = 15
        rk.column_dimensions[get_column_letter(5 + len(groups))].width = 15
        rk.column_dimensions[get_column_letter(ncols)].width = 30
    if _first_sheet[0]:          # every section switched off
        w = wb.active; w.title = 'Grade Breakdown'
        w['A1'] = 'No sections were selected for this export.'
    return wb


# --------------------------------------------------------------------------- #
# HD PNG (the PDF rasterised with PyMuPDF) — bundled into a zip when >1 page
# --------------------------------------------------------------------------- #

def grade_breakdown_png_pages(meta, result, band_label, pass_label, zoom=2.5, opts=None):
    """HD PNG pages — the PDF design rasterised page by page, so the image
    export always matches the PDF exactly."""
    import pymupdf as fitz
    pdf = grade_breakdown_pdf(meta, result, band_label, pass_label, opts=opts)
    d = fitz.open(stream=pdf, filetype='pdf')
    return [p.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes('png') for p in d]


def grade_breakdown_image_export(meta, result, band_label, pass_label, opts=None):
    """Returns (bytes, mimetype, ext) — a single HD PNG, or a zip of pages."""
    pages = grade_breakdown_png_pages(meta, result, band_label, pass_label, opts=opts)
    if len(pages) == 1:
        return pages[0], 'image/png', 'png'
    return zip_pngs(pages, base='grade_breakdown'), 'application/zip', 'zip'
