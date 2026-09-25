"""generator_bp — exports routes (split from the former routes/generator.py)."""
from routes.generator import *  # noqa: F401,F403
from utils.generator_times import clock_params, break_after as _break_after


def _short(subj, fallback_map, maxlen):
    """The short label to print for a generator subject: the user's own short
    name from /generator/subjects when set, else the built-in abbreviation, else
    a truncation of the full name."""
    if subj is None:
        return ''
    sn = (getattr(subj, 'short_name', '') or '').strip()
    if sn:
        return sn
    name = getattr(subj, 'name', '') or ''
    return fallback_map.get(name, name[:maxlen])


def _short_cell(entry, subj, fallback_map, maxlen):
    """The cell text for one slot: `_short(subj, ...)`, plus "/COUNTERPART"
    when annotate_coschedule_pairs() found a co-scheduled subject on an arm
    this document excluded (e.g. "ACC/CRS" for a combined class printed as
    just one arm)."""
    value = _short(subj, fallback_map, maxlen)
    pair = getattr(entry, 'coschedule_pair', None)
    if pair:
        value += '/' + _short(pair, fallback_map, maxlen)
    return value


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
        if entry.coschedule_pair:
            label += '/' + escape(_short(entry.coschedule_pair, abbrev_map, 8))
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
        period_times.append(f"P{p}\n{start_h}:{start_m:02d}-{end_h}:{end_m:02d}")
        start_hour, start_min = end_h, end_m
        if p == break_after:
            break_start = f"{end_h}:{end_m:02d}"
            start_total = start_hour * 60 + start_min + _blen
            start_hour, start_min = start_total // 60, start_total % 60
            break_end = f"{start_hour}:{start_min:02d}"
            break_time = f"BREAK\n{break_start}\n-\n{break_end}"
    
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
    
    # NO COLORS - Pure black text on white, maximum contrast for B&W printing
    school_font = Font(bold=True, size=32, color='000000')
    address_font = Font(bold=False, size=14, color='000000')
    class_title_font = Font(bold=True, size=28, color='000000')
    day_font = Font(bold=True, size=24, color='000000')
    header_font = Font(bold=True, size=11, color='000000')
    cell_font = Font(bold=True, size=32, color='000000')
    break_header_font = Font(bold=True, size=8, color='000000')
    
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
    
    # A4 Landscape: 297mm x 210mm
    # Safe margins for most printers: 0.5" (12.7mm) each side
    # Usable: ~272mm x 185mm
    total_page_height = 500  # points for A4 landscape height (conservative)
    school_header_height = 38
    address_header_height = 20 if school_address else 0
    class_title_height = 32
    period_header_height = 45
    # 5 day rows get ALL remaining space
    fixed_height = school_header_height + address_header_height + class_title_height + period_header_height
    day_row_height = (total_page_height - fixed_height) / 5
    
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
            
            # Day name
            cell = ws.cell(row=current_row, column=col, value=day_name)
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
        
        # Column widths - fit within safe printable area
        # A4 landscape with 0.5" margins: ~250mm usable width
        ws.column_dimensions['A'].width = 12  # Day column
        period_col_width = 28  # Period columns
        break_col_width = 8   # Break column
        
        for col in range(2, total_cols + 1):
            if col == 7:  # Break column
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
        start_str = f"{start_h}:{start_m:02d}"
        end_str = f"{end_h}:{end_m:02d}"

        if p <= break_after:
            period_times_before_break.append(f"P{p}\n{start_str}-{end_str}")
        else:
            period_times_after_break.append(f"P{p}\n{start_str}-{end_str}")

        start_hour, start_min = end_h, end_m

        # Capture break time after the configured period
        if p == break_after:
            break_start = f"{end_h}:{end_m:02d}"
            start_total = start_hour * 60 + start_min + _blen
            start_hour, start_min = start_total // 60, start_total % 60
            break_end = f"{start_hour}:{start_min:02d}"
            break_time = f"BREAK\n{break_start}\n-\n{break_end}"
    
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
    
    # NO COLORS - Pure black text on white for B&W printing
    school_font = Font(bold=True, size=24, color='000000')
    address_font = Font(bold=False, size=12, color='000000')
    day_font = Font(bold=True, size=32, color='000000')
    header_font = Font(bold=True, size=14, color='000000')
    class_font = Font(bold=True, size=20, color='000000')
    cell_font = Font(bold=True, size=24, color='000000')
    break_header_font = Font(bold=True, size=9, color='000000')
    
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

    # Calculate heights (conservative for safe printing). Excel's own
    # fitToPage/fitToWidth/fitToHeight scale whatever we write down to fill
    # exactly one printed page of the chosen paper size — so these are just
    # relative proportions, not a physical constraint we have to solve.
    num_data_rows = len(class_arms)
    school_header_height = 35
    address_header_height = 20
    day_header_height = 45
    period_header_height = 45
    total_page_height = 500  # Conservative for safe printing

    def _write_day_block(ws, d, day_name, start_row):
        """Writes one day's grid into ws starting at start_row. Returns the
        row number immediately after this block, for stacking another one
        (packed layout) or as the next sheet's start_row (unpacked)."""
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

            header_rows_height = school_header_height + (address_header_height if school_address else 0) + day_header_height + period_header_height
            remaining_height = total_page_height - header_rows_height
            data_row_height = remaining_height / num_data_rows
            data_row_height = max(data_row_height, 28)
        else:
            remaining_height = total_page_height - day_header_height - period_header_height
            data_row_height = remaining_height / num_data_rows
            data_row_height = max(data_row_height, 30)

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

        # Period headers with BREAK column
        col = 1
        cell = ws.cell(row=current_row, column=col, value="Class")
        cell.font = header_font
        cell.border = thick_border
        cell.alignment = center_align
        col += 1

        for i, p in enumerate(range(1, break_after + 1)):
            header_value = period_times_before_break[i] if d == 0 else f"P{p}"
            cell = ws.cell(row=current_row, column=col, value=header_value)
            cell.font = header_font
            cell.border = thick_border
            cell.alignment = center_align
            col += 1

        cell = ws.cell(row=current_row, column=col, value=break_time if d == 0 else "BREAK")
        cell.font = break_header_font
        cell.border = thick_border
        cell.alignment = center_align
        col += 1

        for i, p in enumerate(range(break_after + 1, periods_per_day + 1)):
            header_value = period_times_after_break[i] if d == 0 else f"P{p}"
            cell = ws.cell(row=current_row, column=col, value=header_value)
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
    for group in day_groups:
        sheet_title = ' & '.join(n[:3] for n in group) if len(group) > 1 else group[0]
        ws = wb.create_sheet(title=sheet_title[:31])

        ws.page_setup.paperSize = ws.PAPERSIZE_A3 if paper == 'a3' else ws.PAPERSIZE_A4
        ws.page_setup.orientation = 'landscape'
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
        for day_name in group:
            d = days.index(day_name)
            row = _write_day_block(ws, d, day_name, row)
            row += 1  # gap row between stacked day-blocks

        # Column widths - fit within safe printable area
        ws.column_dimensions['A'].width = 8  # Class
        col_width = 26 if periods_per_day <= 8 else 22
        for col in range(2, total_cols + 1):
            if col == 7:  # Break column
                ws.column_dimensions[get_column_letter(col)].width = 8
            else:
                ws.column_dimensions[get_column_letter(col)].width = col_width

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

        time_str = f"P{p}\n{start_h}:{start_m:02d}\n{end_h}:{end_m:02d}"
        if p <= break_after:
            period_times_before.append(time_str)
        else:
            period_times_after.append(time_str)

        start_hour, start_min = end_h, end_m
        if p == break_after:
            break_start = f"{end_h}:{end_m:02d}"
            start_total = start_hour * 60 + start_min + _blen
            start_hour, start_min = start_total // 60, start_total % 60
            break_end = f"{start_hour}:{start_min:02d}"
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
        
        # Period header row
        if d == 0:  # Monday - show times
            header_row = ['Class'] + period_times_before + [break_time] + period_times_after
        else:
            header_row = ['Class'] + [f'P{p}' for p in range(1, break_after + 1)] + ['BREAK'] + [f'P{p}' for p in range(break_after + 1, periods_per_day + 1)]
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
            if school_address:
                day_row_idx = 2
                header_row_idx = 3
                data_start_row = 4
            else:
                day_row_idx = 1
                header_row_idx = 2
                data_start_row = 3
        else:
            day_row_idx = 0
            header_row_idx = 1
            data_start_row = 2
        
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

            # Period header row (P#/times) — bold and readable, not tiny.
            # Confined to a period column, so bound by whichever of
            # height/width is tighter (fit_scale), not height alone.
            ('FONTNAME', (0, header_row_idx), (-1, header_row_idx), 'Helvetica-Bold'),
            ('FONTSIZE', (0, header_row_idx), (-1, header_row_idx), sc_fit(11 if d == 0 else 13)),
            ('LEADING', (0, header_row_idx), (-1, header_row_idx), sc_fit(12 if d == 0 else 14)),
            ('ALIGN', (0, header_row_idx), (-1, header_row_idx), 'CENTER'),
            ('VALIGN', (0, header_row_idx), (-1, header_row_idx), 'MIDDLE'),

            # Break column header (narrow column, keep its multi-line label small)
            ('FONTSIZE', (break_col, header_row_idx), (break_col, header_row_idx), sc_fit(7)),
            ('LEADING', (break_col, header_row_idx), (break_col, header_row_idx), sc_fit(7.5)),

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
    """A plain grid-table PDF (headers + string rows) on one A4 landscape
    page, filling the available width/height — for reports that are one
    flat table rather than a day/period timetable grid."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    output = BytesIO()
    margin = 12 * mm
    doc = SimpleDocTemplate(output, pagesize=landscape(A4),
                            leftMargin=margin, rightMargin=margin,
                            topMargin=margin, bottomMargin=margin)
    page_w, page_h = landscape(A4)
    usable_width = page_w - 2 * margin

    n_cols = len(headers)
    weights = col_widths or [1] * n_cols
    weight_sum = sum(weights)
    col_w = [usable_width * w / weight_sum for w in weights]

    title_style = ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=18,
                                 alignment=TA_CENTER, spaceAfter=12)
    data = [headers] + rows
    table = Table(data, colWidths=col_w, repeatRows=1)
    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#888888')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F7FA')]),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]
    if highlight_col is not None:
        style_cmds.append(('BACKGROUND', (highlight_col, 1), (highlight_col, -1), colors.HexColor('#FFF3CD')))
    table.setStyle(TableStyle(style_cmds))

    doc.build([Paragraph(title, title_style), table])
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
    from reportlab.platypus import SimpleDocTemplate, Paragraph, ListFlowable, ListItem

    summary = _teacher_assignment_summary()
    output = BytesIO()
    margin = 15 * mm
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=margin, rightMargin=margin,
                            topMargin=margin, bottomMargin=margin)

    title_style = ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=18,
                                 spaceAfter=14)
    teacher_style = ParagraphStyle('teacher', fontName='Helvetica-Bold', fontSize=13,
                                   spaceBefore=10, spaceAfter=4)
    line_style = ParagraphStyle('line', fontName='Helvetica', fontSize=10.5, leading=14,
                                alignment=TA_LEFT)
    total_style = ParagraphStyle('total', fontName='Helvetica-Bold', fontSize=10.5,
                                 leading=14, spaceBefore=2, textColor=colors.HexColor('#1e6b3e'))

    elements = [Paragraph('Teacher Assignment Summary', title_style)]
    if not summary:
        elements.append(Paragraph('No assignments yet.', line_style))
    for row in summary:
        elements.append(Paragraph(row['teacher'].name, teacher_style))
        if row['lines']:
            elements.append(ListFlowable(
                [ListItem(Paragraph(line['text'], line_style), leftIndent=6) for line in row['lines']],
                bulletType='bullet', start='-', leftIndent=14))
        plural = 's' if row['total'] != 1 else ''
        elements.append(Paragraph(f"Total — {row['total']} period{plural}/week", total_style))

    doc.build(elements)
    return pdf_response(output, 'teacher_assignment_summary.pdf')
