"""Class broadsheet exports — one designed document in PDF, image, Word and Excel.

Built on ``utils.broadsheet_export.build_model`` (the same ranked rows, averages
and SSS3 divisor as the page), with the options the export dialog offers:

* style: colour or black & white; paper A4 / A3; landscape / portrait; text size
* order: by position, by surname, or boys then girls
* columns: position, student ID, gender, each subject (optionally with its grade),
  total, average, grade, subjects passed / failed
* blocks: school header (logo, address), summary tiles, subject statistics rows
  (average / highest / lowest / pass rate), grade & subject key, highlighting of
  failed scores and the top three, signature lines, page numbers
"""
import io


def _n(v):
    """Scores without trailing zeros: 75.2, 56, 82.71."""
    if v is None or v == '':
        return '–'
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return ('%.2f' % f).rstrip('0').rstrip('.')

SIZES = {'s': 0.88, 'm': 1.0, 'l': 1.14}

# (key, label, default, group) — drives both the dialog and parse_opts().
OPTIONS = [
    ('c_pos', 'Position', True, 'columns'),
    ('c_sid', 'Student ID', False, 'columns'),
    ('c_gender', 'Gender', False, 'columns'),
    ('c_sgrade', 'Grade beside each score', False, 'columns'),
    ('c_total', 'Total', True, 'columns'),
    ('c_avg', 'Average', True, 'columns'),
    ('c_grade', 'Overall grade', True, 'columns'),
    ('c_pf', 'Subjects passed / failed', True, 'columns'),
    ('b_header', 'School name & address', True, 'blocks'),
    ('b_logo', 'School logo', True, 'blocks'),
    ('b_kpis', 'Class summary tiles', True, 'blocks'),
    ('b_stats', 'Subject statistics rows', True, 'blocks'),
    ('b_key', 'Subject & grade key', True, 'blocks'),
    ('b_fail', 'Highlight scores below the pass mark', True, 'blocks'),
    ('b_top', 'Highlight the top three', True, 'blocks'),
    ('b_sign', 'Signature lines', True, 'blocks'),
    ('b_pages', 'Page numbers', True, 'blocks'),
]


def parse_opts(args):
    """Options from a request's query args (missing = default)."""
    o = {}
    for key, _label, default, _g in OPTIONS:
        v = args.get(key)
        o[key] = default if v is None else v not in ('0', '', 'false', 'off')
    o['style'] = 'bw' if args.get('style') == 'bw' else 'colour'
    o['paper'] = 'A3' if (args.get('paper') or '').upper() == 'A3' else 'A4'
    o['orient'] = 'portrait' if args.get('orient') == 'portrait' else 'landscape'
    o['size'] = args.get('size') if args.get('size') in SIZES else 'm'
    o['sort'] = args.get('sort') if args.get('sort') in ('position', 'name', 'gender') else 'position'
    return o


def default_opts():
    return parse_opts({})


# --------------------------------------------------------------------------- #
# Data: rows in the chosen order + class / subject statistics
# --------------------------------------------------------------------------- #

def prepare(model, o):
    """Add ordering, per-subject grades and class statistics to a build_model()."""
    from models import GradeScale
    bands = GradeScale.query.all()

    def grade(v):
        if not v:
            return ''
        b = GradeScale.band_for(v, bands)
        return b.grade if b else ''

    pass_mark = float(model.get('pass_mark') or 50)
    rows = list(model['rows'])
    if o['sort'] == 'name':
        rows.sort(key=lambda r: ((r['student'].surname or '').lower(), (r['student'].first_name or '').lower()))
    elif o['sort'] == 'gender':
        rows.sort(key=lambda r: (0 if (r['student'].gender or '').lower().startswith('m') else 1,
                                 (r['student'].surname or '').lower(), (r['student'].first_name or '').lower()))
    for r in rows:
        r['grade'] = grade(r['average']) if r['average'] else ''
        r['sgrades'] = {cid: grade(v) for cid, v in r['subjects'].items()}
    subjects = model['subjects']
    stats = []
    for cs in subjects:
        vals = [r['subjects'].get(cs.id) for r in model['rows'] if r['subjects'].get(cs.id)]
        stats.append({
            'avg': round(sum(vals) / len(vals), 1) if vals else None,
            'high': max(vals) if vals else None,
            'low': min(vals) if vals else None,
            'pass': round(sum(1 for v in vals if v >= pass_mark) / len(vals) * 100) if vals else None,
            'n': len(vals),
        })
    scored = [r for r in model['rows'] if r['average']]
    class_avg = round(sum(r['average'] for r in scored) / len(scored), 1) if scored else None
    passed = sum(1 for r in scored if r['average'] >= pass_mark)
    best = max(model['rows'], key=lambda r: r['average']) if scored else None
    boys = sum(1 for r in model['rows'] if (r['student'].gender or '').lower().startswith('m'))
    kpis = {
        'students': len(model['rows']), 'boys': boys, 'girls': len(model['rows']) - boys,
        'class_avg': class_avg, 'pass_rate': round(passed / len(scored) * 100) if scored else None,
        'passed': passed, 'scored': len(scored),
        'best': best['student'].full_name if best else None, 'best_avg': best['average'] if best else None,
        'subjects': len(subjects),
    }
    top = {r['student'].id for r in sorted(scored, key=lambda r: r['position'])[:3]}
    return {**model, 'rows': rows, 'stats': stats, 'kpis': kpis, 'top': top, 'pass_mark': pass_mark}


def _short(cs):
    """The subject's own short code, else the app's standard abbreviation
    (ENG, MTH, CIV, FMATH…) rather than a chopped name."""
    if cs.subject.short_name:
        return cs.subject.short_name
    from utils.broadsheet_export import _abbr_one
    return _abbr_one(cs.subject.name)


def _school():
    try:
        from utils.school import school_profile
        return school_profile()
    except Exception:
        return {'name': 'School'}


def columns(m, o):
    """[(key, header, kind)] in order. kind: pos | name | text | subj | num | grade."""
    cols = []
    if o['c_pos']:
        cols.append(('pos', 'Pos', 'pos'))
    cols.append(('name', 'Student', 'name'))
    if o['c_sid']:
        cols.append(('sid', 'ID', 'text'))
    if o['c_gender']:
        cols.append(('gender', 'Sex', 'text'))
    for cs in m['subjects']:
        cols.append(('s%d' % cs.id, _short(cs), 'subj'))
    if o['c_total']:
        cols.append(('total', 'Total', 'num'))
    if o['c_avg']:
        cols.append(('avg', 'Avg', 'num'))
    if o['c_grade']:
        cols.append(('grade', 'Grade', 'grade'))
    if o['c_pf']:
        cols.append(('passed', 'Pass', 'num'))
        cols.append(('failed', 'Fail', 'num'))
    return cols


def cell_value(r, key, o):
    st = r['student']
    if key == 'pos':
        return str(r['position'])
    if key == 'name':
        return st.full_name or ''
    if key == 'sid':
        return st.student_id or ''
    if key == 'gender':
        g = (st.gender or '').strip()
        return g[:1].upper() if g else ''
    if key.startswith('s') and key[1:].isdigit():
        cid = int(key[1:])
        v = r['subjects'].get(cid)
        if not v:
            return '–'
        return f"{_n(v)} {r['sgrades'].get(cid, '')}".strip() if o['c_sgrade'] else _n(v)
    if key == 'total':
        return _n(r['total'])
    if key == 'avg':
        return _n(r['average']) if r['average'] else '–'
    if key == 'grade':
        return r['grade'] or '–'
    if key == 'passed':
        return str(r['passed'])
    if key == 'failed':
        return str(r['failed'])
    return ''


def stat_rows(m, cols):
    """The four statistics rows, aligned to the subject columns."""
    labels = [('avg', 'Subject average'), ('high', 'Highest'), ('low', 'Lowest'), ('pass', 'Pass rate')]
    out = []
    idx = {cs.id: i for i, cs in enumerate(m['subjects'])}
    for k, label in labels:
        row = []
        for key, _h, kind in cols:
            if kind == 'name':
                row.append(label)
            elif kind == 'subj':
                s = m['stats'][idx[int(key[1:])]]
                v = s[k]
                row.append('–' if v is None else (f'{v}%' if k == 'pass' else _n(v)))
            else:
                row.append('')
        out.append(row)
    return out


def title_lines(m):
    asg, term = m['assignment'], m['term']
    return (f"Broadsheet — {asg.display_name}",
            f"{term.full_name} · pass mark {_n(m['pass_mark'])}")


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #

_FONTS_DONE = []


def _fonts():
    """Inter for text and figures, Plus Jakarta Sans for the title (bundled in
    assets/fonts); falls back to Helvetica if they can't be loaded."""
    if _FONTS_DONE:
        return _FONTS_DONE[0]
    import os
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'fonts')
    f = {'r': 'Helvetica', 'm': 'Helvetica', 's': 'Helvetica-Bold', 'b': 'Helvetica-Bold', 'x': 'Helvetica-Bold'}
    try:
        for key, name, file in (('r', 'BS-Inter', 'Inter-Regular.ttf'), ('m', 'BS-InterM', 'Inter-Medium.ttf'),
                                ('s', 'BS-InterS', 'Inter-SemiBold.ttf'), ('b', 'BS-InterB', 'Inter-Bold.ttf'),
                                ('x', 'BS-Jakarta', 'PlusJakartaSans-ExtraBold.ttf')):
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, os.path.join(d, file)))
            f[key] = name
    except Exception:
        pass
    _FONTS_DONE.append(f)
    return f


def _palette(bw):
    from reportlab.lib import colors as C
    H = C.HexColor
    if bw:
        g = {'ink': H('#111111'), 'text': H('#222222'), 'muted': H('#555555'), 'faint': H('#8A8A8A'),
             'line': H('#BDBDBD'), 'hair': H('#DDDDDD'), 'card': H('#F3F3F3'), 'accent': H('#111111'),
             'accent_soft': H('#E9E9E9'), 'fail_fg': H('#000000'), 'fail_bg': H('#E4E4E4'),
             'band': H('#F5F5F5'), 'gold': H('#333333'), 'silver': H('#666666'), 'bronze': H('#999999'),
             'medal_fg': H('#FFFFFF')}
        g['grade'] = lambda k: (H('#E6E6E6'), H('#111111'))
        return g
    p = {'ink': H('#0B1220'), 'text': H('#1F2937'), 'muted': H('#64748B'), 'faint': H('#94A3B8'),
         'line': H('#CBD5E1'), 'hair': H('#E8ECF1'), 'card': H('#F5F7FA'), 'accent': H('#0E7C66'),
         'accent_soft': H('#E3F2EE'), 'fail_fg': H('#B42318'), 'fail_bg': H('#FDE8E7'),
         'band': H('#F7F9FB'), 'gold': H('#D4A017'), 'silver': H('#94A3B8'), 'bronze': H('#C2773A'),
         'medal_fg': H('#FFFFFF')}
    tones = {'a': ('#DCF5EC', '#0B6B4F'), 'b': ('#E1EEFF', '#1D4ED8'), 'c': ('#FFF4D6', '#8A5A00'),
             'd': ('#FFE9D6', '#B45309'), 'e': ('#FFE4DE', '#C2410C'), 'f': ('#FDE2E1', '#B42318')}
    p['grade'] = lambda k: tuple(H(x) for x in tones.get(k, ('#EEF1F5', '#334155')))
    return p


def _grade_key(g):
    g = (g or '').strip().upper()
    return g[:1].lower() if g[:1] in 'ABCDEF' else ''


def _page_size(o):
    from reportlab.lib.pagesizes import A4, A3, landscape, portrait
    base = A3 if o['paper'] == 'A3' else A4
    return landscape(base) if o['orient'] == 'landscape' else portrait(base)


def render_pdf(model, o):
    from reportlab.lib.units import mm
    from reportlab.lib import colors as C
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Table, TableStyle,
                                    Paragraph, Spacer, KeepTogether, Flowable)
    from reportlab.pdfgen.canvas import Canvas
    from utils.web_exports import pdf_escape as E

    m = prepare(model, o)
    F = _fonts()
    P = _palette(o['style'] == 'bw')
    sc = SIZES[o['size']]
    pw, ph = _page_size(o)
    M = 12 * mm
    avail = pw - 2 * M
    school = _school()
    # In the PDF the student ID sits under the name, so no separate column.
    cols = [c for c in columns(m, o) if c[0] != 'sid']
    nsub = len(m['subjects'])
    pm = m['pass_mark']

    class Pill(Flowable):
        """Centered rounded label (grades, failed scores)."""
        def __init__(self, text, bg, fg, font, size, pad=3.2, h=None, outline=None):
            super().__init__()
            self.t, self.bg, self.fg, self.f, self.s, self.pad, self.outline = text, bg, fg, font, size, pad, outline
            self.tw = stringWidth(text, font, size)
            self.width, self.height = self.tw + 2 * pad, h or size * 1.75

        def wrap(self, aw, ah):
            self._aw = aw
            return aw, self.height

        def draw(self):
            c = self.canv
            x = (self._aw - self.width) / 2
            c.setFillColor(self.bg)
            if self.outline is not None:
                c.setStrokeColor(self.outline); c.setLineWidth(0.6)
            c.roundRect(x, 0, self.width, self.height, self.height / 2,
                        stroke=1 if self.outline is not None else 0, fill=1)
            c.setFillColor(self.fg); c.setFont(self.f, self.s)
            c.drawCentredString(self._aw / 2, self.height / 2 - self.s * 0.36, self.t)

    class Medal(Flowable):
        def __init__(self, n, color, size):
            super().__init__()
            self.n, self.color, self.s = n, color, size
            self.d = size * 2.0
            self.width, self.height = self.d, self.d

        def wrap(self, aw, ah):
            self._aw = aw
            return aw, self.d

        def draw(self):
            c = self.canv
            cx = self._aw / 2
            c.setFillColor(self.color); c.circle(cx, self.d / 2, self.d / 2, stroke=0, fill=1)
            c.setFillColor(P['medal_fg']); c.setFont(F['b'], self.s)
            c.drawCentredString(cx, self.d / 2 - self.s * 0.36, str(self.n))

    class KpiStrip(Flowable):
        """The summary cards, drawn as one row of soft rounded panels."""
        def __init__(self, cards, h):
            super().__init__()
            self.cards, self.height = cards, h

        def wrap(self, aw, ah):
            self.width = aw
            return aw, self.height

        def draw(self):
            c = self.canv
            n = len(self.cards)
            gap = 3.2 * mm
            weights = [cd.get('w', 1) for cd in self.cards]
            unit = (self.width - gap * (n - 1)) / sum(weights)
            x = 0
            for cd, wgt in zip(self.cards, weights):
                w = unit * wgt
                c.setFillColor(P['card']); c.roundRect(x, 0, w, self.height, 7, stroke=0, fill=1)
                px = x + 9
                c.setFillColor(P['muted']); c.setFont(F['s'], 6.4 * sc)
                c.drawString(px, self.height - 13 * sc, cd['label'].upper())
                if cd.get('spread'):
                    self._spread(c, px, w - 18, cd['spread'])
                else:
                    big = cd['value']
                    fs = 17 * sc if len(big) < 9 else 11.5 * sc
                    while stringWidth(big, F['x'], fs) > w - 18 and fs > 7:
                        fs -= 0.5
                    c.setFillColor(P['ink']); c.setFont(F['x'], fs)
                    c.drawString(px, self.height - 16 * sc - fs, big)
                    if cd.get('bar') is not None:
                        by, bw_ = 17 * sc, w - 18
                        c.setFillColor(P['hair']); c.roundRect(px, by, bw_, 3.2, 1.6, stroke=0, fill=1)
                        c.setFillColor(P['accent']); c.roundRect(px, by, max(3.2, bw_ * min(cd['bar'], 100) / 100), 3.2, 1.6, stroke=0, fill=1)
                        if cd.get('mark') is not None:
                            mx = px + bw_ * min(cd['mark'], 100) / 100
                            c.setStrokeColor(P['ink']); c.setLineWidth(0.8); c.line(mx, by - 2, mx, by + 5.2)
                    c.setFillColor(P['muted']); c.setFont(F['r'], 7 * sc)
                    c.drawString(px, 7 * sc, cd.get('note', '')[:60])
                x += w + gap

        def _spread(self, c, px, w, spread):
            total = sum(v for _g, v in spread) or 1
            by, bh = self.height - 13 * sc - 16 * sc, 9 * sc
            x = px
            for g, v in spread:
                if not v:
                    continue
                seg = w * v / total
                bg, fg = P['grade'](_grade_key(g))
                c.setFillColor(fg if o['style'] != 'bw' else P['ink']); c.setFillAlpha(0.85 if o['style'] != 'bw' else 0.15 + 0.12 * len(g))
                c.rect(x, by, max(seg - 1, 0.5), bh, stroke=0, fill=1)
                c.setFillAlpha(1)
                x += seg
            # legend
            lx, ly = px, 7 * sc
            c.setFont(F['m'], 6.8 * sc)
            for g, v in spread:
                if not v:
                    continue
                bg, fg = P['grade'](_grade_key(g))
                c.setFillColor(fg if o['style'] != 'bw' else P['ink'])
                txt = '%s %d' % (g, v)
                c.drawString(lx, ly, txt)
                lx += stringWidth(txt, F['m'], 6.8 * sc) + 7
                if lx > px + w - 10:
                    break

    # ---------- column widths ----------
    fs = 7.8 * sc
    fixed = {'pos': 11 * mm, 'text': 11 * mm, 'num': 12.5 * mm, 'grade': 13 * mm}
    name_w = (50 if o['orient'] == 'landscape' else 42) * mm
    if o['c_sid']:
        name_w += 4 * mm
    fixed_w = sum(fixed.get(k, 0) for _c, _h, k in cols if k not in ('name', 'subj'))
    subj_w = (avail - name_w - fixed_w) / max(nsub, 1)
    min_subj = (12.5 if o['c_sgrade'] else 9.5) * mm
    if subj_w < min_subj:
        name_w = max(32 * mm, avail - fixed_w - min_subj * nsub)
        subj_w = (avail - name_w - fixed_w) / max(nsub, 1)
        if subj_w < min_subj:
            fs *= max(0.66, subj_w / min_subj)
    widths = [name_w if k == 'name' else subj_w if k == 'subj' else fixed.get(k, 12 * mm) for _c, _h, k in cols]

    st_name = ParagraphStyle('nm', fontName=F['m'], fontSize=fs, leading=fs * 1.25, textColor=P['ink'])
    head_st = ParagraphStyle('hd', fontName=F['s'], fontSize=6.6 * sc * (fs / (7.8 * sc)), leading=8 * sc,
                             textColor=P['muted'], alignment=1)
    head_st_l = ParagraphStyle('hdl', parent=head_st, alignment=0)

    data = [[Paragraph(E(h.upper()), head_st_l if kind == 'name' else head_st) for _k, h, kind in cols]]
    medals = {1: P['gold'], 2: P['silver'], 3: P['bronze']}
    for r in m['rows']:
        row = []
        for key, _h, kind in cols:
            if kind == 'pos':
                pos = r['position']
                row.append(Medal(pos, medals[pos], fs * 0.95) if (o['b_top'] and pos in medals and r['average'])
                           else str(pos))
            elif kind == 'name':
                sub = []
                if o['c_sid'] and r['student'].student_id:
                    sub.append(E(r['student'].student_id))
                txt = E(r['student'].full_name or '')
                if sub:
                    txt += '<br/><font name="%s" size="%.1f" color="%s">%s</font>' % (
                        F['r'], fs * 0.82, P['muted'].hexval().replace('0x', '#'), ' · '.join(sub))
                row.append(Paragraph(txt, st_name))
            elif kind == 'subj':
                cid = int(key[1:])
                v = r['subjects'].get(cid)
                label = cell_value(r, key, o)
                if v and o['b_fail'] and v < pm:
                    row.append(Pill(label, P['fail_bg'], P['fail_fg'], F['s'], fs))
                else:
                    row.append(label)
            elif kind == 'grade':
                g = r['grade']
                if g:
                    bg, fg = P['grade'](_grade_key(g))
                    row.append(Pill(g, bg, fg, F['b'], fs * 0.95, pad=5))
                else:
                    row.append('–')
            else:
                row.append(cell_value(r, key, o))
        data.append(row)
    n_body = len(data) - 1
    stats = stat_rows(m, cols) if (o['b_stats'] and m['rows']) else []
    data += stats

    name_i = next(i for i, c in enumerate(cols) if c[2] == 'name')
    ts = [
        ('FONTNAME', (0, 1), (-1, -1), F['r']),
        ('FONTSIZE', (0, 1), (-1, -1), fs),
        ('TEXTCOLOR', (0, 1), (-1, -1), P['text']),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (name_i, 0), (name_i, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 1), (-1, -1), 4.2 * sc), ('BOTTOMPADDING', (0, 1), (-1, -1), 4.2 * sc),
        ('TOPPADDING', (0, 0), (-1, 0), 2), ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('LINEBELOW', (0, 0), (-1, 0), 1.1, P['ink']),
        ('LINEBELOW', (0, 1), (-1, n_body - 1 if n_body > 1 else 1), 0.4, P['hair']),
    ]
    for i, (key, _h, kind) in enumerate(cols):
        if key in ('total', 'avg'):
            ts.append(('FONTNAME', (i, 1), (i, n_body), F['s']))
            ts.append(('TEXTCOLOR', (i, 1), (i, n_body), P['ink']))
        if kind == 'pos':
            ts.append(('TEXTCOLOR', (i, 1), (i, n_body), P['muted']))
        if key == 'failed':
            for ri, r in enumerate(m['rows'], 1):
                if r['failed']:
                    ts.append(('TEXTCOLOR', (i, ri), (i, ri), P['fail_fg']))
                    ts.append(('FONTNAME', (i, ri), (i, ri), F['s']))
    # the summary block (total / avg / grade …) sits on a faint band
    tail = [i for i, c in enumerate(cols) if c[0] in ('total', 'avg', 'grade', 'passed', 'failed')]
    if tail:
        ts.append(('BACKGROUND', (tail[0], 0), (tail[-1], n_body), P['band']))
    if stats:
        s0 = n_body + 1
        ts += [('BACKGROUND', (0, s0), (-1, -1), P['card']),
               ('LINEABOVE', (0, s0), (-1, s0), 1.1, P['ink']),
               ('FONTNAME', (0, s0), (-1, -1), F['m']),
               ('FONTSIZE', (0, s0), (-1, -1), fs * 0.92),
               ('TEXTCOLOR', (0, s0), (-1, -1), P['muted']),
               ('FONTNAME', (name_i, s0), (name_i, -1), F['s']),
               ('TEXTCOLOR', (name_i, s0), (name_i, -1), P['text']),
               ('FONTNAME', (0, s0), (-1, s0), F['s']), ('TEXTCOLOR', (0, s0), (-1, s0), P['ink']),
               ('TOPPADDING', (0, s0), (-1, -1), 3 * sc), ('BOTTOMPADDING', (0, s0), (-1, -1), 3 * sc)]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle(ts))

    # ---------- header ----------
    def st(name, **kw):
        return ParagraphStyle(name, **{'fontName': F['r'], 'textColor': P['ink'], **kw})
    asg, term = m['assignment'], m['term']
    left = []
    logo = None
    if o['b_logo']:
        try:
            from utils.school import logo_flowable
            logo = logo_flowable(max_h_mm=15, max_w_mm=26, path=school.get('logo_path'))
        except Exception:
            logo = None
    if o['b_header']:
        left.append(Paragraph(E((school.get('name') or 'School').upper()),
                              st('sn', fontName=F['s'], fontSize=8 * sc, leading=10 * sc, textColor=P['muted'])))
    left.append(Paragraph(E(asg.display_name), st('tt', fontName=F['x'], fontSize=24 * sc, leading=27 * sc)))
    left.append(Paragraph('<font name="%s" color="%s">Broadsheet</font>  ·  %s' % (
        F['s'], P['accent'].hexval().replace('0x', '#'), E(term.full_name)),
        st('ts', fontSize=9.5 * sc, leading=12 * sc, textColor=P['muted'])))
    right = []
    if o['b_header']:
        for line in (school.get('address'), ' · '.join(x for x in (school.get('phone'), school.get('email')) if x)):
            if line:
                right.append(Paragraph(E(line), st('ad', fontSize=7.4 * sc, leading=9.5 * sc, textColor=P['muted'], alignment=2)))
    from utils import timeutil
    printed = timeutil.now().strftime('%d %b %Y').lstrip('0')
    right.append(Spacer(1, 3))
    right.append(Paragraph('PASS MARK <font name="%s" color="%s">%s</font>  ·  PRINTED <font name="%s" color="%s">%s</font>' % (
        F['s'], P['ink'].hexval().replace('0x', '#'), _n(pm), F['s'], P['ink'].hexval().replace('0x', '#'), E(printed.upper())),
        st('mt', fontName=F['m'], fontSize=6.8 * sc, leading=9 * sc, textColor=P['faint'], alignment=2)))
    hcells = ([logo] if logo else []) + [left, right]
    hw = ([30 * mm] if logo else []) + [avail * 0.62 - (30 * mm if logo else 0), avail * 0.38]
    ht = Table([hcells], colWidths=hw)
    ht.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'BOTTOM'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                            ('RIGHTPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
    elems = [ht, Spacer(1, 10 * sc)]

    if o['b_kpis'] and m['rows']:
        k = m['kpis']
        from collections import Counter
        spread = Counter(r['grade'] for r in m['rows'] if r['grade'])
        order = sorted(spread, key=lambda g: (g[:1], g[1:] != '+', g))
        cards = [
            {'label': 'Students', 'value': str(k['students']), 'note': f"{k['boys']} boys · {k['girls']} girls"},
            {'label': 'Class average', 'value': _n(k['class_avg']) if k['class_avg'] is not None else '–',
             'bar': k['class_avg'] or 0, 'mark': pm, 'note': f"Pass mark {_n(pm)} · {k['subjects']} subjects"},
            {'label': 'Passed', 'value': (f"{k['pass_rate']}%" if k['pass_rate'] is not None else '–'),
             'bar': k['pass_rate'] or 0, 'note': f"{k['passed']} of {k['scored']} averaged {_n(pm)}+"},
            {'label': 'Top student', 'value': k['best'] or '–', 'note': (f"Average {_n(k['best_avg'])}" if k['best_avg'] else ''), 'w': 1.35},
        ]
        if spread:
            cards.append({'label': 'Grade spread', 'spread': [(g, spread[g]) for g in order], 'w': 1.35})
        elems += [KpiStrip(cards, 60 * sc), Spacer(1, 10 * sc)]

    elems.append(table if m['rows'] else Paragraph('No students on this class roll for the term.', st('e', fontSize=10)))

    notes = []
    if o['b_key'] and m['subjects']:
        notes.append(Paragraph('  ·  '.join('<font name="%s" color="%s">%s</font> %s' % (
            F['s'], P['ink'].hexval().replace('0x', '#'), E(_short(cs)), E(cs.subject.name)) for cs in m['subjects']),
            st('k', fontSize=7 * sc, leading=10 * sc, textColor=P['muted'])))
        legend = []
        if o['b_fail']:
            legend.append('highlighted scores are below the pass mark (%s)' % _n(pm))
        if o['b_top']:
            legend.append('medals mark the top three')
        if o['b_stats']:
            legend.append('the shaded rows summarise each subject')
        if legend:
            notes.append(Paragraph('Key: ' + '; '.join(legend) + '.', st('k2', fontSize=7 * sc, leading=10 * sc, textColor=P['faint'])))
    if notes:
        elems += [Spacer(1, 7 * sc)] + notes

    if o['b_sign']:
        sw = (avail - 2 * 14 * mm) / 3
        lab = st('sg', fontName=F['m'], fontSize=7.2 * sc, leading=9 * sc, textColor=P['muted'])
        sg = Table([['', '', '', '', ''],
                    [Paragraph('Form teacher · signature & date', lab), '', Paragraph('Head of section', lab), '',
                     Paragraph('Principal · signature & stamp', lab)]],
                   colWidths=[sw, 14 * mm, sw, 14 * mm, sw], rowHeights=[20 * sc, None])
        sg.setStyle(TableStyle([('LINEABOVE', (0, 1), (0, 1), 0.7, P['line']), ('LINEABOVE', (2, 1), (2, 1), 0.7, P['line']),
                                ('LINEABOVE', (4, 1), (4, 1), 0.7, P['line']), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
        elems += [Spacer(1, 16 * sc), KeepTogether(sg)]

    foot_left = '%s  ·  %s  ·  %s' % (school.get('name') or 'School', asg.display_name, term.full_name)

    class _Numbered(Canvas):
        """Two-pass canvas so the footer can say "Page x of y"."""
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._saved = []

        def showPage(self):
            self._saved.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved)
            for state in self._saved:
                self.__dict__.update(state)
                self._footer(total)
                super().showPage()
            super().save()

        def _footer(self, total):
            self.setStrokeColor(P['hair']); self.setLineWidth(0.6)
            self.line(M, 9.5 * mm, pw - M, 9.5 * mm)
            self.setFont(F['r'], 6.8)
            self.setFillColor(P['faint'])
            self.drawString(M, 6 * mm, foot_left)
            if o['b_pages']:
                self.setFont(F['s'], 6.8)
                self.drawRightString(pw - M, 6 * mm, 'Page %d of %d' % (self._pageNumber, total))

    buf = io.BytesIO()
    title = 'Broadsheet — %s — %s' % (asg.display_name, term.full_name)
    doc = BaseDocTemplate(buf, pagesize=(pw, ph), leftMargin=M, rightMargin=M, topMargin=M,
                          bottomMargin=14 * mm, title=title, author=school.get('name') or '')
    frame = Frame(M, 14 * mm, avail, ph - M - 14 * mm, id='f', leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id='p', frames=[frame])])
    doc.build(elems, canvasmaker=_Numbered)
    return buf.getvalue()


def render_png_pages(pdf_bytes, page=None, zoom=2.0):
    """(list_of_png_bytes, total_pages). ``page`` (1-based) renders just that one."""
    import fitz
    d = fitz.open(stream=pdf_bytes, filetype='pdf')
    total = d.page_count
    pages = [d[min(max(page, 1), total) - 1]] if page else list(d)
    return [p.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False).tobytes('png') for p in pages], total


# --------------------------------------------------------------------------- #
# Word
# --------------------------------------------------------------------------- #

def render_docx(model, o):
    from docx import Document
    from docx.shared import Pt, RGBColor, Mm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.section import WD_ORIENT
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    m = prepare(model, o)
    bw = o['style'] == 'bw'
    sc = SIZES[o['size']]
    school = _school()
    title, subtitle = title_lines(m)
    cols = columns(m, o)
    doc = Document()
    sec = doc.sections[0]
    pw, ph = (420, 297) if o['paper'] == 'A3' else (297, 210)
    if o['orient'] == 'portrait':
        pw, ph = ph, pw
    sec.orientation = WD_ORIENT.LANDSCAPE if o['orient'] == 'landscape' else WD_ORIENT.PORTRAIT
    sec.page_width, sec.page_height = Mm(pw), Mm(ph)
    for a in ('left_margin', 'right_margin', 'top_margin', 'bottom_margin'):
        setattr(sec, a, Mm(10))
    accent = RGBColor(0, 0, 0) if bw else RGBColor(0x0E, 0x7C, 0x66)
    muted = RGBColor(0x47, 0x55, 0x69)

    def para(text, size, bold=False, color=None, align=None, italic=False):
        p = doc.add_paragraph()
        r = p.add_run(text); r.bold = bold; r.italic = italic; r.font.size = Pt(size)
        if color is not None:
            r.font.color.rgb = color
        if align:
            p.alignment = align
        p.paragraph_format.space_after = Pt(1)
        return p

    if o['b_header']:
        para(school.get('name') or 'School', 15 * sc, bold=True)
        line2 = ' · '.join(x for x in (school.get('address'), school.get('phone'), school.get('email')) if x)
        if line2:
            para(line2, 8 * sc, color=muted)
    para(title, 13 * sc, bold=True, color=accent)
    para(subtitle, 9 * sc, color=muted)
    if o['b_kpis']:
        k = m['kpis']
        para('Students: %s (%s boys, %s girls) · Class average: %s · Passed: %s · Top: %s' % (
            k['students'], k['boys'], k['girls'], _n(k['class_avg']) if k['class_avg'] is not None else '–',
            f"{k['pass_rate']}%" if k['pass_rate'] is not None else '–',
            f"{k['best']} ({_n(k['best_avg'])})" if k['best'] else '–'), 8.5 * sc, color=muted)

    def shade(cell, hexcol):
        tcPr = cell._tc.get_or_add_tcPr()
        sh = OxmlElement('w:shd'); sh.set(qn('w:val'), 'clear'); sh.set(qn('w:color'), 'auto'); sh.set(qn('w:fill'), hexcol)
        tcPr.append(sh)

    stats = stat_rows(m, cols) if (o['b_stats'] and m['rows']) else []
    table = doc.add_table(rows=1, cols=len(cols))
    table.style = 'Table Grid'
    fs = Pt(7.5 * sc)
    for i, (_k, h, _kind) in enumerate(cols):
        c = table.rows[0].cells[i]
        c.text = h
        shade(c, 'EDEDED' if bw else 'EEF2F6')
        for p in c.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                r.bold = True; r.font.size = fs
                r.font.color.rgb = RGBColor(0x11, 0x11, 0x11) if bw else RGBColor(0x33, 0x41, 0x55)
    for r in m['rows']:
        cells = table.add_row().cells
        top = o['b_top'] and r['student'].id in m['top']
        for i, (key, _h, kind) in enumerate(cols):
            cells[i].text = cell_value(r, key, o)
            fail = (o['b_fail'] and kind == 'subj' and r['subjects'].get(int(key[1:]))
                    and r['subjects'].get(int(key[1:])) < m['pass_mark'])
            if top:
                shade(cells[i], 'F0F0F0' if bw else 'FFF7E0')
            for p in cells[i].paragraphs:
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT if kind == 'name' else WD_ALIGN_PARAGRAPH.CENTER
                for run in p.runs:
                    run.font.size = fs
                    run.bold = bool(top and kind == 'name') or key in ('total', 'avg', 'grade') or bool(fail)
                    if fail:
                        if bw:
                            run.underline = True
                        else:
                            run.font.color.rgb = RGBColor(0xB4, 0x23, 0x18)
    for srow in stats:
        cells = table.add_row().cells
        for i, v in enumerate(srow):
            cells[i].text = v
            shade(cells[i], 'F2F2F2' if bw else 'F5F7FA')
            for p in cells[i].paragraphs:
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT if cols[i][2] == 'name' else WD_ALIGN_PARAGRAPH.CENTER
                for run in p.runs:
                    run.font.size = fs; run.italic = True
    if o['b_key']:
        para('Subjects: ' + ' · '.join(f'{_short(cs)} {cs.subject.name}' for cs in m['subjects']), 7.5 * sc, color=muted)
    if o['b_sign']:
        para('', 6)
        para("Form teacher: ______________________     Head of section: ______________________     "
             "Principal: ______________________", 8 * sc, color=muted)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Excel
# --------------------------------------------------------------------------- #

def render_xlsx(model, o):
    """Workbook: the designed Broadsheet sheet (+ a Subject statistics sheet)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from utils.web_exports import formula_guard

    m = prepare(model, o)
    bw = o['style'] == 'bw'
    school = _school()
    title, subtitle = title_lines(m)
    cols = columns(m, o)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Broadsheet'
    head_fill = PatternFill('solid', fgColor='EDEDED' if bw else 'EEF2F6')
    head_font = Font(bold=True, color='111111' if bw else '334155')
    thin = Side(style='thin', color='BDBDBD' if bw else 'E2E8F0')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    zebra = None if bw else PatternFill('solid', fgColor='F8FAFC')
    top_fill = PatternFill('solid', fgColor='F0F0F0' if bw else 'FFF7E0')
    fail_font = Font(bold=True, underline='single') if bw else Font(bold=True, color='B42318')

    r0 = 1
    if o['b_header']:
        ws.cell(row=r0, column=1, value=formula_guard(school.get('name') or 'School')).font = Font(bold=True, size=14)
        r0 += 1
    ws.cell(row=r0, column=1, value=formula_guard(title)).font = Font(bold=True, size=12,
                                                                      color='000000' if bw else '0E7C66')
    ws.cell(row=r0 + 1, column=1, value=formula_guard(subtitle)).font = Font(color='475569')
    r0 += 2
    if o['b_kpis']:
        k = m['kpis']
        ws.cell(row=r0, column=1, value='Students %s (%s boys, %s girls) · Class average %s · Passed %s · Top: %s' % (
            k['students'], k['boys'], k['girls'], _n(k['class_avg']) if k['class_avg'] is not None else '–',
            f"{k['pass_rate']}%" if k['pass_rate'] is not None else '–',
            formula_guard(f"{k['best']} ({_n(k['best_avg'])})") if k['best'] else '–')).font = Font(color='475569')
        r0 += 1
    hr = r0 + 1
    for i, (_k, h, _kind) in enumerate(cols, 1):
        c = ws.cell(row=hr, column=i, value=h)
        c.fill, c.font, c.border = head_fill, head_font, border
        c.alignment = Alignment(horizontal='center', vertical='center')
    numeric = {'pos', 'num'}
    for ri, r in enumerate(m['rows'], 1):
        rr = hr + ri
        top = o['b_top'] and r['student'].id in m['top']
        for i, (key, _h, kind) in enumerate(cols, 1):
            if kind == 'subj':
                v = r['subjects'].get(int(key[1:]))
                val = (cell_value(r, key, o) if o['c_sgrade'] else (v if v else None))
            elif key == 'total':
                val = r['total']
            elif key == 'avg':
                val = r['average'] or None
            elif kind in numeric:
                val = int(cell_value(r, key, o)) if cell_value(r, key, o).isdigit() else cell_value(r, key, o)
            else:
                val = formula_guard(cell_value(r, key, o))
            c = ws.cell(row=rr, column=i, value=val)
            c.border = border
            c.alignment = Alignment(horizontal='left' if kind == 'name' else 'center')
            if top:
                c.fill = top_fill
            elif zebra is not None and ri % 2 == 0:
                c.fill = zebra
            if key in ('total', 'avg', 'grade'):
                c.font = Font(bold=True)
            if (o['b_fail'] and kind == 'subj' and r['subjects'].get(int(key[1:]))
                    and r['subjects'].get(int(key[1:])) < m['pass_mark']):
                c.font = fail_font
    last = hr + len(m['rows'])
    if o['b_stats'] and m['rows']:
        for si, srow in enumerate(stat_rows(m, cols), 1):
            for i, v in enumerate(srow, 1):
                c = ws.cell(row=last + si, column=i, value=v or None)
                c.font = Font(italic=True, bold=(cols[i - 1][2] == 'name'), color='475569')
                c.fill = PatternFill('solid', fgColor='F2F2F2' if bw else 'F5F7FA')
                c.border = border
                c.alignment = Alignment(horizontal='left' if cols[i - 1][2] == 'name' else 'center')
        last += 4
    if o['b_key']:
        ws.cell(row=last + 2, column=1,
                value=formula_guard('Subjects: ' + ' · '.join(f'{_short(cs)} {cs.subject.name}' for cs in m['subjects']))
                ).font = Font(color='475569', size=9)
    for i, (key, _h, kind) in enumerate(cols, 1):
        ws.column_dimensions[get_column_letter(i)].width = (30 if kind == 'name' else 14 if key == 'sid'
                                                            else (9 if o['c_sgrade'] and kind == 'subj' else 7))
    ws.freeze_panes = ws.cell(row=hr + 1, column=next(i for i, c in enumerate(cols, 1) if c[2] == 'name') + 1)
    ws.page_setup.orientation = o['orient']
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f'{hr}:{hr}'
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def filename(model, ext):
    asg, term = model['assignment'], model['term']
    base = (asg.display_name or 'broadsheet').replace(' ', '_')
    return f"broadsheet_{base}_{term.name.replace(' ', '_')}.{ext}"
