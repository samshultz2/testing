"""State vs Federal comparison export (JSS3 BECE / Basic 5-6 Common Entrance).

``compare_doc`` builds a document dict from ``school_exams.compare_bodies`` and
the trends; ``render_pdf`` draws it with the same letterhead, footer, cards and
type as the WAEC / NECO results exports. The image export is this PDF
rasterised (``exam_results_doc.render_images``), so both stay identical.

Page layout:
  1. two exam cards (State / Federal) with the headline numbers
  2. head-to-head measures, each with paired bars and a gap pill
  3. highlights (sat both + correlation, widest gaps)
  4. subject credit rate chart (grouped bars) and the subject table
  5. met-benchmark trend over the years (two lines)
"""
from __future__ import annotations

import io

from utils import student_list_export as SLE

# Series colours — the same blue / orange as the on-screen comparison charts.
S1, S2 = '#2a78d6', '#e0703c'
S1_SOFT, S2_SOFT = '#eaf2fc', '#fdf0e9'

MEASURES = [
    # key, label, unit, drawn as a bar (0–100 %)
    ('candidates', 'Candidates', '', False),
    ('avg_pct', 'Average score', '%', True),
    ('avg_credits', 'Average credits per candidate', '', False),
    ('core_credit_rate', 'Credit in English & Maths', '%', True),
    ('benchmark_rate', 'Met the benchmark', '%', True),
    ('subject_credit_rate', 'Subject credit rate', '%', True),
    ('subject_pass_rate', 'Subject pass rate', '%', True),
    ('all_pass_rate', 'Passed every subject', '%', True),
    ('admission_rate', 'Admitted / placed', '%', True),
]


def _num(v, unit=''):
    if v is None:
        return '—'
    if isinstance(v, float):
        v = ('%.2f' % v) if unit == '' and v != int(v) else ('%.1f' % v if unit else '%d' % v)
    return '%s%s' % (v, unit)


def _signed(v, unit=''):
    if v is None:
        return '—'
    if abs(v) < .05:
        return '0' + unit
    return ('+%.1f' % v if v > 0 else '−%.1f' % abs(v)) + unit


def agreement(corr):
    if corr is None:
        return 'needs 3+ shared candidates'
    if corr >= .7:
        return 'strong agreement'
    if corr >= .4:
        return 'moderate agreement'
    return 'weak agreement'


def compare_doc(level, year, ctx):
    """Document dict for the State vs Federal comparison of ``year``."""
    from utils import school_exams as svc
    from utils.broadsheet_export import abbreviate_subjects
    cmp = svc.compare_bodies(level, year)
    s, f = cmp['state'], cmp['federal']
    sn, fn = cmp['state_name'], cmp['federal_name']
    has_s, has_f = bool(s.get('candidates')), bool(f.get('candidates'))

    measures = []
    for key, label, unit, bar in MEASURES:
        a = s.get(key) if has_s else None
        b = f.get(key) if has_f else None
        if a is None and b is None:
            continue
        if key == 'admission_rate' and not (s.get('admission_known') or f.get('admission_known')):
            continue
        gap = round(a - b, 2 if unit == '' and key != 'candidates' else 1) if a is not None and b is not None else None
        measures.append({'key': key, 'label': label, 'unit': unit, 'bar': bar,
                         'a': a, 'b': b, 'gap': gap})

    subjects = sorted(cmp['subjects'], key=lambda r: (-r['diff'], r['subject']))
    codes, _ = abbreviate_subjects([r['subject'] for r in subjects])
    for r, c in zip(subjects, codes):
        r['code'] = c

    insights = [('Sat both examinations', '%d candidate%s' % (cmp['both'], '' if cmp['both'] == 1 else 's'),
                 ('correlation %s · %s' % (('%.2f' % cmp['corr']).replace('-', '−'), agreement(cmp['corr'])))
                 if cmp['corr'] is not None else agreement(None))]
    if subjects:
        top, low = subjects[0], subjects[-1]
        if top['diff'] > 0:
            insights.append(('Widest gap for %s' % sn, top['subject'],
                             '%s pts credit rate (%.0f%% vs %.0f%%)' % (_signed(top['diff']), top['state_credit'],
                                                                         top['federal_credit'])))
        if low['diff'] < 0:
            insights.append(('Widest gap for %s' % fn, low['subject'],
                             '%s pts credit rate (%.0f%% vs %.0f%%)' % (_signed(-low['diff']), low['federal_credit'],
                                                                         low['state_credit'])))
        close = min(subjects, key=lambda r: (abs(r['diff']), r['subject']))
        if len(insights) < 3:
            insights.append(('Closest agreement', close['subject'],
                             'within %.1f pts (%.0f%% vs %.0f%%)' % (abs(close['diff']), close['state_credit'],
                                                                     close['federal_credit'])))
        ahead = sum(1 for r in subjects if r['diff'] > 0)
        behind = sum(1 for r in subjects if r['diff'] < 0)
    else:
        ahead = behind = 0

    t_s = {r['year']: r.get('benchmark_rate') for r in svc.trend(level, 'state')}
    t_f = {r['year']: r.get('benchmark_rate') for r in svc.trend(level, 'federal')}
    years = sorted(set(t_s) | set(t_f))
    trend = [(y, t_s.get(y), t_f.get(y)) for y in years] if len(years) > 1 else []

    bs = svc.benchmark_label(svc.get_scheme(level, 'state'))
    bf = svc.benchmark_label(svc.get_scheme(level, 'federal'))
    bench = bs if bs == bf else 'State %s, Federal %s' % (bs, bf)
    cls = svc.level_class_label(level)
    bits = [cls, str(year),
            ('%d sat %s · %d sat %s' % (s.get('candidates') or 0, sn, f.get('candidates') or 0, fn)),
            ('%d sat both' % cmp['both']) if cmp['both'] else None]
    summary = None
    if subjects:
        summary = '%s has the higher credit rate in %d of %d shared subject%s, %s in %d%s.' % (
            sn, ahead, len(subjects), '' if len(subjects) == 1 else 's', fn, behind,
            (', equal in %d' % (len(subjects) - ahead - behind)) if len(subjects) - ahead - behind else '')
    return {
        'type': 'compare', 'school': ctx['school'], 'colors': ctx['colors'],
        'generated': ctx.get('generated'), 'prepared_by': ctx.get('prepared_by'),
        'doc_tag': 'STATE VS FEDERAL', 'year': year,
        'title': '%s vs %s — %s' % (sn, fn, year),
        'subtitle': ' · '.join(b for b in bits if b),
        'footer_title': '%s · State vs Federal %s' % (cls, year),
        'state_name': sn, 'federal_name': fn, 'has_state': has_s, 'has_federal': has_f,
        'state': s, 'federal': f, 'measures': measures, 'subjects': subjects,
        'insights': insights if (has_s and has_f) else [], 'trend': trend, 'summary': summary,
        'bench_label': bench,
    }


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def render_pdf(doc):
    from utils.exam_results_doc import SIZE_SCALE
    SLE._register_fonts()
    F = SLE.F
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph, Table, TableStyle,
                                    Spacer, Flowable, NextPageTemplate, KeepTogether)
    from reportlab.pdfbase.pdfmetrics import stringWidth

    hx = colors.HexColor
    INK, INK2, MUTED, LINE, LINE2, BG = SLE.INK, SLE.INK2, SLE.MUTED, SLE.LINE, SLE.LINE2, SLE.BG
    C = doc['colors']
    K = SIZE_SCALE[doc.get('size') if doc.get('size') in SIZE_SCALE else 'm']
    esc = SLE._esc
    PW, PH = A4
    margin = 34
    avail_w = PW - 2 * margin
    head_h, foot_h, head2_h = 112, 40, 46
    sn, fn = doc['state_name'], doc['federal_name']

    def fit(text, font, size, w):
        while stringWidth(text, font, size) > w and len(text) > 3:
            text = text[:-2].rstrip() + '…' if not text.endswith('…') else text[:-2] + '…'
        return text

    st_title = ParagraphStyle('t', fontName=F['Display'], fontSize=19, leading=23, textColor=hx(INK))
    st_sub = ParagraphStyle('s', fontName=F['Body'], fontSize=9.2, leading=12.5, textColor=hx(INK2))
    fs = 8.4 * K
    st_cell = ParagraphStyle('c', fontName=F['Body'], fontSize=fs, leading=fs * 1.25, textColor=hx(INK2))
    st_note = ParagraphStyle('n', parent=st_cell, fontSize=7.6 * K, leading=10.4 * K, textColor=hx(MUTED))

    class Section(Flowable):
        """Small upper-case section heading with a hairline."""
        def __init__(self, text, right=None):
            super().__init__()
            self.text, self.right = text, right

        def wrap(self, aw, ah):
            self.w = aw
            return aw, 20

        def draw(self):
            cv = self.canv
            cv.setFillColor(hx(INK)); cv.setFont(F['BodyBold'], 8.2)
            cv.drawString(0, 7, self.text.upper(), charSpace=.8)
            tw = stringWidth(self.text.upper(), F['BodyBold'], 8.2) + len(self.text) * .8 + 10
            x_end = self.w
            if self.right:
                cv.setFillColor(hx(MUTED)); cv.setFont(F['Body'], 7.4)
                rw = stringWidth(self.right, F['Body'], 7.4)
                cv.drawRightString(self.w, 7, self.right)
                x_end = self.w - rw - 10
            cv.setStrokeColor(hx(LINE)); cv.setLineWidth(.7)
            if x_end > tw:
                cv.line(tw, 10, x_end, 10)

    class Key(Flowable):
        """Series key: ● State exam   ● Federal exam."""
        def wrap(self, aw, ah):
            self.w = aw
            return aw, 12

        def draw(self):
            cv = self.canv
            x = 0
            for col, name, tag in ((S1, sn, 'State'), (S2, fn, 'Federal')):
                cv.setFillColor(hx(col)); cv.roundRect(x, 2, 9, 7, 2, stroke=0, fill=1)
                cv.setFillColor(hx(INK2)); cv.setFont(F['BodyBold'], 7.4)
                txt = '%s (%s)' % (name, tag)
                cv.drawString(x + 13, 2.6, txt)
                x += 13 + stringWidth(txt, F['BodyBold'], 7.4) + 18

    class ExamCard(Flowable):
        """One examination's headline numbers, with its series colour."""
        def __init__(self, name, tag, k, has, col, soft, w):
            super().__init__()
            self.name, self.tag, self.k, self.has, self.col, self.soft, self.w = name, tag, k, has, col, soft, w

        def wrap(self, aw, ah):
            return self.w, 92

        def draw(self):
            cv, w, h = self.canv, self.w, 92
            cv.setStrokeColor(hx(LINE)); cv.setFillColor(colors.white); cv.setLineWidth(.8)
            cv.roundRect(0, 0, w, h, 10, stroke=1, fill=1)
            # coloured header band
            p = cv.beginPath(); r = 10
            p.moveTo(0, h - 30); p.lineTo(0, h - r); p.arcTo(0, h - 2 * r, 2 * r, h, 180, -90)
            p.lineTo(w - r, h); p.arcTo(w - 2 * r, h - 2 * r, w, h, 90, -90); p.lineTo(w, h - 30); p.close()
            cv.setFillColor(hx(self.soft)); cv.drawPath(p, stroke=0, fill=1)
            cv.setFillColor(hx(self.col)); cv.rect(0, h - 30, w, 1.2, stroke=0, fill=1)
            cv.circle(14, h - 15, 3.6, stroke=0, fill=1)
            cv.setFillColor(hx(INK)); cv.setFont(F['Display'], 11)
            tag = self.tag.upper()
            tag_w = stringWidth(tag, F['BodyBold'], 6.4) + len(tag) * .7 + 12
            cv.drawString(24, h - 19, fit(self.name, F['Display'], 11, w - 40 - tag_w))
            cv.setFillColor(hx(self.col)); cv.roundRect(w - 10 - tag_w, h - 22, tag_w, 13, 6.5, stroke=0, fill=1)
            cv.setFillColor(colors.white); cv.setFont(F['BodyBold'], 6.4)
            cv.drawCentredString(w - 10 - tag_w / 2, h - 17.6, tag, charSpace=.7)
            k = self.k if self.has else {}
            stats = [(_num(k.get('candidates')), 'Candidates'),
                     (_num(k.get('avg_pct'), '%'), 'Avg score'),
                     (_num(k.get('benchmark_rate'), '%'), 'Benchmark'),
                     (_num(k.get('core_credit_rate'), '%'), 'Eng & Maths')]
            if not self.has:
                cv.setFillColor(hx(MUTED)); cv.setFont(F['Body'], 8.4)
                cv.drawString(14, 26, 'No results recorded for this year.')
                return
            # the candidate count needs less room than the percentages
            widths = [.23, .257, .257, .256]
            cw_all = w - 20
            for i, (v, lab) in enumerate(stats):
                x = 12 + sum(widths[:i]) * cw_all
                cw = widths[i] * cw_all
                if i:
                    cv.setStrokeColor(hx(LINE2)); cv.line(x - 4, 14, x - 4, 50)
                vs = 15
                while vs > 10 and stringWidth(v, F['Display'], vs) > cw - 10:
                    vs -= .5
                cv.setFillColor(hx(INK)); cv.setFont(F['Display'], vs)
                cv.drawString(x + 2, 31, v)
                cv.setFillColor(hx(MUTED)); cv.setFont(F['BodyBold'], 5.8)
                cv.drawString(x + 2, 19, fit(lab.upper(), F['BodyBold'], 5.8, cw - 10 - len(lab) * .4),
                              charSpace=.4)

    class Measures(Flowable):
        """Head-to-head rows: label · State value + bar · Federal value + bar · gap."""
        row_h = 25 * K

        def __init__(self, items):
            super().__init__()
            self.items = items

        def wrap(self, aw, ah):
            self.w = aw
            self.h = 20 + self.row_h * len(self.items) + 4
            return aw, self.h

        def draw(self):
            cv, w, h = self.canv, self.w, self.h
            cv.setStrokeColor(hx(LINE)); cv.setFillColor(colors.white); cv.setLineWidth(.8)
            cv.roundRect(0, 0, w, h, 10, stroke=1, fill=1)
            lab_w = 150 * K
            gap_w = 78 * K
            col_w = (w - lab_w - gap_w - 24) / 2
            xs = [12, 12 + lab_w, 12 + lab_w + col_w, 12 + lab_w + 2 * col_w]
            cv.setFillColor(hx(MUTED)); cv.setFont(F['BodyBold'], 6.2 * K)
            cv.drawString(xs[0], h - 14, 'MEASURE', charSpace=.6)
            cv.drawString(xs[1] + 4, h - 14, fit('%s · STATE' % sn.upper(), F['BodyBold'], 6.2 * K, col_w - 12), charSpace=.6)
            cv.drawString(xs[2] + 4, h - 14, fit('%s · FEDERAL' % fn.upper(), F['BodyBold'], 6.2 * K, col_w - 12), charSpace=.6)
            cv.drawRightString(w - 12, h - 14, 'STATE − FEDERAL', charSpace=.6)
            y = h - 20
            for i, m in enumerate(self.items):
                top = y - i * self.row_h
                if i % 2 == 1:
                    cv.setFillColor(hx('#fafbfd')); cv.rect(1, top - self.row_h, w - 2, self.row_h, stroke=0, fill=1)
                cv.setStrokeColor(hx(LINE2)); cv.setLineWidth(.6); cv.line(12, top, w - 12, top)
                mid = top - self.row_h / 2
                cv.setFillColor(hx(INK)); cv.setFont(F['BodyBold'], 8 * K)
                cv.drawString(xs[0], mid - 3 * K, fit(m['label'], F['BodyBold'], 8 * K, lab_w - 8))
                a, b = m['a'], m['b']
                lead = None if m['gap'] is None or abs(m['gap']) < .05 else ('a' if m['gap'] > 0 else 'b')
                for x0, v, col, soft, who in ((xs[1], a, S1, S1_SOFT, 'a'), (xs[2], b, S2, S2_SOFT, 'b')):
                    txt = _num(v, m['unit'])
                    bold = lead == who
                    cv.setFillColor(hx(INK if v is not None else MUTED))
                    cv.setFont(F['Display'] if bold else F['BodyBold'], 9.4 * K)
                    tw = 44 * K
                    cv.drawRightString(x0 + tw, mid - 3.2 * K, txt)
                    if m['bar'] and v is not None:
                        bx, bw_ = x0 + tw + 8, col_w - tw - 20
                        cv.setFillColor(hx(soft)); cv.roundRect(bx, mid - 3, bw_, 6, 3, stroke=0, fill=1)
                        cv.setFillColor(hx(col))
                        fw = bw_ * max(0, min(100, v)) / 100
                        if fw > .5:
                            cv.roundRect(bx, mid - 3, max(fw, 6), 6, 3, stroke=0, fill=1)
                # gap pill
                g = m['gap']
                if g is None:
                    cv.setFillColor(hx(MUTED)); cv.setFont(F['Body'], 8 * K)
                    cv.drawRightString(w - 12, mid - 3, '—')
                else:
                    unit = ' pts' if m['unit'] == '%' else ''
                    txt = _signed(g if m['key'] != 'avg_credits' else round(g, 1), unit) if m['key'] != 'candidates' else (
                        ('+%d' % g) if g > 0 else ('−%d' % abs(g)) if g < 0 else '0')
                    if lead is None:
                        col, soft = MUTED, BG
                    else:
                        col, soft = (S1, S1_SOFT) if lead == 'a' else (S2, S2_SOFT)
                    cv.setFont(F['BodyBold'], 7.6 * K)
                    pw = stringWidth(txt, F['BodyBold'], 7.6 * K) + 14
                    cv.setFillColor(hx(soft)); cv.roundRect(w - 12 - pw, mid - 6.5 * K, pw, 13 * K, 6.5 * K, stroke=0, fill=1)
                    cv.setFillColor(hx(col)); cv.drawCentredString(w - 12 - pw / 2, mid - 2.7 * K, txt)

    class Insight(Flowable):
        def __init__(self, item, w):
            super().__init__()
            self.item, self.w = item, w

        def wrap(self, aw, ah):
            return self.w, 54

        def draw(self):
            cv = self.canv
            head, val, sub = self.item
            cv.setStrokeColor(hx(LINE)); cv.setFillColor(colors.white); cv.setLineWidth(.8)
            cv.roundRect(0, 0, self.w, 54, 9, stroke=1, fill=1)
            accent = S1 if sn in head else S2 if fn in head else C['primary']
            cv.setFillColor(hx(accent)); cv.roundRect(0, 10, 3, 34, 1.5, stroke=0, fill=1)
            cv.setFillColor(hx(MUTED)); cv.setFont(F['BodyBold'], 6.2)
            cv.drawString(11, 41, fit(head.upper(), F['BodyBold'], 6.2, self.w - 30), charSpace=.6)
            sz = 10.5
            while sz > 7 and stringWidth(val, F['Display'], sz) > self.w - 20:
                sz -= .5
            cv.setFillColor(hx(INK)); cv.setFont(F['Display'], sz)
            cv.drawString(11, 25, fit(val, F['Display'], sz, self.w - 20))
            cv.setFillColor(hx(INK2)); cv.setFont(F['Body'], 7)
            cv.drawString(11, 11, fit(sub, F['Body'], 7, self.w - 18))

    class PairChart(Flowable):
        """Grouped bars: credit rate per subject, State beside Federal."""
        def __init__(self, rows, w):
            super().__init__()
            self.rows, self.w = rows, w

        def wrap(self, aw, ah):
            self.h = 196
            return self.w, self.h

        def draw(self):
            cv, w, h = self.canv, self.w, self.h
            cv.setStrokeColor(hx(LINE)); cv.setFillColor(colors.white); cv.setLineWidth(.8)
            cv.roundRect(0, 0, w, h, 10, stroke=1, fill=1)
            n = len(self.rows)
            left, right, base, top = 34, 12, 24, h - 18
            inner = w - left - right
            slot = inner / n
            bw = min(15, slot * .36)
            # y grid 0/25/50/75/100
            cv.setFont(F['Body'], 6.2)
            for t in (0, 25, 50, 75, 100):
                y = base + (top - base) * t / 100
                cv.setStrokeColor(hx(LINE if t == 0 else LINE2)); cv.setLineWidth(.7 if t == 0 else .5)
                cv.line(left, y, w - right, y)
                cv.setFillColor(hx(MUTED)); cv.drawRightString(left - 5, y - 2, '%d%%' % t)
            for i, r in enumerate(self.rows):
                cx = left + slot * (i + .5)
                for j, (v, col) in enumerate(((r['state_credit'], S1), (r['federal_credit'], S2))):
                    x = cx - bw - 1 if j == 0 else cx + 1
                    bh = (top - base) * max(0, min(100, v or 0)) / 100
                    cv.setFillColor(hx(col))
                    if bh > .5:
                        cv.roundRect(x, base, bw, bh, min(2.5, bw / 3), stroke=0, fill=1)
                        cv.rect(x, base, bw, min(2.5, bh), stroke=0, fill=1)
                    if n <= 12 and bw >= 9:
                        cv.setFillColor(hx(INK2)); cv.setFont(F['BodyBold'], 5.6)
                        cv.drawCentredString(x + bw / 2, base + bh + 2.5, '%d' % round(v or 0))
                cv.setFillColor(hx(MUTED)); cv.setFont(F['BodyBold'], 6.2 if n <= 12 else 5.6)
                cv.drawCentredString(cx, base - 10, r['code'])

    class TrendChart(Flowable):
        """Met-benchmark rate by year, one line per examination."""
        def __init__(self, data, w):
            super().__init__()
            self.data, self.w = data, w

        def wrap(self, aw, ah):
            self.h = 150
            return self.w, self.h

        def draw(self):
            cv, w, h = self.canv, self.w, self.h
            cv.setStrokeColor(hx(LINE)); cv.setFillColor(colors.white); cv.setLineWidth(.8)
            cv.roundRect(0, 0, w, h, 10, stroke=1, fill=1)
            left, right, base, top = 38, 24, 26, h - 16
            pad = 26                     # keep the first / last points clear of the axis
            n = len(self.data)
            step = (w - left - right - 2 * pad) / max(1, n - 1)
            cv.setFont(F['Body'], 6.2)
            for t in (0, 25, 50, 75, 100):
                y = base + (top - base) * t / 100
                cv.setStrokeColor(hx(LINE if t == 0 else LINE2)); cv.setLineWidth(.7 if t == 0 else .5)
                cv.line(left, y, w - right, y)
                cv.setFillColor(hx(MUTED)); cv.drawRightString(left - 6, y - 2, '%d%%' % t)
            for i, (yr, _a, _b) in enumerate(self.data):
                cv.setFillColor(hx(MUTED)); cv.setFont(F['BodyBold'], 6.8)
                cv.drawCentredString(left + pad + i * step, base - 13, str(yr))
            for idx, col in ((1, S1), (2, S2)):
                pts = [(left + pad + i * step, base + (top - base) * max(0, min(100, d[idx])) / 100, d)
                       for i, d in enumerate(self.data) if d[idx] is not None]
                cv.setStrokeColor(hx(col)); cv.setLineWidth(1.8)
                for (x1, y1, _), (x2, y2, _) in zip(pts, pts[1:]):
                    cv.line(x1, y1, x2, y2)
                for x, y, d in pts:
                    v, other = d[idx], d[3 - idx]
                    cv.setFillColor(colors.white); cv.setStrokeColor(hx(col)); cv.setLineWidth(1.4)
                    cv.circle(x, y, 3, stroke=1, fill=1)
                    # the higher of the two figures is labelled above its point, the lower below
                    above = other is None or v > other or (v == other and idx == 1)
                    cv.setFillColor(hx(col)); cv.setFont(F['BodyBold'], 6.6)
                    cv.drawCentredString(x, y + (6 if above else -11), '%d%%' % round(v))

    def cards_row(items, h_pad=8):
        n = len(items)
        cw = (avail_w - h_pad * (n - 1)) / n
        t = Table([[it(cw) for it in items]], colWidths=[cw + h_pad] * (n - 1) + [cw])
        t.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                               ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                               ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        return t

    # ---- story ------------------------------------------------------------------
    story = [NextPageTemplate('later'), Paragraph(esc(doc['title']), st_title)]
    if doc.get('subtitle'):
        story += [Spacer(1, 2), Paragraph(esc(doc['subtitle']), st_sub)]
    story.append(Spacer(1, 12))
    story.append(cards_row([
        lambda w: ExamCard(sn, 'State', doc['state'], doc['has_state'], S1, S1_SOFT, w),
        lambda w: ExamCard(fn, 'Federal', doc['federal'], doc['has_federal'], S2, S2_SOFT, w)], 10))

    if doc['measures']:
        story += [Spacer(1, 14), Section('Head to head', 'benchmark = %s · bars on a 0–100%% scale' % doc.get('bench_label', '')),
                  Spacer(1, 4), Measures(doc['measures'])]
    if doc.get('insights'):
        story += [Spacer(1, 12), cards_row([(lambda x: (lambda w: Insight(x, w)))(x) for x in doc['insights']])]
    if not (doc['has_state'] and doc['has_federal']):
        missing = fn if doc['has_state'] else sn
        story += [Spacer(1, 12), Paragraph(
            'Enter the %s results for %s to see the subject-by-subject comparison.' % (esc(missing), doc['year']),
            st_note)]

    subjects = doc['subjects']
    if subjects:
        block = [Section('Subject credit rate — both examinations',
                         '%d shared subject%s' % (len(subjects), '' if len(subjects) == 1 else 's')),
                 Spacer(1, 4), Key(), Spacer(1, 6), PairChart(subjects, avail_w)]
        if doc.get('summary'):
            block += [Spacer(1, 6), Paragraph(esc(doc['summary']), st_note)]
        story += [Spacer(1, 16), KeepTogether(block)]

        st_h = ParagraphStyle('h', fontName=F['BodyBold'], fontSize=fs * .8, leading=fs, textColor=hx(MUTED))
        st_hr = ParagraphStyle('hr', parent=st_h, alignment=2)
        st_r = ParagraphStyle('r', parent=st_cell, alignment=2)
        st_rb = ParagraphStyle('rb', parent=st_r, fontName=F['BodyBold'], textColor=hx(INK))
        st_sb = ParagraphStyle('sb', parent=st_cell, fontName=F['BodyBold'], textColor=hx(INK))
        head = [Paragraph('#', st_h), Paragraph('SUBJECT', st_h),
                Paragraph('<font color="%s">STATE CREDIT</font>' % S1, st_hr),
                Paragraph('<font color="%s">FEDERAL CREDIT</font>' % S2, st_hr),
                Paragraph('GAP (PTS)', st_hr), Paragraph('STATE MEAN', st_hr), Paragraph('FEDERAL MEAN', st_hr)]

        class Gap(Flowable):
            def __init__(self, v):
                super().__init__()
                self.v = v

            def wrap(self, aw, ah):
                self.aw = aw
                return aw, 12 * K

            def draw(self):
                cv, v = self.canv, self.v
                if abs(v) < .05:
                    col, soft, txt = MUTED, BG, 'Equal'
                else:
                    col, soft = (S1, S1_SOFT) if v > 0 else (S2, S2_SOFT)
                    txt = '%s %s' % ('State' if v > 0 else 'Federal', _signed(abs(v)).lstrip('+'))
                cv.setFont(F['BodyBold'], 7 * K)
                pw = stringWidth(txt, F['BodyBold'], 7 * K) + 12
                cv.setFillColor(hx(soft)); cv.roundRect(self.aw - pw, 0, pw, 12 * K, 6 * K, stroke=0, fill=1)
                cv.setFillColor(hx(col)); cv.drawCentredString(self.aw - pw / 2, 3.3 * K, txt)

        def pct(v):
            return '—' if v is None else '%.1f%%' % v

        data = [head]
        for i, r in enumerate(subjects, 1):
            sa, fb = r['state_credit'], r['federal_credit']
            data.append([Paragraph(str(i), st_cell),
                         Paragraph('%s <font color="%s" size="%.1f">%s</font>' % (
                             esc(r['subject']), MUTED, fs * .78, esc(r['code'])), st_sb),
                         Paragraph(pct(sa), st_rb if sa > fb else st_r),
                         Paragraph(pct(fb), st_rb if fb > sa else st_r),
                         Gap(r['diff']), Paragraph(pct(r['state_mean']), st_r),
                         Paragraph(pct(r['federal_mean']), st_r)])
        fixed = [20 * K, None, 66 * K, 72 * K, 78 * K, 56 * K, 62 * K]
        flex = avail_w - sum(x for x in fixed if x)
        widths = [flex if x is None else x for x in fixed]
        t = Table(data, colWidths=widths, repeatRows=1)
        sty = [('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
               ('TOPPADDING', (0, 0), (-1, -1), 4.5 * K), ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5 * K),
               ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
               ('LINEBELOW', (0, 0), (-1, 0), .8, hx(LINE)), ('BACKGROUND', (0, 0), (-1, 0), hx(BG)),
               ('LINEBELOW', (0, 1), (-1, -1), .5, hx(LINE2))]
        for i in range(2, len(data), 2):
            sty.append(('BACKGROUND', (0, i), (-1, i), hx('#fbfcfd')))
        t.setStyle(TableStyle(sty))
        story += [Spacer(1, 12), t]

    if doc.get('trend'):
        story += [Spacer(1, 16), KeepTogether([
            Section('Met-benchmark trend', doc.get('bench_label') or ''), Spacer(1, 4), Key(), Spacer(1, 6),
            TrendChart(doc['trend'], avail_w)])]
    if doc.get('has_state') and doc.get('has_federal'):
        story += [Spacer(1, 10), Paragraph(
            'Each examination is graded on its own scheme. Gaps compare rates, not raw grades; '
            'correlation uses each shared candidate\'s average grade point, scaled to the exam\'s own grading.',
            st_note)]

    spec = {'school': doc['school'], 'colors': C, 'generated': doc.get('generated'),
            'doc_tag': doc['doc_tag'], 'subtitle': '', 'prepared_by': doc.get('prepared_by')}
    canvas_cls = SLE.numbered_canvas(spec, PW, PH, margin, head_h, doc['footer_title'],
                                     note_text='Confidential — for school use')
    buf = io.BytesIO()
    d = BaseDocTemplate(buf, pagesize=(PW, PH), leftMargin=margin, rightMargin=margin,
                        topMargin=margin, bottomMargin=margin, title=doc['title'],
                        author=doc['school'].get('name') or '', creator='Exam comparison export')
    first = Frame(margin, foot_h + 14, avail_w, PH - head_h - foot_h - 14, id='f1',
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    later = Frame(margin, foot_h + 14, avail_w, PH - head2_h - foot_h - 14, id='f2',
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    d.addPageTemplates([PageTemplate('first', [first]), PageTemplate('later', [later])])
    d.build(story, canvasmaker=canvas_cls)
    return buf.getvalue()
