"""
Reports and data management routes
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, jsonify
from utils.helpers import get_active_term, get_active_session, session_terms
from models import db, Student, ParentContact, Term
from sqlalchemy import func
from utils.helpers import login_required
from utils.excel_utils import (
    export_students_to_excel, create_student_import_template,
    import_students_from_excel
)
from utils.web_exports import xlsx_response
from utils.branch_scope import scope_query, scope_by_student, viewing_branch_id, require_branch_access

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')


def _wants_json():
    return request.headers.get('X-Requested-With') == 'fetch' or request.is_json


def _render(payload):
    from utils.spa import render_or_json
    # Every screen gets the section-nav links.
    payload['urls'] = {
        'index': url_for('reports.index'),
        'summary': url_for('reports.summary_report'),
        'export_class': url_for('reports.export_class_students'),
        'import': url_for('reports.import_students'),
        'export_students': url_for('reports.export_students'),
        'export_template': url_for('reports.export_template'),
        **(payload.get('urls') or {}),
    }
    return render_or_json('reports/app.html', 'reports_json', payload)


@reports_bp.route('/')
@login_required
def index():
    """Reports main page"""
    return _render({'page': 'index', 'urls': {
        'summary': url_for('reports.summary_report'),
        'import': url_for('reports.import_students'),
        'export_students': url_for('reports.export_students'),
        'export_template': url_for('reports.export_template'),
    }})


# ============================================================================
# EXPORT FUNCTIONS
# ============================================================================

@reports_bp.route('/export/students')
@login_required
def export_students():
    """Export all students to Excel"""
    students = scope_query(Student.current_query(), Student).order_by(Student.surname).all()
    from utils.audit import log_action
    log_action('data.export_students', detail=f'{len(students)} students')

    excel_file = export_students_to_excel(students)

    return xlsx_response(excel_file, 'students_export.xlsx')


@reports_bp.route('/export/class-students')
@login_required
def export_class_students():
    """Export students for a specific class"""
    from models import ClassArmAssignment, StudentEnrollment
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Border, Side
    import io
    
    assignment_id = request.args.get('assignment_id', type=int)
    term_id = request.args.get('term_id', type=int)
    
    if not assignment_id:
        # Show selection form
        terms = session_terms()
        
        if not term_id:
            active_term = get_active_term()
            if active_term:
                term_id = active_term.id
        
        assignments = []
        if term_id:
            assignments = scope_query(
                ClassArmAssignment.query.filter_by(term_id=term_id), ClassArmAssignment).all()

        return _render({
            'page': 'export_class', 'term_id': term_id or '',
            'terms': [{'id': t.id, 'label': t.full_name} for t in terms],
            'assignments': [{'id': a.id, 'display_name': a.display_name,
                             'student_count': sum(1 for e in a.enrollments if e.is_active),
                             'export_url': url_for('reports.export_class_students', assignment_id=a.id)}
                            for a in assignments],
            'urls': {'self': url_for('reports.export_class_students')},
        })
    
    # Export the class
    assignment = db.get_or_404(ClassArmAssignment, assignment_id)
    require_branch_access(assignment.branch_id)   # no cross-branch roster export (IDOR guard)
    from utils.audit import log_action
    log_action('data.export_students', target=assignment,
               detail=f'class roster: {assignment.display_name}')

    enrollments = StudentEnrollment.query.filter_by(
        class_arm_assignment_id=assignment_id,
        is_active=True
    ).join(Student).order_by(Student.surname, Student.first_name).all()
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Students"
    
    # Styles
    header_fill = PatternFill(start_color='366092', end_color='366092', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF')
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    
    # Title
    ws['A1'] = f"{assignment.display_name} - Student List"
    ws['A1'].font = Font(bold=True, size=14)
    ws['A2'] = f"{assignment.term.full_name}"
    
    # Headers
    headers = ['S/N', 'Student ID', 'Surname', 'First Name', 'Other Names', 'Gender', 'Date of Birth', 'Religion']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.border = thin_border
    
    # Data
    for idx, enrollment in enumerate(enrollments, 1):
        student = enrollment.student
        row = idx + 4
        ws.cell(row=row, column=1, value=idx).border = thin_border
        ws.cell(row=row, column=2, value=student.student_id).border = thin_border
        ws.cell(row=row, column=3, value=student.surname).border = thin_border
        ws.cell(row=row, column=4, value=student.first_name).border = thin_border
        ws.cell(row=row, column=5, value=student.other_names or '').border = thin_border
        ws.cell(row=row, column=6, value=student.gender).border = thin_border
        ws.cell(row=row, column=7, value=student.date_of_birth.strftime('%Y-%m-%d') if student.date_of_birth else '').border = thin_border
        ws.cell(row=row, column=8, value=student.religion or '').border = thin_border
    
    # Auto-width
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except Exception:
                pass
        ws.column_dimensions[column].width = min(max_length + 2, 30)
    
    filename = f"students_{assignment.display_name.replace(' ', '_')}.xlsx"

    return xlsx_response(wb, filename)


@reports_bp.route('/export/template')
@login_required
def export_template():
    """Download student import template"""
    template = create_student_import_template()

    return xlsx_response(template, 'student_import_template.xlsx')


# ============================================================================
# IMPORT FUNCTIONS
# ============================================================================

@reports_bp.route('/import/students', methods=['GET', 'POST'])
@login_required
def import_students():
    """Import students from Excel or CSV, optionally enrolling into a class arm."""
    from models import ClassArmAssignment, SchoolClass, ClassArm

    def _fail(msg):
        if _wants_json():
            return jsonify({'ok': False, 'error': msg}), 400
        flash(msg, 'error')
        return redirect(url_for('reports.import_students'))

    if request.method == 'POST':
        file = request.files.get('file')
        if not file or file.filename == '':
            return _fail('No file selected.')
        if not file.filename.lower().endswith(('.xlsx', '.xls', '.csv')):
            return _fail('Please upload a .xlsx or .csv file.')
        # Soft plan cap: block an upload import when a tiered tenant is already
        # over its student limit (payments and existing students are unaffected).
        from utils.entitlements import creation_cap_check
        _cap = creation_cap_check('students')
        if _cap and _cap['over']:
            return _fail(f"You've reached your {_cap['tier_label']} plan limit of "
                         f"{_cap['cap']} students. Existing students and payments "
                         f"are unaffected — upgrade your subscription to import more.")

        try:
            from utils.branch_scope import branch_for_new
            from utils.helpers import get_active_term
            from utils.excel_utils import import_students_from_upload

            # Optional: enrol all imported students into a chosen class + arm.
            assignment_id = None
            class_id = request.form.get('class_id', type=int)
            arm_id = request.form.get('arm_id', type=int)
            if class_id and not arm_id:
                arm_id = ClassArm.default().id          # arm-less school
            if class_id and arm_id:
                term = get_active_term()
                if not term:
                    flash('No active term set — students imported without a class.', 'warning')
                else:
                    # The (class, arm, term) combo is unique; reuse it if class
                    # management already created it, otherwise make it now.
                    assignment = ClassArmAssignment.query.filter_by(
                        class_id=class_id, arm_id=arm_id, term_id=term.id).first()
                    if not assignment:
                        assignment = ClassArmAssignment(
                            class_id=class_id, arm_id=arm_id, term_id=term.id,
                            branch_id=branch_for_new())
                        db.session.add(assignment)
                        db.session.commit()
                    assignment_id = assignment.id

            success_count, errors = import_students_from_upload(
                file,
                db,
                Student,
                ParentContact,
                branch_id=branch_for_new(),
                class_arm_assignment_id=assignment_id,
            )
            if success_count:
                from utils import query_cache
                query_cache.bump('dash')      # student count changed

            if _wants_json():
                msg = f'Successfully imported {success_count} student(s).' if success_count else 'No students imported.'
                return jsonify({'ok': True, 'message': msg, 'imported': success_count,
                                'warnings': errors[:8], 'more': max(0, len(errors) - 8)})
            if success_count > 0:
                flash(f'Successfully imported {success_count} students!', 'success')
            if errors:
                for error in errors[:5]:  # Show first 5 errors
                    flash(error, 'warning')
                if len(errors) > 5:
                    flash(f'... and {len(errors) - 5} more errors', 'warning')

        except Exception as e:
            return _fail(f'Error importing file: {str(e)}')

        return redirect(url_for('reports.import_students'))

    classes = SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.level).all()
    arms = ClassArm.query.filter_by(is_active=True, is_default=False).order_by(ClassArm.name).all()
    return _render({
        'page': 'import',
        'classes': [{'id': c.id, 'name': c.name} for c in classes],
        'arms': [{'id': a.id, 'name': a.name} for a in arms],
        'upload_url': url_for('reports.import_students'),
        'template_url': url_for('reports.export_template'),
    })


# ============================================================================
# CHARTS DATA API
# ============================================================================

@reports_bp.route('/api/charts/gender-distribution')
@login_required
def api_gender_distribution():
    """Get gender distribution data for charts"""
    male_count = scope_query(Student.query.filter_by(is_active=True, gender='Male'), Student).count()
    female_count = scope_query(Student.query.filter_by(is_active=True, gender='Female'), Student).count()
    
    return jsonify({
        'labels': ['Male', 'Female'],
        'data': [male_count, female_count],
        'backgroundColor': ['#4CAF50', '#E91E63']
    })


@reports_bp.route('/api/charts/religion-distribution')
@login_required
def api_religion_distribution():
    """Get religion distribution data for charts"""
    from sqlalchemy import func
    
    _rq = db.session.query(
        Student.religion,
        func.count(Student.id)
    ).filter(
        Student.is_active == True,
        Student.religion != None
    )
    _bid = viewing_branch_id()
    if _bid is not None:
        _rq = _rq.filter(Student.branch_id == _bid)
    distribution = _rq.group_by(Student.religion).all()
    
    labels = [d[0] or 'Not Specified' for d in distribution]
    data = [d[1] for d in distribution]
    
    colors = ['#2196F3', '#4CAF50', '#FFC107', '#9C27B0', '#FF5722']
    
    return jsonify({
        'labels': labels,
        'data': data,
        'backgroundColor': colors[:len(labels)]
    })


@reports_bp.route('/api/charts/enrollment-by-class')
@login_required
def api_enrollment_by_class():
    """Get enrollment distribution by class"""
    from models import ClassArmAssignment, StudentEnrollment, SchoolClass
    
    active_term = get_active_term()
    
    if not active_term:
        return jsonify({'labels': [], 'data': []})
    
    # Get enrollment counts by class
    from sqlalchemy import func
    
    _enq = db.session.query(
        SchoolClass.name,
        func.count(StudentEnrollment.id)
    ).join(
        ClassArmAssignment,
        ClassArmAssignment.class_id == SchoolClass.id
    ).join(
        StudentEnrollment,
        StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id
    ).filter(
        ClassArmAssignment.term_id == active_term.id,
        StudentEnrollment.is_active == True
    )
    _bid = viewing_branch_id()
    if _bid is not None:
        _enq = _enq.filter(ClassArmAssignment.branch_id == _bid)
    enrollments = _enq.group_by(SchoolClass.name).order_by(SchoolClass.level).all()
    
    return jsonify({
        'labels': [e[0] for e in enrollments],
        'data': [e[1] for e in enrollments],
        'backgroundColor': '#2196F3'
    })


@reports_bp.route('/api/charts/attendance-trend')
@login_required
def api_attendance_trend():
    """Get attendance trend data"""
    from models import Attendance, Week
    from sqlalchemy import func
    
    active_term = get_active_term()
    
    if not active_term:
        return jsonify({'labels': [], 'data': []})
    
    weeks = Week.query.filter_by(term_id=active_term.id).order_by(Week.week_number).all()
    
    from sqlalchemy import case
    weekly_data = []
    for week in weeks:
        # Get total attendance for this week (morning + afternoon ticks)
        attendance = db.session.query(
            func.sum(
                case((Attendance.morning_present == True, 1), else_=0)
                + case((Attendance.afternoon_present == True, 1), else_=0)
            )
        ).filter(Attendance.week_id == week.id).scalar() or 0
        
        weekly_data.append({
            'week': f'Week {week.week_number}',
            'attendance': attendance
        })
    
    return jsonify({
        'labels': [w['week'] for w in weekly_data],
        'data': [w['attendance'] for w in weekly_data],
        'borderColor': '#4CAF50',
        'backgroundColor': 'rgba(76, 175, 80, 0.1)'
    })


@reports_bp.route('/api/charts/waec-grade-distribution')
@login_required
def api_waec_grade_distribution():
    """Get WAEC grade distribution"""
    from models import WAECResult
    from sqlalchemy import func
    from utils.helpers import WAEC_GRADES
    
    year = request.args.get('year', type=int)
    
    query = scope_by_student(db.session.query(
        WAECResult.grade,
        func.count(WAECResult.id)
    ), WAECResult)

    if year:
        query = query.filter(WAECResult.exam_year == year)

    distribution = query.group_by(WAECResult.grade).all()
    
    grade_counts = {g: 0 for g in WAEC_GRADES}
    for grade, count in distribution:
        if grade in grade_counts:
            grade_counts[grade] = count
    
    colors = {
        'A1': '#4CAF50', 'B2': '#8BC34A', 'B3': '#CDDC39',
        'C4': '#FFEB3B', 'C5': '#FFC107', 'C6': '#FF9800',
        'D7': '#FF5722', 'E8': '#F44336', 'F9': '#B71C1C'
    }
    
    return jsonify({
        'labels': WAEC_GRADES,
        'data': [grade_counts[g] for g in WAEC_GRADES],
        'backgroundColor': [colors[g] for g in WAEC_GRADES]
    })


@reports_bp.route('/api/charts/jamb-score-distribution')
@login_required
def api_jamb_score_distribution():
    """Get JAMB score distribution"""
    from models import JAMBResult
    
    year = request.args.get('year', type=int)
    
    query = scope_by_student(JAMBResult.query, JAMBResult)
    if year:
        query = query.filter_by(exam_year=year)
    
    results = query.all()
    
    if not results:
        return jsonify({'labels': [], 'data': []})
    
    ranges = [
        ('0-100', 0, 100),
        ('101-150', 101, 150),
        ('151-200', 151, 200),
        ('201-250', 201, 250),
        ('251-300', 251, 300),
        ('301-350', 301, 350),
        ('351-400', 351, 400)
    ]
    
    distribution = []
    for label, low, high in ranges:
        count = sum(1 for r in results if low <= r.total_score <= high)
        distribution.append({'range': label, 'count': count})
    
    return jsonify({
        'labels': [d['range'] for d in distribution],
        'data': [d['count'] for d in distribution],
        'backgroundColor': '#2196F3'
    })


# ============================================================================
# SUMMARY REPORTS
# ============================================================================

@reports_bp.route('/summary')
@login_required
def summary_report():
    """School at a glance: students, attendance, fees, results, staff, library,
    events and communication for the active term — each block only for people
    who can open that part of the app, and each computed independently so one
    failing section never blanks the page."""
    from flask import current_app
    from utils.access_control import can_access_module
    active_session = get_active_session()
    term = get_active_term()
    out = {'page': 'summary',
           'session': active_session.name if active_session else '',
           'term': term.name if term else '', 'term_id': term.id if term else None,
           'blocks': {}, 'links': {}}

    def block(key, module, fn):
        if module and not can_access_module(module):
            return
        try:
            out['blocks'][key] = fn()
        except Exception:
            db.session.rollback()
            current_app.logger.exception('summary block %s failed', key)

    block('students', 'students', lambda: _sum_students(term))
    block('attendance', 'attendance', lambda: _sum_attendance(term))
    block('finance', 'finance', lambda: _sum_finance(term))
    block('results', 'external_exams', _sum_results)
    block('staff', 'hr', _sum_staff)
    block('library', 'library', _sum_library)
    block('events', 'events', _sum_events)
    block('comms', 'communication', _sum_comms)

    def _u(ep, **kw):
        try:
            return url_for(ep, **kw)
        except Exception:
            return None
    out['links'] = {k: v for k, v in {
        'students': _u('main.students_list'), 'attendance': _u('attendance.index'),
        'finance': _u('finance.dashboard'), 'defaulters': _u('finance.defaulters'),
        'waec': _u('results.waec_list'), 'jamb': _u('results.jamb_list'),
        'staff': _u('hr.dashboard'), 'library': _u('library.dashboard'),
        'overdue': _u('library.loans', status='Overdue'), 'events': _u('events.calendar'),
        'comms': _u('comms.dashboard'), 'contacts_missing': _u('comms.contacts', missing=1),
        'export_students': _u('reports.export_students'), 'export_class': _u('reports.export_class_students'),
        'import': _u('reports.import_students'), 'index': _u('reports.index'),
    }.items() if v}
    return _render(out)


def _sum_students(term):
    from models import ClassArmAssignment, StudentEnrollment, SchoolClass
    base = scope_query(Student.current_query(), Student)
    total = base.count()
    male = base.filter(Student.gender == 'Male').count()
    female = base.filter(Student.gender == 'Female').count()
    by_class, enrolled = [], 0
    if term:
        q = (db.session.query(SchoolClass.name, Student.gender, func.count(StudentEnrollment.id))
             .join(ClassArmAssignment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
             .join(SchoolClass, ClassArmAssignment.class_id == SchoolClass.id)
             .join(Student, StudentEnrollment.student_id == Student.id)
             .filter(ClassArmAssignment.term_id == term.id, StudentEnrollment.is_active.is_(True)))
        bid = viewing_branch_id()
        if bid is not None:
            q = q.filter(ClassArmAssignment.branch_id == bid)
        agg = {}
        order = {c.name: (getattr(c, 'level', None) or 0, c.id) for c in SchoolClass.query.all()}
        for name, g, n in q.group_by(SchoolClass.name, Student.gender).all():
            r = agg.setdefault(name, {'name': name, 'total': 0, 'male': 0, 'female': 0})
            r['total'] += n
            if g == 'Male':
                r['male'] += n
            elif g == 'Female':
                r['female'] += n
        by_class = sorted(agg.values(), key=lambda r: order.get(r['name'], (0, 0)))
        enrolled = sum(r['total'] for r in by_class)
    new_term = 0
    if term and term.start_date and hasattr(Student, 'created_at'):
        from datetime import datetime as _dt, time as _t
        new_term = base.filter(Student.created_at >= _dt.combine(term.start_date, _t.min)).count()
    return {'total': total, 'male': male, 'female': female, 'enrolled': enrolled,
            'not_enrolled': max(total - enrolled, 0), 'new_term': new_term, 'by_class': by_class}


def _sum_attendance(term):
    from models import Attendance, ClassArmAssignment, StudentEnrollment, SchoolClass, Week
    from utils import timeutil

    def scoped(q):
        q = (q.join(StudentEnrollment, Attendance.enrollment_id == StudentEnrollment.id)
              .join(ClassArmAssignment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id))
        bid = viewing_branch_id()
        if bid is not None:
            q = q.filter(ClassArmAssignment.branch_id == bid)
        return q
    pres = func.sum(db.case((Attendance.morning_present.is_(True), 1), else_=0)) \
        + func.sum(db.case((Attendance.afternoon_present.is_(True), 1), else_=0))

    def rate(q):
        p, n = q.with_entities(pres, func.count(Attendance.id)).one()
        return (round((p or 0) / (n * 2) * 100, 1) if n else None), n
    today = timeutil.today()
    today_rate, today_n = rate(scoped(db.session.query(Attendance)).filter(Attendance.date == today))
    if not term:
        return {'today_rate': today_rate, 'today_marked': today_n}
    tq = scoped(db.session.query(Attendance)).filter(ClassArmAssignment.term_id == term.id)
    term_rate, term_n = rate(tq)
    weekly = []
    for wk, p, n in (tq.join(Week, Attendance.week_id == Week.id)
                     .with_entities(Week.week_number, pres, func.count(Attendance.id))
                     .group_by(Week.week_number).order_by(Week.week_number).all()):
        if n:
            weekly.append({'label': f'Wk {wk}', 'rate': round((p or 0) / (n * 2) * 100, 1)})
    classes = []
    for name, p, n in (tq.join(SchoolClass, ClassArmAssignment.class_id == SchoolClass.id)
                       .with_entities(SchoolClass.name, pres, func.count(Attendance.id))
                       .group_by(SchoolClass.name).all()):
        if n:
            classes.append({'name': name, 'rate': round((p or 0) / (n * 2) * 100, 1)})
    classes.sort(key=lambda c: c['rate'])
    return {'term_rate': term_rate, 'term_records': term_n, 'today_rate': today_rate, 'today_marked': today_n,
            'weekly': weekly[-10:], 'low_classes': classes[:4], 'high_classes': classes[::-1][:2]}


def _sum_finance(term):
    if not term:
        return None
    from routes.finance import _term_fee_summary, _term_expense_summary
    from utils.finance import defaulters_summary
    fees = _term_fee_summary(term.id)
    exp = _term_expense_summary(term.id)
    payable = max(fees['expected'] - fees['discounts'], 0)
    collected = fees['collected']
    dflt = defaulters_summary(term.id)
    return {'payable': round(payable, 2), 'collected': round(collected, 2),
            'outstanding': round(max(payable - collected, 0), 2),
            'rate': round(collected / payable * 100, 1) if payable else None,
            'expenses': round(exp['expenses'], 2), 'net': round(collected - exp['expenses'], 2),
            'defaulters': dflt.get('count', 0), 'owed': round(dflt.get('balance', 0) or 0, 2)}


def _sum_results():
    from models import WAECResult, JAMBResult
    out = {'with_waec': scope_by_student(db.session.query(WAECResult.student_id), WAECResult).distinct().count(),
           'with_jamb': scope_by_student(db.session.query(JAMBResult.student_id), JAMBResult).distinct().count()}
    # The latest sitting with a real cohort (a stray early entry for next year
    # shouldn't hide this year's results).
    yrs = (scope_by_student(db.session.query(WAECResult.exam_year, func.count(func.distinct(WAECResult.student_id))), WAECResult)
           .group_by(WAECResult.exam_year).order_by(WAECResult.exam_year.desc()).all())
    yr = next((y for y, n in yrs if n >= 5), yrs[0][0] if yrs else None)
    if yr:
        rows = scope_by_student(db.session.query(WAECResult.student_id, WAECResult.subject, WAECResult.grade)
                                .filter(WAECResult.exam_year == yr), WAECResult).all()
        credit = {'A1', 'B2', 'B3', 'C4', 'C5', 'C6'}
        per = {}
        for sid, subj, g in rows:
            st = per.setdefault(sid, {'credits': 0, 'eng': False, 'maths': False})
            if g in credit:
                st['credits'] += 1
                sl = (subj or '').lower()
                if 'english' in sl:
                    st['eng'] = True
                if 'math' in sl:
                    st['maths'] = True
        n = len(per)
        five = sum(1 for v in per.values() if v['credits'] >= 5 and v['eng'] and v['maths'])
        out.update({'waec_year': yr, 'waec_candidates': n,
                    'waec_five_credits': five, 'waec_five_rate': round(five / n * 100, 1) if n else None,
                    'waec_credit_rate': round(sum(1 for _s, _j, g in rows if g in credit) / len(rows) * 100, 1) if rows else None})
    jyr = db.session.query(func.max(JAMBResult.exam_year)).scalar()
    if jyr:
        tot = [t for (t,) in scope_by_student(db.session.query(JAMBResult.total_score)
                                              .filter(JAMBResult.exam_year == jyr), JAMBResult).all() if t is not None]
        if tot:
            out.update({'jamb_year': jyr, 'jamb_candidates': len(tot), 'jamb_avg': round(sum(tot) / len(tot), 1),
                        'jamb_200': sum(1 for t in tot if t >= 200)})
    return out


def _sum_staff():
    from models import StaffMember, StaffAttendance
    from utils import timeutil
    base = scope_query(StaffMember.query.filter(StaffMember.status == 'Active'), StaffMember)
    total = base.count()
    teaching = base.filter(StaffMember.staff_type == 'Teaching').count()
    today = timeutil.today()
    ids = [i for (i,) in base.with_entities(StaffMember.id).all()]
    att = (db.session.query(StaffAttendance.status, func.count(StaffAttendance.id))
           .filter(StaffAttendance.date == today, StaffAttendance.staff_id.in_(ids or [0]))
           .group_by(StaffAttendance.status).all())
    by = {k: n for k, n in att}
    return {'total': total, 'teaching': teaching, 'non_teaching': total - teaching,
            'present_today': by.get('Present', 0) + by.get('Late', 0), 'late_today': by.get('Late', 0),
            'absent_today': by.get('Absent', 0), 'marked_today': sum(by.values())}


def _sum_library():
    from models import Book, BookLoan
    from utils import timeutil
    books = scope_query(Book.query.filter_by(is_active=True), Book)
    loans = scope_query(BookLoan.query.join(Book, BookLoan.book_id == Book.id), Book)
    return {'titles': books.count(),
            'copies': int(scope_query(db.session.query(func.coalesce(func.sum(Book.copies_total), 0)), Book).scalar() or 0),
            'on_loan': loans.filter(BookLoan.status == 'Borrowed').count(),
            'overdue': loans.filter(BookLoan.status == 'Borrowed', BookLoan.due_date < timeutil.today()).count()}


def _sum_events():
    from models import SchoolEvent
    from utils import timeutil
    today = timeutil.today()
    rows = (SchoolEvent.query.filter(db.func.coalesce(SchoolEvent.end_date, SchoolEvent.start_date) >= today)
            .order_by(SchoolEvent.start_date).limit(5).all())
    return {'upcoming': [{'title': e.title, 'category': e.category, 'color': e.color,
                          'date': e.start_date.isoformat(), 'end': e.end_date.isoformat() if e.end_date else '',
                          'time': e.start_time if (e.start_time and not e.all_day) else ''} for e in rows]}


def _sum_comms():
    from models import Message, MessageRecipient
    from utils import comms
    cov = comms.coverage_stats()
    sent = (scope_query(db.session.query(func.count(MessageRecipient.id))
                        .join(Message, MessageRecipient.message_id == Message.id), Message)
            .filter(MessageRecipient.status == 'Sent').scalar() or 0)
    return {'coverage': cov.get('pct', 0), 'without_contact': cov.get('without_contact', 0),
            'campaigns': scope_query(Message.query, Message).count(), 'delivered': int(sent)}
