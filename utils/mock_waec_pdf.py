"""Server-side PDFs for Mock WAEC — broadsheet, blank recording sheet and result
slips. Rendered with reportlab (no headless browser) so they preview/print the
same everywhere. School identity comes from SchoolSettings; an ``opts`` dict
controls which optional blocks (COMPETENCE banner, address, contact, motto,
summary, signatures) are included.
"""
import io

from reportlab.lib.pagesizes import A4, A3, A2, A1, A0, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                Spacer, PageBreak, Flowable, HRFlowable)
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas as _PDFCanvas
from utils.web_exports import pdf_escape
from utils import timeutil

_BLACK = colors.black
_HEAD = colors.HexColor('#d9d9d9')
_FOOT = colors.HexColor('#eeeeee')
_SHADE = colors.HexColor('#cfcfcf')

# WASSCE grade bands (mirror models.mock_waec.waec_grade_from_score). Credit = C6+.
_GRADE_KEY = [('A1', '75–100'), ('B2', '70–74'), ('B3', '65–69'), ('C4', '60–64'),
              ('C5', '55–59'), ('C6', '50–54'), ('D7', '45–49'), ('E8', '40–44'),
              ('F9', '0–39')]
_BLANK_SUMMARY = ['No. offered', 'No. passed (C6+)', 'No. failed',
                  'Average score %', 'Average grade']
_EXTRA_ROWS = 3        # blank rows before the summary, for hand-written additions

# Headers + per-student values for the independently-toggleable last-sheet-only
# summary columns (broadsheet_pdf's ``tail_cols``).
_TAIL_LABELS = {'credits': 'Credits', 'average': 'Average %', 'position': 'Position',
                'subjects_sat': 'Subjects Sat', 'remark': 'Remark'}
# Relative width of each tail column, as a fraction of the standard 1-unit
# width every other column gets. Credits/Average only ever hold a couple of
# digits, so they read fine narrower; Position/Subjects Sat/Remark keep the
# full unit (Remark in particular needs the room to wrap "Not Qualified").
_TAIL_WEIGHT = {'credits': 0.6, 'average': 0.6}


class _VHead(Flowable):
    """A column header drawn vertically (bottom-to-top), like the on-screen
    broadsheet — lets subject columns stay narrow while showing full names."""
    def __init__(self, text, size=8, pad=6):
        Flowable.__init__(self)
        self.text = text or ''
        self.size = size
        self.pad = pad

    def wrap(self, aw, ah):
        self.width = self.size + 2
        self.height = stringWidth(self.text, 'Helvetica-Bold', self.size) + self.pad
        return (self.width, self.height)

    def draw(self):
        c = self.canv
        c.saveState()
        c.translate(self.size, self.pad / 2.0)
        c.rotate(90)
        c.setFont('Helvetica-Bold', self.size)
        c.drawString(0, -self.size * 0.28, self.text)
        c.restoreState()

_S = {}


def _styles():
    if _S:
        return _S
    base = getSampleStyleSheet()
    _S['school'] = ParagraphStyle('sch', parent=base['Title'], fontSize=18, leading=20,
                                  alignment=TA_CENTER, spaceAfter=0, textColor=_BLACK)
    _S['addr'] = ParagraphStyle('addr', parent=base['Normal'], fontSize=9,
                                alignment=TA_CENTER, spaceAfter=0)
    _S['branch'] = ParagraphStyle('branch', parent=base['Normal'], fontSize=10.5,
                                  alignment=TA_CENTER, spaceAfter=0, fontName='Helvetica-Bold')
    _S['comp'] = ParagraphStyle('comp', parent=base['Normal'], fontSize=14,
                                alignment=TA_CENTER, spaceBefore=4, spaceAfter=2,
                                fontName='Helvetica-Bold')
    _S['exam'] = ParagraphStyle('exam', parent=base['Normal'], fontSize=11,
                                alignment=TA_CENTER, spaceAfter=6, fontName='Helvetica-Bold')
    _S['colhead'] = ParagraphStyle('ch', parent=base['Normal'], fontSize=7.5, leading=8.5,
                                   alignment=TA_CENTER, fontName='Helvetica-Bold')
    _S['name'] = ParagraphStyle('nm', parent=base['Normal'], fontSize=8.5, leading=9.5,
                                fontName='Helvetica-Bold')
    _S['cell'] = ParagraphStyle('c', parent=base['Normal'], fontSize=10)
    _S['letter'] = ParagraphStyle('letter', parent=base['Normal'], fontSize=17, leading=19,
                                  alignment=TA_CENTER, fontName='Helvetica-Bold')
    return _S


def _triple_rule():
    """Three thin parallel rules spanning one table cell -- a fresh set of
    ``HRFlowable`` instances every call, since reusing one object across
    multiple cells corrupts its wrap geometry after the first cell."""
    return [
        HRFlowable(width='100%', thickness=0.6, color=_BLACK, hAlign='CENTER',
                  vAlign='MIDDLE', spaceBefore=0, spaceAfter=1.6),
        HRFlowable(width='100%', thickness=0.6, color=_BLACK, hAlign='CENTER',
                  vAlign='MIDDLE', spaceBefore=0, spaceAfter=1.6),
        HRFlowable(width='100%', thickness=0.6, color=_BLACK, hAlign='CENTER',
                  vAlign='MIDDLE', spaceBefore=0, spaceAfter=0),
    ]


def _summary_word_row(ncols, word='SUMMARY', lead=2):
    """A row spelling ``word`` into the sheet's own existing Score/Grade
    columns (one letter per real column, centred among them, no new boxes),
    with every other cell in the row filled by a triple rule-through-text so
    the whole row reads as one deliberate section divider. ``lead`` is the
    count of non-subject columns before the Score/Grade block (S/N, Name,
    and an optional Arm column).

    Returns ``(row, spans_full_width)`` — when there are fewer Score/Grade
    columns than letters (a sheet filtered down to very few subjects), it
    falls back to one centred label spanning the whole row instead of
    truncating the word."""
    score_cols = ncols - lead
    if score_cols < len(word):
        row = [Paragraph(word, _S['letter'])] + [''] * (ncols - 1)
        return row, True
    start = lead + (score_cols - len(word)) // 2
    row = [_triple_rule() for _ in range(ncols)]
    for i, ch in enumerate(word):
        row[start + i] = Paragraph(ch, _S['letter'])
    return row, False


def _opt(opts, key, default=True):
    return default if opts is None else opts.get(key, default)


def _short_name(st):
    """Surname + first name only for the broadsheet name column — the middle name
    is dropped so the column can stay narrow and leave more room for the score /
    grade boxes."""
    parts = [st.surname or '', st.first_name or '']
    return ' '.join(p for p in parts if p).strip() or st.full_name


def _school_header(e, school, opts, subtitle):
    """School identity block + optional COMPETENCE RESULT banner + a subtitle.

    When a logo is uploaded it sits to the left of the centred name/address block
    (letterhead style); otherwise the text block is centred on its own."""
    _styles()
    # (paragraph, plain text, font, size) — text+font size the column so the logo
    # hugs the name block rather than sitting at the far-left margin.
    items = []
    if school.get('name'):
        nm = (school['name'] or '').upper()
        items.append((Paragraph(pdf_escape(nm), _S['school']), nm, 'Helvetica-Bold', 18))
    if _opt(opts, 'branch_name') and school.get('branch_name'):
        bn = school['branch_name'].upper()
        items.append((Paragraph(pdf_escape(bn), _S['branch']), bn, 'Helvetica-Bold', 10.5))
    if _opt(opts, 'address') and school.get('address'):
        items.append((Paragraph(pdf_escape(school['address']), _S['addr']), school['address'], 'Helvetica', 9))
    if _opt(opts, 'contact'):
        contact = ' · '.join(x for x in (school.get('phone'), school.get('email')) if x)
        if contact:
            items.append((Paragraph(pdf_escape(contact), _S['addr']), contact, 'Helvetica', 9))
    if _opt(opts, 'motto') and school.get('motto'):
        items.append((Paragraph('<i>%s</i>' % pdf_escape(school['motto']), _S['addr']), school['motto'], 'Helvetica-Oblique', 9))
    block = [it[0] for it in items]
    logo = None
    if school.get('logo_path'):
        from utils.school import logo_flowable
        logo = logo_flowable(max_h_mm=18, max_w_mm=30, path=school.get('logo_path'))
    if logo is not None and block:
        from utils.school import logo_header_flowable
        e.append(logo_header_flowable(logo, items))
    else:
        e.extend(block)
    if _opt(opts, 'title'):
        e.append(Paragraph('COMPETENCE RESULT', _S['comp']))
    if subtitle:
        e.append(Paragraph(pdf_escape(subtitle), _S['exam']))


def _groups(subjects, per):
    return ([subjects[i:i + per] for i in range(0, len(subjects), per)]
            if per and len(subjects) > per else [subjects])


_PAPER_SIZES = {'A4': A4, 'A3': A3, 'A2': A2, 'A1': A1, 'A0': A0}
# A3 and bigger have enough spare vertical room that a couple of rows'
# worth of it is better spent on slightly taller, more comfortable rows
# than on cramming in the extra students that height would otherwise fit —
# fewer students per page, a touch more breathing room per row.
_BIG_SIZES = {'A3', 'A2', 'A1', 'A0'}


def _row_pad(size):
    """Cell TOPPADDING/BOTTOMPADDING (points) for the main table — a touch
    taller on A3+."""
    return 3.3 if (size or 'A4').upper() in _BIG_SIZES else 2.5


def _row_h(size, base_mm):
    """A fixed row height (e.g. the blank sheet's per-student row) — a touch
    taller on A3+."""
    return (base_mm + 0.9) * mm if (size or 'A4').upper() in _BIG_SIZES else base_mm * mm


def _pagesize(orient, size='A4'):
    """A4 landscape by default. ``orient='portrait'`` for tall paper;
    ``size`` is 'A4', 'A3', 'A2', 'A1' or 'A0' — a bigger sheet than A4 lets
    more subject columns fit at full width before the sheet has to split
    into groups (A1/A0 for a wall-sized print or to merge several sheets
    into one by hand)."""
    base = _PAPER_SIZES.get((size or 'A4').upper(), A4)
    return base if orient == 'portrait' else landscape(base)


def _grade_key_table(usable):
    """Compact WASSCE grade-band reference strip."""
    _styles()
    head = [Paragraph('Grade', _S['colhead'])] + [Paragraph(g, _S['colhead']) for g, _ in _GRADE_KEY]
    rng = [Paragraph('Score', _S['colhead'])] + [Paragraph(r, _S['colhead']) for _, r in _GRADE_KEY]
    label_w = 16 * mm
    cell_w = min(18 * mm, (usable - label_w) / len(_GRADE_KEY))
    t = Table([head, rng], colWidths=[label_w] + [cell_w] * len(_GRADE_KEY))
    t.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.7, _BLACK),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    return t


def _broadsheet_signatures(opts, usable):
    """Up to 3 independently-toggled signature lines for the broadsheet
    footer — Principal, HOD (Sciences), HOD (Arts/Humanities) — all three
    included by default."""
    labels = []
    if _opt(opts, 'sig_principal'):
        labels.append('Principal')
    if _opt(opts, 'sig_hod_sci'):
        labels.append('HOD (Sciences)')
    if _opt(opts, 'sig_hod_arts'):
        labels.append('HOD (Arts/Humanities)')
    if not labels:
        return None
    cols = [Paragraph(f'_______________________<br/>{lab}', _S['cell']) for lab in labels]
    w = min(70 * mm, usable / len(cols))
    t = Table([cols], colWidths=[w] * len(cols))
    t.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
    return t


def _faint_logo_image(logo_path, strength=0.16):
    """A neutral-gray, mostly-transparent RGBA version of a school logo for
    use as a watermark.

    ``mask='auto'`` (reportlab's way of honouring an image's own
    transparency) only works when the image actually *has* an alpha
    channel — simply lightening a flat 'L' (grayscale, no alpha) image and
    passing ``mask='auto'`` draws it fully opaque, since there is nothing
    for "auto" to mask on. That drew a hard, boxy rectangle (the logo's own
    background included) instead of a faint watermark.

    Here the alpha channel is derived from how dark each pixel is — near-
    white background pixels become fully transparent and only the ink/crest
    itself fades in at ``strength`` — so a flat logo with no transparency of
    its own still watermarks cleanly. Any real transparency the logo
    already has is preserved by multiplying it in too."""
    from PIL import Image as _PILImage, ImageChops as _ImageChops
    im = _PILImage.open(logo_path).convert('RGBA')
    gray = im.convert('L')
    orig_alpha = im.getchannel('A')
    darkness = _PILImage.eval(gray, lambda v: 255 - v)
    combined = _ImageChops.multiply(darkness, orig_alpha)
    faint_alpha = combined.point(lambda v: int(v * strength))
    return _PILImage.merge('RGBA', (gray, gray, gray, faint_alpha))


def _broadsheet_canvasmaker(opts, school, page_wh):
    """A reportlab Canvas that defers every ``showPage`` so the final page
    count is known before any per-page footer is drawn — lets the watermark
    (school name text and/or a faint school-logo image, either able to carry
    the branch name too), "Page X of Y" and "Generated on ..." line all be
    independently toggled (see utils/student_export.py's ``Numbered`` for the
    same defer-until-save technique, minus the watermark).

    "Page X of Y" and "Generated on ..." run vertically in the left/right
    page margins rather than horizontally across the top or bottom. The
    table always fills exactly the width between the margins (see
    ``broadsheet_pdf``/``blank_broadsheet_pdf``), so margin text can never
    overlap it — unlike a top/bottom placement, which collided with the
    table's own top edge on any page where the roster overflows onto a
    continuation page (no school header there to leave clear space for it).
    It also survives a printed sheet being trimmed and glued to the next,
    since that trims the top/bottom edge, not the sides."""
    show_wm_name = _opt(opts, 'watermark_name')
    show_wm_logo = _opt(opts, 'watermark_logo', default=False)
    show_branch = _opt(opts, 'branch_name', default=False)
    show_pg = _opt(opts, 'page_numbers')
    show_printed = _opt(opts, 'printed_on')
    pw, ph = page_wh
    wm_text = (school.get('name') or 'OFFICIAL').upper()[:24]
    branch_text = (school.get('branch_name') or '').upper()[:30] if show_branch else ''
    logo_path = school.get('logo_path')
    printed_str = timeutil.now().strftime('%d %b %Y, %I:%M %p')

    # Built once (not per page) — same faint image reused for every page.
    logo_reader = None
    if show_wm_logo and logo_path:
        try:
            from reportlab.lib.utils import ImageReader
            logo_reader = ImageReader(_faint_logo_image(logo_path))
        except Exception:
            logo_reader = None

    class _BroadsheetCanvas(_PDFCanvas):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._bs_saved = []

        def showPage(self):
            self._bs_saved.append(dict(self.__dict__))
            self._startPage()

        def _draw_watermark_logo(self):
            ws = min(pw, ph) * 0.55
            self.saveState()
            self.drawImage(logo_reader, pw / 2 - ws / 2, ph / 2 - ws / 2,
                           width=ws, height=ws, mask='auto', preserveAspectRatio=True)
            self.restoreState()

        def save(self):
            n = len(self._bs_saved)
            for i, state in enumerate(self._bs_saved, 1):
                self.__dict__.update(state)
                if logo_reader:
                    self._draw_watermark_logo()
                if show_wm_name:
                    self.saveState()
                    self.translate(pw / 2, ph / 2)
                    self.rotate(30)
                    self.setFillColor(colors.Color(0, 0, 0, alpha=0.06))
                    self.setFont('Helvetica-Bold', 56 if branch_text else 60)
                    self.drawCentredString(0, 16 if branch_text else 0, wm_text)
                    if branch_text:
                        self.setFont('Helvetica-Bold', 26)
                        self.drawCentredString(0, -28, branch_text)
                    self.restoreState()
                if show_printed:
                    self.saveState()
                    self.setFont('Helvetica', 7.5)
                    self.setFillColor(colors.HexColor('#666666'))
                    self.translate(4 * mm, ph / 2)
                    self.rotate(90)
                    self.drawCentredString(0, 0, f'Generated on {printed_str}')
                    self.restoreState()
                if show_pg:
                    self.saveState()
                    self.setFont('Helvetica', 7.5)
                    self.setFillColor(colors.HexColor('#666666'))
                    self.translate(pw - 4 * mm, ph / 2)
                    self.rotate(90)
                    self.drawCentredString(0, 0, f'Page {i} of {n}')
                    self.restoreState()
                super().showPage()
            super().save()
    return _BroadsheetCanvas


def _fit_per(usable, sn_w, name_w, reserve, min_w, per, n):
    """Largest subjects-per-sheet that keeps each subject column at least ``min_w``
    wide, so headers never collapse into an un-renderable sliver. A requested
    ``per`` (incl. 0 = "one wide page") is reduced to this when it wouldn't fit;
    the sheet then splits across pages instead of overflowing."""
    room = usable - sn_w - name_w - reserve
    fit = max(1, int(room / min_w)) if min_w > 0 else n
    if not per or per <= 0 or per > fit:
        return fit
    return per


def broadsheet_pdf(bs, exam, school, opts=None, per=8, orient='landscape',
                   size='A4', separate_cols=False):
    """Full score+grade matrix. Wide subject sets split across pages (``per``
    columns each); no admission numbers. ``opts['summary']`` toggles the
    per-subject offered/passed/failed/average rows, led by a "SUMMARY"
    divider spelled into the sheet's own columns (see ``_summary_word_row``).
    ``orient``/``size`` pick the paper (A4/A3/A2/A1/A0, landscape or
    portrait), filling the page with an 8mm margin. ``separate_cols`` gives
    each subject its own Score and Grade sub-columns (like the blank
    recording sheet) instead of one combined "score grade" column."""
    _styles()
    page = _pagesize(orient, size)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=page, topMargin=8 * mm,
                            bottomMargin=8 * mm, leftMargin=8 * mm, rightMargin=8 * mm,
                            title=f'Broadsheet — {exam.display_name}')
    usable = page[0] - 16 * mm
    sn_w, name_w = 9 * mm, 52 * mm
    show_arm = _opt(opts, 'arm_col')
    arm_w = 14 * mm if show_arm else 0
    lead = 2 + (1 if show_arm else 0)      # S/N, Name, (Arm) -- columns before subjects
    # Vertical headers don't constrain width, so columns only need to fit a
    # score; separate-columns mode needs 2 columns/subject, so its per-subject
    # minimum is double a single narrow column's.
    min_w = 16 * mm if separate_cols else 13 * mm
    per = _fit_per(usable, sn_w, name_w + arm_w, 24 * mm, min_w, per, len(bs['subjects']))
    groups = _groups(bs['subjects'], per)
    ss = bs['subject_summary']
    nrows = len(bs['rows'])
    show_summary = _opt(opts, 'summary')
    header_rows = 2 if separate_cols else 1
    e = []
    for gi, group in enumerate(groups):
        last = gi == len(groups) - 1
        sub = f'{exam.display_name} — Broadsheet'
        if _opt(opts, 'exam_date') and exam.exam_date:
            sub += f' · {exam.exam_date.strftime("%d %b %Y")}'
        if len(groups) > 1:
            sub += f' (Sheet {gi + 1} of {len(groups)})'
        _school_header(e, school, opts, sub)

        tail_cols = []
        if last:
            if _opt(opts, 'credits'):
                tail_cols.append('credits')
            if _opt(opts, 'average'):
                tail_cols.append('average')
            if _opt(opts, 'position'):
                tail_cols.append('position')
            if _opt(opts, 'subjects_sat'):
                tail_cols.append('subjects_sat')
            if _opt(opts, 'remark'):
                tail_cols.append('remark')
        tail = len(tail_cols)
        n_subj_cols = 2 * len(group) if separate_cols else len(group)
        # Every individual column (each subject sub-column, and each tail
        # column) is one "unit" wide, except Credits/Average which are
        # narrower (see _TAIL_WEIGHT). In separate-columns mode a subject's 2
        # sub-columns and each tail column's own weighted share are each
        # reserved out of 2 units total, so a full-weight (1.0) tail column
        # keeps the same footprint as one full subject block — matching
        # combined mode, where every full-weight column is simply 1 unit.
        base_per_tail = 2 if separate_cols else 1
        tail_weights = [_TAIL_WEIGHT.get(tc, 1.0) for tc in tail_cols]
        tail_units = base_per_tail * sum(tail_weights)
        unit = (usable - sn_w - name_w - arm_w) / (n_subj_cols + tail_units)

        if separate_cols:
            h1 = [Paragraph('S/N', _S['colhead']), Paragraph('Name of Student', _S['colhead'])]
            if show_arm:
                h1.append(Paragraph('Arm', _S['colhead']))
            h2 = [''] * lead
            for s in group:
                h1 += [_VHead(s), '']
                h2 += [_VHead('Score', size=7), _VHead('Grade', size=7)]
            for tc in tail_cols:
                h1.append(_VHead(_TAIL_LABELS[tc]))
                h2.append('')
            data = [h1, h2]
        else:
            header = [Paragraph('S/N', _S['colhead']), Paragraph('Name of Student', _S['colhead'])]
            if show_arm:
                header.append(Paragraph('Arm', _S['colhead']))
            header += [_VHead(s) for s in group]
            for tc in tail_cols:
                header.append(_VHead(_TAIL_LABELS[tc]))
            data = [header]

        for i, row in enumerate(bs['rows'], 1):
            line = [str(i), Paragraph(pdf_escape(_short_name(row['student'])), _S['name'])]
            if show_arm:
                line.append(row.get('arm') or '—')
            for s in group:
                r = row['cells'].get(s)
                is_ab = bool(r and getattr(r, 'is_absent', False))
                has = r and r.score is not None
                if separate_cols:
                    if is_ab:
                        line += ['AB', '']
                    else:
                        line += [str(r.score), r.grade] if has else ['', '']
                else:
                    if is_ab:
                        line.append('AB')
                    else:
                        line.append(f'{r.score} {r.grade}' if has else '')
            for tc in tail_cols:
                if tc == 'credits':
                    line.append(str(row['credits']))
                elif tc == 'average':
                    line.append(str(row['average_score']) if row['average_score'] is not None else '')
                elif tc == 'position':
                    line.append(str(row['position']) if row.get('position') is not None else '')
                elif tc == 'subjects_sat':
                    line.append(str(row.get('subjects_sat', '')))
                else:
                    # Paragraph (not a bare string) so "Not Qualified" wraps
                    # instead of overflowing a narrow column.
                    line.append(Paragraph(row.get('remark', ''), _S['colhead']))
            data.append(line)

        ncols = lead + n_subj_cols + tail
        for _ in range(_EXTRA_ROWS):                          # blank rows for additions
            data.append([''] * ncols)

        summary_heading_row = len(data)
        summary_heading_spans_full = False
        if show_summary:
            # Centre "SUMMARY" within the SUBJECT columns only -- the lead
            # (S/N, Name, Arm) and tail columns (Credits, Average %, ...) on
            # the last sheet aren't part of the per-subject block and
            # shouldn't take letters.
            heading_row, summary_heading_spans_full = _summary_word_row(lead + n_subj_cols, lead=lead)
            if tail:
                heading_row += ([_triple_rule() for _ in range(tail)] if not summary_heading_spans_full
                                else [''] * tail)
            data.append(heading_row)

        sum0 = len(data)
        if show_summary:
            for label, fn in (('No. offered', lambda d: d['offered']),
                              ('No. passed (C6+)', lambda d: d['passed']),
                              ('No. failed', lambda d: d['failed']),
                              ('Average score %', lambda d: d['avg_score'] if d['avg_score'] is not None else '—'),
                              ('Average grade', lambda d: d['avg_grade'])):
                # Label always sits under Name (col 1), same as with no Arm
                # column, rather than sliding into Arm's narrow cell.
                rr = [''] + [label] + [''] * (lead - 2)
                for s in group:
                    rr += [str(fn(ss[s])), ''] if separate_cols else [str(fn(ss[s]))]
                if tail:
                    rr += [''] * tail
                data.append(rr)

        widths = [sn_w, name_w] + ([arm_w] if show_arm else []) + [unit] * n_subj_cols
        if tail:
            # Matches the divisor above: in separate-columns mode a tail
            # column reserves its weighted share out of 2 units (same
            # footprint as a subject's Score+Grade pair for a full-weight
            # column), not 1 -- using 1 here left part of that width
            # unallocated, shrinking the table and (since reportlab centres
            # an under-width table in its frame) padding out both margins
            # instead of just the right one.
            widths += [unit * base_per_tail * w for w in tail_weights]
        heights = ([None] * header_rows + [None] * nrows + [7.5 * mm] * _EXTRA_ROWS
                   + ([9.5 * mm] if show_summary else [])
                   + ([None] * len(_BLANK_SUMMARY) if show_summary else []))
        # repeatRows=0: the header (subject names, S/N, Name, Credits, Average)
        # appears on the first page only; an overflowing roster continues without
        # the header band repeating.
        t = Table(data, colWidths=widths, repeatRows=0, rowHeights=heights)
        style = [
            ('GRID', (0, 0), (-1, -1), 0.9, _BLACK),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, header_rows), (-1, header_rows - 1 + nrows), 9.5),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('VALIGN', (0, 0), (-1, header_rows - 1), 'BOTTOM'),
            ('TOPPADDING', (0, 0), (-1, -1), _row_pad(size)),
            ('BOTTOMPADDING', (0, 0), (-1, -1), _row_pad(size)),
        ]
        if separate_cols:
            style += [('SPAN', (0, 0), (0, 1)), ('SPAN', (1, 0), (1, 1)),
                     ('LEFTPADDING', (lead, 0), (-1, -1), 1), ('RIGHTPADDING', (lead, 0), (-1, -1), 1)]
            if show_arm:
                style.append(('SPAN', (2, 0), (2, 1)))
            for j in range(len(group)):
                c0 = lead + j * 2
                style.append(('SPAN', (c0, 0), (c0 + 1, 0)))
            if tail:
                last_col = lead + n_subj_cols
                for k in range(tail):
                    style.append(('SPAN', (last_col + k, 0), (last_col + k, 1)))
        if show_summary:
            style.append(('FONTSIZE', (0, sum0), (-1, -1), 8.5))
            style.append(('LINEABOVE', (0, summary_heading_row), (-1, summary_heading_row), 1.6, _BLACK))
            style.append(('LINEBELOW', (0, summary_heading_row), (-1, summary_heading_row), 1.6, _BLACK))
            if summary_heading_spans_full:
                style.append(('SPAN', (0, summary_heading_row), (ncols - 1, summary_heading_row)))
            if separate_cols:
                for k in range(len(_BLANK_SUMMARY)):
                    for j in range(len(group)):
                        c0 = lead + j * 2
                        style.append(('SPAN', (c0, sum0 + k), (c0 + 1, sum0 + k)))
        t.setStyle(TableStyle(style))
        e.append(t)
        if _opt(opts, 'grades'):
            e.append(Spacer(1, 6))
            e.append(_grade_key_table(usable))
        if last:
            sig = _broadsheet_signatures(opts, usable)
            if sig:
                e.append(Spacer(1, 14))
                e.append(sig)
        if not last:
            e.append(PageBreak())
    doc.build(e, canvasmaker=_broadsheet_canvasmaker(opts, school, page))
    buf.seek(0)
    return buf


def blank_broadsheet_pdf(students, offered, subjects, exam, school, opts=None,
                         per=0, orient='landscape', size='A4', arm_by_student=None):
    """A blank recording sheet: student names down the side, every subject across
    the top with its own **Score** and **Grade** columns to write into.
    ``orient``/``size`` pick the paper — landscape or portrait, A4/A3/A2/A1/A0.
    (``offered`` is accepted for call compatibility but no longer used —
    cells are left plain rather than shading out non-offered subjects.)
    ``arm_by_student`` is an optional ``{student_id: arm label}`` map for the
    toggleable Arm column.

    Columns are sized to fit the whole subject set on one sheet by default
    (``per=0``): with the full WAEC load (~16 subjects) all of them stay on one
    landscape page instead of spilling a few onto a second sheet. The score/grade
    columns are deliberately narrow (hand-writing a 2-digit score or a grade), so
    cell padding and the Score/Grade sub-labels are kept compact — a bigger sheet
    (A3/A2) gives that same subject set noticeably more breathing room."""
    _styles()
    page = _pagesize(orient, size)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=page, topMargin=8 * mm,
                            bottomMargin=8 * mm, leftMargin=8 * mm, rightMargin=8 * mm,
                            title=f'Blank broadsheet — {exam.display_name}')
    usable = page[0] - 16 * mm
    # Surname + first name only, so the name column can be narrow and hand more
    # width to the Score/Grade boxes.
    sn_w, name_w = 8 * mm, 34 * mm
    show_arm = _opt(opts, 'arm_col')
    arm_w = 14 * mm if show_arm else 0
    arm_by_student = arm_by_student or {}
    lead = 2 + (1 if show_arm else 0)      # S/N, Name, (Arm) -- columns before subjects
    # Two writable columns (Score + Grade) per subject. Reserve only ~13mm per
    # subject so the full WAEC set fits one landscape sheet; columns narrow before
    # the sheet splits.
    per = _fit_per(usable, sn_w, name_w + arm_w, 0, 13 * mm, per, len(subjects))
    groups = _groups(subjects, per)
    nstud = len(students)
    e = []
    for gi, group in enumerate(groups):
        sub = f'{exam.display_name} — Recording Sheet'
        if _opt(opts, 'exam_date') and exam.exam_date:
            sub += f' · {exam.exam_date.strftime("%d %b %Y")}'
        if len(groups) > 1:
            sub += f' (Sheet {gi + 1} of {len(groups)})'
        _school_header(e, school, opts, sub)

        pair_w = (usable - sn_w - name_w - arm_w) / len(group)      # width per subject
        cell_w = pair_w / 2                                  # Score | Grade

        # Two-row header: the vertical subject name spanning its Score+Grade
        # columns, then the Score / Grade sub-labels (compact for narrow columns).
        h1 = [Paragraph('S/N', _S['colhead']), Paragraph('Name of Student', _S['colhead'])]
        if show_arm:
            h1.append(Paragraph('Arm', _S['colhead']))
        h2 = [''] * lead
        for s in group:
            h1 += [_VHead(s), '']
            h2 += [_VHead('Score', size=7), _VHead('Grade', size=7)]   # vertical sub-labels
        data = [h1, h2]
        for i, st in enumerate(students, 1):
            line = [str(i), Paragraph(pdf_escape(_short_name(st)), _S['name'])]
            if show_arm:
                line.append(arm_by_student.get(st.id) or '—')
            line += ['', ''] * len(group)
            data.append(line)

        for _ in range(_EXTRA_ROWS):                        # blank rows for additions
            data.append([''] * lead + [''] * (2 * len(group)))

        # Blank summary rows for filling the per-subject tallies by hand, led
        # by a "SUMMARY" divider spelled into the sheet's own existing
        # columns (see _summary_word_row) so the block is clearly marked
        # before it starts.
        show_summary = _opt(opts, 'summary')
        ncols = lead + 2 * len(group)
        summary_heading_row = len(data)
        summary_heading_spans_full = False
        if show_summary:
            heading_row, summary_heading_spans_full = _summary_word_row(ncols, lead=lead)
            data.append(heading_row)
        sum0 = len(data)                        # table row of the first summary row
        if show_summary:
            for label in _BLANK_SUMMARY:
                # Label always sits under Name (col 1), same as with no Arm
                # column, rather than sliding into Arm's narrow cell.
                data.append([''] + [Paragraph(pdf_escape(label), _S['name'])] + [''] * (lead - 2)
                           + [''] * (2 * len(group)))

        widths = [sn_w, name_w] + ([arm_w] if show_arm else []) + [cell_w] * (2 * len(group))
        row_h = _row_h(size, 8.5)
        heights = ([None, None] + [row_h] * nstud + [row_h] * _EXTRA_ROWS
                   + ([row_h + 1.5 * mm] if show_summary else [])
                   + ([row_h] * len(_BLANK_SUMMARY) if show_summary else []))
        # repeatRows=0: the column labels (subjects, Score/Grade, S/N, Name) appear
        # only on the first page — when the roster overflows onto further pages the
        # students continue without the header band repeating.
        t = Table(data, colWidths=widths, repeatRows=0, rowHeights=heights)
        style = [
            ('GRID', (0, 0), (-1, -1), 0.9, _BLACK),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('SPAN', (0, 0), (0, 1)),          # S/N spans both header rows
            ('SPAN', (1, 0), (1, 1)),          # Name spans both header rows
            ('TOPPADDING', (0, 0), (-1, -1), _row_pad(size)),
            ('BOTTOMPADDING', (0, 0), (-1, -1), _row_pad(size)),
            ('LEFTPADDING', (lead, 0), (-1, -1), 1),    # narrow score/grade columns
            ('RIGHTPADDING', (lead, 0), (-1, -1), 1),
        ]
        if show_arm:
            style.append(('SPAN', (2, 0), (2, 1)))     # Arm spans both header rows
        for j in range(len(group)):           # subject name spans its 2 columns
            c0 = lead + j * 2
            style.append(('SPAN', (c0, 0), (c0 + 1, 0)))
        if show_summary:                       # one writing box per subject per row
            # Double-weight rule top and bottom of the "SUMMARY" divider row —
            # a classic printed-form section break, no colour or shading.
            style.append(('LINEABOVE', (0, summary_heading_row), (-1, summary_heading_row), 1.6, _BLACK))
            style.append(('LINEBELOW', (0, summary_heading_row), (-1, summary_heading_row), 1.6, _BLACK))
            if summary_heading_spans_full:     # too few columns to spell it out letter-by-letter
                style.append(('SPAN', (0, summary_heading_row), (ncols - 1, summary_heading_row)))
            for k in range(len(_BLANK_SUMMARY)):
                for j in range(len(group)):
                    c0 = lead + j * 2
                    style.append(('SPAN', (c0, sum0 + k), (c0 + 1, sum0 + k)))
        t.setStyle(TableStyle(style))
        e.append(t)

        if _opt(opts, 'grades'):              # WASSCE grade-band reference
            e.append(Spacer(1, 6))
            e.append(_grade_key_table(usable))
        if gi == len(groups) - 1:
            sig = _broadsheet_signatures(opts, usable)
            if sig:
                e.append(Spacer(1, 14))
                e.append(sig)
        if gi != len(groups) - 1:
            e.append(PageBreak())
    doc.build(e, canvasmaker=_broadsheet_canvasmaker(opts, school, page))
    buf.seek(0)
    return buf


def _signature_row(signers):
    """Signature line(s) chosen by the user: both / principal / teacher / none."""
    cols = []
    if signers in ('both', 'teacher'):
        cols.append(Paragraph('_______________________<br/>Class Teacher', _S['cell']))
    if signers in ('both', 'principal'):
        cols.append(Paragraph('_______________________<br/>Principal', _S['cell']))
    if not cols:
        return None
    w = 91 * mm if len(cols) == 2 else 110 * mm
    t = Table([cols], colWidths=[w] * len(cols))
    t.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
    return t


import os as _os
from reportlab.pdfbase import pdfmetrics as _pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont as _TTFont

# Palette + fonts for the designed "Competence Result" slip.
_SL = {
    'NAVY': colors.HexColor('#20304F'), 'GOLD': colors.HexColor('#B8862B'),
    'TAN': colors.HexColor('#D9BC86'), 'INK': colors.HexColor('#22303C'),
    'MUTED': colors.HexColor('#6B7280'), 'LINE': colors.HexColor('#DBE0E8'),
    'PANEL': colors.HexColor('#F6F7F9'), 'ZEBRA': colors.HexColor('#F3F5F8'),
    'STEEL': colors.HexColor('#9AA6BE'), 'RED': colors.HexColor('#B91C1C'),
    'REDBG': colors.HexColor('#F2DADA'), 'WHITE': colors.white,
    'BORDER': colors.HexColor('#111827'),
}
_ICON = {'pin': '', 'phone': '', 'mail': '', 'user': '',
         'mars': '', 'venus': '', 'book': '', 'cert': '',
         'layers': '', 'award': '', 'star': '', 'chart': '',
         'check': '', 'clip': ''}


def _slip_fonts():
    """Register the icon font once; the serif faces are reportlab built-ins."""
    fa = 'Helvetica-Bold'
    try:
        if 'FA' not in _pdfmetrics.getRegisteredFontNames():
            p = _os.path.join(_os.path.dirname(__file__), '..', 'static', 'vendor',
                              'fontawesome', 'webfonts', 'fa-solid-900.ttf')
            _pdfmetrics.registerFont(_TTFont('FA', p))
        fa = 'FA'
    except Exception:
        fa = None
    return {'ser': 'Times-Roman', 'serb': 'Times-Bold', 'seri': 'Times-Italic', 'fa': fa}


def _waec_remark(grade):
    """WAEC band descriptor for the remark column."""
    g = (grade or '').upper()
    return {'A1': 'Excellent', 'B2': 'Very Good', 'B3': 'Good',
            'C4': 'Credit', 'C5': 'Credit', 'C6': 'Credit',
            'D7': 'Pass', 'E8': 'Pass', 'F9': 'Fail'}.get(g, '—')


def _grade_badge_colors(grade, bw=False):
    """(fill, text, border) for a grade badge. In B&W: distinctions are solid
    black, everything else is an outlined white chip so it prints cleanly."""
    g = (grade or '').upper()
    if bw:
        # Uniform grey chips (matches the print-friendly reference); a fail is an
        # outlined white chip so it still reads differently on a mono printer.
        if g in ('A1', 'B2', 'B3', 'C4', 'C5', 'C6'):
            return colors.HexColor('#9BA0A6'), colors.HexColor('#161616'), None
        return colors.white, colors.HexColor('#161616'), colors.HexColor('#555555')
    if g == 'A1':
        return _SL['NAVY'], _SL['WHITE'], None
    if g in ('B2', 'B3'):
        return _SL['TAN'], _SL['INK'], None
    if g in ('C4', 'C5', 'C6'):
        return _SL['STEEL'], _SL['WHITE'], None
    return _SL['REDBG'], _SL['RED'], None


def _draw_competence_slip(c, PW, PH, student, s, exam, school, opts, signers, F, bw=False):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    if bw:
        NAVY = colors.black; GOLD = colors.HexColor('#333333'); TAN = colors.white
        INK = colors.black; MUTED = colors.HexColor('#333333'); LINE = colors.HexColor('#666666')
        PANEL = colors.HexColor('#F2F2F2'); ZEBRA = colors.HexColor('#EFEFEF')
        WHITE = colors.white; border = colors.black
    else:
        NAVY, GOLD, TAN = _SL['NAVY'], _SL['GOLD'], _SL['TAN']
        INK, MUTED, LINE = _SL['INK'], _SL['MUTED'], _SL['LINE']
        PANEL, ZEBRA, WHITE = _SL['PANEL'], _SL['ZEBRA'], _SL['WHITE']
        border = _SL['BORDER']
    ser, serb, seri, fa = F['ser'], F['serb'], F['seri'], F['fa']
    M = 30
    session = exam.session.name if exam.session else ''

    def icon(ch, cx, cy, size, color):
        if not fa or not ch:
            return
        c.setFont(fa, size); c.setFillColor(color)
        c.drawString(cx - stringWidth(ch, fa, size) / 2, cy - size * 0.36, ch)

    def icon_circle(ch, cx, cy, r, glyph_size, ring=LINE, glyph=NAVY):
        c.setStrokeColor(ring); c.setFillColor(WHITE); c.setLineWidth(1)
        c.circle(cx, cy, r, stroke=1, fill=1)
        icon(ch, cx, cy, glyph_size, glyph)

    # outer border
    c.setStrokeColor(border); c.setLineWidth(1.4)
    c.roundRect(14, 14, PW - 28, PH - 28, 6, stroke=1, fill=0)

    # faint crest watermark behind the table (grayscale, print-friendly)
    logo0 = (school or {}).get('logo_path') if _opt(opts, 'logo') else None
    if bw and logo0 and _os.path.exists(logo0):
        try:
            from PIL import Image as _PILImage
            from reportlab.lib.utils import ImageReader
            im = _PILImage.open(logo0).convert('L')
            im = im.point(lambda v: int(255 - (255 - v) * 0.08))   # ~8% ink → very light
            wm = ImageReader(im)
            ws = 340
            c.drawImage(wm, PW / 2 - ws / 2, PH / 2 - ws / 2 - 40, width=ws, height=ws,
                        mask='auto', preserveAspectRatio=True)
        except Exception:
            pass

    top = PH - 34
    # ---- Masthead ----------------------------------------------------------
    box_w = 120
    box_x = PW - M - box_w
    logo = (school or {}).get('logo_path') if _opt(opts, 'logo') else None
    name_x = M
    if logo and _os.path.exists(logo):
        try:
            from reportlab.lib.utils import ImageReader
            ir = ImageReader(logo); iw, ih = ir.getSize()
            lh = 74; lw = lh * (iw / ih) if ih else 74
            lw = min(lw, 86)
            c.drawImage(ir, M, top - lh + 4, width=lw, height=lh, mask='auto',
                        preserveAspectRatio=True)
            name_x = M + lw + 14
        except Exception:
            name_x = M
    name = ((school or {}).get('name') or 'School').upper()
    nsize = 30
    name_avail = box_x - 12 - name_x
    while nsize > 15 and stringWidth(name, serb, nsize) > name_avail:
        nsize -= 1
    c.setFillColor(NAVY); c.setFont(serb, nsize)
    c.drawString(name_x, top - 20, name)
    # contact rows
    cy = top - 38
    c.setFont(ser, 10.5)
    addr = (school or {}).get('address') or ''
    if _opt(opts, 'address') and addr:
        icon(_ICON['pin'], name_x + 5, cy + 3.5, 10, NAVY)
        c.setFillColor(INK); c.setFont(ser, 10.5)
        c.drawString(name_x + 15, cy, addr[:70]); cy -= 16
    if _opt(opts, 'contact'):
        phone = (school or {}).get('phone') or ''
        email = (school or {}).get('email') or ''
        x = name_x + 5
        if phone:
            icon(_ICON['phone'], x, cy + 3.5, 9.5, NAVY)
            c.setFillColor(INK); c.setFont(ser, 10.5); c.drawString(x + 12, cy, phone)
            x += 12 + stringWidth(phone, ser, 10.5) + 24
        if email:
            icon(_ICON['mail'], x, cy + 3.5, 9.5, NAVY)
            c.setFillColor(INK); c.setFont(ser, 10.5); c.drawString(x + 13, cy, email)
        cy -= 16
    motto = (school or {}).get('motto') or ''
    if _opt(opts, 'motto') and motto:
        c.setFillColor(GOLD)
        mtext = motto
        mw = stringWidth(mtext, seri, 12)
        mcx = name_x + (name_avail) / 2
        c.setFont(seri, 12); c.setFillColor(colors.HexColor('#4B4B4B'))
        c.drawCentredString(mcx, cy - 2, mtext)
        c.setStrokeColor(GOLD); c.setLineWidth(1)
        c.line(name_x, cy + 2, mcx - mw / 2 - 8, cy + 2)
        c.line(mcx + mw / 2 + 8, cy + 2, box_x - 12, cy + 2)

    # session box
    bx, by, bh = box_x, top - 82, 84
    c.setStrokeColor(LINE); c.setFillColor(colors.HexColor('#FAFBFC')); c.setLineWidth(1)
    c.roundRect(bx, by, box_w, bh, 8, stroke=1, fill=1)
    icon_circle(_ICON['cert'], bx + box_w / 2, by + bh - 20, 14, 15, ring=GOLD, glyph=NAVY)
    c.setFillColor(MUTED); c.setFont(serb, 8.5)
    c.drawCentredString(bx + box_w / 2, by + bh - 44, 'ACADEMIC')
    c.drawCentredString(bx + box_w / 2, by + bh - 54, 'SESSION')
    c.setFillColor(NAVY); c.setFont(serb, 15)
    c.drawCentredString(bx + box_w / 2, by + 16, session or '—')
    c.setStrokeColor(GOLD); c.setLineWidth(1.4)
    c.line(bx + 20, by + 12, bx + box_w - 20, by + 12)

    y = top - 108
    # ---- COMPETENCE RESULT heading ----------------------------------------
    if _opt(opts, 'title'):
        c.setFillColor(NAVY); c.setFont(serb, 26)
        heading = 'COMPETENCE RESULT'
        c.drawCentredString(PW / 2, y - 18, heading)
        hw = stringWidth(heading, serb, 26)
        for sgn in (-1, 1):
            ex = PW / 2 + sgn * (hw / 2 + 18)
            c.setStrokeColor(GOLD); c.setLineWidth(1.2)
            c.line(ex, y - 10, ex + sgn * 40, y - 10)
            c.setFillColor(GOLD)
            c.rect(ex + sgn * 44, y - 13, 5, 5, stroke=0, fill=1)
        y -= 40

    # ---- ribbon banner -----------------------------------------------------
    # Exam name and "Statement of Result" are independently toggleable —
    # either half alone, both, or (if neither is wanted) no banner at all.
    ribbon_parts = []
    if _opt(opts, 'ribbon_exam'):
        ribbon_parts.append(exam.display_name)
    if _opt(opts, 'ribbon_statement'):
        ribbon_parts.append('Statement of Result')
    sub = ' — '.join(ribbon_parts)
    if sub:
        c.setFont(serb, 11.5)
        rw = min(stringWidth(sub, serb, 11.5) + 60, PW - 2 * M)
        rx = PW / 2 - rw / 2; rh2 = 26; ry = y - rh2
        notch = 10
        c.setFillColor(NAVY)
        c.rect(rx, ry, rw, rh2, stroke=0, fill=1)
        p = c.beginPath(); p.moveTo(rx, ry); p.lineTo(rx - notch, ry + rh2 / 2); p.lineTo(rx, ry + rh2); p.close()
        c.drawPath(p, stroke=0, fill=1)
        p = c.beginPath(); p.moveTo(rx + rw, ry); p.lineTo(rx + rw + notch, ry + rh2 / 2); p.lineTo(rx + rw, ry + rh2); p.close()
        c.drawPath(p, stroke=0, fill=1)
        c.setFillColor(WHITE); c.setFont(serb, 11.5)
        c.drawCentredString(PW / 2, ry + 8, sub)
        y = ry - 16

    # ---- student info bar --------------------------------------------------
    bar_h = 52
    c.setStrokeColor(LINE); c.setFillColor(PANEL); c.setLineWidth(1)
    c.roundRect(M, y - bar_h, PW - 2 * M, bar_h, 8, stroke=1, fill=1)
    g = (student.gender or '').lower()
    gi = _ICON['mars'] if g.startswith('m') else (_ICON['venus'] if g.startswith('f') else _ICON['user'])
    cells = [(_ICON['user'], 'Name', student.full_name),
             (gi, 'Gender', student.gender or '—'),
             (_ICON['book'], 'Stream', student.stream or '—')]
    # Name needs the most room; Gender/Stream are short — proportion the cells so
    # a long name never runs under Gender and the short cells aren't half-empty.
    # (Shared by the colour and black-and-white variants.)
    weights = [2.7, 0.95, 1.3]
    total_w = PW - 2 * M
    widths = [total_w * w / sum(weights) for w in weights]
    x_at = M
    for i, (ic, lab, val) in enumerate(cells):
        cx0 = x_at
        cwid = widths[i]
        if i:
            c.setStrokeColor(LINE); c.setLineWidth(0.8)
            c.line(cx0, y - bar_h + 10, cx0, y - 10)
        icon_circle(ic, cx0 + 24, y - bar_h / 2, 13, 13, ring=LINE, glyph=NAVY)
        tx = cx0 + 44
        avail_v = cwid - 44 - 12
        c.setFillColor(MUTED); c.setFont(ser, 9.5)
        c.drawString(tx, y - bar_h / 2 + 3, lab + ':')
        vt = str(val); vf = 12.5
        while vf > 9 and stringWidth(vt, serb, vf) > avail_v:
            vf -= 0.5
        if stringWidth(vt, serb, vf) > avail_v:      # still too long → ellipsise
            while vt and stringWidth(vt + '…', serb, vf) > avail_v:
                vt = vt[:-1]
            vt = (vt + '…') if vt else ''
        c.setFillColor(INK); c.setFont(serb, vf)
        c.drawString(tx, y - bar_h / 2 - 12, vt)
        x_at += cwid
    y -= bar_h + 14

    # ---- results table -----------------------------------------------------
    # Score, Grade and Remark are each independently toggleable — "#" and
    # "SUBJECT" always stay (there's no useful statement of result without
    # the subject list); whichever of the three is hidden, Subject simply
    # absorbs its width rather than leaving a gap.
    results = (s or {}).get('results') or []
    show_score = _opt(opts, 'score')
    show_grade = _opt(opts, 'grade')
    show_remark = _opt(opts, 'remark')
    fixed_w = {'score': 96, 'grade': 92, 'remark': 118}
    kinds = ['num', 'subject']
    if show_score:
        kinds.append('score')
    if show_grade:
        kinds.append('grade')
    if show_remark:
        kinds.append('remark')
    subject_w = PW - 2 * M - 34 - sum(fixed_w[k] for k in kinds if k in fixed_w)
    width_of = dict(fixed_w, num=34, subject=subject_w)
    header_of = {'num': '#', 'subject': 'SUBJECT', 'score': 'SCORE (%)',
                'grade': 'GRADE', 'remark': 'REMARK'}
    align_of = {'num': 'c', 'subject': 'l', 'score': 'c', 'grade': 'c', 'remark': 'c'}
    cols = [width_of[k] for k in kinds]
    headers = [header_of[k] for k in kinds]
    aligns = [align_of[k] for k in kinds]
    x0 = M
    x_of = {}
    xp = x0
    for k, w in zip(kinds, cols):
        x_of[k] = xp
        xp += w
    hh = 28
    c.setFillColor(NAVY); c.rect(x0, y - hh, sum(cols), hh, stroke=0, fill=1)
    cxp = x0
    c.setFont(serb, 10.5); c.setFillColor(WHITE)
    for w, h, al in zip(cols, headers, aligns):
        if al == 'l':
            c.drawString(cxp + 14, y - hh + 9, h)
        else:
            c.drawCentredString(cxp + w / 2, y - hh + 9, h)
        cxp += w
    yy = y - hh
    n = max(1, len(results))
    rh = min(34, max(20, (yy - 150) / n))   # keep room for the summary below
    for i, r in enumerate(results, 1):
        if i % 2 == 0:
            c.setFillColor(ZEBRA); c.rect(x0, yy - rh, sum(cols), rh, stroke=0, fill=1)
        mid = yy - rh / 2
        c.setFillColor(INK); c.setFont(serb, 11)
        c.drawCentredString(x_of['num'] + width_of['num'] / 2, mid - 4, str(i))
        c.setFillColor(INK); c.setFont(ser, 11)
        c.drawString(x_of['subject'] + 14, mid - 4, str(r.subject)[:34])
        if show_score:
            c.setFillColor(INK); c.setFont(ser, 11)
            c.drawCentredString(x_of['score'] + width_of['score'] / 2, mid - 4,
                                '' if r.score is None else str(r.score))
        if show_grade:
            # grade badge
            bgc, fgc, bdc = _grade_badge_colors(r.grade, bw)
            bw2 = 40; bh2 = 20
            bcx = x_of['grade'] + width_of['grade'] / 2
            c.setFillColor(bgc)
            if bdc is not None:
                c.setStrokeColor(bdc); c.setLineWidth(0.8)
            c.roundRect(bcx - bw2 / 2, mid - bh2 / 2, bw2, bh2, 4,
                        stroke=(1 if bdc is not None else 0), fill=1)
            c.setFillColor(fgc); c.setFont(serb, 10.5)
            c.drawCentredString(bcx, mid - 4, (r.grade or '—'))
        if show_remark:
            # remark — WAEC band descriptor (Excellent / Very Good / Good /
            # Credit / Pass / Fail). A fail (F9) is emphasised.
            rk = _waec_remark(r.grade)
            is_fail = (rk == 'Fail')
            remark_color = (_SL['RED'] if (is_fail and not bw) else INK)
            c.setFillColor(remark_color); c.setFont(serb if is_fail else ser, 11)
            c.drawCentredString(x_of['remark'] + width_of['remark'] / 2, mid - 4, rk)
        c.setStrokeColor(LINE); c.setLineWidth(0.6)
        c.line(x0, yy - rh, x0 + sum(cols), yy - rh)
        yy -= rh
    if not results:
        c.setFillColor(MUTED); c.setFont(seri, 11)
        c.drawCentredString(PW / 2, yy - 24, 'No results recorded for this student.')
        yy -= 44
    c.setStrokeColor(NAVY); c.setLineWidth(1)
    c.rect(x0, yy, sum(cols), (y - hh) - yy, stroke=1, fill=0)
    c.rect(x0, y - hh, sum(cols), hh, stroke=1, fill=0)
    y = yy - 14

    # ---- summary panel -----------------------------------------------------
    if _opt(opts, 'summary') and s:
        core = ', '.join(s.get('missing_core') or []) or 'None'
        avg = s.get('average_score')
        rows = [
            (_ICON['layers'], 'Subjects:', str(s.get('subjects', 0)),
             _ICON['award'], 'Credits (C6+):', str(s.get('credits', 0))),
            (_ICON['star'], 'Distinctions (A1–B3):', str(s.get('distinctions', 0)),
             _ICON['chart'], 'Average:', ('%s%%' % avg if avg is not None else '—')),
            (_ICON['check'], '5 credits incl. English & Maths:',
             'YES' if s.get('has_5_incl_core') else 'NO',
             _ICON['clip'], 'Missing core:', core),
        ]
        ph = 30 * len(rows) + 16
        c.setStrokeColor(LINE); c.setFillColor(PANEL); c.setLineWidth(1)
        c.roundRect(M, y - ph, PW - 2 * M, ph, 8, stroke=1, fill=1)
        colw = (PW - 2 * M) / 2
        ry2 = y - 8
        for r in rows:
            for half in (0, 1):
                ic, lab, val = r[half * 3], r[half * 3 + 1], r[half * 3 + 2]
                cx0 = M + half * colw + 12
                midy = ry2 - 15
                icon_circle(ic, cx0 + 11, midy, 11, 11, ring=LINE, glyph=NAVY)
                c.setFillColor(MUTED); c.setFont(ser, 10)
                c.drawString(cx0 + 28, midy + 3.5, lab)
                c.setFillColor(NAVY); c.setFont(serb, 12)
                vx = M + half * colw + colw - 16
                c.drawRightString(vx, midy - 4, str(val)[:22])
                # dotted leader
                lab_end = cx0 + 28 + stringWidth(lab, ser, 10) + 6
                val_w = stringWidth(str(val)[:22], serb, 12)
                c.setDash(1, 2); c.setStrokeColor(LINE); c.setLineWidth(0.6)
                if vx - val_w - 6 > lab_end:
                    c.line(lab_end, midy - 1, vx - val_w - 6, midy - 1)
                c.setDash()
            ry2 -= 30
        y -= ph + 16

    # ---- signatures --------------------------------------------------------
    if signers in ('both', 'teacher', 'principal'):
        labels = []
        if signers in ('both', 'teacher'):
            labels.append('Class Teacher')
        if signers in ('both', 'principal'):
            labels.append('Principal')
        nsig = len(labels)
        sy = max(y - 30, 92)             # y of the signature rule (clear of the panel)
        seg = (PW - 2 * M) / nsig
        halfline = min(84, seg / 2 - 24)
        if nsig == 2:                    # divider between the two signers
            c.setStrokeColor(LINE); c.setLineWidth(0.8)
            c.line(PW / 2, sy + 34, PW / 2, sy - 40)
        for i, lab in enumerate(labels):
            lcx = M + seg * i + seg / 2
            c.setStrokeColor(INK); c.setLineWidth(0.9)          # signature rule
            c.line(lcx - halfline, sy, lcx + halfline, sy)
            c.setFillColor(INK); c.setFont(ser, 11)             # label under the rule
            c.drawCentredString(lcx, sy - 16, lab)
            c.setFillColor(MUTED); c.setFont(ser, 10)           # Date: ______
            dlabel = 'Date:'
            c.drawString(lcx - halfline, sy - 34, dlabel)
            dx = lcx - halfline + stringWidth(dlabel + ' ', ser, 10) + 3
            c.setStrokeColor(LINE); c.setLineWidth(0.7)
            c.line(dx, sy - 34, lcx + halfline, sy - 34)

    # ---- footer ------------------------------------------------------------
    c.setStrokeColor(border); c.setLineWidth(0.8)
    c.line(M, 40, PW - M, 40)
    tail = 'Thank you for choosing %s' % ((school or {}).get('name') or 'our school')
    c.setFillColor(colors.HexColor('#4B4B4B')); c.setFont(seri, 10)
    tw = stringWidth(tail, seri, 10)
    c.drawCentredString(PW / 2, 27, tail)
    c.setFillColor(GOLD)
    for sgn in (-1, 1):
        c.circle(PW / 2 + sgn * (tw / 2 + 12), 30.5, 1.6, stroke=0, fill=1)


def result_slips_pdf(slips, exam, school, opts=None, signers='both', bw=False):
    """One A4 designed "Competence Result" statement per student. ``opts`` toggles
    the identity/banner/summary blocks; ``signers`` chooses the signature line(s).
    ``bw=True`` renders a black-and-white, print-friendly variant."""
    from reportlab.pdfgen import canvas as _canvas
    F = _slip_fonts()
    buf = io.BytesIO()
    PW, PH = A4
    c = _canvas.Canvas(buf, pagesize=A4)
    c.setTitle('Results — %s' % exam.display_name)
    if not slips:
        c.setFont('Times-Roman', 12)
        c.drawCentredString(PW / 2, PH / 2, 'No results to print.')
        c.showPage(); c.save(); buf.seek(0)
        return buf
    for slip in slips:
        _draw_competence_slip(c, PW, PH, slip['student'], slip['summary'],
                              exam, school, opts, signers, F, bw=bw)
        c.showPage()
    c.save(); buf.seek(0)
    return buf
