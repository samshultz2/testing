"""Exam Hall Allocator (Tools).

Admin tool that spreads exam candidates across halls to curb malpractice:
students from the same class + arm are scattered across as many halls as
possible, halls fill in proportion to capacity (a big Main hall holds more),
and each hall is gender-balanced where possible.
"""
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, session, Response, abort)
from models import db, Student, StudentEnrollment, ClassArmAssignment
from utils.helpers import get_active_term
from utils.branch_scope import scope_query, viewing_branch_id, can_access_branch
from utils.access_control import login_required, is_admin
from utils.exam_hall_allocator import allocate_halls

exam_halls_bp = Blueprint('exam_halls', __name__, url_prefix='/tools/exam-halls')


def _admin_only():
    if not is_admin():
        abort(403)


def _assignments_for_term():
    """Branch-scoped class-arm assignments for the active term, each with its
    active-student count (only those with students are worth showing)."""
    term = get_active_term()
    if not term:
        return []
    q = scope_query(ClassArmAssignment.query.filter_by(term_id=term.id), ClassArmAssignment)
    rows = []
    for a in q.all():
        count = StudentEnrollment.query.filter_by(
            class_arm_assignment_id=a.id, is_active=True).count()
        if count:
            rows.append({'id': a.id, 'label': a.display_name,
                         'class_name': a.school_class.name if a.school_class else '',
                         'arm': a.arm_label, 'count': count})
    rows.sort(key=lambda r: (r['class_name'], r['arm']))
    return rows


def _masthead():
    from utils.school import school_profile
    from models.models_branch import Branch
    sname = (school_profile() or {}).get('name') or ''
    bid = viewing_branch_id()
    if bid and bid not in (None, -1):
        b = db.session.get(Branch, bid)
        branch = b.name if b else ''
    else:
        branches = Branch.query.all()
        branch = branches[0].name if len(branches) == 1 else 'All Branches'
    term = get_active_term()
    return sname, branch, (term.full_name if term else '')


def _parse_halls(form):
    """Read the parallel hall_name[]/hall_capacity[] fields + the main-hall pick."""
    names = form.getlist('hall_name')
    caps = form.getlist('hall_capacity')
    main_idx = form.get('main_hall', type=int)
    halls = []
    for i, (nm, cap) in enumerate(zip(names, caps)):
        nm = (nm or '').strip()
        try:
            cap = int(cap)
        except (TypeError, ValueError):
            cap = 0
        if not nm and cap <= 0:
            continue
        halls.append({'name': nm or f'Hall {i + 1}', 'capacity': cap,
                      'is_main': (main_idx == i)})
    return halls


def _gather_groups(form):
    """Selected class-arm assignments -> allocator groups (branch/access checked)."""
    from utils.access_control import can_access_class
    ids = form.getlist('assignments', type=int)
    groups = []
    for aid in ids:
        a = db.session.get(ClassArmAssignment, aid)
        if not a or not can_access_class(aid):
            continue
        enrs = (StudentEnrollment.query.filter_by(class_arm_assignment_id=aid, is_active=True)
                .join(Student).order_by(Student.surname, Student.first_name).all())
        studs = []
        for e in enrs:
            s = e.student
            if not s:
                continue
            studs.append({'id': s.id, 'student_id': s.student_id, 'name': s.full_name,
                          'gender': s.gender, 'class_name': a.school_class.name if a.school_class else '',
                          'arm': a.arm_label})
        if studs:
            groups.append({'key': a.display_name, 'students': studs})
    return groups


@exam_halls_bp.route('/')
@login_required
def index():
    _admin_only()
    return render_template('exam_halls/index.html',
                           assignments=_assignments_for_term(),
                           has_term=bool(get_active_term()))


@exam_halls_bp.route('/allocate', methods=['POST'])
@login_required
def allocate():
    _admin_only()
    groups = _gather_groups(request.form)
    halls = _parse_halls(request.form)
    balance = request.form.get('balance_gender') == 'on'
    if not groups:
        flash('Select at least one class/arm that has students.', 'error')
        return redirect(url_for('exam_halls.index'))
    if not halls:
        flash('Add at least one hall with a capacity.', 'error')
        return redirect(url_for('exam_halls.index'))
    try:
        result = allocate_halls(groups, halls, balance_gender=balance)
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('exam_halls.index'))

    sname, branch, term = _masthead()
    # Preserve the submitted inputs so the PDF button can re-run identically.
    payload = {'assignments': request.form.getlist('assignments'),
               'hall_name': request.form.getlist('hall_name'),
               'hall_capacity': request.form.getlist('hall_capacity'),
               'main_hall': request.form.get('main_hall', ''),
               'balance_gender': 'on' if balance else ''}
    return render_template('exam_halls/result.html', result=result,
                           school_name=sname, branch=branch, term=term,
                           payload=payload)


@exam_halls_bp.route('/pdf', methods=['POST'])
@login_required
def pdf():
    _admin_only()
    groups = _gather_groups(request.form)
    halls = _parse_halls(request.form)
    balance = request.form.get('balance_gender') == 'on'
    try:
        result = allocate_halls(groups, halls, balance_gender=balance)
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('exam_halls.index'))
    sname, branch, term = _masthead()
    data = _build_pdf(result, sname, branch, term)
    return Response(data, mimetype='application/pdf', headers={
        'Content-Disposition': 'attachment; filename="exam_hall_allocation.pdf"'})


def _build_pdf(result, school_name, branch, term):
    """One A4 page per hall: masthead + hall/capacity + candidate list."""
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                    Spacer, PageBreak)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=14 * mm, bottomMargin=14 * mm,
                            leftMargin=14 * mm, rightMargin=14 * mm)
    ss = getSampleStyleSheet()
    h_school = ParagraphStyle('school', parent=ss['Title'], fontSize=16, spaceAfter=2,
                              textColor=colors.HexColor('#0f172a'))
    h_branch = ParagraphStyle('branch', parent=ss['Normal'], fontSize=11, alignment=1,
                              textColor=colors.HexColor('#334155'), spaceAfter=1)
    h_line = ParagraphStyle('line', parent=ss['Normal'], fontSize=11, alignment=1,
                            textColor=colors.HexColor('#007bff'), spaceAfter=1)
    h_hall = ParagraphStyle('hall', parent=ss['Normal'], fontSize=13, alignment=1,
                            spaceBefore=6, spaceAfter=8, textColor=colors.HexColor('#0f172a'))
    elems = []
    halls = [h for h in result['halls'] if h['count'] > 0] or result['halls']
    for hi, hall in enumerate(halls):
        if hi > 0:
            elems.append(PageBreak())
        if school_name:
            elems.append(Paragraph(school_name.upper(), h_school))
        if branch:
            elems.append(Paragraph(branch.upper(), h_branch))
        elems.append(Paragraph('EXAM HALL ALLOCATION' + (f' — {term}' if term else ''), h_line))
        g = hall['gender']
        elems.append(Paragraph(
            f"{hall['name'].upper()}  ·  {hall['count']}/{hall['capacity']} seats  ·  "
            f"{g['Female']}F / {g['Male']}M", h_hall))
        data = [['S/N', 'Student ID', 'Name', 'Class/Arm', 'Gender']]
        for i, s in enumerate(hall['students'], 1):
            arm = (s.get('class_name') or '') + (f" {s.get('arm')}" if s.get('arm') else '')
            data.append([str(i), s.get('student_id') or '', s.get('name') or '',
                         arm.strip(), s.get('gender') or ''])
        t = Table(data, colWidths=[13 * mm, 28 * mm, 72 * mm, 40 * mm, 22 * mm], repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#007bff')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (4, 0), (4, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f1f5f9')]),
            ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
        elems.append(t)
        elems.append(Spacer(1, 6))
    doc.build(elems)
    return buf.getvalue()
