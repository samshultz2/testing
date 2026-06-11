"""
Excel import/export utilities for the Student Management System
Uses openpyxl for Excel file operations
"""
import io
from datetime import datetime
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter


# Style definitions
HEADER_FONT = Font(bold=True, color='FFFFFF', size=11)
HEADER_FILL = PatternFill(start_color='2E7D32', end_color='2E7D32', fill_type='solid')
HEADER_ALIGNMENT = Alignment(horizontal='center', vertical='center', wrap_text=True)

CELL_ALIGNMENT = Alignment(horizontal='left', vertical='center')
THIN_BORDER = Border(
    left=Side(style='thin'),
    right=Side(style='thin'),
    top=Side(style='thin'),
    bottom=Side(style='thin')
)


def create_styled_workbook():
    """Create a new workbook with default styling"""
    wb = Workbook()
    return wb


def style_header_row(ws, row_num=1, num_cols=None):
    """Apply header styling to a row"""
    if num_cols is None:
        num_cols = ws.max_column
    
    for col in range(1, num_cols + 1):
        cell = ws.cell(row=row_num, column=col)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGNMENT
        cell.border = THIN_BORDER


def auto_adjust_columns(ws):
    """Auto-adjust column widths based on content"""
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except Exception:
                pass
        
        adjusted_width = min(max_length + 2, 50)  # Cap at 50
        ws.column_dimensions[column_letter].width = adjusted_width


def export_students_to_excel(students):
    """
    Export student data to Excel
    
    Args:
        students: List of Student model objects
    
    Returns:
        BytesIO object containing the Excel file
    """
    wb = create_styled_workbook()
    ws = wb.active
    ws.title = "Students"
    
    # Define headers
    headers = [
        'Student ID', 'Surname', 'First Name', 'Middle Name', 'Gender',
        'Date of Birth', 'Religion', 'Home Address', 'Hobbies',
        'Primary Contact', 'Created Date'
    ]
    
    # Write headers
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    
    style_header_row(ws, 1, len(headers))
    
    # Write data
    for row, student in enumerate(students, 2):
        primary_contact = student.parent_contacts.filter_by(is_primary=True).first()
        
        ws.cell(row=row, column=1, value=student.student_id)
        ws.cell(row=row, column=2, value=student.surname)
        ws.cell(row=row, column=3, value=student.first_name)
        ws.cell(row=row, column=4, value=student.middle_name or '')
        ws.cell(row=row, column=5, value=student.gender)
        ws.cell(row=row, column=6, value=student.date_of_birth.strftime('%Y-%m-%d') if student.date_of_birth else '')
        ws.cell(row=row, column=7, value=student.religion or '')
        ws.cell(row=row, column=8, value=student.home_address or '')
        ws.cell(row=row, column=9, value=student.hobbies or '')
        ws.cell(row=row, column=10, value=primary_contact.phone_number if primary_contact else '')
        ws.cell(row=row, column=11, value=student.created_at.strftime('%Y-%m-%d'))
        
        # Apply border to data cells
        for col in range(1, len(headers) + 1):
            ws.cell(row=row, column=col).border = THIN_BORDER
    
    auto_adjust_columns(ws)
    
    # Save to BytesIO
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def create_student_import_template():
    """
    Create a template Excel file for importing students
    
    Returns:
        BytesIO object containing the Excel template
    """
    wb = create_styled_workbook()
    ws = wb.active
    ws.title = "Student Import Template"

    # One clean header row (row 1) — columns are matched by name, in any order.
    # Only Surname and First Name are required. The importer also accepts a sheet
    # typed straight from a class register with the same column names.
    headers = [
        'Surname', 'First Name', 'Middle Name', 'Gender', 'Date of Birth',
        'Religion', 'Address', 'Hobbies', 'Name of Primary Contact',
        'Phone Number', 'Relationship',
    ]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws, 1, len(headers))

    # A single example row. Its surname is 'EXAMPLE', which the importer always
    # skips — so the file imports cleanly even if you forget to delete it.
    example = [
        'EXAMPLE', 'John', 'Oluwaseun', 'Male', '2010-05-15',
        'Christianity', '25 Broad Street, Lagos', 'Football, Reading',
        'Mrs. Jane Adeyemi', '08012345678', 'Mother',
    ]
    for col, value in enumerate(example, 1):
        cell = ws.cell(row=2, column=col, value=value)
        cell.font = Font(italic=True, color='999999')

    # Instructions live in a comment on the first header cell (doesn't affect import).
    from openpyxl.comments import Comment
    ws.cell(row=1, column=1).comment = Comment(
        "Fill one student per row from row 2 down.\n"
        "Required: Surname, First Name.\n"
        "Gender: Male/Female (optional — blank becomes 'Unknown').\n"
        "Date of Birth: e.g. 2010-05-15 or 15/05/2010.\n"
        "Delete the grey EXAMPLE row (or leave it — it is ignored).",
        "PosyHub")

    auto_adjust_columns(ws)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def _norm_header(value):
    """Normalise a header cell to a comparison key: lowercased, no '*'/spaces/punct."""
    if value is None:
        return ''
    s = str(value).strip().lower().replace('*', '')
    for ch in ('_', '-', '.', '/'):
        s = s.replace(ch, ' ')
    return ' '.join(s.split())


# Accepted column-name aliases → canonical field. Header matching is order-free,
# so the spreadsheet's columns can be in any order and named loosely.
_HEADER_ALIASES = {
    'surname': 'surname', 'last name': 'surname', 'lastname': 'surname',
    'first name': 'first_name', 'firstname': 'first_name', 'first': 'first_name',
    'middle name': 'middle_name', 'middlename': 'middle_name',
    'other name': 'middle_name', 'other names': 'middle_name',
    'gender': 'gender', 'sex': 'gender',
    'date of birth': 'dob', 'dob': 'dob', 'birth date': 'dob', 'birthdate': 'dob',
    'religion': 'religion',
    'address': 'address', 'home address': 'address', 'house address': 'address',
    'hobbies': 'hobbies', 'hobby': 'hobbies', 'interests': 'hobbies',
    'name of primary contact': 'parent_name', 'primary contact': 'parent_name',
    'parent name': 'parent_name', 'guardian name': 'parent_name',
    'parent': 'parent_name', 'guardian': 'parent_name', 'parent guardian': 'parent_name',
    'phone number': 'parent_phone', 'phone': 'parent_phone', 'phone no': 'parent_phone',
    'parent phone': 'parent_phone', 'guardian phone': 'parent_phone',
    'contact': 'parent_phone', 'contact number': 'parent_phone', 'mobile': 'parent_phone',
    'relationship': 'parent_rel', 'relation': 'parent_rel',
}

# First-column values that mark a non-data row (instruction/sample artefacts from
# older templates) and should be skipped rather than imported.
_SKIP_FIRST_CELL = {'instructions:', 'instruction', 'required', 'optional',
                    'surname', 'last name', 'example'}


def _cell_str(value):
    """Excel cell → trimmed string, dropping the spurious '.0' on integer floats."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    s = str(value).strip()
    return s or None


def _parse_dob(value, errors, row_num):
    """Parse a date-of-birth cell that may be a real date or a string."""
    from datetime import date as _date
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, _date):
        return value
    s = str(value).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y', '%d-%m-%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    errors.append(f"Row {row_num}: couldn't read date of birth '{s}' — left blank")
    return None


def _normalise_phone(value):
    """Nigerian phone tidy-up: keep digits, restore a leading 0 lost by Excel."""
    s = _cell_str(value)
    if not s:
        return None
    digits = ''.join(c for c in s if c.isdigit())
    if not digits:
        return s
    # Excel stores 08012345678 as the integer 8012345678 — restore the 0.
    if len(digits) == 10 and not digits.startswith('0'):
        digits = '0' + digits
    return digits


def _normalise_gender(value):
    """Map loose gender values to Male/Female; return None if unrecognised."""
    s = _cell_str(value)
    if not s:
        return None
    t = s.strip().lower()
    if t in ('m', 'male', 'boy'):
        return 'Male'
    if t in ('f', 'female', 'girl'):
        return 'Female'
    return None


def import_students_from_excel(file_stream, db, Student, ParentContact, branch_id=None):
    """
    Import students from an Excel file.

    Columns are matched by **header name** (row 1), in any order, so a register
    typed as Surname / First Name / Middle Name / Date of Birth / Address /
    Phone Number / Religion / Name of Primary Contact imports cleanly. Only
    Surname and First Name are required; a missing Gender column defaults to
    'Unknown' (flagged so you can fill it in later).

    Args:
        file_stream: File stream of the Excel file
        db: SQLAlchemy database instance
        Student: Student model class
        ParentContact: ParentContact model class
        branch_id: branch to stamp on every imported student (optional)

    Returns:
        Tuple of (success_count, messages) — messages are per-row notes/errors.
    """
    wb = load_workbook(file_stream, data_only=True)
    ws = wb.active

    success_count = 0
    errors = []

    # Build {canonical_field: column_index} from the header row.
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return 0, ['The sheet is empty.']
    header = rows[0]
    colmap = {}
    for idx, cell in enumerate(header):
        field = _HEADER_ALIASES.get(_norm_header(cell))
        if field and field not in colmap:
            colmap[field] = idx

    if 'surname' not in colmap or 'first_name' not in colmap:
        return 0, [
            "Couldn't find the required column headers. Row 1 must include at "
            "least 'Surname' and 'First Name' columns. Found: "
            + ', '.join(str(h) for h in header if h) + '.'
        ]

    def get(row, field):
        idx = colmap.get(field)
        if idx is None or idx >= len(row):
            return None
        return row[idx]

    gender_defaulted = 0

    for row_num, row in enumerate(rows[1:], start=2):
        surname = _cell_str(get(row, 'surname'))
        first_name = _cell_str(get(row, 'first_name'))

        # Skip blank rows and leftover instruction/sample rows.
        if not surname and not first_name:
            continue
        if surname and surname.lower() in _SKIP_FIRST_CELL:
            continue
        if not surname or not first_name:
            errors.append(f"Row {row_num}: missing Surname or First Name — skipped")
            continue

        gender = _normalise_gender(get(row, 'gender'))
        defaulted = gender is None
        if defaulted:
            gender = 'Unknown'

        try:
            # Per-row savepoint: a bad row rolls back only itself, never the
            # rows already imported in this batch.
            with db.session.begin_nested():
                student = Student(
                    student_id=Student.generate_student_id(),
                    surname=surname,
                    first_name=first_name,
                    middle_name=_cell_str(get(row, 'middle_name')),
                    gender=gender,
                    date_of_birth=_parse_dob(get(row, 'dob'), errors, row_num),
                    religion=_cell_str(get(row, 'religion')),
                    home_address=_cell_str(get(row, 'address')),
                    hobbies=_cell_str(get(row, 'hobbies')),
                    branch_id=branch_id,
                    is_active=True,
                )
                db.session.add(student)
                db.session.flush()  # assign student.id

                # phone_number is required on a contact, so only create one when
                # a phone is present (a name on its own is dropped).
                parent_phone = _normalise_phone(get(row, 'parent_phone'))
                if parent_phone:
                    db.session.add(ParentContact(
                        student_id=student.id,
                        name=_cell_str(get(row, 'parent_name')),
                        phone_number=parent_phone,
                        relationship=_cell_str(get(row, 'parent_rel')) or 'Guardian',
                        is_primary=True,
                    ))

            success_count += 1
            if defaulted:
                gender_defaulted += 1

        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")

    if success_count > 0:
        db.session.commit()

    if gender_defaulted:
        errors.insert(0, f"{gender_defaulted} student(s) had no Gender column/value "
                         "and were set to 'Unknown' — edit them to set Male/Female.")

    return success_count, errors



def export_attendance_to_excel(attendance_data, class_name, week_info):
    """
    Export weekly attendance data to Excel
    
    Args:
        attendance_data: Dict from get_weekly_attendance_summary
        class_name: Name of the class arm
        week_info: Week details
    
    Returns:
        BytesIO object containing the Excel file
    """
    wb = create_styled_workbook()
    ws = wb.active
    ws.title = "Weekly Attendance"
    
    # Title section
    ws.cell(row=1, column=1, value=f"Weekly Attendance Report - {class_name}")
    ws.cell(row=1, column=1).font = Font(bold=True, size=14)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=8)
    
    ws.cell(row=2, column=1, value=f"Week {week_info['week_number']}: {week_info['start_date']} to {week_info['end_date']}")
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=8)
    
    # Headers
    headers = ['S/N', 'Student Name', 'Gender']
    for day in attendance_data['school_days']:
        headers.append(f"{day.strftime('%a')} AM")
        headers.append(f"{day.strftime('%a')} PM")
    headers.extend(['Weekly Total', 'Percentage'])
    
    for col, header in enumerate(headers, 1):
        ws.cell(row=4, column=col, value=header)
    
    style_header_row(ws, 4, len(headers))
    
    # Student data
    times_opened = attendance_data['times_opened']
    for idx, student in enumerate(attendance_data['students'], 1):
        row = idx + 4
        ws.cell(row=row, column=1, value=idx)
        ws.cell(row=row, column=2, value=student['student_name'])
        ws.cell(row=row, column=3, value=student['gender'])
        
        col = 4
        for daily in student['daily']:
            ws.cell(row=row, column=col, value='✓' if daily['morning'] else '✗')
            ws.cell(row=row, column=col + 1, value='✓' if daily['afternoon'] else '✗')
            col += 2
        
        ws.cell(row=row, column=col, value=student['weekly_total'])
        percentage = round((student['weekly_total'] / times_opened * 100), 2) if times_opened > 0 else 0
        ws.cell(row=row, column=col + 1, value=f"{percentage}%")
        
        # Apply borders
        for c in range(1, len(headers) + 1):
            ws.cell(row=row, column=c).border = THIN_BORDER
    
    # Summary section
    summary_row = len(attendance_data['students']) + 6
    totals = attendance_data['class_totals']
    
    ws.cell(row=summary_row, column=1, value="CLASS SUMMARY")
    ws.cell(row=summary_row, column=1).font = Font(bold=True)
    
    ws.cell(row=summary_row + 1, column=1, value=f"Total Students: {attendance_data['total_students']}")
    ws.cell(row=summary_row + 2, column=1, value=f"Male: {attendance_data['total_male']}, Female: {attendance_data['total_female']}")
    ws.cell(row=summary_row + 3, column=1, value=f"Times Opened: {times_opened}")
    ws.cell(row=summary_row + 4, column=1, value=f"Total Morning Attendance: {totals['total_morning']}")
    ws.cell(row=summary_row + 5, column=1, value=f"Total Afternoon Attendance: {totals['total_afternoon']}")
    ws.cell(row=summary_row + 6, column=1, value=f"Total Attendance: {totals['total_attendance']}")
    ws.cell(row=summary_row + 7, column=1, value=f"Weekly Percentage: {totals['weekly_percentage']}%")
    
    auto_adjust_columns(ws)
    
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def export_waec_results_to_excel(results_data):
    """
    Export WAEC results to Excel
    
    Args:
        results_data: List of result dictionaries
    
    Returns:
        BytesIO object containing the Excel file
    """
    wb = create_styled_workbook()
    ws = wb.active
    ws.title = "WAEC Results"
    
    # Get all unique subjects
    all_subjects = set()
    for result in results_data:
        all_subjects.update(result.get('subjects', {}).keys())
    subjects = sorted(all_subjects)
    
    # Headers
    headers = ['S/N', 'Student Name', 'Exam Year'] + subjects + ['Total Points', 'Credit Passes']
    
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    
    style_header_row(ws, 1, len(headers))
    
    # Data rows
    for idx, result in enumerate(results_data, 1):
        row = idx + 1
        ws.cell(row=row, column=1, value=idx)
        ws.cell(row=row, column=2, value=result['student_name'])
        ws.cell(row=row, column=3, value=result['exam_year'])
        
        col = 4
        total_points = 0
        credit_passes = 0
        
        for subject in subjects:
            grade = result.get('subjects', {}).get(subject, '-')
            ws.cell(row=row, column=col, value=grade)
            
            if grade != '-':
                from models import WAECResult
                total_points += WAECResult.grade_to_points(grade)
                if WAECResult.is_pass(grade):
                    credit_passes += 1
            col += 1
        
        ws.cell(row=row, column=col, value=total_points)
        ws.cell(row=row, column=col + 1, value=credit_passes)
        
        for c in range(1, len(headers) + 1):
            ws.cell(row=row, column=c).border = THIN_BORDER
    
    auto_adjust_columns(ws)
    
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output
