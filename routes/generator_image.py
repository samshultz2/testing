"""
Timetable Image Export
Generates high-quality JPG images of timetables using Pillow
V3: JPG format, correct abbreviations, school watermark
"""
from flask import Response
from models import GenTimetableResult, GenTimetableRule, GenTeacher, GenSubject, GenSettings
from routes.generator import gen_bid
from utils.generator_times import clock_params, break_after as _break_after
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO


def _load_logo():
    """The uploaded school logo as an RGBA PIL image, or None if none is set."""
    try:
        from utils.school import logo_path
        p = logo_path()
        if not p:
            return None
        return Image.open(p).convert('RGBA')
    except Exception:
        return None


def _paste_logo_left(img, logo, text_x, top_y, target_h, gap):
    """Paste ``logo`` (RGBA) scaled to height ``target_h`` just left of ``text_x``,
    aligned to ``top_y``. Returns the pasted width (0 if nothing pasted)."""
    if logo is None:
        return 0
    try:
        h = max(1, int(target_h))
        w = max(1, int(logo.width * (h / logo.height)))
        scaled = logo.resize((w, h))
        lx = max(0, int(text_x) - w - int(gap))
        img.paste(scaled, (lx, int(top_y)), scaled)
        return w
    except Exception:
        return 0


def get_font(size, bold=False):
    """Get a font, trying system fonts first"""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    try:
        return ImageFont.load_default()
    except (OSError, IOError):
        return None


# Abbreviations for subjects actually used
SUBJECT_ABBREV = {
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
    'History': 'Hist',
    'Phonics': 'Phon',
    'Livestock Farming': 'Livst',
    # JSS Subjects
    'Basic Science': 'B.Sci',
    'Basic Technology': 'B.Tech',
    'Social Studies': 'Soc',
    'Home Economics': 'H/Eco',
    'Business Studies': 'Bus',
    'Physical Health Education': 'PHE',
    # Additional subjects
    'Accounting': 'Acct',
    'French': 'Fren',
    'Hausa': 'Hau',
    'Igbo': 'Igbo',
    'Yoruba': 'Yor',
    'Islamic Religious Studies': 'IRS',
    'Technical Drawing': 'T/Drw',
    'Visual Arts': 'V/Art',
    'Music': 'Music',
    'Physical Education': 'P.E',
    'Food and Nutrition': 'F&N',
    'Fisheries': 'Fish',
    'Data Processing': 'D.Pro',
    'Marketing': 'Mkt',
}


def _abbrev(subj, maxlen=6):
    """The short label for a subject in the image: the user's own short name
    (from /generator/subjects) if set, else the built-in abbreviation, else a
    truncation of the full name."""
    if subj is None:
        return ''
    sn = (getattr(subj, 'short_name', '') or '').strip()
    if sn:
        return sn
    name = getattr(subj, 'name', '') or ''
    return SUBJECT_ABBREV.get(name, name[:maxlen] if len(name) > maxlen else name)


def get_school_name():
    """Get school name from GenSettings"""
    try:
        return GenSettings.get('school_name', 'School Timetable')
    except Exception:
        return "School Timetable"


def get_short_code(class_name, arm):
    """Convert SSS1 Iris -> 1I or JSS2 Rose -> J2R"""
    if class_name.startswith('JSS'):
        class_num = class_name.replace('JSS', '')
        arm_letter = arm[0].upper()
        return f"J{class_num}{arm_letter}"
    else:
        class_num = class_name.replace('SSS', '')
        arm_letter = arm[0].upper()
        return f"{class_num}{arm_letter}"


def generate_timetable_image(batch_id, layout='by_day', quality='ultra'):
    """
    Generate HIGH QUALITY timetable image for printing
    
    quality options:
    - 'hd': 4x scale (good for screen/web)
    - 'ultra': 8x scale (best for printing)
    
    Resolution: 4x or 8x scale for maximum clarity
    Format: PNG for lossless quality
    Includes: School name, address, period times, BREAK column
    """
    results = GenTimetableResult.query.filter_by(batch_id=batch_id, branch_id=gen_bid()).all()
    if not results:
        return None
    
    # Determine school level from results
    school_level = results[0].school_level if results else 'sss'
    
    rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(is_active=True, school_level=school_level, branch_id=gen_bid()).all()}
    periods_per_day = int(rules.get('periods_per_day', 8))
    break_after = _break_after(rules, periods_per_day)

    class_arms = sorted(set((r.class_name, r.arm_name) for r in results))
    days = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY']
    
    school_name = get_school_name()
    
    # Get school address
    try:
        school_address = GenSettings.get('school_address', '')
    except Exception:
        school_address = ''
    
    # Period times — start/period-length/break-length are per-level settings.
    period_times_before = []  # P1-P5
    period_times_after = []   # P6-P8
    break_time = ""

    start_hour, start_min, _plen, _blen = clock_params(rules)
    for p in range(1, periods_per_day + 1):
        start_total = start_hour * 60 + start_min
        end_total = start_total + _plen
        start_h, start_m = start_total // 60, start_total % 60
        end_h, end_m = end_total // 60, end_total % 60

        time_str = f"P{p}\n{start_h}:{start_m:02d}-{end_h}:{end_m:02d}"
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
            break_time = f"{break_start}-{break_end}"
    
    # Resolution settings
    scale = 8 if quality == 'ultra' else 4
    cell_width = 85 * scale
    cell_height = 35 * scale
    header_height = 55 * scale  # Taller for time display
    day_header_height = 55 * scale
    class_col_width = 55 * scale
    break_col_width = 35 * scale  # Narrower break column
    margin = 50 * scale
    day_spacing = 25 * scale
    title_height = 120 * scale  # Taller for school name + address
    
    # Total columns: Class + periods-before + BREAK + periods-after
    num_periods_before = break_after
    num_periods_after = periods_per_day - break_after
    
    table_width = class_col_width + (num_periods_before * cell_width) + break_col_width + (num_periods_after * cell_width)
    img_height = title_height + (len(days) * (day_header_height + header_height + (len(class_arms) * cell_height) + day_spacing)) + (margin * 2)
    img_width = table_width + (margin * 2)
    
    # Create image - white background
    img = Image.new('RGB', (img_width, img_height), color='white')
    draw = ImageDraw.Draw(img)
    
    # Fonts - LARGER for ultra-high resolution printing
    font_title = get_font(36 * scale, bold=True)
    font_address = get_font(16 * scale, bold=False)
    font_day = get_font(28 * scale, bold=True)
    font_header = get_font(12 * scale, bold=True)  # For time display
    font_header_simple = get_font(16 * scale, bold=True)  # For P1, P2 etc
    font_cell = get_font(16 * scale, bold=True)
    font_class = get_font(16 * scale, bold=True)
    font_break = get_font(14 * scale, bold=True)
    font_watermark = get_font(12 * scale, bold=False)
    
    # Colors
    color_black = (0, 0, 0)
    color_dark_gray = (50, 50, 50)
    color_gray = (120, 120, 120)
    color_light_gray = (245, 245, 245)
    color_border = (80, 80, 80)
    color_watermark = (200, 200, 200)
    color_break = (255, 107, 107)  # Red for break
    color_white = (255, 255, 255)
    color_day_bg = (68, 114, 196)  # Blue for day header
    
    # School name header (with the uploaded logo to its left, if any)
    logo_img = _load_logo()
    y_pos = margin
    if font_title:
        bbox = draw.textbbox((0, 0), school_name.upper(), font=font_title)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = (img_width - text_width) // 2
        _paste_logo_left(img, logo_img, text_x, y_pos, text_height + 14 * scale, 16 * scale)
        draw.text((text_x, y_pos), school_name.upper(), fill=color_black, font=font_title)
        y_pos += 40 * scale
    
    # School address
    if school_address and font_address:
        bbox = draw.textbbox((0, 0), school_address, font=font_address)
        text_width = bbox[2] - bbox[0]
        text_x = (img_width - text_width) // 2
        draw.text((text_x, y_pos), school_address, fill=color_gray, font=font_address)
        y_pos += 25 * scale
    
    # Subtitle
    subtitle = "MASTER TIMETABLE"
    if font_address:
        bbox = draw.textbbox((0, 0), subtitle, font=font_address)
        text_width = bbox[2] - bbox[0]
        text_x = (img_width - text_width) // 2
        draw.text((text_x, y_pos), subtitle, fill=color_gray, font=font_address)
    
    y_offset = margin + title_height
    
    for day_idx, day_name in enumerate(days):
        # Day header - blue background
        x = margin
        draw.rectangle([x, y_offset, x + table_width, y_offset + day_header_height],
                      fill=color_day_bg, outline=color_border, width=scale)
        if font_day:
            bbox = draw.textbbox((0, 0), day_name, font=font_day)
            text_width = bbox[2] - bbox[0]
            text_x = x + (table_width - text_width) // 2
            text_y = y_offset + (day_header_height - (bbox[3] - bbox[1])) // 2
            draw.text((text_x, text_y), day_name, fill=color_white, font=font_day)
        y_offset += day_header_height
        
        # Period header row
        x = margin
        
        # Class header cell
        draw.rectangle([x, y_offset, x + class_col_width, y_offset + header_height], 
                      fill=color_light_gray, outline=color_border, width=scale)
        if font_header_simple:
            text = "Class"
            bbox = draw.textbbox((0, 0), text, font=font_header_simple)
            text_width = bbox[2] - bbox[0]
            text_x = x + (class_col_width - text_width) // 2
            draw.text((text_x, y_offset + 15 * scale), text, fill=color_black, font=font_header_simple)
        x += class_col_width
        
        # P1-P5 headers with times (only on Monday)
        for i in range(num_periods_before):
            draw.rectangle([x, y_offset, x + cell_width, y_offset + header_height],
                          fill=color_light_gray, outline=color_border, width=scale)
            
            if day_idx == 0:  # Monday - show times
                text = period_times_before[i]
                lines = text.split('\n')
                if font_header:
                    # Period number
                    bbox = draw.textbbox((0, 0), lines[0], font=font_header_simple)
                    text_width = bbox[2] - bbox[0]
                    text_x = x + (cell_width - text_width) // 2
                    draw.text((text_x, y_offset + 5 * scale), lines[0], fill=color_black, font=font_header_simple)
                    # Time
                    bbox = draw.textbbox((0, 0), lines[1], font=font_header)
                    text_width = bbox[2] - bbox[0]
                    text_x = x + (cell_width - text_width) // 2
                    draw.text((text_x, y_offset + 28 * scale), lines[1], fill=color_gray, font=font_header)
            else:
                text = f"P{i+1}"
                if font_header_simple:
                    bbox = draw.textbbox((0, 0), text, font=font_header_simple)
                    text_width = bbox[2] - bbox[0]
                    text_x = x + (cell_width - text_width) // 2
                    draw.text((text_x, y_offset + 15 * scale), text, fill=color_black, font=font_header_simple)
            x += cell_width
        
        # BREAK header
        draw.rectangle([x, y_offset, x + break_col_width, y_offset + header_height],
                      fill=color_break, outline=color_border, width=scale)
        if day_idx == 0 and font_header:  # Monday - show break time
            bbox = draw.textbbox((0, 0), "BREAK", font=font_header)
            text_width = bbox[2] - bbox[0]
            text_x = x + (break_col_width - text_width) // 2
            draw.text((text_x, y_offset + 5 * scale), "BREAK", fill=color_white, font=font_header)
            bbox = draw.textbbox((0, 0), break_time, font=font_header)
            text_width = bbox[2] - bbox[0]
            text_x = x + (break_col_width - text_width) // 2
            draw.text((text_x, y_offset + 28 * scale), break_time, fill=color_white, font=font_header)
        else:
            text = "BREAK"
            if font_header:
                bbox = draw.textbbox((0, 0), text, font=font_header)
                text_width = bbox[2] - bbox[0]
                text_x = x + (break_col_width - text_width) // 2
                draw.text((text_x, y_offset + 15 * scale), text, fill=color_white, font=font_header)
        x += break_col_width
        
        # P6-P8 headers with times (only on Monday)
        for i in range(num_periods_after):
            draw.rectangle([x, y_offset, x + cell_width, y_offset + header_height],
                          fill=color_light_gray, outline=color_border, width=scale)
            
            if day_idx == 0:  # Monday - show times
                text = period_times_after[i]
                lines = text.split('\n')
                if font_header:
                    bbox = draw.textbbox((0, 0), lines[0], font=font_header_simple)
                    text_width = bbox[2] - bbox[0]
                    text_x = x + (cell_width - text_width) // 2
                    draw.text((text_x, y_offset + 5 * scale), lines[0], fill=color_black, font=font_header_simple)
                    bbox = draw.textbbox((0, 0), lines[1], font=font_header)
                    text_width = bbox[2] - bbox[0]
                    text_x = x + (cell_width - text_width) // 2
                    draw.text((text_x, y_offset + 28 * scale), lines[1], fill=color_gray, font=font_header)
            else:
                text = f"P{6+i}"
                if font_header_simple:
                    bbox = draw.textbbox((0, 0), text, font=font_header_simple)
                    text_width = bbox[2] - bbox[0]
                    text_x = x + (cell_width - text_width) // 2
                    draw.text((text_x, y_offset + 15 * scale), text, fill=color_black, font=font_header_simple)
            x += cell_width
        
        y_offset += header_height
        
        # Class rows
        for class_name, arm in class_arms:
            x = margin
            short_code = get_short_code(class_name, arm)
            
            # Class code cell
            draw.rectangle([x, y_offset, x + class_col_width, y_offset + cell_height],
                          fill=color_light_gray, outline=color_border, width=scale)
            if font_class:
                bbox = draw.textbbox((0, 0), short_code, font=font_class)
                text_width = bbox[2] - bbox[0]
                text_x = x + (class_col_width - text_width) // 2
                text_y = y_offset + (cell_height - (bbox[3] - bbox[1])) // 2
                draw.text((text_x, text_y), short_code, fill=color_black, font=font_class)
            x += class_col_width
            
            # Get results for this class-arm on this day
            day_results = {r.period_number: r for r in results 
                          if r.class_name == class_name and r.arm_name == arm and r.day_of_week == day_idx}
            
            # Before-break cells
            for p in range(1, break_after + 1):
                result = day_results.get(p)
                draw.rectangle([x, y_offset, x + cell_width, y_offset + cell_height],
                              fill='white', outline=color_border, width=scale)

                if result:
                    subj = GenSubject.query.get(result.subject_id)
                    if subj:
                        abbrev = _abbrev(subj, 6)
                        if font_cell:
                            bbox = draw.textbbox((0, 0), abbrev, font=font_cell)
                            text_width = bbox[2] - bbox[0]
                            text_x = x + (cell_width - text_width) // 2
                            text_y = y_offset + (cell_height - (bbox[3] - bbox[1])) // 2
                            draw.text((text_x, text_y), abbrev, fill=color_dark_gray, font=font_cell)
                
                x += cell_width
            
            # BREAK cell - vertical text
            draw.rectangle([x, y_offset, x + break_col_width, y_offset + cell_height],
                          fill=color_break, outline=color_border, width=scale)
            # Draw vertical "BREAK" - each letter stacked
            if font_break:
                letters = ['B', 'R', 'E', 'A', 'K']
                letter_height = cell_height // (len(letters) + 1)
                for i, letter in enumerate(letters):
                    bbox = draw.textbbox((0, 0), letter, font=font_break)
                    text_width = bbox[2] - bbox[0]
                    text_x = x + (break_col_width - text_width) // 2
                    text_y = y_offset + (i + 0.5) * letter_height
                    draw.text((text_x, text_y), letter, fill=color_white, font=font_break)
            x += break_col_width
            
            # After-break cells
            for p in range(break_after + 1, periods_per_day + 1):
                result = day_results.get(p)
                draw.rectangle([x, y_offset, x + cell_width, y_offset + cell_height],
                              fill='white', outline=color_border, width=scale)
                
                if result:
                    subj = GenSubject.query.get(result.subject_id)
                    if subj:
                        abbrev = _abbrev(subj, 6)
                        if font_cell:
                            bbox = draw.textbbox((0, 0), abbrev, font=font_cell)
                            text_width = bbox[2] - bbox[0]
                            text_x = x + (cell_width - text_width) // 2
                            text_y = y_offset + (cell_height - (bbox[3] - bbox[1])) // 2
                            draw.text((text_x, text_y), abbrev, fill=color_dark_gray, font=font_cell)
                
                x += cell_width
            
            y_offset += cell_height
        
        # Spacing between days
        y_offset += day_spacing
    
    # Watermark at bottom
    if font_watermark:
        watermark = f"Generated by School Timetable System"
        bbox = draw.textbbox((0, 0), watermark, font=font_watermark)
        text_width = bbox[2] - bbox[0]
        text_x = (img_width - text_width) // 2
        draw.text((text_x, img_height - margin + 10 * scale), watermark, fill=color_watermark, font=font_watermark)
    
    return img


def generate_teacher_timetable_image(batch_id, teacher_id):
    """Generate high-quality timetable image for a single teacher"""
    results = GenTimetableResult.query.filter_by(batch_id=batch_id, teacher_id=teacher_id, branch_id=gen_bid()).all()
    teacher = GenTeacher.query.get(teacher_id)
    
    if not results or not teacher:
        return None
    
    rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(is_active=True, branch_id=gen_bid()).all()}
    periods_per_day = int(rules.get('periods_per_day', 8))
    
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    school_name = get_school_name()
    
    # HIGH RESOLUTION (4x scale)
    scale = 4
    cell_width = 110 * scale
    cell_height = 55 * scale
    header_height = 42 * scale
    day_col_width = 100 * scale
    margin = 50 * scale
    title_height = 100 * scale
    
    table_width = day_col_width + (periods_per_day * cell_width)
    table_height = header_height + (5 * cell_height)
    img_width = table_width + (margin * 2)
    img_height = title_height + table_height + (margin * 2) + 30 * scale  # Extra for watermark
    
    img = Image.new('RGB', (img_width, img_height), color='white')
    draw = ImageDraw.Draw(img)
    
    # Fonts
    font_school = get_font(18 * scale, bold=True)
    font_title = get_font(24 * scale, bold=True)
    font_subtitle = get_font(12 * scale, bold=False)
    font_header = get_font(13 * scale, bold=True)
    font_cell = get_font(11 * scale)
    font_cell_small = get_font(9 * scale)
    font_watermark = get_font(9 * scale, bold=False)
    
    color_black = (0, 0, 0)
    color_gray = (100, 100, 100)
    color_light_gray = (245, 245, 245)
    color_border = (100, 100, 100)
    color_watermark = (200, 200, 200)
    
    # School name
    logo_img = _load_logo()
    if font_school:
        bbox = draw.textbbox((0, 0), school_name.upper(), font=font_school)
        text_width = bbox[2] - bbox[0]
        text_x = (img_width - text_width) // 2
        draw.text((text_x, margin - 10 * scale), school_name.upper(), fill=color_gray, font=font_school)

    # Teacher name (with the uploaded logo to its left, if any)
    title = teacher.name
    if font_title:
        bbox = draw.textbbox((0, 0), title, font=font_title)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = (img_width - text_width) // 2
        _paste_logo_left(img, logo_img, text_x, margin + 20 * scale, text_height + 30 * scale, 16 * scale)
        draw.text((text_x, margin + 20 * scale), title, fill=color_black, font=font_title)
    
    # Subtitle
    subtitle = f"Weekly Timetable | Max {teacher.max_periods_per_day} periods/day"
    if font_subtitle:
        bbox = draw.textbbox((0, 0), subtitle, font=font_subtitle)
        text_width = bbox[2] - bbox[0]
        text_x = (img_width - text_width) // 2
        draw.text((text_x, margin + 55 * scale), subtitle, fill=color_gray, font=font_subtitle)
    
    y_start = margin + title_height
    
    # Header row
    x = margin
    draw.rectangle([x, y_start, x + day_col_width, y_start + header_height], 
                  fill=color_light_gray, outline=color_border, width=scale)
    text = "Day"
    if font_header:
        bbox = draw.textbbox((0, 0), text, font=font_header)
        text_width = bbox[2] - bbox[0]
        draw.text((x + (day_col_width - text_width) // 2, y_start + 12 * scale), text, 
                 fill=color_black, font=font_header)
    x += day_col_width
    
    for p in range(1, periods_per_day + 1):
        draw.rectangle([x, y_start, x + cell_width, y_start + header_height],
                      fill=color_light_gray, outline=color_border, width=scale)
        text = f"P{p}"
        if font_header:
            bbox = draw.textbbox((0, 0), text, font=font_header)
            text_width = bbox[2] - bbox[0]
            draw.text((x + (cell_width - text_width) // 2, y_start + 12 * scale), text,
                     fill=color_black, font=font_header)
        x += cell_width
    
    y_start += header_height
    
    # Day rows
    for day_idx, day_name in enumerate(days):
        x = margin
        
        # Day cell
        draw.rectangle([x, y_start, x + day_col_width, y_start + cell_height],
                      fill=color_light_gray, outline=color_border, width=scale)
        if font_header:
            bbox = draw.textbbox((0, 0), day_name, font=font_header)
            text_width = bbox[2] - bbox[0]
            draw.text((x + (day_col_width - text_width) // 2, y_start + 18 * scale), day_name,
                     fill=color_black, font=font_header)
        x += day_col_width
        
        day_results = {r.period_number: r for r in results if r.day_of_week == day_idx}
        
        for p in range(1, periods_per_day + 1):
            result = day_results.get(p)
            draw.rectangle([x, y_start, x + cell_width, y_start + cell_height],
                          fill='white', outline=color_border, width=scale)
            
            if result:
                subj = GenSubject.query.get(result.subject_id)
                subj_text = _abbrev(subj, 8) if subj else ""
                short_class = get_short_code(result.class_name, result.arm_name)
                
                if font_cell:
                    bbox = draw.textbbox((0, 0), subj_text, font=font_cell)
                    text_width = bbox[2] - bbox[0]
                    draw.text((x + (cell_width - text_width) // 2, y_start + 12 * scale), subj_text,
                             fill=color_black, font=font_cell)
                
                if font_cell_small:
                    bbox = draw.textbbox((0, 0), short_class, font=font_cell_small)
                    text_width = bbox[2] - bbox[0]
                    draw.text((x + (cell_width - text_width) // 2, y_start + 32 * scale), short_class,
                             fill=color_gray, font=font_cell_small)
            
            x += cell_width
        
        y_start += cell_height
    
    # Watermark
    if font_watermark:
        watermark = f"Generated by PosyHub Timetable System"
        bbox = draw.textbbox((0, 0), watermark, font=font_watermark)
        text_width = bbox[2] - bbox[0]
        text_x = (img_width - text_width) // 2
        draw.text((text_x, img_height - margin + 15 * scale), watermark, fill=color_watermark, font=font_watermark)
    
    return img


def image_to_response(img, filename):
    """Convert PIL Image to Flask Response - LOSSLESS PNG for maximum quality"""
    buffer = BytesIO()
    # Save as PNG for lossless quality (no compression artifacts)
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    
    # Update filename extension
    if filename.endswith('.jpg') or filename.endswith('.jpeg'):
        filename = filename.replace('.jpg', '.png').replace('.jpeg', '.png')
    elif not filename.endswith('.png'):
        filename += '.png'
    
    return Response(
        buffer.getvalue(),
        mimetype='image/png',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )
