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
            except:
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
    
    # Define headers with instructions
    headers = [
        ('Surname*', 'Required'),
        ('First Name*', 'Required'),
        ('Middle Name', 'Optional'),
        ('Gender*', 'Male or Female'),
        ('Date of Birth', 'YYYY-MM-DD format'),
        ('Religion', 'Christianity, Islam, Traditional, Others'),
        ('Home Address', 'Full address'),
        ('Hobbies', 'Comma-separated'),
        ('Parent Name', 'Name of primary contact'),
        ('Parent Phone*', '11-digit Nigerian number'),
        ('Parent Relationship', 'Father, Mother, Guardian, etc.')
    ]
    
    # Write headers
    for col, (header, _) in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    
    style_header_row(ws, 1, len(headers))
    
    # Write instructions row
    ws.cell(row=2, column=1, value="Instructions:")
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(headers))
    
    for col, (_, instruction) in enumerate(headers, 1):
        ws.cell(row=3, column=col, value=instruction)
        ws.cell(row=3, column=col).font = Font(italic=True, color='666666')
    
    # Add sample data row
    sample_data = [
        'Adeyemi', 'John', 'Oluwaseun', 'Male', '2008-05-15',
        'Christianity', '25 Broad Street, Lagos', 'Football, Reading',
        'Mr. James Adeyemi', '08012345678', 'Father'
    ]
    
    for col, value in enumerate(sample_data, 1):
        ws.cell(row=5, column=col, value=value)
    
    auto_adjust_columns(ws)
    
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def import_students_from_excel(file_stream, db, Student, ParentContact):
    """
    Import students from an Excel file
    
    Args:
        file_stream: File stream of the Excel file
        db: SQLAlchemy database instance
        Student: Student model class
        ParentContact: ParentContact model class
    
    Returns:
        Tuple of (success_count, error_list)
    """
    wb = load_workbook(file_stream)
    ws = wb.active
    
    success_count = 0
    errors = []
    
    # Skip header rows (row 1 = headers, row 2-3 = instructions, row 4 = empty)
    for row_num, row in enumerate(ws.iter_rows(min_row=5, values_only=True), 5):
        # Skip empty rows
        if not row[0]:
            continue
        
        try:
            surname = str(row[0]).strip() if row[0] else None
            first_name = str(row[1]).strip() if row[1] else None
            middle_name = str(row[2]).strip() if row[2] else None
            gender = str(row[3]).strip() if row[3] else None
            dob_str = str(row[4]).strip() if row[4] else None
            religion = str(row[5]).strip() if row[5] else None
            address = str(row[6]).strip() if row[6] else None
            hobbies = str(row[7]).strip() if row[7] else None
            parent_name = str(row[8]).strip() if row[8] else None
            parent_phone = str(row[9]).strip() if row[9] else None
            parent_rel = str(row[10]).strip() if row[10] else 'Guardian'
            
            # Validate required fields
            if not surname or not first_name:
                errors.append(f"Row {row_num}: Missing required name fields")
                continue
            
            if not gender or gender not in ['Male', 'Female']:
                errors.append(f"Row {row_num}: Invalid gender (must be Male or Female)")
                continue
            
            # Parse date of birth
            dob = None
            if dob_str:
                try:
                    dob = datetime.strptime(dob_str, '%Y-%m-%d').date()
                except ValueError:
                    try:
                        dob = datetime.strptime(dob_str, '%d/%m/%Y').date()
                    except ValueError:
                        errors.append(f"Row {row_num}: Invalid date format")
            
            # Create student
            student = Student(
                student_id=Student.generate_student_id(),
                surname=surname,
                first_name=first_name,
                middle_name=middle_name,
                gender=gender,
                date_of_birth=dob,
                religion=religion,
                home_address=address,
                hobbies=hobbies
            )
            
            db.session.add(student)
            db.session.flush()  # Get the student ID
            
            # Add parent contact if provided
            if parent_phone:
                contact = ParentContact(
                    student_id=student.id,
                    name=parent_name,
                    phone_number=parent_phone,
                    relationship=parent_rel,
                    is_primary=True
                )
                db.session.add(contact)
            
            success_count += 1
            
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")
            db.session.rollback()
    
    if success_count > 0:
        db.session.commit()
    
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
