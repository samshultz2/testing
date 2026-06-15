"""
Timetable Management routes
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from utils.helpers import get_active_term
from models import (
    db, TimetableSlot, ClassTimetable, ClassArmAssignment, Subject,
    Term, ClassSubject
)
from utils.helpers import login_required
from utils.branch_scope import require_branch_access

timetable_bp = Blueprint('timetable', __name__, url_prefix='/timetable')

DAYS_OF_WEEK = [
    (0, 'Monday'),
    (1, 'Tuesday'),
    (2, 'Wednesday'),
    (3, 'Thursday'),
    (4, 'Friday')
]


@timetable_bp.route('/designer')
@login_required
def designer():
    """Stand-alone designer for special, one-off timetables (Saturday classes,
    holiday lessons, exams, or a blank custom grid). Everything is entered and
    rendered in the browser and printed/saved as PDF — nothing is stored."""
    from models import SchoolSettings
    school_name = SchoolSettings.get('school_name', '') or ''
    subjects = [s.name for s in
                Subject.query.filter_by(is_active=True).order_by(Subject.name).all()]
    return render_template('timetable/designer.html',
                           school_name=school_name, subjects=subjects)


@timetable_bp.route('/backups')
@login_required
def backups():
    """List timetable backups so a previous (e.g. replaced) timetable can be
    restored."""
    from models import TimetableBackup
    term_id = request.args.get('term_id', type=int)
    if not term_id:
        active = get_active_term()
        term_id = active.id if active else None
    terms = Term.query.order_by(Term.id.desc()).all()
    q = TimetableBackup.query
    if term_id:
        q = q.filter_by(term_id=term_id)
    backups = q.order_by(TimetableBackup.created_at.desc()).all()
    selected_term = Term.query.get(term_id) if term_id else None
    return render_template('timetable/backups.html', backups=backups, terms=terms,
                           selected_term=selected_term, term_id=term_id)


@timetable_bp.route('/backups/create', methods=['POST'])
@login_required
def create_backup():
    """Manually snapshot the current timetable for a term."""
    from utils.timetable_backup import snapshot_term
    term_id = request.form.get('term_id', type=int)
    active = get_active_term()
    term_id = term_id or (active.id if active else None)
    if not term_id:
        flash('Pick a term to back up.', 'error')
        return redirect(url_for('timetable.backups'))
    label = (request.form.get('label') or '').strip() or 'Manual backup'
    backup = snapshot_term(term_id, label, skip_if_empty=False)
    db.session.commit()
    flash(f'Backed up {backup.entry_count} timetable entr(y/ies).', 'success')
    return redirect(url_for('timetable.backups', term_id=term_id))


@timetable_bp.route('/backups/<int:backup_id>/restore', methods=['POST'])
@login_required
def restore_backup_route(backup_id):
    """Restore a backup. The current timetable is itself backed up first, so the
    restore can be undone."""
    from models import TimetableBackup
    from utils.timetable_backup import snapshot_term, restore_backup
    backup = db.get_or_404(TimetableBackup, backup_id)
    if backup.term_id:
        snapshot_term(backup.term_id,
                      f'Auto-backup before restoring "{backup.label}"')
    n = restore_backup(backup)
    db.session.commit()
    flash(f'Restored {n} timetable entr(y/ies) from "{backup.label}".', 'success')
    return redirect(url_for('timetable.backups', term_id=backup.term_id))


@timetable_bp.route('/backups/<int:backup_id>/delete', methods=['POST'])
@login_required
def delete_backup(backup_id):
    from models import TimetableBackup
    backup = db.get_or_404(TimetableBackup, backup_id)
    term_id = backup.term_id
    db.session.delete(backup)
    db.session.commit()
    flash('Backup deleted.', 'success')
    return redirect(url_for('timetable.backups', term_id=term_id))


@timetable_bp.route('/')
@login_required
def index():
    """Timetable main page - select class to view/edit"""
    term_id = request.args.get('term_id', type=int)
    assignment_id = request.args.get('assignment_id', type=int)
    
    terms = Term.query.order_by(Term.id.desc()).all()
    
    # Get active term if not specified
    if not term_id:
        active_term = get_active_term()
        if active_term:
            term_id = active_term.id
    
    selected_term = Term.query.get(term_id) if term_id else None
    
    # Get class assignments for selected term (branch-scoped picker)
    from utils.branch_scope import scope_query, can_access_branch
    assignments = []
    if term_id:
        assignments = scope_query(
            ClassArmAssignment.query.filter_by(term_id=term_id), ClassArmAssignment).all()

    selected_assignment = ClassArmAssignment.query.get(assignment_id) if assignment_id else None
    if selected_assignment and not can_access_branch(selected_assignment.branch_id):
        selected_assignment = None   # no peeking at another branch's timetable by id
    
    # Get timetable slots
    slots = TimetableSlot.query.filter_by(is_active=True).order_by(TimetableSlot.order).all()
    
    # Build timetable grid
    timetable_grid = {}
    subjects_for_class = []
    
    if selected_assignment and slots:
        # Get subjects available for this class
        subjects_for_class = ClassSubject.query.filter_by(
            term_id=term_id,
            class_id=selected_assignment.class_id,
            is_active=True
        ).filter(
            (ClassSubject.arm_id == None) | (ClassSubject.arm_id == selected_assignment.arm_id)
        ).join(Subject).order_by(Subject.name).all()
        
        # Get existing timetable entries
        entries = ClassTimetable.query.filter_by(
            class_arm_assignment_id=assignment_id,
            is_active=True
        ).all()
        
        # Build grid: {day: {slot_id: entry}}
        for day_num, day_name in DAYS_OF_WEEK:
            timetable_grid[day_num] = {}
            for slot in slots:
                timetable_grid[day_num][slot.id] = None
        
        for entry in entries:
            if entry.day_of_week in timetable_grid and entry.slot_id in timetable_grid[entry.day_of_week]:
                timetable_grid[entry.day_of_week][entry.slot_id] = entry
    
    return render_template('timetable/index.html',
        terms=terms, term_id=term_id, selected_term=selected_term,
        assignments=assignments, assignment_id=assignment_id, selected_assignment=selected_assignment,
        slots=slots, days=DAYS_OF_WEEK, timetable_grid=timetable_grid,
        subjects_for_class=subjects_for_class
    )


@timetable_bp.route('/edit/<int:assignment_id>')
@login_required
def edit_timetable(assignment_id):
    """Edit timetable for a class"""
    assignment = ClassArmAssignment.query.get_or_404(assignment_id)
    require_branch_access(assignment.branch_id)   # no cross-branch timetables

    slots = TimetableSlot.query.filter_by(is_active=True).order_by(TimetableSlot.order).all()

    # Get subjects for this class
    subjects = ClassSubject.query.filter_by(
        term_id=assignment.term_id,
        class_id=assignment.class_id,
        is_active=True
    ).filter(
        (ClassSubject.arm_id == None) | (ClassSubject.arm_id == assignment.arm_id)
    ).join(Subject).order_by(Subject.name).all()
    
    # Get existing entries
    entries = ClassTimetable.query.filter_by(
        class_arm_assignment_id=assignment_id,
        is_active=True
    ).all()
    
    # Build lookup: {(day, slot_id): entry}
    entries_lookup = {(e.day_of_week, e.slot_id): e for e in entries}
    
    return render_template('timetable/edit.html',
        assignment=assignment, slots=slots, days=DAYS_OF_WEEK,
        subjects=subjects, entries_lookup=entries_lookup
    )


@timetable_bp.route('/save/<int:assignment_id>', methods=['POST'])
@login_required
def save_timetable(assignment_id):
    """Save timetable entries"""
    assignment = ClassArmAssignment.query.get_or_404(assignment_id)
    require_branch_access(assignment.branch_id)   # no cross-branch writes

    try:
        slots = TimetableSlot.query.filter_by(is_active=True).all()
        
        for day_num, day_name in DAYS_OF_WEEK:
            for slot in slots:
                if slot.is_break:
                    continue
                
                field_name = f'entry_{day_num}_{slot.id}'
                subject_id = request.form.get(field_name)
                teacher_name = request.form.get(f'teacher_{day_num}_{slot.id}', '').strip()
                
                # Get or create entry
                entry = ClassTimetable.query.filter_by(
                    class_arm_assignment_id=assignment_id,
                    slot_id=slot.id,
                    day_of_week=day_num
                ).first()
                
                if subject_id:
                    if entry:
                        entry.subject_id = int(subject_id)
                        entry.teacher_name = teacher_name or None
                        entry.is_active = True
                    else:
                        entry = ClassTimetable(
                            class_arm_assignment_id=assignment_id,
                            slot_id=slot.id,
                            day_of_week=day_num,
                            subject_id=int(subject_id),
                            teacher_name=teacher_name or None
                        )
                        db.session.add(entry)
                else:
                    # Clear entry if no subject selected
                    if entry:
                        entry.is_active = False
        
        db.session.commit()
        flash('Timetable saved!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('timetable.index', 
        term_id=assignment.term_id, assignment_id=assignment_id))


@timetable_bp.route('/copy', methods=['POST'])
@login_required
def copy_timetable():
    """Copy timetable from one class to another"""
    try:
        from_assignment_id = request.form.get('from_assignment_id', type=int)
        to_assignment_id = request.form.get('to_assignment_id', type=int)
        
        if not from_assignment_id or not to_assignment_id:
            flash('Select both source and destination classes.', 'error')
            return redirect(url_for('timetable.index'))
        
        from_assignment = ClassArmAssignment.query.get(from_assignment_id)
        to_assignment = ClassArmAssignment.query.get(to_assignment_id)
        
        if not from_assignment or not to_assignment:
            flash('Invalid class selection.', 'error')
            return redirect(url_for('timetable.index'))
        require_branch_access(from_assignment.branch_id)   # no cross-branch copy
        require_branch_access(to_assignment.branch_id)

        # Get source entries
        source_entries = ClassTimetable.query.filter_by(
            class_arm_assignment_id=from_assignment_id,
            is_active=True
        ).all()
        
        # Clear destination entries
        ClassTimetable.query.filter_by(
            class_arm_assignment_id=to_assignment_id
        ).update({ClassTimetable.is_active: False})
        
        # Copy entries
        copied = 0
        for entry in source_entries:
            new_entry = ClassTimetable(
                class_arm_assignment_id=to_assignment_id,
                slot_id=entry.slot_id,
                day_of_week=entry.day_of_week,
                subject_id=entry.subject_id,
                teacher_name=entry.teacher_name
            )
            db.session.add(new_entry)
            copied += 1
        
        db.session.commit()
        flash(f'Copied {copied} entries to {to_assignment.display_name}!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('timetable.index', 
        term_id=to_assignment.term_id, assignment_id=to_assignment_id))


@timetable_bp.route('/print/<int:assignment_id>')
@login_required
def print_timetable(assignment_id):
    """Generate the per-class timetable as a horizontal PDF (days as rows, time
    periods as columns) with ReportLab. Teacher names are excluded by default;
    pass ?teachers=1 to include them."""
    from io import BytesIO
    from flask import send_file
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from models import SchoolSettings

    assignment = ClassArmAssignment.query.get_or_404(assignment_id)
    require_branch_access(assignment.branch_id)   # no cross-branch timetable PDF
    include_teachers = request.args.get('teachers') == '1'

    slots = TimetableSlot.query.filter_by(is_active=True).order_by(TimetableSlot.order).all()
    entries = ClassTimetable.query.filter_by(
        class_arm_assignment_id=assignment_id, is_active=True).all()
    # grid[(day, slot_id)] = entry
    grid = {(e.day_of_week, e.slot_id): e for e in entries}

    def hhmm(t):
        return t.strftime('%-H:%M') if t else ''

    cell = ParagraphStyle('cell', fontName='Helvetica', fontSize=12,
                          alignment=TA_CENTER, leading=13)
    cell_b = ParagraphStyle('cellb', parent=cell, fontName='Helvetica-Bold')
    head = ParagraphStyle('head', parent=cell_b, fontSize=11, leading=12,
                          textColor=colors.white)
    # One huge bold capital letter per cell, used to spell BREAK down a column.
    brk = ParagraphStyle('brk', fontName='Helvetica-Bold', fontSize=42,
                         leading=44, alignment=TA_CENTER,
                         textColor=colors.HexColor('#9a3412'))

    days = list(DAYS_OF_WEEK)
    n_days = len(days)
    BREAK_WORD = 'BREAK'

    def break_letter(row_idx):
        """Letter of BREAK for body row ``row_idx`` (spread top→bottom)."""
        if n_days == len(BREAK_WORD):
            return BREAK_WORD[row_idx]
        # distribute as evenly as possible if there aren't exactly 5 day rows
        pos = int(round(row_idx * (len(BREAK_WORD) - 1) / max(n_days - 1, 1)))
        return BREAK_WORD[pos] if 0 <= row_idx < n_days else ''

    # Header row: Day + each slot. Break columns get a blank header (the column
    # itself spells BREAK), teaching columns show name + time range.
    header = [Paragraph('Day', head)]
    for s in slots:
        if s.is_break:
            header.append(Paragraph('', head))
            continue
        label = f'{s.name}'
        if s.start_time and s.end_time:
            label += f'<br/>{hhmm(s.start_time)}–{hhmm(s.end_time)}'
        header.append(Paragraph(label, head))

    table_data = [header]
    break_cols = [i + 1 for i, s in enumerate(slots) if s.is_break]
    for r, (day_num, day_name) in enumerate(days):
        row = [Paragraph(day_name, cell_b)]
        for s in slots:
            if s.is_break:
                row.append(Paragraph(break_letter(r), brk))
                continue
            e = grid.get((day_num, s.id))
            if not e or not e.subject:
                row.append(Paragraph('', cell))
                continue
            txt = e.subject.short_name or e.subject.name
            if include_teachers and e.teacher_name:
                txt += f'<br/><font size=9 color="#555555">{e.teacher_name}</font>'
            row.append(Paragraph(txt, cell_b))
        table_data.append(row)

    # ---- size everything to fill the A4 page with tiny margins ----
    page_w, page_h = landscape(A4)
    m_side, m_top, m_bottom = 6 * mm, 7 * mm, 6 * mm
    content_w = page_w - 2 * m_side
    content_h = page_h - m_top - m_bottom

    n_break = len(break_cols)
    n_teach = len(slots) - n_break
    day_w = 28 * mm
    break_w = 13 * mm
    teach_w = (content_w - day_w - n_break * break_w) / max(n_teach, 1)
    col_widths = [day_w] + [(break_w if s.is_break else teach_w) for s in slots]

    header_reserve = 56            # space for school/class/term block
    header_row_h = 26
    body_row_h = (content_h - header_reserve - header_row_h) / max(n_days, 1)
    row_heights = [header_row_h] + [body_row_h] * n_days

    style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f766e')),
        ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#e2e8f0')),
        ('GRID', (0, 0), (-1, -1), 0.75, colors.HexColor('#475569')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
    ]
    for c in break_cols:
        style.append(('BACKGROUND', (c, 0), (c, -1), colors.HexColor('#ffedd5')))

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=m_side, rightMargin=m_side,
                            topMargin=m_top, bottomMargin=m_bottom)
    title_style = ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=14,
                                 alignment=TA_CENTER, leading=16)
    sub_style = ParagraphStyle('sub', fontName='Helvetica', fontSize=9,
                               alignment=TA_CENTER, leading=11,
                               textColor=colors.HexColor('#475569'))
    school = SchoolSettings.get('school_name', '') or ''
    term = assignment.term.full_name if assignment.term else ''
    elems = []
    if school:
        elems.append(Paragraph(school, title_style))
    sub = f'{assignment.display_name} — Class Timetable'
    if term:
        sub += f' &nbsp;•&nbsp; {term}'
    elems.append(Paragraph(sub, sub_style))
    elems.append(Spacer(1, 4))
    t = Table(table_data, colWidths=col_widths, rowHeights=row_heights, repeatRows=1)
    t.setStyle(TableStyle(style))
    elems.append(t)
    doc.build(elems)
    buf.seek(0)

    suffix = 'with-teachers' if include_teachers else 'no-teachers'
    fname = f'timetable_{assignment.display_name.replace(" ", "_")}_{suffix}.pdf'
    return send_file(buf, mimetype='application/pdf', as_attachment=False,
                     download_name=fname)


# ============================================================================
# API ENDPOINTS
# ============================================================================

@timetable_bp.route('/api/entries/<int:assignment_id>')
@login_required
def api_get_entries(assignment_id):
    """Get timetable entries for a class"""
    require_branch_access(db.get_or_404(ClassArmAssignment, assignment_id).branch_id)
    entries = ClassTimetable.query.filter_by(
        class_arm_assignment_id=assignment_id,
        is_active=True
    ).all()
    
    return jsonify([{
        'id': e.id,
        'day': e.day_of_week,
        'day_name': e.day_name,
        'slot_id': e.slot_id,
        'slot_name': e.slot.name,
        'subject': e.subject.name if e.subject else None,
        'teacher': e.teacher_name
    } for e in entries])
