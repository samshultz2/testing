"""Branded exam-results documents — Students List and Subject Analysis.

One design for every external exam (WAEC, NECO, JSS3 BECE, Basic Common
Entrance / NCEE): the student-export letterhead, four summary tiles, a grade
key that follows the exam's own grading scale, a calm table (ink + the
school's colour, red only for fails) and, for the subject analysis, a credit
rate chart and three highlight cards. PDF is drawn with reportlab, the image is
the PDF rasterised, and Word mirrors the same structure.

Callers describe the exam with a :class:`Scale` and hand over plain candidate
/ subject data; :func:`students_doc` / :func:`subjects_doc` turn that into a
document dict that :func:`render_pdf` / :func:`render_images` /
:func:`render_docx` draw.
"""
from __future__ import annotations

import io
import math

from utils import student_list_export as SLE

KINDS = ('d', 'c', 'p', 'f')        # distinction, credit, pass, fail
FAIL = '#b91c1c'
PASS_INK = '#94a3b8'
DASH = '#cbd5e1'


# --------------------------------------------------------------------------- #
# Grading scale
# --------------------------------------------------------------------------- #
class Scale:
    """An exam's grades (best first), each with a kind (d/c/p/f) and points
    (higher is better)."""

    def __init__(self, grades, kinds, points=None):
        self.grades = list(grades)
        self.kinds = dict(kinds)
        n = len(self.grades)
        self.points = dict(points) if points else {g: n - i for i, g in enumerate(self.grades)}

    def kind(self, g):
        return self.kinds.get(g, 'f')

    def span(self, kinds):
        gs = [g for g in self.grades if self.kind(g) in kinds]
        if not gs:
            return ''
        return gs[0] if len(gs) == 1 else '%s–%s' % (gs[0], gs[-1])

    def key(self):
        """[(label, kind)] for the grade key, e.g. ('A1–B3', 'd')."""
        return [(self.span((k,)), k) for k in KINDS if self.span((k,))]

    @property
    def top_grades(self):
        return [g for g in self.grades if self.kind(g) == 'd']


WAEC_SCALE = Scale(['A1', 'B2', 'B3', 'C4', 'C5', 'C6', 'D7', 'E8', 'F9'],
                   {'A1': 'd', 'B2': 'd', 'B3': 'd', 'C4': 'c', 'C5': 'c', 'C6': 'c',
                    'D7': 'p', 'E8': 'p', 'F9': 'f'})

KIND_NAMES = {'d': 'Distinction', 'c': 'Credit', 'p': 'Pass', 'f': 'Fail'}
_SCHEME_KIND = {'distinction': 'd', 'credit': 'c', 'pass': 'p', 'fail': 'f'}


def scale_from_scheme(scheme):
    """A :class:`Scale` from a JSS3 / Basic exam scheme."""
    return Scale(scheme.grades, {g: _SCHEME_KIND.get(scheme.kind_of(g) or 'fail', 'f') for g in scheme.grades},
                 {g: scheme.grade_points(g) for g in scheme.grades})


def is_core(subject):
    s = (subject or '').strip().lower()
    return s.startswith('english') or s in ('mathematics', 'maths', 'math', 'general mathematics')


def _core_key(subject):
    s = (subject or '').strip().lower()
    if s.startswith('english'):
        return 'eng'
    if s in ('mathematics', 'maths', 'math', 'general mathematics'):
        return 'mth'
    return None


def _pct(n, d):
    return round(n / d * 100, 1) if d else 0.0


def _fmt(v, nd=1):
    if v is None:
        return '—'
    if isinstance(v, float):
        return ('%.' + str(nd) + 'f') % v
    return str(v)


def _signed(v):
    return ('+%.1f' % v) if v >= 0 else ('−%.1f' % abs(v))


# --------------------------------------------------------------------------- #
# Students list
# --------------------------------------------------------------------------- #
STUDENT_ORDER = ['rank', 'gender', 'grade_counts', 'allgrades', 'distinctions', 'credits', 'passes',
                 'fails', 'avg', 'avgpct', 'total', 'grades', 'core', 'benchmark', 'placement']


def students_doc(ctx, cands, cols, scale):
    """Document dict for the Students List.

    ``ctx``: school, colors, prepared_by, generated, tag, exam (e.g. 'WASSCE
    2026'), cls ('SSS3'), detail (extra subtitle bits), bench_min (credits for
    the benchmark, default 5), rank_note, sort (True → rank by credits then
    average points here; False → keep the caller's order / ``position``).

    ``cands``: dicts with name, student_id, exam_no, gender, results
    [(subject, grade)], and optionally position, avg_pct, total, placement.

    ``cols``: selected column keys — rank, student_id, exam_no, gender,
    g:<grade>, allgrades, distinctions, credits, passes, fails, avg, avgpct,
    total, grades, core, benchmark, placement.
    """
    from utils.broadsheet_export import abbreviate_subjects
    cols = set(cols)
    bench_min = ctx.get('bench_min', 5)
    subjects = sorted({s for c in cands for s, _g in c['results']})
    codes, legend = abbreviate_subjects(subjects)
    code_of = dict(zip(subjects, codes))

    rows = []
    for c in cands:
        res = sorted(c['results'], key=lambda r: (0 if _core_key(r[0]) == 'eng' else 1 if _core_key(r[0]) == 'mth' else 2, r[0]))
        counts = {g: 0 for g in scale.grades}
        for _s, g in res:
            if g in counts:
                counts[g] += 1
        k = {kk: sum(n for g, n in counts.items() if scale.kind(g) == kk) for kk in KINDS}
        credits = k['d'] + k['c']
        core = {}
        for s, g in res:
            ck = _core_key(s)
            if ck:
                core[ck] = scale.kind(g) in ('d', 'c')
        core_ok = c['core'] if 'core' in c else (bool(core.get('eng')) and bool(core.get('mth')))
        bench_ok = c['bench'] if 'bench' in c else (core_ok and credits >= bench_min)
        pts = [scale.points.get(g, 0) for _s, g in res]
        rows.append({
            'c': c, 'res': res, 'counts': counts, 'dist': k['d'], 'credits': credits,
            'passes': credits + k['p'], 'fails': k['f'], 'n': len(res),
            'avg': round(sum(pts) / len(pts), 2) if pts else 0.0,
            'core': core_ok, 'bench': bench_ok,
        })
    if ctx.get('sort', True):
        rows.sort(key=lambda r: (-r['credits'], -r['avg'], r['c']['name'].lower()))
        for i, r in enumerate(rows, 1):
            r['pos'] = i
    else:
        for i, r in enumerate(rows, 1):
            r['pos'] = r['c'].get('position') or i

    # Columns, in the canonical order.
    columns = []
    if 'rank' in cols:
        columns.append({'key': 'pos', 'label': 'Pos', 'kind': 'pos'})
    columns.append({'key': 'name', 'label': 'Candidate', 'kind': 'name'})
    if 'gender' in cols:
        columns.append({'key': 'gender', 'label': 'Sex', 'kind': 'text', 'center': True})
    picked = [g for g in scale.grades if 'g:' + g in cols]
    if 'allgrades' in cols:
        picked = list(scale.grades)
    for g in picked:
        columns.append({'key': 'g:' + g, 'label': g, 'kind': 'num'})
    if 'distinctions' in cols:
        columns.append({'key': 'dist', 'label': 'Dist.', 'kind': 'num'})
    if 'credits' in cols:
        columns.append({'key': 'credits', 'label': 'Credits', 'kind': 'frac'})
    if 'passes' in cols:
        columns.append({'key': 'passes', 'label': 'Passes', 'kind': 'frac'})
    if 'fails' in cols:
        columns.append({'key': 'fails', 'label': 'Fails', 'kind': 'num'})
    if 'avg' in cols:
        columns.append({'key': 'avg', 'label': 'Avg pts', 'kind': 'dec'})
    if 'avgpct' in cols:
        columns.append({'key': 'avgpct', 'label': 'Avg %', 'kind': 'dec'})
    if 'total' in cols:
        columns.append({'key': 'total', 'label': 'Total', 'kind': 'dec'})
    if 'grades' in cols:
        columns.append({'key': 'grades', 'label': 'Subject grades', 'kind': 'grades'})
    if 'core' in cols:
        columns.append({'key': 'core', 'label': 'Eng + Maths', 'kind': 'flag', 'yes': 'Yes', 'no': 'No'})
    if 'benchmark' in cols:
        columns.append({'key': 'bench', 'label': ctx.get('bench_head') or '%d cr. + E/M' % bench_min, 'kind': 'flag',
                        'yes': 'Met', 'no': 'Not met'})
    if 'placement' in cols:
        columns.append({'key': 'placement', 'label': 'Placement', 'kind': 'text'})

    out_rows = []
    for r in rows:
        c = r['c']
        sub = []
        if 'student_id' in cols and c.get('student_id'):
            sub.append(c['student_id'])
        if 'exam_no' in cols and c.get('exam_no'):
            sub.append(c['exam_no'])
        row = {'pos': r['pos'], 'name': (c['name'], ' · '.join(sub)),
               'gender': (c.get('gender') or '')[:1].upper(),
               'dist': r['dist'], 'credits': (r['credits'], r['n']), 'passes': (r['passes'], r['n']),
               'fails': r['fails'], 'avg': '%.2f' % r['avg'],
               'avgpct': _fmt(c.get('avg_pct')), 'total': _fmt(c.get('total')),
               'grades': [(code_of[s], g, scale.kind(g)) for s, g in r['res']],
               'core': r['core'], 'bench': r['bench'], 'placement': c.get('placement') or ''}
        for g in scale.grades:
            row['g:' + g] = r['counts'][g]
        out_rows.append(row)

    n = len(rows)
    entries = sum(r['n'] for r in rows)
    dist = sum(r['dist'] for r in rows)
    credits = sum(r['credits'] for r in rows)
    bench = sum(1 for r in rows if r['bench'])
    dspan, cspan = scale.span(('d',)), scale.span(('d', 'c'))
    kpis = [
        {'v': str(n), 'l': 'Candidates', 's': '%d subject entries' % entries},
        {'v': str(dist), 'l': 'Distinctions (%s)' % dspan, 's': '%d%% of all grades' % round(_pct(dist, entries))},
        {'v': '%.1f%%' % _pct(credits, entries), 'l': 'Credit rate (%s)' % cspan, 's': '%d credits' % credits},
        {'v': '%.1f%%' % _pct(bench, n), 'l': ctx.get('bench_label') or '%d credits incl. Eng + Maths' % bench_min,
         's': '%d of %d candidates' % (bench, n)},
    ]
    used = [x for x in legend if x[0] in {g[0] for r in out_rows for g in r['grades']}]
    bits = [ctx.get('cls'), ctx.get('detail'), '%d subjects' % len(subjects) if subjects else None,
            ctx.get('rank_note') or 'ranked by credits, then average grade points']
    return {
        'type': 'students', 'school': ctx['school'], 'colors': ctx['colors'],
        'generated': ctx.get('generated'), 'prepared_by': ctx.get('prepared_by'),
        'doc_tag': ctx.get('tag') or 'EXAM RESULTS',
        'title': '%s — Results' % ctx['exam'], 'subtitle': ' · '.join(b for b in bits if b),
        'footer_title': ' · '.join(b for b in (ctx['exam'], ctx.get('cls')) if b),
        'kpis': kpis, 'key': scale.key(), 'columns': columns, 'rows': out_rows,
        'codes': used if 'grades' in cols else [],
    }


# --------------------------------------------------------------------------- #
# Subject analysis
# --------------------------------------------------------------------------- #
def subjects_doc(ctx, by_subject, cols, scale, prev_rates=None, prev_year=None, mean_pct=None):
    """Document dict for the Subject Analysis.

    ``by_subject``: {subject: [grade, …]}. ``prev_rates``: {subject: credit
    rate %} for ``prev_year`` (for the "vs" column, KPI and Most improved).
    ``mean_pct``: optional {subject: mean score %}.

    ``cols``: total, g:<grade>, spread, crate, drate, prate, frate, mean,
    avgpts, delta, chart.
    """
    from utils.broadsheet_export import abbreviate_subjects
    cols = set(cols)
    prev_rates = prev_rates or {}
    rows = []
    for subject, grades in by_subject.items():
        n = len(grades)
        if not n:
            continue
        counts = {g: 0 for g in scale.grades}
        for g in grades:
            if g in counts:
                counts[g] += 1
        k = {kk: sum(v for g, v in counts.items() if scale.kind(g) == kk) for kk in KINDS}
        cr = _pct(k['d'] + k['c'], n)
        rows.append({
            'subject': subject, 'core': is_core(subject), 'n': n, 'counts': counts, 'k': k,
            'cr': cr, 'dr': _pct(k['d'], n), 'pr': _pct(n - k['f'], n), 'fr': _pct(k['f'], n),
            'ap': round(sum(scale.points.get(g, 0) for g in grades) / n, 2),
            'mean': (mean_pct or {}).get(subject),
            'delta': round(cr - prev_rates[subject], 1) if subject in prev_rates else None,
        })
    rows.sort(key=lambda r: (-r['cr'], -r['ap'], r['subject']))
    codes, _legend = abbreviate_subjects([r['subject'] for r in rows])
    for r, code in zip(rows, codes):
        r['code'] = code
    has_prev = any(r['delta'] is not None for r in rows)

    columns = [{'key': 'rank', 'label': '#', 'kind': 'rank'},
               {'key': 'subject', 'label': 'Subject', 'kind': 'subject'}]
    if 'total' in cols:
        columns.append({'key': 'n', 'label': 'Entries', 'kind': 'num'})
    for g in scale.grades:
        if 'g:' + g in cols:
            columns.append({'key': 'g:' + g, 'label': g, 'kind': 'gcount'})
    if 'spread' in cols:
        columns.append({'key': 'spread', 'label': 'Spread', 'kind': 'spread'})
    if 'crate' in cols:
        columns.append({'key': 'cr', 'label': 'Credit', 'kind': 'pctb'})
    if 'drate' in cols:
        columns.append({'key': 'dr', 'label': 'Dist.', 'kind': 'pct'})
    if 'prate' in cols:
        columns.append({'key': 'pr', 'label': 'Pass', 'kind': 'pct'})
    if 'frate' in cols:
        columns.append({'key': 'fr', 'label': 'Fail', 'kind': 'pct'})
    if 'mean' in cols:
        columns.append({'key': 'mean', 'label': 'Mean %', 'kind': 'pct'})
    if 'avgpts' in cols:
        columns.append({'key': 'ap', 'label': 'Avg pts', 'kind': 'dec'})
    if 'delta' in cols and has_prev:
        columns.append({'key': 'delta', 'label': 'vs %s' % prev_year, 'kind': 'delta'})

    def as_row(r, rank):
        row = {'rank': rank, 'subject': (r['subject'], r['core']), 'n': r['n'],
               'spread': tuple(r['k'][kk] for kk in KINDS), 'cr': r['cr'], 'dr': r['dr'],
               'pr': r['pr'], 'fr': r['fr'], 'mean': r['mean'], 'ap': '%.2f' % r['ap'],
               'delta': r['delta']}
        for g in scale.grades:
            row['g:' + g] = r['counts'][g]
        return row

    out_rows = [as_row(r, i) for i, r in enumerate(rows, 1)]
    N = sum(r['n'] for r in rows)
    K = {kk: sum(r['k'][kk] for r in rows) for kk in KINDS}
    total = {'rank': '', 'subject': ('All subjects', False), 'n': N,
             'spread': tuple(K[kk] for kk in KINDS), 'cr': _pct(K['d'] + K['c'], N),
             'dr': _pct(K['d'], N), 'pr': _pct(N - K['f'], N), 'fr': _pct(K['f'], N),
             'mean': None, 'ap': '%.2f' % (sum(r['ap'] * r['n'] for r in rows) / N if N else 0)}
    for g in scale.grades:
        total['g:' + g] = sum(r['counts'][g] for r in rows)
    means = [(r['mean'], r['n']) for r in rows if r['mean'] is not None]
    if means:
        total['mean'] = round(sum(m * n for m, n in means) / sum(n for _m, n in means), 1)
    # Overall change: this year's rate vs last year's over the same subjects.
    overall_delta = None
    if has_prev:
        both = [r for r in rows if r['delta'] is not None]
        cur = _pct(sum(r['k']['d'] + r['k']['c'] for r in both), sum(r['n'] for r in both))
        prev = sum(prev_rates[r['subject']] * r['n'] for r in both) / sum(r['n'] for r in both)
        overall_delta = round(cur - prev, 1)
    total['delta'] = overall_delta

    dspan, cspan = scale.span(('d',)), scale.span(('d', 'c'))
    fail_label = scale.span(('f',)) or 'Fail'
    kpis = [
        {'v': str(len(rows)), 'l': 'Subjects', 's': '%d entries' % N},
        {'v': '%.1f%%' % total['cr'], 'l': 'Credit rate (%s)' % cspan,
         's': ('%s pts vs %s' % (_signed(overall_delta), prev_year)) if overall_delta is not None
         else '%d credits' % (K['d'] + K['c'])},
        {'v': '%.1f%%' % total['dr'], 'l': 'Distinction rate', 's': '%d at %s' % (K['d'], dspan)},
        {'v': '%.1f%%' % total['fr'], 'l': '%s rate' % fail_label, 's': '%d fails in total' % K['f']},
    ]
    insights, chart = [], None
    if 'chart' in cols and rows:
        chart = [(r['code'], r['cr']) for r in rows]
        best, worst = rows[0], rows[-1]
        insights.append(('Strongest subject', best['subject'],
                         '%.1f%% credits · %d distinctions' % (best['cr'], best['k']['d'])))
        if len(rows) > 1:
            insights.append(('Needs attention', worst['subject'],
                             '%.1f%% credits · %d fails' % (worst['cr'], worst['k']['f'])))
        imp = max((r for r in rows if r['delta'] is not None), key=lambda r: r['delta'], default=None)
        if imp is not None and imp['delta'] > 0:
            insights.append(('Most improved', imp['subject'], '%s pts on %s' % (_signed(imp['delta']), prev_year)))
        else:
            most = max(rows, key=lambda r: (r['k']['d'], r['cr']))
            insights.append(('Most distinctions', most['subject'], '%d at %s' % (most['k']['d'], dspan)))
    bits = [ctx.get('cls'), '%d candidates' % ctx['candidates'] if ctx.get('candidates') else None,
            '%d subjects' % len(rows), 'ranked by credit rate (%s)' % cspan,
            ('compared with %s' % prev_year) if has_prev else None]
    return {
        'type': 'subjects', 'school': ctx['school'], 'colors': ctx['colors'],
        'generated': ctx.get('generated'), 'prepared_by': ctx.get('prepared_by'),
        'doc_tag': 'SUBJECT ANALYSIS',
        'title': '%s — Subject Analysis' % ctx['exam'], 'subtitle': ' · '.join(b for b in bits if b),
        'footer_title': ' · '.join(b for b in (ctx['exam'], ctx.get('cls')) if b),
        'kpis': kpis, 'key': scale.key(), 'columns': columns, 'rows': out_rows, 'total': total,
        'chart': chart, 'chart_title': 'Credit rate (%s) by subject' % cspan, 'insights': insights,
    }


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def _grade_color(kind, C):
    return {'d': C['primary'], 'c': SLE.INK, 'p': PASS_INK}.get(kind, FAIL)


def _per_row(n):
    return n if n <= 9 else math.ceil(n / 2)


def render_pdf(doc):
    SLE._register_fonts()
    F = SLE.F
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph, Table,
                                    TableStyle, Spacer, Flowable, NextPageTemplate, KeepTogether)
    from reportlab.pdfbase.pdfmetrics import stringWidth

    C = doc['colors']
    hx = colors.HexColor
    INK, INK2, MUTED, LINE, LINE2, BG, ZEBRA = (SLE.INK, SLE.INK2, SLE.MUTED, SLE.LINE, SLE.LINE2,
                                               SLE.BG, SLE.ZEBRA)
    students = doc['type'] == 'students'
    fs = 8.4 if students else 8.0
    margin = 34
    esc = SLE._esc

    # ---- column widths -----------------------------------------------------
    rows = doc['rows']
    max_subj = max((len(r.get('grades') or []) for r in rows), default=0)
    per_row = _per_row(max_subj) if max_subj else 0
    chip_w = 0
    if students and per_row:
        codes_w = max((stringWidth(g[0], F['BodyBold'], 5.2) for r in rows for g in r['grades']), default=10)
        grade_w = max((stringWidth(g[1], F['Display'], 8.4) for r in rows for g in r['grades']), default=8)
        chip_w = max(codes_w, grade_w) + 4.5

    def head_w(label):
        return stringWidth(label.upper(), F['BodyBold'], fs * .78) + 9

    def text_w(col):
        vals = [str(r.get(col['key']) or '') for r in rows]
        return min(110, max([stringWidth(v, F['Body'], fs) for v in vals] + [0]) + 10)

    fixed = {}
    flex_key = 'name' if students else 'subject'
    for col in doc['columns']:
        k = col['kind']
        w = {'pos': 28, 'rank': 18, 'num': 24, 'gcount': 14, 'frac': 38, 'dec': 34,
             'flag': 44, 'pctb': 42, 'pct': 39, 'delta': 36, 'spread': 68}.get(k)
        if k == 'grades':
            w = per_row * chip_w + 8
        elif k == 'text':
            w = text_w(col)
        elif k in ('name', 'subject'):
            continue
        if k not in ('gcount', 'grades', 'spread'):
            w = max(w, head_w(col['label']))
        fixed[col['key']] = w
    if students:
        names = [stringWidth(r['name'][0], F['BodyBold'], fs * 1.02) for r in rows] + [70]
        name_need = min(max(names) + 12, 170)
    else:
        names = [stringWidth(r['subject'][0], F['BodyBold'], fs) + (24 if r['subject'][1] else 0) for r in rows]
        name_need = min(max(names + [80]) + 10, 128)
    need = sum(fixed.values()) + name_need
    PW, PH = A4
    if need > PW - 2 * margin:
        PW, PH = landscape(A4)
    avail_w = PW - 2 * margin
    flex_w = max(name_need, avail_w - sum(fixed.values()))
    if sum(fixed.values()) + flex_w > avail_w:          # still too wide: squeeze evenly
        scale = (avail_w - flex_w) / sum(fixed.values())
        fixed = {k: v * scale for k, v in fixed.items()}
    col_w = [flex_w if c['key'] == flex_key else fixed[c['key']] for c in doc['columns']]

    head_h, foot_h, head2_h = 112, 40, 46
    spec = {'school': doc['school'], 'colors': C, 'generated': doc.get('generated'),
            'doc_tag': doc['doc_tag'], 'subtitle': '', 'prepared_by': doc.get('prepared_by')}
    canvas_cls = SLE.numbered_canvas(spec, PW, PH, margin, head_h, doc['footer_title'],
                                     note_text='Confidential — for school use')

    # ---- styles & small flowables --------------------------------------------
    st_title = ParagraphStyle('t', fontName=F['Display'], fontSize=19, leading=23, textColor=hx(INK))
    st_sub = ParagraphStyle('s', fontName=F['Body'], fontSize=9.2, leading=12.5, textColor=hx(INK2))
    st_cell = ParagraphStyle('c', fontName=F['Body'], fontSize=fs, leading=fs * 1.25, textColor=hx(INK2))
    st_ctr = ParagraphStyle('cc', parent=st_cell, alignment=1)
    st_rt = ParagraphStyle('cr', parent=st_cell, alignment=2)
    st_head = ParagraphStyle('h', fontName=F['BodyBold'], fontSize=fs * .78, leading=fs, textColor=hx(MUTED))
    st_head_c = ParagraphStyle('hc', parent=st_head, alignment=1)
    st_head_r = ParagraphStyle('hr', parent=st_head, alignment=2)

    class Kpi(Flowable):
        def __init__(self, k, w):
            super().__init__()
            self.k, self.w = k, w

        def wrap(self, aw, ah):
            return self.w, 50

        def draw(self):
            cv = self.canv
            cv.setStrokeColor(hx(LINE)); cv.setFillColor(colors.white); cv.setLineWidth(.8)
            cv.roundRect(0, 0, self.w, 50, 9, stroke=1, fill=1)
            cv.setFillColor(hx(INK)); cv.setFont(F['Display'], 15)
            cv.drawString(10, 31, self.k['v'])
            cv.setFillColor(hx(MUTED)); cv.setFont(F['BodyBold'], 6.2)
            lab = self.k['l'].upper()
            while stringWidth(lab, F['BodyBold'], 6.2) + len(lab) * .4 > self.w - 16 and len(lab) > 4:
                lab = lab[:-2]
            cv.drawString(10, 20, lab, charSpace=.4)
            cv.setFillColor(hx(INK2)); cv.setFont(F['Body'], 7.2)
            cv.drawString(10, 9, self.k.get('s') or '')

    class Legend(Flowable):
        def __init__(self, key, w):
            super().__init__()
            self.key, self.w = key, w

        def wrap(self, aw, ah):
            return self.w, 18

        def draw(self):
            cv = self.canv
            cv.setFillColor(hx(MUTED)); cv.setFont(F['BodyBold'], 6.6)
            cv.drawString(0, 5, 'GRADE KEY', charSpace=.8)
            x = stringWidth('GRADE KEY', F['BodyBold'], 6.6) + 8 * .8 + 12
            for label, kind in self.key:
                w = stringWidth(label, F['Display'], 7.6) + 10
                cv.setStrokeColor(hx(LINE)); cv.setFillColor(colors.white); cv.setLineWidth(.7)
                cv.roundRect(x, 0, w, 14, 4, stroke=1, fill=1)
                cv.setFillColor(hx(_grade_color(kind, C))); cv.setFont(F['Display'], 7.6)
                cv.drawCentredString(x + w / 2, 4.2, label)
                x += w + 5
                cv.setFillColor(hx(INK2)); cv.setFont(F['Body'], 8)
                cv.drawString(x, 4.2, KIND_NAMES[kind])
                x += stringWidth(KIND_NAMES[kind], F['Body'], 8) + 14

    class Pos(Flowable):
        def __init__(self, n):
            super().__init__()
            self.n = n

        def wrap(self, aw, ah):
            self.aw = aw
            return aw, 15

        def draw(self):
            cv = self.canv
            x = (self.aw - 20) / 2
            if isinstance(self.n, int) and self.n <= 3:
                cv.setFillColor(hx(C['soft'])); cv.roundRect(x, 0, 20, 15, 4.5, stroke=0, fill=1)
                cv.setFillColor(hx(C['primary']))
            else:
                cv.setFillColor(hx(INK2))
            cv.setFont(F['Display'], 8.6)
            cv.drawCentredString(x + 10, 4.3, str(self.n))

    class Grades(Flowable):
        def __init__(self, items):
            super().__init__()
            self.items = items

        def wrap(self, aw, ah):
            lines = max(1, math.ceil(len(self.items) / per_row)) if per_row else 1
            self.h = lines * 17.5 - 1.5
            return per_row * chip_w, self.h

        def draw(self):
            cv = self.canv
            for i, (code, g, kind) in enumerate(self.items):
                row, col = divmod(i, per_row)
                x = col * chip_w + chip_w / 2
                y = self.h - row * 17.5
                cv.setFillColor(hx(MUTED)); cv.setFont(F['BodyBold'], 5.2)
                cv.drawCentredString(x, y - 5.6, code)
                cv.setFillColor(hx(_grade_color(kind, C)))
                cv.setFont(F['Display'] if kind != 'p' else F['BodyBold'], 8.4)
                cv.drawCentredString(x, y - 14.6, g)

    class Flag(Flowable):
        def __init__(self, ok, yes, no):
            super().__init__()
            self.ok, self.yes, self.no = ok, yes, no

        def wrap(self, aw, ah):
            self.aw = aw
            return aw, 10

        def draw(self):
            cv = self.canv
            t = self.yes if self.ok else self.no
            font = F['BodySemi'] if self.ok else F['Body']
            tw = stringWidth(t, font, fs * .92) + (9 if self.ok else 0)
            x = (self.aw - tw) / 2
            if self.ok:
                cv.setStrokeColor(hx(INK2)); cv.setLineWidth(1.1)
                p = cv.beginPath(); p.moveTo(x, 4.6); p.lineTo(x + 2.4, 2.2); p.lineTo(x + 6.4, 7.2)
                cv.drawPath(p, stroke=1, fill=0)
                x += 9
            cv.setFillColor(hx(INK2 if self.ok else MUTED)); cv.setFont(font, fs * .92)
            cv.drawString(x, 2.2, t)

    class Spread(Flowable):
        def __init__(self, parts, w):
            super().__init__()
            self.parts, self.w = parts, w

        def wrap(self, aw, ah):
            return self.w, 11

        def draw(self):
            cv = self.canv
            n = sum(self.parts)
            cv.saveState()
            p = cv.beginPath(); p.roundRect(0, 0, self.w, 11, 3)
            cv.clipPath(p, stroke=0, fill=0)
            cv.setFillColor(hx(LINE2)); cv.rect(0, 0, self.w, 11, stroke=0, fill=1)
            fills = [C['primary'], SLE._mix(C['primary'], '#ffffff', .42), '#cbd5e1', '#f87171']
            x = 0
            for v, col in zip(self.parts, fills):
                if not v or not n:
                    continue
                w = self.w * v / n
                cv.setFillColor(hx(col)); cv.rect(x, 0, w, 11, stroke=0, fill=1)
                label = str(v)
                if w > stringWidth(label, F['BodyBold'], 6.4) + 5:
                    cv.setFillColor(hx(INK2) if col == '#cbd5e1' else colors.white)
                    cv.setFont(F['BodyBold'], 6.4)
                    cv.drawCentredString(x + w / 2, 3.4, label)
                x += w
            cv.restoreState()

    class Delta(Flowable):
        def __init__(self, v, bold=False):
            super().__init__()
            self.v, self.bold = v, bold

        def wrap(self, aw, ah):
            self.aw = aw
            return aw, 10

        def draw(self):
            cv = self.canv
            if self.v is None:
                cv.setFillColor(hx(DASH)); cv.setFont(F['Body'], fs)
                cv.drawRightString(self.aw, 2, '—')
                return
            up = self.v >= 0
            t = '%.1f' % abs(self.v)
            font = F['BodyBold']
            tw = stringWidth(t, font, fs * .92)
            x = self.aw - tw
            col = hx(INK2 if up else FAIL)
            cv.setFillColor(col); cv.setFont(font, fs * .92)
            cv.drawString(x, 2, t)
            tx = x - 8.5
            p = cv.beginPath()
            if up:
                p.moveTo(tx, 2.4); p.lineTo(tx + 6, 2.4); p.lineTo(tx + 3, 7.8)
            else:
                p.moveTo(tx, 7.8); p.lineTo(tx + 6, 7.8); p.lineTo(tx + 3, 2.4)
            p.close()
            cv.drawPath(p, stroke=0, fill=1)

    class Chart(Flowable):
        def __init__(self, data, title, w):
            super().__init__()
            self.data, self.title, self.w = data, title, w

        def wrap(self, aw, ah):
            return self.w, 114

        def draw(self):
            cv = self.canv
            cv.setStrokeColor(hx(LINE)); cv.setFillColor(colors.white); cv.setLineWidth(.8)
            cv.roundRect(0, 0, self.w, 114, 9, stroke=1, fill=1)
            cv.setFillColor(hx(MUTED)); cv.setFont(F['BodyBold'], 6.6)
            cv.drawString(12, 101, self.title.upper(), charSpace=.7)
            n = len(self.data)
            inner = self.w - 24
            gap = 6 if n > 10 else 10
            bw = (inner - gap * (n - 1)) / n
            base, top = 18, 92
            cv.setStrokeColor(hx(LINE)); cv.line(12, base, self.w - 12, base)
            top3 = sorted(range(n), key=lambda i: -self.data[i][1])[:3]
            for i, (code, v) in enumerate(self.data):
                x = 12 + i * (bw + gap)
                h = (top - base - 10) * max(0, min(100, v)) / 100
                cv.setFillColor(hx(C['primary'] if i in top3 else '#cbd5e1'))
                cv.roundRect(x, base, bw, max(h, 1), min(3, bw / 3), stroke=0, fill=1)
                cv.rect(x, base, bw, min(3, h), stroke=0, fill=1)
                cv.setFillColor(hx(INK)); cv.setFont(F['BodyBold'], 6.4)
                cv.drawCentredString(x + bw / 2, base + h + 3, '%d' % round(v))
                cv.setFillColor(hx(MUTED)); cv.setFont(F['BodyBold'], 5.6 if n > 12 else 6.2)
                cv.drawCentredString(x + bw / 2, base - 8, code)

    class Insight(Flowable):
        def __init__(self, item, w):
            super().__init__()
            self.item, self.w = item, w

        def wrap(self, aw, ah):
            return self.w, 50

        def draw(self):
            cv = self.canv
            head, val, sub = self.item
            cv.setStrokeColor(hx(LINE)); cv.setFillColor(colors.white); cv.setLineWidth(.8)
            cv.roundRect(0, 0, self.w, 50, 9, stroke=1, fill=1)
            cv.setFillColor(hx(MUTED)); cv.setFont(F['BodyBold'], 6.4)
            cv.drawString(10, 37, head.upper(), charSpace=.7)
            cv.setFillColor(hx(INK))
            sz = 10.5
            while sz > 7 and stringWidth(val, F['Display'], sz) > self.w - 20:
                sz -= .5
            cv.setFont(F['Display'], sz)
            cv.drawString(10, 22, val)
            cv.setFillColor(hx(INK2)); cv.setFont(F['Body'], 7.4)
            cv.drawString(10, 9, sub)

    # ---- cells -------------------------------------------------------------------
    def cell(col, row, bold=False):
        k, v = col['kind'], row.get(col['key'])
        b = F['BodyBold']
        if k == 'pos':
            return Pos(v)
        if k == 'rank':
            return Paragraph('<font name="%s" color="%s">%s</font>' % (F['Display'], MUTED, v), st_ctr)
        if k == 'name':
            name, sub = v
            t = '<font name="%s" color="%s" size="%s">%s</font>' % (b, INK, fs * 1.02, esc(name))
            if sub:
                t += '<br/><font size="%s" color="%s">%s</font>' % (fs * .82, MUTED, esc(sub))
            return Paragraph(t, st_cell)
        if k == 'subject':
            name, core = v
            t = '<font name="%s" color="%s">%s</font>' % (b, INK, esc(name))
            if core:
                t += ' <font name="%s" size="5.4" color="%s" backColor="%s">&nbsp;CORE&nbsp;</font>' % (
                    b, C['primary'], C['soft'])
            return Paragraph(t, st_cell)
        if k in ('num', 'gcount'):
            if not v:
                return Paragraph('<font color="%s">%s</font>' % (DASH, '·' if k == 'gcount' else '–'), st_ctr)
            f = b if (bold or k == 'num') else F['Body']
            return Paragraph('<font name="%s">%s</font>' % (f, v), st_ctr)
        if k == 'frac':
            n, of = v
            return Paragraph('<font name="%s" color="%s">%d</font><font size="%s" color="%s">/%d</font>' % (
                F['Display'], INK, n, fs * .76, MUTED, of), st_ctr)
        if k == 'dec':
            return Paragraph('<font name="%s">%s</font>' % (b if bold else F['Body'], esc(v)), st_ctr if students else st_rt)
        if k == 'grades':
            return Grades(v)
        if k == 'flag':
            return Flag(v, col['yes'], col['no'])
        if k == 'spread':
            return Spread(v, fixed['spread'] - 6)
        if k == 'pctb':
            return Paragraph('<font name="%s" color="%s">%.1f%%</font>' % (F['Display'], INK, v), st_rt)
        if k == 'pct':
            if v is None:
                return Paragraph('<font color="%s">—</font>' % DASH, st_rt)
            return Paragraph('<font name="%s">%.1f%%</font>' % (b if bold else F['Body'], v), st_rt)
        if k == 'delta':
            return Delta(v, bold)
        if k == 'text':
            return Paragraph(esc(v), st_ctr if col.get('center') else st_cell)
        return Paragraph(esc(v), st_cell)

    def head(col):
        k = col['kind']
        st = st_head_c if k in ('pos', 'num', 'gcount', 'frac', 'flag', 'rank') or (students and k == 'dec') \
            or col.get('center') else st_head_r if k in ('pctb', 'pct', 'dec', 'delta') else st_head
        return Paragraph(esc(col['label'].upper()), st)

    data = [[head(c) for c in doc['columns']]]
    for r in rows:
        data.append([cell(c, r) for c in doc['columns']])
    if doc.get('total'):
        data.append([cell(c, doc['total'], bold=True) for c in doc['columns']])
    t = Table(data, colWidths=col_w, repeatRows=1) if rows else None
    pad = 3 if not students else 4
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), hx(BG)),
        ('LINEABOVE', (0, 0), (-1, 0), .7, hx(LINE)), ('LINEBELOW', (0, 0), (-1, 0), .7, hx(LINE)),
        ('LINEBELOW', (0, 1), (-1, -1), .5, hx(LINE2)),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, 0), 6), ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 4.2 if students else 3.6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4.2 if students else 3.6),
        ('LEFTPADDING', (0, 0), (-1, -1), pad), ('RIGHTPADDING', (0, 0), (-1, -1), pad),
    ]
    for i in range(2, len(rows) + 1, 2):
        style.append(('BACKGROUND', (0, i), (-1, i), hx(ZEBRA)))
    for j, c in enumerate(doc['columns']):
        if c['kind'] == 'gcount':           # narrow grade-count columns: no side padding
            style += [('LEFTPADDING', (j, 0), (j, -1), 0), ('RIGHTPADDING', (j, 0), (j, -1), 0)]
    if doc.get('total'):
        style += [('BACKGROUND', (0, -1), (-1, -1), hx(C['soft'])),
                  ('LINEABOVE', (0, -1), (-1, -1), 1.4, hx(C['primary']))]
    if t is not None:
        t.setStyle(TableStyle(style))

    # ---- story -----------------------------------------------------------------
    story = [NextPageTemplate('later'), Paragraph(esc(doc['title']), st_title)]
    if doc.get('subtitle'):
        story += [Spacer(1, 2), Paragraph(esc(doc['subtitle']), st_sub)]
    story.append(Spacer(1, 10))
    gap = 7
    kw = (avail_w - gap * (len(doc['kpis']) - 1)) / len(doc['kpis'])
    kt = Table([[Kpi(k, kw) for k in doc['kpis']]], colWidths=[kw + gap] * (len(doc['kpis']) - 1) + [kw])
    kt.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                            ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
    story += [kt, Spacer(1, 10), Legend(doc['key'], avail_w), Spacer(1, 8)]
    if rows:
        story.append(t)
    else:
        story.append(Paragraph('No results have been recorded for this exam year.', st_sub))
    if doc.get('codes'):
        st_note = ParagraphStyle('nt', parent=st_cell, fontSize=7.4, leading=10)
        txt = '<font name="%s" color="%s">Subject codes:</font> %s' % (
            F['BodyBold'], INK, ' · '.join('%s %s' % (esc(c), esc(n)) for c, n in doc['codes']))
        note = Table([[Paragraph(txt, st_note)]], colWidths=[avail_w])
        note.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), .7, hx(LINE), None, (2, 2)),
                                  ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                                  ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
        story += [Spacer(1, 10), note]
    if doc.get('chart'):
        story += [Spacer(1, 12), KeepTogether([Chart(doc['chart'], doc['chart_title'], avail_w)])]
    if doc.get('insights'):
        n = len(doc['insights'])
        iw = (avail_w - gap * (n - 1)) / n
        it = Table([[Insight(x, iw) for x in doc['insights']]], colWidths=[iw + gap] * (n - 1) + [iw])
        it.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                                ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
        story += [Spacer(1, 10), it]

    buf = io.BytesIO()
    d = BaseDocTemplate(buf, pagesize=(PW, PH), leftMargin=margin, rightMargin=margin,
                        topMargin=margin, bottomMargin=margin, title=doc['title'],
                        author=doc['school'].get('name') or '', creator='Exam results export')
    first = Frame(margin, foot_h + 14, avail_w, PH - head_h - foot_h - 14, id='f1',
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    later = Frame(margin, foot_h + 14, avail_w, PH - head2_h - foot_h - 14, id='f2',
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    d.addPageTemplates([PageTemplate('first', [first]), PageTemplate('later', [later])])
    d.build(story, canvasmaker=canvas_cls)
    doc['_orientation'] = 'landscape' if PW > PH else 'portrait'
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Image — the PDF, rasterised (one PNG per page, empty band trimmed)
# --------------------------------------------------------------------------- #
def render_images(doc, zoom=2.0, only_page=None):
    import fitz
    from PIL import Image as PI, ImageChops
    pdf = fitz.open(stream=render_pdf(doc), filetype='pdf')
    total = pdf.page_count
    pages = [pdf[min(only_page, total) - 1]] if only_page else list(pdf)
    out = []
    for page in pages:
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        im = PI.frombytes('RGB', (pix.width, pix.height), pix.samples)
        foot = int(58 * zoom)
        body = im.crop((0, 0, im.width, im.height - foot))
        bbox = ImageChops.difference(body, PI.new('RGB', body.size, 'white')).getbbox()
        if bbox and bbox[3] + int(24 * zoom) < body.height:
            cut = bbox[3] + int(18 * zoom)
            new = PI.new('RGB', (im.width, cut + foot), 'white')
            new.paste(body.crop((0, 0, im.width, cut)), (0, 0))
            new.paste(im.crop((0, im.height - foot, im.width, im.height)), (0, cut))
            im = new
        b = io.BytesIO()
        im.save(b, 'PNG')
        out.append(b.getvalue())
    return (out, total) if only_page else out


# --------------------------------------------------------------------------- #
# Word
# --------------------------------------------------------------------------- #
def render_docx(doc):
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, Cm, RGBColor

    C = doc['colors']
    if '_orientation' not in doc:
        render_pdf(doc)          # decides portrait / landscape like the PDF
    rgb = lambda h: RGBColor(*SLE._hex(h))   # noqa: E731

    d = Document()
    sec = d.sections[0]
    if doc['_orientation'] == 'landscape':
        sec.orientation = WD_ORIENT.LANDSCAPE
        sec.page_width, sec.page_height = Cm(29.7), Cm(21.0)
    else:
        sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    for side in ('left_margin', 'right_margin', 'top_margin', 'bottom_margin'):
        setattr(sec, side, Cm(1.3))
    base = d.styles['Normal']
    base.font.name = 'Calibri'
    base.font.size = Pt(9)

    def shade(cell, hexcol):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement('w:shd')
        shd.set(qn('w:val'), 'clear'); shd.set(qn('w:color'), 'auto'); shd.set(qn('w:fill'), hexcol.lstrip('#'))
        tcPr.append(shd)

    def borders(table, color='E2E8F0', inside=True):
        tblPr = table._tbl.tblPr
        b = OxmlElement('w:tblBorders')
        edges = ('top', 'left', 'bottom', 'right', 'insideH', 'insideV') if inside else ('top', 'left', 'bottom', 'right')
        for e in edges:
            el = OxmlElement('w:' + e)
            el.set(qn('w:val'), 'single'); el.set(qn('w:sz'), '4'); el.set(qn('w:color'), color)
            b.append(el)
        tblPr.append(b)

    def para(text='', size=9, bold=False, color=SLE.INK2, align=None, space_after=2):
        p = d.add_paragraph()
        p.paragraph_format.space_after = Pt(space_after)
        if align:
            p.alignment = align
        if text:
            r = p.add_run(text); r.font.size = Pt(size); r.bold = bold; r.font.color.rgb = rgb(color)
        return p

    school = doc['school']
    para(school.get('name') or 'School', 16, True, SLE.INK, space_after=0)
    if school.get('motto'):
        para(school['motto'].upper(), 7.5, True, C['primary'], space_after=0)
    line = SLE._contact_line(school)
    if line:
        para(line, 8, False, SLE.MUTED, space_after=0)
    gen = doc.get('generated') or SLE._now()
    para('%s · Generated %s' % (doc['doc_tag'], gen.strftime('%d %b %Y, %H:%M')), 7.5, True, C['primary'],
         space_after=6)
    para(doc['title'], 17, True, SLE.INK, space_after=0)
    if doc.get('subtitle'):
        para(doc['subtitle'], 9, False, SLE.INK2, space_after=6)

    kt = d.add_table(rows=1, cols=len(doc['kpis']))
    borders(kt)
    for cell, k in zip(kt.rows[0].cells, doc['kpis']):
        p = cell.paragraphs[0]
        r = p.add_run(k['v']); r.bold = True; r.font.size = Pt(14); r.font.color.rgb = rgb(SLE.INK)
        p2 = cell.add_paragraph(); r = p2.add_run(k['l'].upper()); r.bold = True; r.font.size = Pt(6.5)
        r.font.color.rgb = rgb(SLE.MUTED)
        p3 = cell.add_paragraph(); r = p3.add_run(k.get('s') or ''); r.font.size = Pt(7.5)
        r.font.color.rgb = rgb(SLE.INK2)

    p = para(space_after=4)
    p.paragraph_format.space_before = Pt(6)
    r = p.add_run('GRADE KEY   '); r.bold = True; r.font.size = Pt(7); r.font.color.rgb = rgb(SLE.MUTED)
    for label, kind in doc['key']:
        r = p.add_run(label + ' '); r.bold = True; r.font.size = Pt(8.5); r.font.color.rgb = rgb(_grade_color(kind, C))
        r = p.add_run(KIND_NAMES[kind] + '    '); r.font.size = Pt(8.5); r.font.color.rgb = rgb(SLE.INK2)

    cols = doc['columns']
    rows = list(doc['rows']) + ([doc['total']] if doc.get('total') else [])
    t = d.add_table(rows=1 + len(rows), cols=len(cols))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    borders(t)
    right = {'pctb', 'pct', 'delta'} | ({'dec'} if doc['type'] == 'subjects' else set())
    center = {'pos', 'rank', 'num', 'gcount', 'frac', 'flag'} | ({'dec'} if doc['type'] == 'students' else set())
    for cell, c in zip(t.rows[0].cells, cols):
        shade(cell, SLE.BG)
        p = cell.paragraphs[0]
        r = p.add_run(c['label'].upper()); r.bold = True; r.font.size = Pt(6.8); r.font.color.rgb = rgb(SLE.MUTED)
        if c['kind'] in center:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif c['kind'] in right:
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    per_row = _per_row(max((len(r.get('grades') or []) for r in doc['rows']), default=0) or 1)
    for i, row in enumerate(rows, 1):
        is_total = doc.get('total') is not None and i == len(rows)
        for cell, c in zip(t.rows[i].cells, cols):
            p = cell.paragraphs[0]
            if c['kind'] in center:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            elif c['kind'] in right:
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            if is_total:
                shade(cell, C['soft'])
            elif i % 2 == 0:
                shade(cell, SLE.ZEBRA)
            v = row.get(c['key'])
            k = c['kind']

            def run(text, size=8.5, bold=is_total, color=SLE.INK2):
                rr = p.add_run(str(text)); rr.font.size = Pt(size); rr.bold = bold; rr.font.color.rgb = rgb(color)
                return rr
            if k == 'name':
                run(v[0], 9, True, SLE.INK)
                if v[1]:
                    p.add_run().add_break()
                    run(v[1], 7, False, SLE.MUTED)
            elif k == 'subject':
                run(v[0], 8.5, True, SLE.INK)
                if v[1]:
                    run('  CORE', 6, True, C['primary'])
            elif k == 'grades':
                for j, (code, g, kind) in enumerate(v):
                    if j and j % per_row == 0:
                        p.add_run().add_break()
                    run(code + ' ', 6, True, SLE.MUTED)
                    run(g + '  ', 8.5, True, _grade_color(kind, C))
            elif k == 'frac':
                run(v[0], 9, True, SLE.INK); run('/%d' % v[1], 7, False, SLE.MUTED)
            elif k == 'flag':
                run(('✓ ' + c['yes']) if v else c['no'], 8, bool(v), SLE.INK2 if v else SLE.MUTED)
            elif k == 'spread':
                run(' · '.join(str(x) for x in v), 8, False, SLE.INK2)
            elif k == 'pctb':
                run('%.1f%%' % v, 9, True, SLE.INK)
            elif k == 'pct':
                run('—' if v is None else '%.1f%%' % v)
            elif k == 'delta':
                if v is None:
                    run('—', color=DASH)
                else:
                    run(('▲ ' if v >= 0 else '▼ ') + '%.1f' % abs(v), 8.5, True, SLE.INK2 if v >= 0 else FAIL)
            elif k in ('num', 'gcount') and not v:
                run('–', color=DASH)
            elif k == 'pos':
                run(v, 9, True, C['primary'] if isinstance(v, int) and v <= 3 else SLE.INK2)
            else:
                run('' if v is None else v)
    if doc.get('codes'):
        para('Subject codes: ' + ' · '.join('%s %s' % c for c in doc['codes']), 7.5, False, SLE.INK2,
             space_after=4).paragraph_format.space_before = Pt(8)
    if doc.get('chart'):
        para(doc['chart_title'], 8, True, SLE.MUTED).paragraph_format.space_before = Pt(10)
        ct = d.add_table(rows=1, cols=len(doc['chart']))
        borders(ct)
        top3 = sorted(range(len(doc['chart'])), key=lambda i: -doc['chart'][i][1])[:3]
        for j, (cell, (code, v)) in enumerate(zip(ct.rows[0].cells, doc['chart'])):
            p = cell.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run('%d%%' % round(v)); r.bold = True; r.font.size = Pt(8)
            r.font.color.rgb = rgb(C['primary'] if j in top3 else SLE.INK2)
            p2 = cell.add_paragraph(); p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p2.add_run(code); r.font.size = Pt(6.5); r.bold = True; r.font.color.rgb = rgb(SLE.MUTED)
    if doc.get('insights'):
        para(space_after=2)
        it = d.add_table(rows=1, cols=len(doc['insights']))
        borders(it)
        for cell, (h, v, s) in zip(it.rows[0].cells, doc['insights']):
            p = cell.paragraphs[0]
            r = p.add_run(h.upper()); r.bold = True; r.font.size = Pt(6.5); r.font.color.rgb = rgb(SLE.MUTED)
            p2 = cell.add_paragraph(); r = p2.add_run(v); r.bold = True; r.font.size = Pt(10.5)
            r.font.color.rgb = rgb(SLE.INK)
            p3 = cell.add_paragraph(); r = p3.add_run(s); r.font.size = Pt(7.5); r.font.color.rgb = rgb(SLE.INK2)
    foot = sec.footer.paragraphs[0]
    r = foot.add_run('%s · %s%s · Confidential — for school use' % (
        school.get('name') or 'School', doc['footer_title'],
        (' · prepared by ' + doc['prepared_by']) if doc.get('prepared_by') else ''))
    r.font.size = Pt(7); r.font.color.rgb = rgb(SLE.MUTED)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def file_response(doc, fmt, stem):
    """Flask response for ``fmt`` in pdf / word / image (image: ``?page=``)."""
    from flask import Response, request
    from utils.web_exports import pdf_response
    if fmt == 'pdf':
        return pdf_response(io.BytesIO(render_pdf(doc)), stem + '.pdf', inline=False)
    if fmt == 'word':
        return Response(render_docx(doc), headers={'Content-Disposition': 'attachment; filename="%s.docx"' % stem},
                        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    page = max(1, request.args.get('page', type=int) or 1)
    pages, total = render_images(doc, only_page=page)
    suffix = '' if total == 1 else '_p%d' % min(page, total)
    return Response(pages[0], mimetype='image/png', headers={
        'Content-Disposition': 'attachment; filename="%s%s.png"' % (stem, suffix),
        'X-Total-Pages': str(total), 'Access-Control-Expose-Headers': 'X-Total-Pages'})
