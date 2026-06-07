"""
Timetable Management routes
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import (
    db, TimetableSlot, ClassTimetable, ClassArmAssignment, Subject,
    Term, ClassSubject
)
from utils.helpers import login_required

timetable_bp = Blueprint('timetable', __name__, url_prefix='/timetable')

DAYS_OF_WEEK = [
    (0, 'Monday'),
    (1, 'Tuesday'),
    (2, 'Wednesday'),
    (3, 'Thursday'),
    (4, 'Friday')
]


@timetable_bp.route('/')
@login_required
def index():
    """Timetable main page - select class to view/edit"""
    term_id = request.args.get('term_id', type=int)
    assignment_id = request.args.get('assignment_id', type=int)
    
    terms = Term.query.order_by(Term.id.desc()).all()
    
    # Get active term if not specified
    if not term_id:
        active_term = Term.query.filter_by(is_active=True).first()
        if active_term:
            term_id = active_term.id
    
    selected_term = Term.query.get(term_id) if term_id else None
    
    # Get class assignments for selected term
    assignments = []
    if term_id:
        assignments = ClassArmAssignment.query.filter_by(term_id=term_id).all()
    
    selected_assignment = ClassArmAssignment.query.get(assignment_id) if assignment_id else None
    
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
    """Print-friendly timetable view"""
    assignment = ClassArmAssignment.query.get_or_404(assignment_id)
    
    slots = TimetableSlot.query.filter_by(is_active=True).order_by(TimetableSlot.order).all()
    
    entries = ClassTimetable.query.filter_by(
        class_arm_assignment_id=assignment_id,
        is_active=True
    ).all()
    
    # Build grid
    timetable_grid = {}
    for day_num, day_name in DAYS_OF_WEEK:
        timetable_grid[day_num] = {}
        for slot in slots:
            timetable_grid[day_num][slot.id] = None
    
    for entry in entries:
        if entry.day_of_week in timetable_grid:
            timetable_grid[entry.day_of_week][entry.slot_id] = entry
    
    return render_template('timetable/print.html',
        assignment=assignment, slots=slots, days=DAYS_OF_WEEK,
        timetable_grid=timetable_grid
    )


# ============================================================================
# API ENDPOINTS
# ============================================================================

@timetable_bp.route('/api/entries/<int:assignment_id>')
@login_required
def api_get_entries(assignment_id):
    """Get timetable entries for a class"""
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
