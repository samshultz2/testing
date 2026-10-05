"""generator_bp — exports routes (split from the former routes/generator.py)."""
from routes.generator import *  # noqa: F401,F403
from utils.generator_times import clock_params, break_after as _break_after
from utils.timeutil import format_clock


def _short(subj, fallback_map, maxlen):
    """The short label to print for a generator subject: the user's own short
    name from /generator/subjects when set, else the built-in abbreviation, else
    a truncation of the full name. Always upper-cased for a consistent look
    across the grid, regardless of how the short name was typed in."""
    if subj is None:
        return ''
    sn = (getattr(subj, 'short_name', '') or '').strip()
    if sn:
        return sn.upper()
    name = getattr(subj, 'name', '') or ''
    return fallback_map.get(name, name[:maxlen]).upper()


def _short_cell(entry, subj, fallback_map, maxlen):
    """The cell text for one slot: `_short(subj, ...)`, plus "/COUNTERPART"
    for each co-scheduled subject annotate_coschedule_pairs() found on an arm
    this document excluded (e.g. "ACC/CRS/GOV" for a 3-arm combined class
    printed as just one arm)."""
    value = _short(subj, fallback_map, maxlen)
    for pair in getattr(entry, 'coschedule_pairs', None) or []:
        value += '/' + _short(pair, fallback_map, maxlen)
    return value


# A4 and A3 landscape share one aspect ratio, but the fixed-inch margins
# used throughout the xlsx exports below eat a smaller share of the bigger
# page, so the real scale factor between them isn't a flat sqrt(2) -- it has
# to be computed against the actual usable area. Shared by every xlsx export
# below so A4 vs A3 sizing math can't drift between them.
_XLSX_A4_W_PT, _XLSX_A4_H_PT = 841.89, 595.28    # A4 landscape points (297 x 210mm)
_XLSX_A3_W_PT, _XLSX_A3_H_PT = 1190.55, 841.89   # A3 landscape points (420 x 297mm)


def _xlsx_paper_scale(paper, margin_lr_in=0.5, margin_tb_in=0.4):
    """Real physical-size scale factors for an A4-vs-A3 landscape xlsx sheet
    with the given fixed-inch margins on each side. Returns
    (hscale, wscale, fit_scale, usable_w, usable_h) in points -- hscale/
    wscale scale a row height / column width from its A4 baseline up for
    A3, fit_scale (the tighter of the two) is for anything confined to one
    column AND row, like a font size."""
    page_w_pt, page_h_pt = (_XLSX_A3_W_PT, _XLSX_A3_H_PT) if paper == 'a3' else (_XLSX_A4_W_PT, _XLSX_A4_H_PT)
    usable_w = page_w_pt - 2 * margin_lr_in * 72
    usable_h = page_h_pt - 2 * margin_tb_in * 72
    baseline_w = _XLSX_A4_W_PT - 2 * margin_lr_in * 72
    baseline_h = _XLSX_A4_H_PT - 2 * margin_tb_in * 72
    hscale = usable_h / baseline_h
    wscale = usable_w / baseline_w
    fit_scale = min(hscale, wscale)
    return hscale, wscale, fit_scale, usable_w, usable_h


def _xlsx_col_width_for_pts(target_pts):
    """Convert a target physical column width (points) into Excel's
    'character width' unit (approx. Calibri 11: ~7px/char + 5px padding at
    96 DPI) -- Excel's width model is defined against that font's metrics
    regardless of what font actually renders inside the column."""
    px = target_pts * 96 / 72
    return max(1.0, (px - 5) / 7)


@generator_bp.route('/results/<batch_id>/print')
@login_required
def print_results(batch_id):
    level = get_current_level()
    all_results = GenTimetableResult.query.filter_by(batch_id=batch_id, school_level=level, branch_id=gen_bid()).all()
    if not all_results:
        flash('No results.', 'error')
        return redirect(url_for('generator.results_list'))

    results = filter_results_by_arm(all_results)
    if not results:
        flash('No class-arms selected.', 'error')
        return redirect(url_for('generator.view_results', batch_id=batch_id))
    annotate_coschedule_pairs(all_results, results)

    timetables = {}
    for r in results:
        key = f"{r.class_name}_{r.arm_name}"
        if key not in timetables:
            timetables[key] = {'class_name': r.class_name, 'arm_name': r.arm_name, 'grid': {d: {} for d in range(5)}}
        timetables[key]['grid'][r.day_of_week][r.period_number] = r
    
    school_level = results[0].school_level or 'sss'
    rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(is_active=True, school_level=school_level, branch_id=gen_bid()).all()}

    return render_template('generator/print_results.html',
        batch_id=batch_id, timetables=dict(sorted(timetables.items())),
        periods_per_day=int(rules.get('periods_per_day', 8)),
        break_after_period=int(rules.get('break_after_period', 5)),
        days=DAYS_OF_WEEK,
        school_name=GenSettings.get('school_name', ''),
        academic_year=GenSettings.get('academic_year', ''),
        term_name=GenSettings.get('term_name', '')
    )


@generator_bp.route('/results/<batch_id>/print/<class_name>/<arm_name>')
@login_required
def print_single_timetable(batch_id, class_name, arm_name):
    results = GenTimetableResult.query.filter_by(batch_id=batch_id, class_name=class_name, arm_name=arm_name, branch_id=gen_bid()).all()
    if not results:
        flash('Not found.', 'error')
        return redirect(url_for('generator.view_results', batch_id=batch_id))

    # Printing a single arm always excludes every other arm, so show any
    # co-scheduled counterpart subject right alongside this one (e.g. "ACC/CRS").
    all_results = GenTimetableResult.query.filter_by(batch_id=batch_id, branch_id=gen_bid()).all()
    annotate_coschedule_pairs(all_results, results)

    grid = {d: {} for d in range(5)}
    for r in results:
        grid[r.day_of_week][r.period_number] = r
    
    school_level = results[0].school_level or 'sss'
    rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(is_active=True, school_level=school_level, branch_id=gen_bid()).all()}

    return render_template('generator/print_single.html',
        batch_id=batch_id, class_name=class_name, arm_name=arm_name, grid=grid,
        periods_per_day=int(rules.get('periods_per_day', 8)),
        break_after_period=int(rules.get('break_after_period', 5)),
        days=DAYS_OF_WEEK,
        school_name=GenSettings.get('school_name', ''),
        academic_year=GenSettings.get('academic_year', ''),
        term_name=GenSettings.get('term_name', '')
    )


@generator_bp.route('/results/<batch_id>/print/<class_name>/<arm_name>/pdf')
@login_required
def print_single_timetable_pdf(batch_id, class_name, arm_name):
    """One class-arm's full week as a single-page A4-landscape PDF, filling
    the available space — a proper backend-rendered document rather than a
    browser print-to-PDF of the HTML view. ?teachers=0 drops the teacher
    name from each cell (on by default)."""
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    include_teachers = request.args.get('teachers', '1') != '0'

    results = GenTimetableResult.query.filter_by(batch_id=batch_id, class_name=class_name,
                                                  arm_name=arm_name, branch_id=gen_bid()).all()
    if not results:
        flash('Not found.', 'error')
        return redirect(url_for('generator.view_results', batch_id=batch_id))

    all_results = GenTimetableResult.query.filter_by(batch_id=batch_id, branch_id=gen_bid()).all()
    annotate_coschedule_pairs(all_results, results)

    grid = {d: {} for d in range(5)}
    for r in results:
        grid[r.day_of_week][r.period_number] = r

    school_level = results[0].school_level or 'sss'
    rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(
        is_active=True, school_level=school_level, branch_id=gen_bid()).all()}
    periods_per_day = int(rules.get('periods_per_day', 8))
    break_after = _break_after(rules, periods_per_day)

    school_name = GenSettings.get('school_name', 'School')
    school_address = GenSettings.get('school_address', '')

    abbrev_map = {
        'Mathematics': 'Maths', 'English Language': 'Eng', 'Physics': 'Phy',
        'Chemistry': 'Chem', 'Biology': 'Bio', 'Economics': 'Econs',
        'Government': 'Govt', 'Literature in English': 'Lit', 'Agricultural Science': 'Agric',
        'Christian Religious Studies': 'CRS', 'Civic Education': 'Civic',
        'Computer Studies': 'Comp', 'Commerce': 'Comm', 'Geography': 'Geo',
        'Further Mathematics': 'F/Mth', 'Livestock Farming': 'Livst',
        'History': 'Hist', 'Phonics': 'Phon',
    }

    output = BytesIO()
    margin = 10 * mm
    # SimpleDocTemplate wraps its content in a Frame with a default 6pt
    # padding on every side (on top of the doc's own margins) — the table's
    # row heights must budget for that too, or the last sliver of the table
    # spills onto an unwanted second page.
    frame_pad = 6
    doc = SimpleDocTemplate(output, pagesize=landscape(A4),
                            leftMargin=margin, rightMargin=margin,
                            topMargin=margin, bottomMargin=margin)
    page_w, page_h = landscape(A4)
    usable_width = page_w - 2 * margin - 2 * frame_pad

    first_col_width = 22 * mm
    period_col_width = (usable_width - first_col_width) / periods_per_day
    col_widths = [first_col_width] + [period_col_width] * periods_per_day

    subject_font_size = 12 if include_teachers else 14
    cell_style = ParagraphStyle('cell', fontName='Helvetica-Bold', fontSize=subject_font_size,
                                alignment=TA_CENTER, leading=subject_font_size + 2)

    # Build the cell content for one (day, period) slot as a Paragraph, so a
    # long subject/teacher name wraps within its own column instead of
    # overflowing into the next one (a plain string, with no word-wrap,
    # would just spill over visually).
    def cell_lines(day_idx, period):
        entry = grid[day_idx].get(period)
        if not entry or not entry.subject:
            return Paragraph('-', cell_style)
        label = escape(_short(entry.subject, abbrev_map, 8))
        for pair in getattr(entry, 'coschedule_pairs', None) or []:
            label += '/' + escape(_short(pair, abbrev_map, 8))
        text = f'<b>{label}</b>'
        if include_teachers and entry.teacher:
            text += f'<br/><font size="9">{escape(entry.teacher.name)}</font>'
        return Paragraph(text, cell_style)

    header_row = ['Period'] + DAYS_OF_WEEK
    table_data = [header_row]
    for p in range(1, periods_per_day + 1):
        row = [f'P{p}'] + [cell_lines(d, p) for d in range(5)]
        table_data.append(row)
        if p == break_after:
            table_data.append(['BREAK'] + [''] * 5)

    title_style = ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=16, alignment=TA_CENTER, leading=19)
    subtitle_style = ParagraphStyle('subtitle', fontName='Helvetica', fontSize=10, alignment=TA_CENTER,
                                    textColor=colors.HexColor('#555555'), leading=12)

    title_elements = [Paragraph(f'{school_name.upper()}', title_style)]
    if school_address:
        title_elements.append(Paragraph(school_address, subtitle_style))
    title_elements.append(Paragraph(f'{class_name} {arm_name} — Weekly Timetable', title_style))
    spacer = Spacer(1, 4)

    # Measure the actual rendered height of everything above the table (the
    # title block can vary with whether there's a school address), so the
    # table's own row heights are sized to exactly fill what's left on the
    # page rather than guessed — a guess that's even slightly too generous
    # here means the table spills onto an unwanted second page.
    title_block_height = spacer.height
    for el in title_elements:
        _, h = el.wrap(usable_width, page_h)
        title_block_height += h

    num_rows = len(table_data)
    header_height = 10 * mm
    available_height = page_h - 2 * margin - 2 * frame_pad - title_block_height - header_height
    data_row_height = available_height / (num_rows - 1)
    row_heights = [header_height] + [data_row_height] * (num_rows - 1)

    table = Table(table_data, colWidths=col_widths, rowHeights=row_heights, repeatRows=1)
    break_row_indices = [i for i, row in enumerate(table_data) if row[0] == 'BREAK']
    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 13),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (0, -1), subject_font_size),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.75, colors.HexColor('#666666')),
        ('BOX', (0, 0), (-1, -1), 1.5, colors.black),
    ]
    for ri in break_row_indices:
        style_cmds.append(('SPAN', (1, ri), (-1, ri)))
        style_cmds.append(('BACKGROUND', (0, ri), (-1, ri), colors.HexColor('#FF6B6B')))
        style_cmds.append(('TEXTCOLOR', (0, ri), (-1, ri), colors.white))
        style_cmds.append(('FONTSIZE', (0, ri), (-1, ri), 10))
    table.setStyle(TableStyle(style_cmds))

    elements = title_elements + [spacer, table]

    doc.build(elements)
    return pdf_response(output, f'timetable_{class_name}_{arm_name}_{batch_id}.pdf')


@generator_bp.route('/results/<batch_id>/export')
@login_required
def export_results(batch_id):
    """Export timetable by class - Each class MAXIMIZES its page (A4 or A3
    landscape, ?paper=a4|a3), no teacher names, NO COLORS for B&W printing"""
    import openpyxl
    from openpyxl.styles import Font, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    paper = (request.args.get('paper') or 'a4').lower()
    if paper not in ('a4', 'a3'):
        paper = 'a4'

    # Row/column/font sizing below was tuned for A4 landscape. Excel's own
    # fitToPage scaling (set further down) only kicks in when actually
    # PRINTING -- opened plainly in Excel/LibreOffice/Sheets the content
    # would be the same physical size on A4 and A3, just surrounded by more
    # blank page. Scale every size up for A3 so the sheet itself already
    # fills the bigger page.
    hscale, wscale, fit_scale, usable_w, usable_h = _xlsx_paper_scale(paper)
    # NOT applying _XLSX_GRID_FILL to width here (export_results used to, and
    # it directly caused subject codes with a wide letter like "M" --
    # "CHM", "MTH" -- to wrap mid-word even at "no scaling": fitToPage is
    # set below and rescales the WHOLE sheet by one uniform factor when a
    # viewer prints with it on, which doesn't change the width:font-size
    # RATIO a column's text wraps against, so shrinking width specifically
    # (while fonts, scaled by fit_scale, stayed the same) broke wrapping in
    # fit-to-page mode too, not just at "no scaling". It also broke the
    # width:height aspect-ratio match this file depends on for fit-to-page
    # to fill the page on both axes at once, which is what showed up as
    # blank margin on the sides. usable_w/usable_h stay at the exact
    # physical page size; PERIOD_COL_MIN_PT below (not a blanket shrink)
    # is what guards against "no scaling" overflow instead.

    def sc(pt):
        """Scale by page height -- for full-width single-line rows."""
        return pt * hscale

    def sc_w(width):
        """Scale by page width -- for column widths."""
        return width * wscale

    def sc_fit(pt):
        """Scale by whichever axis is tighter -- for font sizes, so text
        never outgrows the column/row it sits in."""
        return round(pt * fit_scale)

    all_results = GenTimetableResult.query.filter_by(batch_id=batch_id, branch_id=gen_bid()).all()
    if not all_results:
        flash('No results.', 'error')
        return redirect(url_for('generator.results_list'))
    results = filter_results_by_arm(all_results)
    if not results:
        flash('No class-arms selected.', 'error')
        return redirect(url_for('generator.view_results', batch_id=batch_id))
    annotate_coschedule_pairs(all_results, results)

    # Get school info
    school_name = GenSettings.get('school_name', 'School')
    school_address = GenSettings.get('school_address', '')

    timetables = {}
    for r in results:
        key = f"{r.class_name}_{r.arm_name}"
        if key not in timetables:
            timetables[key] = {'class_name': r.class_name, 'arm_name': r.arm_name, 'grid': {d: {} for d in range(5)}}
        timetables[key]['grid'][r.day_of_week][r.period_number] = r

    school_level = results[0].school_level or 'sss'
    rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(is_active=True, school_level=school_level, branch_id=gen_bid()).all()}
    periods_per_day = int(rules.get('periods_per_day', 8))
    break_after = _break_after(rules, periods_per_day)

    # Period time slots — start/period-length/break-length are per-level settings.
    period_times = []
    break_time = ""
    start_hour, start_min, _plen, _blen = clock_params(rules)
    for p in range(1, periods_per_day + 1):
        start_total = start_hour * 60 + start_min
        end_total = start_total + _plen
        start_h, start_m = start_total // 60, start_total % 60
        end_h, end_m = end_total // 60, end_total % 60
        period_times.append(f"P{p}\n{format_clock(start_h, start_m)}-{format_clock(end_h, end_m)}")
        start_hour, start_min = end_h, end_m
        if p == break_after:
            break_start = format_clock(end_h, end_m)
            start_total = start_hour * 60 + start_min + _blen
            start_hour, start_min = start_total // 60, start_total % 60
            break_end = format_clock(start_hour, start_min)
            break_time = f"BREAK\n{break_start}-{break_end}"

    # Abbreviations
    abbrev_map = {
        'Mathematics': 'Maths', 'English Language': 'Eng', 'Physics': 'Phy',
        'Chemistry': 'Chem', 'Biology': 'Bio', 'Economics': 'Econs',
        'Government': 'Govt', 'Literature in English': 'Lit', 'Agricultural Science': 'Agric',
        'Christian Religious Studies': 'CRS', 'Civic Education': 'Civic',
        'Computer Studies': 'Comp', 'Commerce': 'Comm', 'Geography': 'Geo',
        'Further Mathematics': 'F/Mth', 'Livestock Farming': 'Livst',
        'History': 'Hist', 'Phonics': 'Phon',
    }
    
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    
    # NO COLORS - Pure black text on white, maximum contrast for B&W printing.
    # Sizes are the A4 baseline; sc_fit() scales them up for A3 so the
    # period-time headers (and everything else) stay legible-sized instead
    # of looking lost in bigger cells. header_font governs the period-time
    # headers specifically -- bumped from 11 to 20 (an earlier pass only
    # got as far as 14, still reported as too small) so they read as bold
    # and big even at the A4 baseline, not just proportionally on A3.
    school_font = Font(bold=True, size=sc_fit(32), color='000000')
    address_font = Font(bold=False, size=sc_fit(14), color='000000')
    class_title_font = Font(bold=True, size=sc_fit(28), color='000000')
    day_font = Font(bold=True, size=sc_fit(24), color='000000')
    header_font = Font(bold=True, size=sc_fit(20), color='000000')
    cell_font = Font(bold=True, size=sc_fit(32), color='000000')
    break_header_font = Font(bold=True, size=sc_fit(10), color='000000')

    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    thick_border = Border(
        left=Side(style='medium'), right=Side(style='medium'),
        top=Side(style='medium'), bottom=Side(style='medium')
    )

    center_align = Alignment(horizontal='center', vertical='center', wrap_text=True)

    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

    # Total columns: Day label + periods-before + BREAK + periods-after.
    total_cols = 1 + break_after + 1 + (periods_per_day - break_after)
    break_col = break_after + 2  # 1 (Day) + before-break periods, then BREAK

    # A4 Landscape: 297mm x 210mm
    # Safe margins for most printers: 0.5" (12.7mm) each side
    # Usable: ~272mm x 185mm
    # Always landscape (set per-sheet below). Filled to the EXACT usable
    # height/width (not a conservative under-estimate) so the grid itself
    # fills the page -- previously the row-height total (a flat "500pt,
    # conservative for A4") and the column-width total (12/28/8 character
    # units, independent of any physical measurement) had wildly different
    # aspect ratios from the actual page, so Excel's own fitToPage, which
    # applies ONE uniform scale bound by whichever axis is tighter, shrank
    # to fit the (much too wide) columns and left the rows far short of the
    # page height -- most of it blank top and bottom once centered. That
    # mismatch scaled up right along with everything else for A3, which is
    # why it became obvious there. Sizing both totals to the real usable
    # dimensions up front removes the mismatch instead of just scaling it.
    # Column widths computed FIRST -- the Day and BREAK columns' content
    # needs a roughly FIXED physical width regardless of periods_per_day --
    # "Wed" at day_font size, or "BREAK"/a time like "11:10" at
    # break_header_font size, take the same room whether there are 6
    # periods or 9. Splitting the page width by a *proportional share* (as
    # before) let those two columns get squeezed to near nothing on a day
    # with many periods, wrapping "Wednesday" letter-by-letter and crushing
    # the break label. Reserve a fixed floor for each (scaled for A3 like
    # everything else), then split whatever's left evenly across the
    # actual period columns.
    DAY_FLOOR_PT = sc_w(60)    # fits a 3-letter day abbreviation at day_font size
    BREAK_FLOOR_PT = sc_w(42)  # fits "BREAK" / a time label at break_header_font size
    period_cols = total_cols - 2  # all period columns, before + after break
    # A plain character-count average undersells how much room bold text
    # actually needs once a code contains a wide letter -- "CHM"/"MTH"
    # (both containing "M", one of the widest letters in most fonts) wrapped
    # mid-word at a width that fit other, narrower 3-letter codes fine in
    # the same column. Floored per-character at a generous fraction of
    # cell_font's own point size, for a 4-char code (covers the built-in
    # abbreviation fallbacks too, several of which run to 4-5 letters).
    PERIOD_COL_MIN_PT = cell_font.size * 0.9 * 4
    period_col_pts = max((usable_w - DAY_FLOOR_PT - BREAK_FLOOR_PT) / period_cols, PERIOD_COL_MIN_PT)
    natural_width = DAY_FLOOR_PT + BREAK_FLOOR_PT + period_cols * period_col_pts

    day_col_width = _xlsx_col_width_for_pts(DAY_FLOOR_PT)
    period_col_width = _xlsx_col_width_for_pts(period_col_pts)
    break_col_width = _xlsx_col_width_for_pts(BREAK_FLOOR_PT)

    # Heights, computed AFTER width -- a dense day (many periods, or codes
    # with a wide letter) can force natural_width past usable_w via the
    # floor above. Under "fit to page" that's fine BY ITSELF (Excel/Sheets
    # still scale the whole sheet down to one page, uniformly, so nothing
    # wraps worse than it already doesn't) -- but letting width grow while
    # height stayed at exactly usable_h would make the aspect ratio
    # narrower than the page's own, so the uniform scale would end up
    # bound by width and leave the page's TOP and BOTTOM under-filled once
    # printed. Growing the height budget by that same overflow ratio keeps
    # the two in proportion, so fit-to-page still fills the whole page on
    # both axes -- "no scaling" mode simply needs more than one page in
    # that case, same as it already does width-wise.
    total_page_height = usable_h * max(1.0, natural_width / usable_w)
    school_header_height = sc(38)
    address_header_height = sc(20) if school_address else 0
    class_title_height = sc(32)
    # Needs to fit 3 wrapped lines at header_font's size (e.g. "P1" /
    # "8:00 AM-" / "8:40 AM") without the text overflowing a fixed row
    # height -- Excel/Sheets center wrap_text vertically and CLIP whatever
    # doesn't fit, which is what cut the header text off at the top.
    # Grown along with header_font's own bump to 20pt.
    period_header_height = sc(95)
    # 5 day rows get ALL remaining space, floored against cell_font's own
    # (already A3-scaled) size so a single line of cell text can't end up
    # taller than its row.
    fixed_height = school_header_height + address_header_height + class_title_height + period_header_height
    min_day_row_height = cell_font.size * 1.3
    day_row_height = max((total_page_height - fixed_height) / 5, min_day_row_height)
    
    for key in sorted(timetables.keys()):
        tt = timetables[key]
        ws = wb.create_sheet(title=f"{tt['class_name']} {tt['arm_name']}"[:31])
        
        # Page setup - fit on ONE page of the chosen paper size
        ws.page_setup.paperSize = ws.PAPERSIZE_A3 if paper == 'a3' else ws.PAPERSIZE_A4
        ws.page_setup.orientation = 'landscape'
        ws.page_setup.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 1
        ws.print_options.horizontalCentered = True
        ws.print_options.verticalCentered = True
        
        # Safe margins for most printers (0.5 inch = 12.7mm)
        ws.page_margins.left = 0.5
        ws.page_margins.right = 0.5
        ws.page_margins.top = 0.4
        ws.page_margins.bottom = 0.4
        ws.page_margins.header = 0
        ws.page_margins.footer = 0
        
        current_row = 1
        
        # School name
        ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=total_cols)
        cell = ws.cell(row=current_row, column=1, value=school_name.upper())
        cell.font = school_font
        cell.alignment = center_align
        ws.row_dimensions[current_row].height = school_header_height
        current_row += 1
        
        # School address
        if school_address:
            ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=total_cols)
            cell = ws.cell(row=current_row, column=1, value=school_address)
            cell.font = address_font
            cell.alignment = center_align
            ws.row_dimensions[current_row].height = address_header_height
            current_row += 1
        
        # Class title
        ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=total_cols)
        cell = ws.cell(row=current_row, column=1, value=f"{tt['class_name']} {tt['arm_name']} - TIMETABLE")
        cell.font = class_title_font
        cell.alignment = center_align
        cell.border = thick_border
        for col in range(1, total_cols + 1):
            ws.cell(row=current_row, column=col).border = thick_border
        ws.row_dimensions[current_row].height = class_title_height
        current_row += 1
        
        # Period header row (times)
        col = 1
        cell = ws.cell(row=current_row, column=col, value="Day")
        cell.font = header_font
        cell.border = thick_border
        cell.alignment = center_align
        col += 1
        
        # Before-break period headers
        for i in range(break_after):
            cell = ws.cell(row=current_row, column=col, value=period_times[i])
            cell.font = header_font
            cell.border = thick_border
            cell.alignment = center_align
            col += 1

        # Break header
        cell = ws.cell(row=current_row, column=col, value=break_time)
        cell.font = break_header_font
        cell.border = thick_border
        cell.alignment = center_align
        col += 1

        # After-break period headers
        for i in range(break_after, periods_per_day):
            cell = ws.cell(row=current_row, column=col, value=period_times[i])
            cell.font = header_font
            cell.border = thick_border
            cell.alignment = center_align
            col += 1
        
        ws.row_dimensions[current_row].height = period_header_height
        current_row += 1
        
        # Data rows (one per day)
        for day_idx, day_name in enumerate(days):
            col = 1

            # Day name -- abbreviated to 3 letters: at day_font's size
            # (24pt+ bold) the Day column only has room for a short code,
            # not the full word, without wrapping letter-by-letter.
            cell = ws.cell(row=current_row, column=col, value=day_name[:3].upper())
            cell.font = day_font
            cell.border = thick_border
            cell.alignment = center_align
            col += 1
            
            # Before-break periods
            for p in range(1, break_after + 1):
                entry = tt['grid'][day_idx].get(p)
                value = ""
                if entry and entry.subject:
                    value = _short_cell(entry, entry.subject, abbrev_map, 6)

                cell = ws.cell(row=current_row, column=col, value=value)
                cell.font = cell_font
                cell.border = thin_border
                cell.alignment = center_align
                col += 1

            # Break column - empty with border
            cell = ws.cell(row=current_row, column=col, value="")
            cell.border = thin_border
            col += 1

            # After-break periods
            for p in range(break_after + 1, periods_per_day + 1):
                entry = tt['grid'][day_idx].get(p)
                value = ""
                if entry and entry.subject:
                    value = _short_cell(entry, entry.subject, abbrev_map, 6)
                
                cell = ws.cell(row=current_row, column=col, value=value)
                cell.font = cell_font
                cell.border = thin_border
                cell.alignment = center_align
                col += 1
            
            ws.row_dimensions[current_row].height = day_row_height
            current_row += 1
        
        # Column widths - precomputed above to exactly fill the usable width.
        ws.column_dimensions['A'].width = day_col_width  # Day column
        for col in range(2, total_cols + 1):
            if col == break_col:
                ws.column_dimensions[get_column_letter(col)].width = break_col_width
            else:
                ws.column_dimensions[get_column_letter(col)].width = period_col_width
    
    return xlsx_response(wb, f'timetables_{batch_id}_{paper}.xlsx')


@generator_bp.route('/results/<batch_id>/export_by_day')
@login_required
def export_results_by_day(batch_id):
    """Export timetable in day-wise format — one day per sheet (A4 or A3), or
    on A3, two days stacked on one sheet ("packed"). NO COLORS.

    ?paper=a4|a3 (default a4), ?layout=single|packed (default single; packed
    only takes effect on A3). Excel's own fitToPage scaling does the actual
    size-to-fit-one-page work, so paper size alone already makes a single
    day bigger on A3 — packed just stacks two days into that same fit."""
    import openpyxl
    from openpyxl.styles import Font, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    paper = (request.args.get('paper') or 'a4').lower()
    if paper not in ('a4', 'a3'):
        paper = 'a4'
    layout = (request.args.get('layout') or 'single').lower()
    days_per_page = 2 if (paper == 'a3' and layout == 'packed') else 1

    # Same real-physical-size scaling as export_results(). usable_h is the
    # full page's usable height for an UNPACKED (1 day/page) sheet; a packed
    # A3 page stacks 2 of those blocks plus a gap into that same usable_h,
    # so each block's own height budget is computed further down once
    # days_per_page is known.
    hscale, wscale, fit_scale, usable_w, usable_h = _xlsx_paper_scale(paper)
    # NOT applying _XLSX_GRID_FILL to width here (export_results used to, and
    # it directly caused subject codes with a wide letter like "M" --
    # "CHM", "MTH" -- to wrap mid-word even at "no scaling": fitToPage is
    # set below and rescales the WHOLE sheet by one uniform factor when a
    # viewer prints with it on, which doesn't change the width:font-size
    # RATIO a column's text wraps against, so shrinking width specifically
    # (while fonts, scaled by fit_scale, stayed the same) broke wrapping in
    # fit-to-page mode too, not just at "no scaling". It also broke the
    # width:height aspect-ratio match this file depends on for fit-to-page
    # to fill the page on both axes at once, which is what showed up as
    # blank margin on the sides. usable_w/usable_h stay at the exact
    # physical page size; PERIOD_COL_MIN_PT below (not a blanket shrink)
    # is what guards against "no scaling" overflow instead.

    def sc(pt):
        """Scale by page height -- for full-width single-line rows."""
        return pt * hscale

    def sc_w(width):
        """Scale by page width -- for column widths."""
        return width * wscale

    def sc_fit(pt):
        """Scale by whichever axis is tighter -- for font sizes, so text
        never outgrows the column/row it sits in."""
        return round(pt * fit_scale)

    all_results = GenTimetableResult.query.filter_by(batch_id=batch_id, branch_id=gen_bid()).all()
    if not all_results:
        flash('No results.', 'error')
        return redirect(url_for('generator.results_list'))
    results = filter_results_by_arm(all_results)
    if not results:
        flash('No class-arms selected.', 'error')
        return redirect(url_for('generator.view_results', batch_id=batch_id))
    annotate_coschedule_pairs(all_results, results)

    # Determine school level from results
    school_level = results[0].school_level if results else 'sss'
    
    rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(is_active=True, school_level=school_level, branch_id=gen_bid()).all()}
    periods_per_day = int(rules.get('periods_per_day', 8))
    break_after = _break_after(rules, periods_per_day)

    # Get school info
    school_name = GenSettings.get('school_name', 'School')
    school_address = GenSettings.get('school_address', '')

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

    # Period time slots — start/period-length/break-length are per-level settings.
    period_times_before_break = []  # before the break
    period_times_after_break = []   # after the break
    break_time = ""

    start_hour, start_min, _plen, _blen = clock_params(rules)
    for p in range(1, periods_per_day + 1):
        start_total = start_hour * 60 + start_min
        end_total = start_total + _plen
        start_h, start_m = start_total // 60, start_total % 60
        end_h, end_m = end_total // 60, end_total % 60
        start_str = format_clock(start_h, start_m)
        end_str = format_clock(end_h, end_m)

        if p <= break_after:
            period_times_before_break.append(f"P{p}\n{start_str}\n{end_str}")
        else:
            period_times_after_break.append(f"P{p}\n{start_str}\n{end_str}")

        start_hour, start_min = end_h, end_m

        # Capture break time after the configured period
        if p == break_after:
            break_start = format_clock(end_h, end_m)
            start_total = start_hour * 60 + start_min + _blen
            start_hour, start_min = start_total // 60, start_total % 60
            break_end = format_clock(start_hour, start_min)
            break_time = f"BREAK\n{break_start}-{break_end}"

    class_arms = sorted(set((r.class_name, r.arm_name) for r in results))
    
    def get_short_code(class_name, arm):
        if class_name.startswith('JSS'):
            class_num = class_name.replace('JSS', '')
            arm_letter = arm[0].upper()
            return f"J{class_num}{arm_letter}"
        else:
            class_num = class_name.replace('SSS', '')
            arm_letter = arm[0].upper()
            return f"{class_num}{arm_letter}"
    
    abbrev_map = {
        'Mathematics': 'Maths',
        'English Language': 'Eng',
        'Physics': 'Phy',
        'Chemistry': 'Chem',
        'Biology': 'Bio',
        'Economics': 'Econs',
        'Government': 'Govt',
        'Literature in English': 'Lit',
        'Agricultural Science': 'Agric',
        'Christian Religious Studies': 'CRS',
        'Civic Education': 'Civic',
        'Computer Studies': 'Comp',
        'Commerce': 'Comm',
        'Geography': 'Geo',
        'Further Mathematics': 'F/Mth',
        'Livestock Farming': 'Livst',
        'History': 'Hist',
        'Phonics': 'Phon',
        # JSS subjects
        'Basic Science': 'B.Sci',
        'Basic Technology': 'B.Tech',
        'Social Studies': 'Soc',
        'Home Economics': 'H/Eco',
        'Business Studies': 'Bus',
        'Physical Health Education': 'PHE',
        'Islamic Religious Studies': 'IRS',
        'French': 'Fren',
        'Yoruba': 'Yor',
        'Igbo': 'Igbo',
        'Hausa': 'Hau',
        'Music': 'Music',
        'Fine Art': 'Art',
        'Data Processing': 'D.Pro',
        'Marketing': 'Mkt',
        'Accounting': 'Acct',
        'Food and Nutrition': 'F&N',
    }
    
    # Build a lookup dict for subjects
    subject_lookup = {s.id: s for s in GenSubject.query.filter_by(is_active=True, school_level=school_level, branch_id=gen_bid()).all()}
    
    # NO COLORS - Pure black text on white for B&W printing. Sizes are the
    # A4 baseline; sc_fit() scales them up for A3 the same way export_results
    # does, so the grid fills the bigger page instead of just Excel's
    # print-time fit.
    school_font = Font(bold=True, size=sc_fit(24), color='000000')
    address_font = Font(bold=False, size=sc_fit(12), color='000000')
    day_font = Font(bold=True, size=sc_fit(32), color='000000')
    header_font = Font(bold=True, size=sc_fit(14), color='000000')
    class_font = Font(bold=True, size=sc_fit(20), color='000000')
    # Bumped from 24 -- the data-row floor below is derived from this size,
    # so a bigger cell_font is what actually grows the printed cell/font
    # size for typical class counts (see min_data_row_height's comment: the
    # floor is ALREADY the binding constraint for realistic data volumes,
    # not just the dense 15-arm stress case, so raising the baseline here is
    # the one lever that reliably makes cells read bigger on a real page).
    # A first pass only went to 30 -- measured against a real print render,
    # that was NOT visibly different from the original 24 (the uniform
    # fit-to-page shrink mostly absorbed it, same mechanism as the margin
    # bug above: a bigger floor also raises overflow_ratio, so the PRINTED
    # size gains much less than the raw point value suggests, and keeps
    # diminishing the higher this goes). Went further, to 40, and paired it
    # with real header-row trims below (not just font) so some of this
    # actually reaches the page instead of being shrunk back out -- also
    # re-verified against a real print render, this time against the
    # previous (pre-this-session) baseline, not just the intermediate 30.
    cell_font = Font(bold=True, size=sc_fit(40), color='000000')
    break_header_font = Font(bold=True, size=sc_fit(10), color='000000')
    
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    thick_border = Border(
        left=Side(style='medium'),
        right=Side(style='medium'),
        top=Side(style='medium'),
        bottom=Side(style='medium')
    )
    
    center_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
    
    # Total columns: Class + periods-before + BREAK + periods-after.
    total_cols = 1 + break_after + 1 + (periods_per_day - break_after)
    break_col = break_after + 2   # 1 (Class) + break_after period columns, then BREAK

    # Floors for both axes computed FIRST, before either width or height is
    # finalized -- Class/BREAK columns need a roughly FIXED physical width
    # regardless of periods_per_day (see export_results's comment on the
    # same issue), and data rows need a minimum height regardless of how
    # many class-arms are packed in. Either floor can independently force
    # its axis's NATURAL (unconstrained) size past that axis's usable page
    # size -- a wide `periods_per_day` overflows width, a tall class-arm
    # count (doubled again on a packed A3 page, which stacks 2 days'
    # worth of rows into one page) overflows height.
    num_data_rows = len(class_arms)
    CLASS_FLOOR_PT = sc_w(50)   # fits a short class code ("S1A") at class_font size
    BREAK_FLOOR_PT = sc_w(42)   # fits "BREAK" / a time label at break_header_font size
    period_cols = total_cols - 2
    PERIOD_COL_MIN_PT = cell_font.size * 0.9 * 4
    natural_width_floor = CLASS_FLOOR_PT + BREAK_FLOOR_PT + period_cols * PERIOD_COL_MIN_PT

    # Rounded to 2dp at the source so every sheet's total (summed in a
    # different order/grouping per sheet) lands on the exact same float --
    # otherwise IEEE754 rounding noise (~1e-13) can make two sheets that are
    # supposed to be pixel-identical compare unequal.
    # Trimmed from 35/20 -- still has headroom over school_font/address_font's
    # own (A3-scaled) single-line height, just less spare than before.
    school_header_height = round(sc(28), 2)
    address_header_height = round(sc(16), 2)
    # Trimmed from 45 -- still has headroom over day_font's own (A3-scaled)
    # height, just less spare than before, freeing that difference (doubled,
    # on a packed page's 2 day-banners) for the data rows below instead.
    day_header_height = round(sc(42), 2)
    # Trimmed from 68 -- still fits the 3 stacked period-header lines ("P1" /
    # start / end) at header_font's (now A3-scaled) size without clipping,
    # just with less spare margin above/below the text than before. This is
    # the single biggest fixed-overhead row on the page (bigger than school
    # + address combined), so it's the main lever -- besides cell_font
    # itself -- for how much headroom is actually left for data rows.
    period_header_height = round(sc(52), 2)
    # Trimmed from 15 -- purely a blank spacer row between stacked days, no
    # text to clip, so shrinking it is free room for the data rows below.
    gap_row_height = round(sc(3), 2)  # between stacked day-blocks on a packed page

    # One data-row height for the WHOLE export -- every day, every page, every
    # sheet uses this exact value, so row sizing reads as consistent instead
    # of Monday's rows (which share a page with the school name/address) being
    # visibly shorter than every other day's. Sized against the tightest
    # case -- the group containing Monday, which carries the school header
    # AND (being first in its group) the period-header row -- a day_header
    # per block but the school/address/period-header overhead only ONCE per
    # GROUP (every other block in a packed pair skips its own period header
    # since the periods repeat, and only Monday itself ever shows school/
    # address), so that's how it's budgeted here, not per block.
    _header_rows_height = (school_header_height + (address_header_height if school_address else 0)
                           + days_per_page * day_header_height + period_header_height
                           + gap_row_height * (days_per_page - 1))
    # Floor is derived from cell_font's own (already A3-scaled) size, not a
    # flat historical constant -- a flat "28pt" was tuned for the old A4-only
    # 24pt font and silently went unsafe once cell_font started scaling up
    # for A3 and the packed layout started splitting the page's height
    # budget across 2 stacked days.
    min_data_row_height = cell_font.size * 1.3
    natural_height_floor = _header_rows_height + days_per_page * num_data_rows * min_data_row_height

    # Excel's fitToPage applies ONE uniform scale bound by whichever axis is
    # tighter, so a content block whose row-height total and column-width
    # total don't already match the real page's aspect ratio ends up with a
    # lot of blank space on the LOOSER axis once printed -- this is what
    # showed up as a wide blank strip on both sides of a packed A3 page with
    # many class-arms: the row-height floor alone (doubled for 2 stacked
    # days) pushed natural height well past usable_h, but width stayed at
    # exactly usable_w, so a viewer's auto "fit to page" scaling -- which
    # applies ONE shrink factor bound by whichever axis is tighter -- shrank
    # width along with it, far below the page. Scaling BOTH axes' targets up
    # by whichever floor overflows worse keeps natural width : natural
    # height in the same ratio as the physical page, so a single scale
    # fills the page on both axes at once, same as "no scaling" mode simply
    # needing more than one page when content doesn't fit at all.
    overflow_ratio = max(1.0, natural_width_floor / usable_w, natural_height_floor / usable_h)
    target_w = usable_w * overflow_ratio
    target_h = usable_h * overflow_ratio

    period_col_pts = max((target_w - CLASS_FLOOR_PT - BREAK_FLOOR_PT) / period_cols, PERIOD_COL_MIN_PT)
    class_col_width = _xlsx_col_width_for_pts(CLASS_FLOOR_PT)
    period_col_width = _xlsx_col_width_for_pts(period_col_pts)
    break_col_width = _xlsx_col_width_for_pts(BREAK_FLOOR_PT)

    data_row_height = round(max((target_h - _header_rows_height) / (days_per_page * num_data_rows), min_data_row_height), 2)

    # No intermediate rounding here -- counterintuitively, that's what makes
    # the final stored totals agree. Each sheet's "remaining" padding row
    # (below) is computed as target_block_height MINUS this exact (unrounded)
    # running total, in the SAME left-to-right order the file will later be
    # summed in. Floating-point subtraction's whole job is to find the
    # precise delta between two floats, including sub-2dp noise from how
    # THIS group's particular rows happened to accumulate -- round that delta
    # away and it stops exactly cancelling that noise, so two sheets whose
    # rows are the same multiset in a different order (e.g. the school
    # header first vs the padding row last) land on bit-different totals
    # that both merely *display* as the same 2dp number.
    def _block_rows(d, is_first_in_group):
        """The individual row heights one day's block takes up, as a flat
        list -- one entry per PHYSICAL row that will actually be written,
        not a pre-summed total. _group_height()/used_height below both
        reduce lists like this with one plain sum() each, so they add the
        same values in the same left-to-right order the file is later
        re-summed in. A pre-summed per-block subtotal (added as one float
        to an outer accumulator) is a DIFFERENT floating-point expression
        from summing all those rows flat -- even identical values, same
        order, round differently once grouped into (a+b+c)+d vs
        a+(b+c)+d. Likewise num_data_rows*data_row_height is a different
        operation from adding data_row_height that many times over; this
        lists the latter explicitly."""
        rows = []
        if d == 0:
            rows.append(school_header_height)
            if school_address:
                rows.append(address_header_height)
        rows.append(day_header_height)
        if is_first_in_group:
            rows.append(period_header_height)
        rows.extend([data_row_height] * num_data_rows)
        return rows

    def _group_rows(group):
        rows = []
        for i, day_name in enumerate(group):
            rows.extend(_block_rows(days.index(day_name), i == 0))
            if i < len(group) - 1:
                rows.append(gap_row_height)
        return rows

    def _group_height(group):
        return sum(_group_rows(group))

    def _write_day_block(ws, d, day_name, start_row, show_period_header=True):
        """Writes one day's grid into ws starting at start_row. Returns the
        row number immediately after this block, for stacking another one
        (packed layout) or as the next sheet's start_row (unpacked).

        ``show_period_header`` is False for the second day of a packed A3
        pair: its "Class | P1...P9 | BREAK | ..." row would just repeat the
        first day's (periods are the same every day), so it's skipped and
        that day's data rows start right under its own day-name bar."""
        current_row = start_row

        # School name and address ONLY on the very first block of the workbook.
        if d == 0:
            ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=total_cols)
            cell = ws.cell(row=current_row, column=1, value=school_name.upper())
            cell.font = school_font
            cell.alignment = center_align
            ws.row_dimensions[current_row].height = school_header_height
            current_row += 1

            if school_address:
                ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=total_cols)
                cell = ws.cell(row=current_row, column=1, value=school_address)
                cell.font = address_font
                cell.alignment = center_align
                ws.row_dimensions[current_row].height = address_header_height
                current_row += 1

        # Day header
        ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=total_cols)
        cell = ws.cell(row=current_row, column=1, value=day_name.upper())
        cell.font = day_font
        cell.alignment = center_align
        cell.border = thick_border
        for col in range(1, total_cols + 1):
            ws.cell(row=current_row, column=col).border = thick_border
        ws.row_dimensions[current_row].height = day_header_height
        current_row += 1

        # Period headers with BREAK column -- only for the first day of a
        # packed pair (or any single-day page, where it's always the first).
        # Being inside this `if` already means THIS block is the one
        # showing the header, whichever day it happens to be -- the times
        # are the same every day, so there's no reason to show them only on
        # Monday (d == 0) and fall back to bare "P1"/"BREAK" on every other
        # page's own header row, which is what the previous `d == 0` checks
        # here did: Wed&Thu's and Friday's pages lost their times entirely.
        if show_period_header:
            col = 1
            cell = ws.cell(row=current_row, column=col, value="Class")
            cell.font = header_font
            cell.border = thick_border
            cell.alignment = center_align
            col += 1

            for i, p in enumerate(range(1, break_after + 1)):
                cell = ws.cell(row=current_row, column=col, value=period_times_before_break[i])
                cell.font = header_font
                cell.border = thick_border
                cell.alignment = center_align
                col += 1

            cell = ws.cell(row=current_row, column=col, value=break_time)
            cell.font = break_header_font
            cell.border = thick_border
            cell.alignment = center_align
            col += 1

            for i, p in enumerate(range(break_after + 1, periods_per_day + 1)):
                cell = ws.cell(row=current_row, column=col, value=period_times_after_break[i])
                cell.font = header_font
                cell.border = thick_border
                cell.alignment = center_align
                col += 1

            ws.row_dimensions[current_row].height = period_header_height
            current_row += 1

        # Data rows
        for class_name, arm in class_arms:
            short_code = get_short_code(class_name, arm)
            col = 1

            cell = ws.cell(row=current_row, column=col, value=short_code)
            cell.font = class_font
            cell.border = thick_border
            cell.alignment = center_align
            col += 1

            arm_results = [r for r in results if r.class_name == class_name and r.arm_name == arm and r.day_of_week == d]

            for p in range(1, break_after + 1):
                slot_result = next((r for r in arm_results if r.period_number == p), None)
                value = ""
                if slot_result and slot_result.subject_id:
                    subj = subject_lookup.get(slot_result.subject_id)
                    if subj:
                        value = _short_cell(slot_result, subj, abbrev_map, 5)

                cell = ws.cell(row=current_row, column=col, value=value)
                cell.font = cell_font
                cell.border = thin_border
                cell.alignment = center_align
                col += 1

            cell = ws.cell(row=current_row, column=col, value="")
            cell.border = thin_border
            cell.alignment = center_align
            col += 1

            for p in range(break_after + 1, periods_per_day + 1):
                slot_result = next((r for r in arm_results if r.period_number == p), None)
                value = ""
                if slot_result and slot_result.subject_id:
                    subj = subject_lookup.get(slot_result.subject_id)
                    if subj:
                        value = _short_cell(slot_result, subj, abbrev_map, 5)

                cell = ws.cell(row=current_row, column=col, value=value)
                cell.font = cell_font
                cell.border = thin_border
                cell.alignment = center_align
                col += 1

            ws.row_dimensions[current_row].height = data_row_height
            current_row += 1

        return current_row

    # Group days into pages: 1 day/page normally, 2 (stacked, gap row
    # between) on a "packed" A3 page.
    day_groups = [days[i:i + days_per_page] for i in range(0, len(days), days_per_page)]

    # Excel's fitToPage scales EACH sheet independently to fill exactly one
    # page -- so a sheet with fewer rows (e.g. Friday alone, the leftover
    # from pairing 5 days 2-at-a-time) gets stretched MORE than a denser one
    # (Monday+Tuesday), and its rows/columns end up visibly bigger even
    # though the stored heights/widths are identical. Padding every sheet's
    # content out to the same total height as the densest one neutralizes
    # that: every sheet scales by the same factor, so row and column sizing
    # reads identically everywhere -- sparser pages just carry blank space
    # at the bottom instead of stretching to fill it.
    target_block_height = max(_group_height(g) for g in day_groups)

    for group in day_groups:
        sheet_title = ' & '.join(n[:3] for n in group) if len(group) > 1 else group[0]
        ws = wb.create_sheet(title=sheet_title[:31])

        ws.page_setup.paperSize = ws.PAPERSIZE_A3 if paper == 'a3' else ws.PAPERSIZE_A4
        ws.page_setup.orientation = 'landscape'
        # fitToWidth/fitToHeight (auto-fit), not an explicit scale percentage
        # -- a manually computed scale% was tried and reverted: it depends on
        # our own column-width-in-points math landing on the exact same
        # physical width LibreOffice/Excel/Sheets independently resolve a
        # "character width" column unit to, and in practice it doesn't quite
        # -- enough drift at this page's column count pushed content just
        # past one physical page width at the chosen scale, SPLITTING the
        # sheet across two printed pages instead of merely leaving a margin.
        # Auto-fit never has that failure mode (it always lands on exactly
        # one page), so it stays in place; the overflow_ratio sizing above is
        # what actually fixes the blank-margin symptom, by keeping natural
        # width:height proportioned to the page so auto-fit's one shrink
        # factor empties onto both axes evenly instead of being bound by
        # just one.
        ws.page_setup.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 1
        ws.print_options.horizontalCentered = True
        ws.print_options.verticalCentered = True

        # Safe margins for most printers (0.5 inch)
        ws.page_margins.left = 0.5
        ws.page_margins.right = 0.5
        ws.page_margins.top = 0.4
        ws.page_margins.bottom = 0.4
        ws.page_margins.header = 0
        ws.page_margins.footer = 0

        row = 1
        used_height = sum(_group_rows(group))
        for i, day_name in enumerate(group):
            d = days.index(day_name)
            row = _write_day_block(ws, d, day_name, row, show_period_header=(i == 0))
            if i < len(group) - 1:
                ws.row_dimensions[row].height = gap_row_height
                row += 1

        # Deliberately NOT rounded -- see _block_rows's comment. This raw
        # float subtraction is what makes used_height + remaining reconstruct
        # target_block_height exactly when the file is re-summed -- which
        # now actually holds, since used_height (one flat sum()) and the
        # file's eventual re-summed total use the identical operation.
        remaining = target_block_height - used_height
        if remaining > 0.5:
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=total_cols)
            ws.row_dimensions[row].height = remaining

        # Column widths - precomputed above to exactly fill the usable width.
        # Same formula every sheet (periods_per_day/break_after are fixed
        # for the whole export), so every day/page gets identical widths.
        ws.column_dimensions['A'].width = class_col_width  # Class
        for col in range(2, total_cols + 1):
            if col == break_col:
                ws.column_dimensions[get_column_letter(col)].width = break_col_width
            else:
                ws.column_dimensions[get_column_letter(col)].width = period_col_width

    suffix = f'_{paper}' + ('_packed' if days_per_page > 1 else '')
    return xlsx_response(wb, f'timetables_by_day_{batch_id}{suffix}.xlsx')


@generator_bp.route('/results/<batch_id>/export_by_day_pdf')
@login_required
def export_results_by_day_pdf(batch_id):
    """Export timetable as PDF — one day per page (A4 or A3), or on A3, two
    days stacked per page ("packed") — NO COLORS.

    ?paper=a4|a3 (default a4), ?layout=single|packed (default single; packed
    only takes effect on A3 — A4 has no room to pack two days legibly)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, A3, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, PageBreak, Spacer

    paper = (request.args.get('paper') or 'a4').lower()
    if paper not in ('a4', 'a3'):
        paper = 'a4'
    layout = (request.args.get('layout') or 'single').lower()
    days_per_page = 2 if (paper == 'a3' and layout == 'packed') else 1

    all_results = GenTimetableResult.query.filter_by(batch_id=batch_id, branch_id=gen_bid()).all()
    if not all_results:
        flash('No results.', 'error')
        return redirect(url_for('generator.results_list'))
    results = filter_results_by_arm(all_results)
    if not results:
        flash('No class-arms selected.', 'error')
        return redirect(url_for('generator.view_results', batch_id=batch_id))
    annotate_coschedule_pairs(all_results, results)

    school_level = results[0].school_level or 'sss'
    rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(is_active=True, school_level=school_level, branch_id=gen_bid()).all()}
    periods_per_day = int(rules.get('periods_per_day', 8))
    break_after = _break_after(rules, periods_per_day)

    # Get school info
    school_name = GenSettings.get('school_name', 'School')
    school_address = GenSettings.get('school_address', '')

    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

    # Period times with break tracking — per-level start/period/break settings.
    period_times_before = []  # before the break
    period_times_after = []   # after the break
    break_time = ""

    start_hour, start_min, _plen, _blen = clock_params(rules)
    for p in range(1, periods_per_day + 1):
        start_total = start_hour * 60 + start_min
        end_total = start_total + _plen
        start_h, start_m = start_total // 60, start_total % 60
        end_h, end_m = end_total // 60, end_total % 60

        time_str = f"P{p}\n{format_clock(start_h, start_m)}\n{format_clock(end_h, end_m)}"
        if p <= break_after:
            period_times_before.append(time_str)
        else:
            period_times_after.append(time_str)

        start_hour, start_min = end_h, end_m
        if p == break_after:
            break_start = format_clock(end_h, end_m)
            start_total = start_hour * 60 + start_min + _blen
            start_hour, start_min = start_total // 60, start_total % 60
            break_end = format_clock(start_hour, start_min)
            break_time = f"BREAK\n{break_start}\n-\n{break_end}"
    
    class_arms = sorted(set((r.class_name, r.arm_name) for r in results))
    num_data_rows = len(class_arms)
    
    def get_short_code(class_name, arm):
        class_num = class_name.replace('SSS', '')
        arm_letter = arm[0].upper()
        return f"{class_num}{arm_letter}"
    
    abbrev_map = {
        'Mathematics': 'Maths', 'English Language': 'Eng', 'Physics': 'Phy',
        'Chemistry': 'Chem', 'Biology': 'Bio', 'Economics': 'Econs',
        'Government': 'Govt', 'Literature in English': 'Lit', 'Agricultural Science': 'Agric',
        'Christian Religious Studies': 'CRS', 'Civic Education': 'Civic',
        'Computer Studies': 'Comp', 'Commerce': 'Comm', 'Geography': 'Geo',
        'Further Mathematics': 'F/Mth', 'Livestock Farming': 'Livst',
        'History': 'Hist', 'Phonics': 'Phon',
    }
    
    output = BytesIO()

    # Small margins so the grid fills the page, on whichever sheet size was chosen.
    margin = 7*mm
    # reportlab's default Frame keeps 6pt of padding on every side; if we don't
    # subtract it the table is fractionally taller than the frame and its last
    # row is pushed onto a second page (leaving the first page half-empty).
    frame_pad = 6
    sheet_size = A3 if paper == 'a3' else A4
    page_w, page_h = landscape(sheet_size)
    usable_width = page_w - 2*margin - 2*frame_pad
    # Packed A3 splits the page into `days_per_page` stacked blocks with a
    # gap between them; single-day pages (A4, or A3 unpacked) use the whole
    # page height for one day, same as before.
    block_gap = 6*mm if days_per_page > 1 else 0
    usable_height = ((page_h - 2*margin - 2*frame_pad) - block_gap * (days_per_page - 1)) / days_per_page

    # Every font size, column width and fixed header height below was tuned
    # for a single day filling a full A4 landscape page. Scale them against
    # that baseline on two independent axes — height and width — so a bigger
    # sheet (A3, single day) fills out proportionally in both directions
    # instead of just growing taller while its fixed-width columns stay put
    # (that used to make single-line labels like "Class" spill past their
    # column border once the font outgrew it), and a packed block (A3, two
    # days) shrinks just enough to fit its halved height without shrinking
    # any further than that — it still has the full page width to work with.
    baseline_usable_height = landscape(A4)[1] - 2*margin - 2*frame_pad
    baseline_usable_width = landscape(A4)[0] - 2*margin - 2*frame_pad
    hscale = usable_height / baseline_usable_height
    wscale = usable_width / baseline_usable_width
    # For anything that has to fit inside one specific column (a class code,
    # a period header, the break label) the binding constraint is whichever
    # axis is tighter — packed mode is squeezed by height, not width, so it
    # must not be sized as if the ample width were the only limit.
    fit_scale = min(hscale, wscale)

    def sc(pt):
        """Scale by page height — for full-width single-line rows (school
        name, day header) where only vertical room is a real constraint."""
        return pt * hscale

    def sc_w(pt):
        """Scale by page width — for column widths."""
        return pt * wscale

    def sc_fit(pt):
        """Scale by whichever axis is tighter — for text confined to one
        column, which must fit both its row's height and its column's width."""
        return pt * fit_scale

    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(sheet_size),
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin
    )

    elements = []

    # Total columns: Class + periods-before + BREAK + periods-after
    num_periods_before = break_after
    num_periods_after = periods_per_day - break_after
    total_cols = 1 + num_periods_before + 1 + num_periods_after

    # Column widths - fill entire width. The class-code column is sized to
    # this batch's own longest code (get_short_code() output can be a couple
    # of characters or, for a naming scheme get_short_code() doesn't shorten,
    # several) at the class-code font size below — a fixed guess either
    # wasted space for short codes or overflowed for long ones. Bounded so
    # one long-named class-arm can't crush the period columns for everyone.
    from reportlab.pdfbase.pdfmetrics import stringWidth
    class_code_font = sc_fit(14)
    longest_code = max((get_short_code(cn, arm) for cn, arm in class_arms), default='Class')
    longest_code = max(longest_code, 'Class', key=lambda s: stringWidth(s, 'Helvetica-Bold', class_code_font))
    code_text_width = stringWidth(longest_code, 'Helvetica-Bold', class_code_font)
    first_col_width = min(max(sc_w(12*mm), code_text_width + sc_w(6*mm)), sc_w(28*mm))
    break_col_width = sc_w(10*mm)
    remaining_width = usable_width - first_col_width - break_col_width
    period_col_width = remaining_width / periods_per_day
    
    col_widths = [first_col_width]
    col_widths += [period_col_width] * num_periods_before
    col_widths += [break_col_width]
    col_widths += [period_col_width] * num_periods_after
    
    for d, day_name in enumerate(days):
        table_data = []
        row_heights = []

        # Only the first day in each stacked page-group shows the period
        # header row (P#/times + BREAK) — the next day(s) sharing that page
        # flow straight into their data rows instead of repeating it.
        show_period_header = (d % days_per_page == 0)

        # Calculate row heights to fit EXACTLY on this day's block
        if d == 0:  # Monday - include school name and address
            school_header_height = sc(9*mm)
            address_header_height = sc(5*mm) if school_address else 0
            day_header_height = sc(11*mm)
            period_header_height = sc(16*mm)    # taller: shows the P#/start/end times, bigger
            fixed_height = school_header_height + address_header_height + day_header_height + period_header_height
        else:
            day_header_height = sc(11*mm)
            period_header_height = sc(10*mm)
            fixed_height = day_header_height + period_header_height

        # Data rows split ALL remaining height so the grid fills the page. (-1pt
        # guards against float rounding tipping the table onto a second page.)
        available_for_data = usable_height - fixed_height - 1
        data_row_height = available_for_data / num_data_rows
        
        # Build table data
        if d == 0:
            # School name row
            school_row = [school_name.upper()] + [''] * (total_cols - 1)
            table_data.append(school_row)
            row_heights.append(school_header_height)
            
            if school_address:
                address_row = [school_address] + [''] * (total_cols - 1)
                table_data.append(address_row)
                row_heights.append(address_header_height)
        
        # Day header row
        day_row = [day_name.upper()] + [''] * (total_cols - 1)
        table_data.append(day_row)
        row_heights.append(day_header_height)
        
        # Period header row — skipped for a day that isn't first on its page
        # (the freed height stays reserved in fixed_height above, so
        # data_row_height is unaffected and matches the day before it; it
        # just shows up as blank space at the end of this shorter block).
        if show_period_header:
            # Whichever day this is, being inside show_period_header means
            # THIS page's header row is the one being shown -- times are
            # the same every day, so always show them (not just on
            # Monday/d==0, which left every other page's own header with
            # bare "P1"/"BREAK" and no times at all).
            header_row = ['Class'] + period_times_before + [break_time] + period_times_after
            table_data.append(header_row)
            row_heights.append(period_header_height)

        # Data rows
        for class_name, arm in class_arms:
            short_code = get_short_code(class_name, arm)
            row = [short_code]
            
            arm_results = [r for r in results if r.class_name == class_name and r.arm_name == arm and r.day_of_week == d]
            
            # Before-break periods
            for p in range(1, break_after + 1):
                slot_result = next((r for r in arm_results if r.period_number == p), None)
                if slot_result and slot_result.subject:
                    row.append(_short_cell(slot_result, slot_result.subject, abbrev_map, 5))
                else:
                    row.append('')

            # BREAK column - empty
            row.append('')

            # After-break periods
            for p in range(break_after + 1, periods_per_day + 1):
                slot_result = next((r for r in arm_results if r.period_number == p), None)
                if slot_result and slot_result.subject:
                    row.append(_short_cell(slot_result, slot_result.subject, abbrev_map, 5))
                else:
                    row.append('')
            
            table_data.append(row)
            row_heights.append(data_row_height)
        
        # Create table with exact dimensions
        table = Table(table_data, colWidths=col_widths, rowHeights=row_heights)
        
        # Break column index = Class col (0) + the before-break periods
        break_col = 1 + break_after
        
        # Calculate row indices
        if d == 0:
            day_row_idx = 2 if school_address else 1
        else:
            day_row_idx = 0
        if show_period_header:
            header_row_idx = day_row_idx + 1
            data_start_row = header_row_idx + 1
        else:
            header_row_idx = None
            data_start_row = day_row_idx + 1

        # NO COLORS - just black text on white, with borders. Padding is kept
        # tight and every font size gets an explicit LEADING close to it (a
        # single line needs about 1.05x its size) rather than relying on
        # reportlab's default ~1.2x leading + 3pt/side padding — that default
        # headroom is a fixed point amount that doesn't scale with the page,
        # so at A3 size (fonts ~1.45x bigger) it was too little, and large
        # single-line headers like the day name were visibly bleeding into
        # the row below.
        style_commands = [
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),

            # Day header row
            ('SPAN', (0, day_row_idx), (-1, day_row_idx)),
            ('TEXTCOLOR', (0, day_row_idx), (-1, day_row_idx), colors.black),
            ('FONTNAME', (0, day_row_idx), (-1, day_row_idx), 'Helvetica-Bold'),
            ('FONTSIZE', (0, day_row_idx), (-1, day_row_idx), sc(22)),
            ('LEADING', (0, day_row_idx), (-1, day_row_idx), sc(23)),
            ('ALIGN', (0, day_row_idx), (-1, day_row_idx), 'CENTER'),
            ('VALIGN', (0, day_row_idx), (-1, day_row_idx), 'MIDDLE'),

            # Class codes column — confined to the first column, so fit_scale.
            ('FONTNAME', (0, data_start_row), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, data_start_row), (0, -1), sc_fit(14)),
            ('LEADING', (0, data_start_row), (0, -1), sc_fit(15)),

            # Subject cells - LARGE, but still confined to a period column.
            ('FONTNAME', (1, data_start_row), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (1, data_start_row), (-1, -1), sc_fit(18)),
            ('LEADING', (1, data_start_row), (-1, -1), sc_fit(19)),

            # All cells alignment
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),

            # Borders only - no background colors
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BOX', (0, 0), (-1, -1), 1.5, colors.black),
        ]

        # Period header row (P#/times) — bold and readable, not tiny. Only
        # present when this day shows it (see show_period_header above).
        # Confined to a period column, so bound by whichever of
        # height/width is tighter (fit_scale), not height alone.
        if show_period_header:
            style_commands.extend([
                ('FONTNAME', (0, header_row_idx), (-1, header_row_idx), 'Helvetica-Bold'),
                ('FONTSIZE', (0, header_row_idx), (-1, header_row_idx), sc_fit(11 if d == 0 else 13)),
                ('LEADING', (0, header_row_idx), (-1, header_row_idx), sc_fit(12 if d == 0 else 14)),
                ('ALIGN', (0, header_row_idx), (-1, header_row_idx), 'CENTER'),
                ('VALIGN', (0, header_row_idx), (-1, header_row_idx), 'MIDDLE'),

                # Break column header (narrow column, keep its multi-line label small)
                ('FONTSIZE', (break_col, header_row_idx), (break_col, header_row_idx), sc_fit(7)),
                ('LEADING', (break_col, header_row_idx), (break_col, header_row_idx), sc_fit(7.5)),
            ])

        # Add school name styling for Monday
        if d == 0:
            style_commands.extend([
                ('SPAN', (0, 0), (-1, 0)),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), sc(16)),
                ('LEADING', (0, 0), (-1, 0), sc(17)),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
            ])
            if school_address:
                style_commands.extend([
                    ('SPAN', (0, 1), (-1, 1)),
                    ('FONTNAME', (0, 1), (-1, 1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, 1), sc(8)),
                    ('LEADING', (0, 1), (-1, 1), sc(9)),
                    ('TEXTCOLOR', (0, 1), (-1, 1), colors.black),
                    ('ALIGN', (0, 1), (-1, 1), 'CENTER'),
                    ('VALIGN', (0, 1), (-1, 1), 'MIDDLE'),
                ])

        table.setStyle(TableStyle(style_commands))
        elements.append(table)

        is_last_day = (d == len(days) - 1)
        if not is_last_day:
            # Full page used up (single-day layout, or the last slot in a
            # packed page) -> new page. Otherwise stack the next day's block
            # right below this one on the same page.
            if (d + 1) % days_per_page == 0:
                elements.append(PageBreak())
            else:
                elements.append(Spacer(1, block_gap))

    doc.build(elements)
    suffix = f'_{paper}' + ('_packed' if days_per_page > 1 else '')
    return pdf_response(output, f'timetables_by_day_{batch_id}{suffix}.pdf', inline=False)


@generator_bp.route('/results/<batch_id>/export_image')
@login_required
def export_image(batch_id):
    """Export timetable as PNG image (Ultra HD - 8x scale)"""
    from routes.generator_image import generate_timetable_image, image_to_response
    
    quality = request.args.get('quality', 'ultra')  # 'hd' or 'ultra'
    img = generate_timetable_image(batch_id, quality=quality)
    if not img:
        flash('No results found.', 'error')
        return redirect(url_for('generator.results_list'))
    
    quality_suffix = '_hd' if quality == 'hd' else '_ultrahd'
    return image_to_response(img, f'timetable_{batch_id}{quality_suffix}.png')


@generator_bp.route('/results/<batch_id>/export_image_hd')
@login_required
def export_image_hd(batch_id):
    """Export timetable as PNG image (HD - 4x scale)"""
    from routes.generator_image import generate_timetable_image, image_to_response
    
    img = generate_timetable_image(batch_id, quality='hd')
    if not img:
        flash('No results found.', 'error')
        return redirect(url_for('generator.results_list'))
    
    return image_to_response(img, f'timetable_{batch_id}_hd.png')


@generator_bp.route('/results/<batch_id>/export_image_ultra')
@login_required
def export_image_ultra(batch_id):
    """Export timetable as PNG image (Ultra HD - 8x scale)"""
    from routes.generator_image import generate_timetable_image, image_to_response
    
    img = generate_timetable_image(batch_id, quality='ultra')
    if not img:
        flash('No results found.', 'error')
        return redirect(url_for('generator.results_list'))
    
    return image_to_response(img, f'timetable_{batch_id}_ultrahd.png')


@generator_bp.route('/results/<batch_id>/teacher/<int:teacher_id>/image')
@login_required
def export_teacher_image(batch_id, teacher_id):
    """Export individual teacher timetable as PNG image"""
    from routes.generator_image import generate_teacher_timetable_image, image_to_response
    
    img = generate_teacher_timetable_image(batch_id, teacher_id)
    if not img:
        flash('No results found for this teacher.', 'error')
        return redirect(url_for('generator.teacher_timetable', batch_id=batch_id))
    
    teacher = GenTeacher.query.get(teacher_id)
    filename = f'timetable_{teacher.name.replace(" ", "_")}_{batch_id}.png'
    
    return image_to_response(img, filename)


@generator_bp.route('/results/<batch_id>/teacher/<int:teacher_id>/print')
@login_required
def print_teacher_timetable(batch_id, teacher_id):
    """Printable view for individual teacher timetable"""
    teacher = gen_owned_or_404(GenTeacher, teacher_id)
    results = GenTimetableResult.query.filter_by(batch_id=batch_id, teacher_id=teacher_id, branch_id=gen_bid()).all()
    
    if not results:
        flash('No timetable found for this teacher.', 'error')
        return redirect(url_for('generator.teacher_timetable', batch_id=batch_id))
    
    rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(is_active=True, branch_id=gen_bid()).all()}
    periods_per_day = int(rules.get('periods_per_day', 8))
    
    # Build timetable grid
    timetable = {d: {p: None for p in range(1, periods_per_day + 1)} for d in range(5)}
    for r in results:
        timetable[r.day_of_week][r.period_number] = {
            'subject': r.subject,
            'class_name': r.class_name,
            'arm_name': r.arm_name
        }
    
    return render_template('generator/print_teacher_timetable.html',
        teacher=teacher,
        timetable=timetable,
        batch_id=batch_id,
        periods=range(1, periods_per_day + 1),
        days=DAYS_OF_WEEK
    )


@generator_bp.route('/teacher-timetable/print-all-pdf')
@login_required
def print_all_teacher_timetables_pdf():
    """Every teacher's individual weekly timetable in one PDF, one teacher
    per page (A4 landscape) — the bulk counterpart to print_teacher_timetable(),
    which downloads just one. Defaults to the same batch the teacher-timetable
    page itself would default to: the level's active/published batch, falling
    back to the most recently generated one, when ?batch_id isn't given.

    Each page reuses generate_teacher_timetable_image() — the same PNG design
    already used for the single-teacher image download (school header + logo,
    teacher name, "Weekly Timetable | Max N periods/day" subtitle, break shown
    as its own column with its time range, PosyHub footer) — rather than a
    separate hand-built PDF layout, so the two exports always look identical
    and periods_per_day/break placement always come from the same per-level
    GenTimetableRule lookup that function already does correctly."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Image as RLImage, PageBreak, Spacer
    from models import ActiveTimetableBatch
    from utils.branch_scope import viewing_branch_id
    from routes.generator_image import generate_teacher_timetable_image

    batch_id = request.args.get('batch_id')
    level = get_current_level()
    if not batch_id:
        batch_id = ActiveTimetableBatch.active_batch_id(viewing_branch_id(), level)
        if not batch_id:
            latest = GenTimetableResult.query.filter_by(branch_id=gen_bid()).order_by(GenTimetableResult.generated_at.desc()).first()
            if latest:
                batch_id = latest.batch_id

    if not batch_id:
        flash('No timetable results found.', 'error')
        return redirect(url_for('generator.teacher_timetable'))

    all_results = GenTimetableResult.query.filter_by(batch_id=batch_id, branch_id=gen_bid()).all()
    if not all_results:
        flash('No timetable found for this batch.', 'error')
        return redirect(url_for('generator.teacher_timetable', batch_id=batch_id))

    teacher_ids = sorted({r.teacher_id for r in all_results if r.teacher_id})
    if not teacher_ids:
        flash('No teacher assignments found in this batch.', 'error')
        return redirect(url_for('generator.teacher_timetable', batch_id=batch_id))

    teachers = {t.id: t for t in GenTeacher.query.filter(GenTeacher.id.in_(teacher_ids)).all()}
    ordered_ids = sorted((tid for tid in teacher_ids if tid in teachers),
                        key=lambda tid: teachers[tid].name)

    output = BytesIO()
    margin = 8 * mm
    doc = SimpleDocTemplate(output, pagesize=landscape(A4),
                            leftMargin=margin, rightMargin=margin,
                            topMargin=margin, bottomMargin=margin)
    page_w, page_h = landscape(A4)
    usable_width = page_w - 2 * margin
    usable_height = page_h - 2 * margin

    elements = []
    for idx, tid in enumerate(ordered_ids):
        img = generate_teacher_timetable_image(batch_id, tid)
        if not img:
            continue
        png_buf = BytesIO()
        img.save(png_buf, format='PNG')
        png_buf.seek(0)

        # Scale the image down to fit the page, preserving its aspect ratio
        # (never upscale a small one past its own size), and center it
        # vertically — the design's own aspect ratio is wider than A4
        # landscape, so fitting to width alone would leave it pinned to the
        # top with a dead gap below.
        iw, ih = img.size
        fit_scale = min(usable_width / iw, usable_height / ih, 1.0)
        draw_h = ih * fit_scale
        top_gap = max(0, (usable_height - draw_h) / 2)
        if top_gap:
            elements.append(Spacer(1, top_gap))
        rl_img = RLImage(png_buf, width=iw * fit_scale, height=draw_h)
        rl_img.hAlign = 'CENTER'
        elements.append(rl_img)
        if idx < len(ordered_ids) - 1:
            elements.append(PageBreak())

    if not elements:
        flash('No teacher timetables could be rendered for this batch.', 'error')
        return redirect(url_for('generator.teacher_timetable', batch_id=batch_id))

    doc.build(elements)
    return pdf_response(output, f'all_teacher_timetables_{batch_id}.pdf')


def _simple_table_pdf(title, headers, rows, filename, col_widths=None, highlight_col=None):
    """A plain grid-table PDF (headers + string rows) on A4 landscape,
    filling the available width — for reports that are one flat table
    rather than a day/period timetable grid.

    Row height/font auto-fits so a realistic table (school with dozens of
    teachers/classes) lands on ONE page instead of spilling its last row or
    two onto an otherwise-empty second sheet: at the default font/padding,
    if all rows fit within the page then explicit row heights are set to
    exactly fill it (like print_single_timetable_pdf does for the weekly
    grid); if not, font/padding step down (to a legibility floor) until it
    does fit. A genuinely huge table (past what even the floor can fit)
    paginates naturally rather than being crushed illegibly small."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    output = BytesIO()
    margin = 12 * mm
    # SimpleDocTemplate wraps its content in a Frame with a default 6pt
    # padding on every side (on top of the doc's own margins) — budget for
    # that too, or a table that looks like it should just fit spills a
    # sliver onto an unwanted second page (see print_single_timetable_pdf).
    frame_pad = 6
    doc = SimpleDocTemplate(output, pagesize=landscape(A4),
                            leftMargin=margin, rightMargin=margin,
                            topMargin=margin, bottomMargin=margin)
    page_w, page_h = landscape(A4)
    usable_width = page_w - 2 * margin - 2 * frame_pad

    n_cols = len(headers)
    weights = col_widths or [1] * n_cols
    weight_sum = sum(weights)
    col_w = [usable_width * w / weight_sum for w in weights]

    title_style = ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=18,
                                 alignment=TA_CENTER, spaceAfter=12)
    title_para = Paragraph(title, title_style)
    _, title_height = title_para.wrap(usable_width, page_h)

    data = [headers] + rows
    n_rows = len(data)
    available_height = page_h - 2 * margin - 2 * frame_pad - title_height

    header_font = 11
    row_heights = None
    for data_font, pad in ((10, 6), (9, 5), (8, 4), (7, 3)):
        header_h = header_font + 2 * pad + 3
        data_h = data_font + 2 * pad + 3
        if header_h + data_h * (n_rows - 1) <= available_height:
            row_heights = [header_h] + [data_h] * (n_rows - 1)
            break
    else:
        data_font, pad = 7, 3   # smallest tried; still too many rows -- let it paginate

    table = Table(data, colWidths=col_w, rowHeights=row_heights, repeatRows=1)
    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), header_font),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), data_font),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#888888')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F7FA')]),
        ('TOPPADDING', (0, 0), (-1, -1), pad),
        ('BOTTOMPADDING', (0, 0), (-1, -1), pad),
    ]
    if highlight_col is not None:
        style_cmds.append(('BACKGROUND', (highlight_col, 1), (highlight_col, -1), colors.HexColor('#FFF3CD')))
    table.setStyle(TableStyle(style_cmds))

    doc.build([title_para, table])
    return pdf_response(output, filename)


@generator_bp.route('/reports/unassigned/<batch_id>/image')
@login_required
def unassigned_report_image(batch_id):
    from routes.generator.generation import _unassigned_rows
    from routes.generator_image import generate_simple_table_image, image_to_response

    rows, _ = _unassigned_rows(batch_id)
    headers = ['Class', 'Arm'] + [d[:3] for d in DAYS_OF_WEEK] + ['Total/Week']
    table_rows = [[r['class'], r['arm']] + [str(c) for c in r['per_day']] + [str(r['total'])] for r in rows]
    img = generate_simple_table_image('Empty / Unassigned Slots', headers, table_rows,
                                      col_widths=[1.3, 1, 0.7, 0.7, 0.7, 0.7, 0.7, 1],
                                      quality='ultra', highlight_col=len(headers) - 1)
    return image_to_response(img, f'empty_slots_{batch_id}.png')


@generator_bp.route('/reports/unassigned/<batch_id>/pdf')
@login_required
def unassigned_report_pdf(batch_id):
    from routes.generator.generation import _unassigned_rows

    rows, _ = _unassigned_rows(batch_id)
    headers = ['Class', 'Arm'] + [d[:3] for d in DAYS_OF_WEEK] + ['Total/Week']
    table_rows = [[r['class'], r['arm']] + [str(c) for c in r['per_day']] + [str(r['total'])] for r in rows]
    return _simple_table_pdf('Empty / Unassigned Slots', headers, table_rows,
                             f'empty_slots_{batch_id}.pdf',
                             col_widths=[1.3, 1, 0.7, 0.7, 0.7, 0.7, 0.7, 1],
                             highlight_col=len(headers) - 1)


@generator_bp.route('/reports/teacher-workload/<batch_id>/image')
@login_required
def teacher_workload_report_image(batch_id):
    from routes.generator.generation import _teacher_workload
    from routes.generator_image import generate_simple_table_image, image_to_response

    workload = _teacher_workload(batch_id)
    headers = ['Teacher'] + [d[:3] for d in DAYS_OF_WEEK] + ['Total', 'Max', 'Status']
    table_rows = []
    for data in workload.values():
        status = 'OK' if data['total'] <= data['teacher'].max_periods_per_week else 'Overload'
        table_rows.append([data['teacher'].name] + [str(data['per_day'][d]) for d in range(5)] +
                          [str(data['total']), str(data['teacher'].max_periods_per_week), status])
    img = generate_simple_table_image('Teacher Workload Report', headers, table_rows,
                                      col_widths=[1.8, 0.6, 0.6, 0.6, 0.6, 0.6, 0.7, 0.6, 0.9],
                                      quality='ultra', highlight_col=6)
    return image_to_response(img, f'teacher_workload_{batch_id}.png')


@generator_bp.route('/reports/teacher-workload/<batch_id>/pdf')
@login_required
def teacher_workload_report_pdf(batch_id):
    from routes.generator.generation import _teacher_workload

    workload = _teacher_workload(batch_id)
    headers = ['Teacher'] + [d[:3] for d in DAYS_OF_WEEK] + ['Total', 'Max', 'Status']
    table_rows = []
    for data in workload.values():
        status = 'OK' if data['total'] <= data['teacher'].max_periods_per_week else 'Overload'
        table_rows.append([data['teacher'].name] + [str(data['per_day'][d]) for d in range(5)] +
                          [str(data['total']), str(data['teacher'].max_periods_per_week), status])
    return _simple_table_pdf('Teacher Workload Report', headers, table_rows,
                             f'teacher_workload_{batch_id}.pdf',
                             col_widths=[1.8, 0.6, 0.6, 0.6, 0.6, 0.6, 0.7, 0.6, 0.9],
                             highlight_col=6)


def _period_count_table(batch_id):
    """(headers, rows, col_widths) for the period-count report's image/PDF
    exports: just the actual assigned periods for each class/subject, "-"
    when unassigned."""
    from routes.generator.generation import _period_count_data
    from routes.generator_image import _abbrev

    counts, _configs, subjects = _period_count_data(batch_id)
    headers = ['Class'] + [_abbrev(s, maxlen=6) for s in subjects]
    table_rows = []
    for class_arm, subj_counts in counts.items():
        row = [class_arm]
        for s in subjects:
            actual = subj_counts.get(s.id, 0)
            row.append(str(actual) if actual else '-')
        table_rows.append(row)
    col_widths = [1.6] + [0.7] * len(subjects)
    return headers, table_rows, col_widths


@generator_bp.route('/reports/period-count/<batch_id>/image')
@login_required
def period_count_report_image(batch_id):
    from routes.generator_image import generate_simple_table_image, image_to_response

    headers, table_rows, col_widths = _period_count_table(batch_id)
    img = generate_simple_table_image('Period Count Report', headers, table_rows,
                                      col_widths=col_widths, quality='ultra')
    return image_to_response(img, f'period_count_{batch_id}.png')


@generator_bp.route('/reports/period-count/<batch_id>/pdf')
@login_required
def period_count_report_pdf(batch_id):
    headers, table_rows, col_widths = _period_count_table(batch_id)
    return _simple_table_pdf('Period Count Report', headers, table_rows,
                             f'period_count_{batch_id}.pdf', col_widths=col_widths)


@generator_bp.route('/assignments/report/image')
@login_required
def teacher_assignment_summary_image():
    from routes.generator.generation import _teacher_assignment_summary
    from routes.generator_image import generate_teacher_assignment_summary_image, image_to_response

    summary = _teacher_assignment_summary()
    img = generate_teacher_assignment_summary_image(summary)
    return image_to_response(img, 'teacher_assignment_summary.png')


@generator_bp.route('/assignments/report/pdf')
@login_required
def teacher_assignment_summary_pdf():
    from routes.generator.generation import _teacher_assignment_summary
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, ListFlowable, ListItem, Table, TableStyle, Spacer
    from xml.sax.saxutils import escape

    summary = _teacher_assignment_summary()
    output = BytesIO()
    margin = 15 * mm
    page_size = A4
    doc = SimpleDocTemplate(output, pagesize=page_size, leftMargin=margin, rightMargin=margin,
                            topMargin=margin, bottomMargin=margin)

    title_style = ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=18,
                                 spaceAfter=14)
    teacher_style = ParagraphStyle('teacher', fontName='Helvetica-Bold', fontSize=13,
                                   spaceBefore=0, spaceAfter=4)
    line_style = ParagraphStyle('line', fontName='Helvetica', fontSize=10.5, leading=14,
                                alignment=TA_LEFT)
    total_style = ParagraphStyle('total', fontName='Helvetica-Bold', fontSize=10.5,
                                 leading=14, spaceBefore=2, textColor=colors.HexColor('#1e6b3e'))

    # 2 columns (portrait page) so a page isn't mostly blank on the right of
    # a narrow name-and-bullets block — each teacher only needs a fraction of
    # a full page's width. Paired row-by-row (not a balanced-height split) so
    # the reading order stays a simple left-then-right, top-to-bottom grid.
    gutter = 8 * mm
    content_width = page_size[0] - 2 * margin
    col_width = (content_width - gutter) / 2

    def _teacher_cell(row):
        if row is None:
            return []
        flow = [Paragraph(escape(row['teacher'].name), teacher_style)]
        if row['lines']:
            flow.append(ListFlowable(
                [ListItem(Paragraph(escape(line['text']), line_style), leftIndent=6) for line in row['lines']],
                bulletType='bullet', start='-', leftIndent=14))
        plural = 's' if row['total'] != 1 else ''
        flow.append(Paragraph(f"Total — {row['total']} period{plural}/week", total_style))
        return flow

    elements = [Paragraph('Teacher Assignment Summary', title_style)]
    if not summary:
        elements.append(Paragraph('No assignments yet.', line_style))
    for i in range(0, len(summary), 2):
        left = summary[i]
        right = summary[i + 1] if i + 1 < len(summary) else None
        row_table = Table([[_teacher_cell(left), _teacher_cell(right)]], colWidths=[col_width, col_width])
        row_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (0, -1), gutter),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
        ]))
        elements.append(row_table)

    doc.build(elements)
    return pdf_response(output, 'teacher_assignment_summary.pdf', inline=False)
