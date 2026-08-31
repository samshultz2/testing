"""
Timetable Generator routes - Complete Version with all features
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response
from models import (
    db, GenSubject, GenTeacher, GenTeacherSubject, GenTeacherAvailability, GenSubjectConfig,
    GenClassSubjectConfig, GenClassStreamSubject, GenStream, GenStreamSubject, GenClassConfig, GenClassArmStream, GenRoom,
    GenTeacherAssignment, GenTimetableRule, GenTimetableResult, GenSettings,
    Subject
)
from utils.helpers import login_required
from utils.access_control import timetable_generate_required
from io import BytesIO
from datetime import datetime
from utils.web_exports import xlsx_response, pdf_response
import uuid

generator_bp = Blueprint('generator', __name__, url_prefix='/generator')

DAYS_OF_WEEK = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
SUBJECT_COLORS = [
    '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7',
    '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9'
]


# ============================================================================
# MAIN DASHBOARD - LEVEL SELECTOR
# ============================================================================







def get_current_level():
    """Get current school level from session"""
    from flask import session
    return session.get('generator_level', 'sss')


# ============================================================================
# TEACHERS
# ============================================================================

















# ============================================================================
# SUBJECT CONFIGURATION
# ============================================================================













# ============================================================================
# PER-CLASS SUBJECT CONFIGURATION
# ============================================================================











# ============================================================================
# ROOMS
# ============================================================================







# ============================================================================
# STREAMS
# ============================================================================













# ============================================================================
# CLASSES
# ============================================================================













# ============================================================================
# TEACHER ASSIGNMENTS
# ============================================================================







# ============================================================================
# RULES
# ============================================================================





# ============================================================================
# SETTINGS
# ============================================================================





# ============================================================================
# GENERATION
# ============================================================================







def generate_for_class(batch_id, cc, arm, periods_per_day, break_after, no_repeat, distribute, teacher_schedule):
    from random import shuffle
    conflicts = []
    
    # Get stream
    stream_id = None
    if cc.has_streams:
        cas = GenClassArmStream.query.filter_by(class_config_id=cc.id, arm_name=arm).first()
        if cas:
            stream_id = cas.stream_id
    
    # Get per-class subject configs (the "Takes" checkbox settings)
    class_configs = {c.subject_id: c for c in GenClassSubjectConfig.query.filter_by(
        class_config_id=cc.id, is_active=True
    ).all()}
    
    # Determine which subjects this class arm should take
    subjects = []
    
    if cc.has_streams and stream_id:
        # Class has streams - ONLY use subjects defined in the stream
        # (User already selected all subjects including core in the stream setup)
        for ss in GenStreamSubject.query.filter_by(stream_id=stream_id).all():
            # Check per-class "Takes" checkbox - if explicitly disabled, skip
            class_cfg = class_configs.get(ss.subject_id)
            if class_cfg and not class_cfg.is_enabled:
                continue  # Explicitly unchecked "Takes" for this class
            
            # Get subject config for periods info
            cfg = GenSubjectConfig.query.filter_by(subject_id=ss.subject_id, is_active=True).first()
            subj_name = ss.subject.name if ss.subject else f'[Subject {ss.subject_id}]'
            if cfg:
                subjects.append({'id': ss.subject_id, 'name': subj_name, 'category': cfg.category})
            else:
                # Subject not configured in Subject Settings, use defaults
                subjects.append({'id': ss.subject_id, 'name': subj_name, 'category': 'general'})
    else:
        # Class doesn't have streams (e.g., JSS) - include all enabled subjects
        for cfg in GenSubjectConfig.query.filter_by(is_active=True).all():
            # Check per-class "Takes" checkbox
            class_cfg = class_configs.get(cfg.subject_id)
            if class_cfg and not class_cfg.is_enabled:
                continue  # Explicitly unchecked "Takes" for this class
            
            subj_name = cfg.subject.name if cfg.subject else f'[Subject {cfg.subject_id}]'
            subjects.append({'id': cfg.subject_id, 'name': subj_name, 'category': cfg.category})
    
    # Get teacher assignments
    assignments = {}
    for ta in GenTeacherAssignment.query.filter_by(class_config_id=cc.id, is_active=True).filter(
        (GenTeacherAssignment.arm_name == None) | (GenTeacherAssignment.arm_name == arm)
    ).all():
        assignments[ta.subject_id] = ta.teacher_id
    
    # Get max consecutive periods from rules
    max_consecutive_rule = GenTimetableRule.query.filter_by(rule_type='max_consecutive').first()
    max_consecutive = int(max_consecutive_rule.value) if max_consecutive_rule else 3
    
    # Initialize timetable - 8 periods (5 morning + 3 afternoon), break is between period 5 and 6
    # Period 1-5 = morning, Period 6-8 = afternoon
    timetable = {d: {p: None for p in range(1, periods_per_day + 1)} for d in range(5)}
    # Note: break_after indicates break comes after this period (e.g., 5 means break after period 5)
    
    # Build needs - using per-class config if available, else global
    needs = []
    for subj in subjects:
        global_cfg = GenSubjectConfig.query.filter_by(subject_id=subj['id']).first()
        class_cfg = class_configs.get(subj['id'])
        
        # Use class-specific config if available, otherwise global
        if class_cfg:
            periods = class_cfg.periods_per_week
            needs_double = class_cfg.needs_double_period
            double_count = class_cfg.double_period_count if needs_double else 0
        elif global_cfg:
            periods = global_cfg.periods_per_week
            needs_double = global_cfg.needs_double_period
            double_count = global_cfg.double_period_count if needs_double else 0
        else:
            periods = 4
            needs_double = False
            double_count = 0
        
        teacher_id = assignments.get(subj['id'])
        single_count = periods - (double_count * 2)
        
        # Get constraints from global config
        not_first = global_cfg.not_first_period if global_cfg else False
        not_last = global_cfg.not_last_period if global_cfg else False
        preferred = global_cfg.preferred_time if global_cfg else 'any'
        
        for _ in range(double_count):
            needs.append({
                'subject_id': subj['id'], 'name': subj['name'], 'teacher_id': teacher_id,
                'not_first': not_first, 'not_last': not_last, 'preferred': preferred,
                'is_double': True
            })
        for _ in range(single_count):
            needs.append({
                'subject_id': subj['id'], 'name': subj['name'], 'teacher_id': teacher_id,
                'not_first': not_first, 'not_last': not_last, 'preferred': preferred,
                'is_double': False
            })
    
    # Count how busy each teacher already is (from teacher_schedule)
    def teacher_busyness(tid):
        if not tid or tid not in teacher_schedule:
            return 0
        return len(teacher_schedule[tid])
    
    # Group needs by subject and count total periods per subject
    subject_periods = {}
    for need in needs:
        sid = need['subject_id']
        if sid not in subject_periods:
            subject_periods[sid] = 0
        subject_periods[sid] += 1
    
    # Sort by:
    # 1. Subjects with MORE periods per week first (harder to fit, need more days)
    # 2. Double periods before singles (harder to place)
    # 3. Subjects with constraints (not first/last)
    # 4. Subjects with teachers over those without
    needs.sort(key=lambda x: (
        -subject_periods.get(x['subject_id'], 0),  # More periods first
        -1 if x['is_double'] else 0,  # Doubles first
        -1 if x['not_first'] or x['not_last'] else 0,  # Constrained subjects
        0 if x['teacher_id'] else 1,  # Subjects with teachers
    ))
    
    # Calculate total periods needed vs available slots
    total_periods_needed = len(needs)  # Each need is 1 period (doubles counted as 2 separate needs)
    total_slots_available = periods_per_day * 5  # 5 days
    
    if total_periods_needed > total_slots_available:
        conflicts.append(f"WARNING: {cc.class_name} {arm} needs {total_periods_needed} periods but only {total_slots_available} slots available!")
    
    # Track teacher periods per day and week
    teacher_day_count = {}  # {teacher_id: {day: count}}
    teacher_week_count = {}  # {teacher_id: total_count}
    
    def get_teacher_day_count(tid, day):
        if not tid:
            return 0
        if tid not in teacher_day_count:
            teacher_day_count[tid] = {d: 0 for d in range(5)}
        return teacher_day_count[tid].get(day, 0)
    
    def get_teacher_week_count(tid):
        if not tid:
            return 0
        return teacher_week_count.get(tid, 0)
    
    def increment_teacher_count(tid, day, count=1):
        if not tid:
            return
        if tid not in teacher_day_count:
            teacher_day_count[tid] = {d: 0 for d in range(5)}
        teacher_day_count[tid][day] = teacher_day_count[tid].get(day, 0) + count
        teacher_week_count[tid] = teacher_week_count.get(tid, 0) + count
    
    def is_teacher_free(tid, day, period):
        if not tid:
            return True
        # Check availability table
        if GenTeacherAvailability.query.filter_by(
            teacher_id=tid, day_of_week=day, period_number=period, is_available=False
        ).first():
            return False
        # Check clash with other classes
        if tid in teacher_schedule and (day, period) in teacher_schedule[tid]:
            return False
        return True
    
    def can_teacher_take_more(tid, day):
        """Check if teacher can take more periods on this day and week"""
        if not tid:
            return True
        teacher = GenTeacher.query.get(tid)
        if not teacher:
            return True
        # Check daily limit
        if get_teacher_day_count(tid, day) >= teacher.max_periods_per_day:
            return False
        # Check weekly limit
        if get_teacher_week_count(tid) >= teacher.max_periods_per_week:
            return False
        return True
    
    def get_teacher_consecutive_at(tid, day, period):
        """Count how many consecutive periods teacher already has ending at this period"""
        if not tid:
            return 0
        count = 0
        p = period - 1
        while p >= 1:
            # Break resets consecutive count
            if p == break_after:
                break
            if tid in teacher_schedule and (day, p) in teacher_schedule[tid]:
                count += 1
                p -= 1
            else:
                break
        return count
    
    def would_exceed_consecutive(tid, day, period, adding=1):
        """Check if assigning this period would exceed max consecutive for teacher"""
        if not tid:
            return False
        
        # Count consecutive before this period
        before = get_teacher_consecutive_at(tid, day, period)
        
        # Count consecutive after this period
        after = 0
        p = period + adding  # If adding double, start check from period + 2
        while p <= periods_per_day:
            if p == break_after + 1:  # Just after break
                break  # Break resets
            if tid in teacher_schedule and (day, p) in teacher_schedule[tid]:
                after += 1
                p += 1
            else:
                break
        
        total_consecutive = before + adding + after
        return total_consecutive > max_consecutive
    
    def count_on_day(sid, day):
        """Count how many times a subject appears on a day for THIS class arm"""
        return sum(1 for p in range(1, periods_per_day + 1) 
                   if timetable[day][p] and not timetable[day][p].get('is_break') 
                   and timetable[day][p].get('subject_id') == sid)
    
    def subject_already_on_day(sid, day):
        """Check if subject has ANY appearance on this day (single or double)"""
        for p in range(1, periods_per_day + 1):
            if timetable[day][p] and timetable[day][p].get('subject_id') == sid:
                return True
        return False
    
    def teacher_day_load(tid, day):
        """Count how many periods teacher has on this day across ALL classes"""
        if not tid or tid not in teacher_schedule:
            return 0
        return sum(1 for (d, p) in teacher_schedule[tid] if d == day)
    
    def sort_slots_for_teacher(slots, tid):
        """Sort slots to prefer days where teacher has fewer periods (better distribution)"""
        if not tid:
            return slots
        # Sort by: (teacher's load on that day, period number)
        return sorted(slots, key=lambda s: (teacher_day_load(tid, s[0]), s[1]))
    
    # First pass - assign with all constraints
    unassigned = []
    for need in needs:
        assigned = False
        slots = [(d, p) for d in range(5) for p in range(1, periods_per_day + 1) if timetable[d][p] is None]
        
        # Sort slots to:
        # 1. Prefer days where this subject hasn't appeared yet (spread across week)
        # 2. Then by teacher's load on that day (spread teacher's work)
        # 3. Then by period number
        def slot_score(slot):
            day, period = slot
            subject_on_day = 1 if subject_already_on_day(need['subject_id'], day) else 0
            teacher_load = teacher_day_load(need['teacher_id'], day) if need['teacher_id'] else 0
            return (subject_on_day, teacher_load, period)
        
        slots.sort(key=slot_score)
        
        for day, period in slots:
            if timetable[day][period]:
                continue
            if need['not_first'] and period == 1:
                continue
            if need['not_last'] and period == periods_per_day:
                continue
            if need['preferred'] == 'morning' and period > break_after:
                continue
            if need['preferred'] == 'afternoon' and period <= break_after:
                continue
            if not is_teacher_free(need['teacher_id'], day, period):
                continue
            if not can_teacher_take_more(need['teacher_id'], day):
                continue
            
            # NO subject repeat on same day for same arm - if subject already appeared, skip this day
            if subject_already_on_day(need['subject_id'], day):
                continue
            
            # Check consecutive periods for teacher
            if would_exceed_consecutive(need['teacher_id'], day, period, 1):
                continue
            
            if need['is_double']:
                np = period + 1
                # Double period cannot span across break
                if period == break_after:
                    continue  # Can't start double at last morning period
                if np > periods_per_day or timetable[day][np]:
                    continue
                if not is_teacher_free(need['teacher_id'], day, np):
                    continue
                if would_exceed_consecutive(need['teacher_id'], day, period, 2):
                    continue
                
                timetable[day][period] = {'subject_id': need['subject_id'], 'teacher_id': need['teacher_id'], 'is_double': True}
                timetable[day][np] = {'subject_id': need['subject_id'], 'teacher_id': need['teacher_id'], 'is_double': True}
                
                if need['teacher_id']:
                    if need['teacher_id'] not in teacher_schedule:
                        teacher_schedule[need['teacher_id']] = {}
                    teacher_schedule[need['teacher_id']][(day, period)] = (cc.class_name, arm)
                    teacher_schedule[need['teacher_id']][(day, np)] = (cc.class_name, arm)
                    increment_teacher_count(need['teacher_id'], day, 2)
            else:
                timetable[day][period] = {'subject_id': need['subject_id'], 'teacher_id': need['teacher_id'], 'is_double': False}
                if need['teacher_id']:
                    if need['teacher_id'] not in teacher_schedule:
                        teacher_schedule[need['teacher_id']] = {}
                    teacher_schedule[need['teacher_id']][(day, period)] = (cc.class_name, arm)
                    increment_teacher_count(need['teacher_id'], day, 1)
            
            assigned = True
            break
        
        if not assigned:
            unassigned.append(need)
    
    # Second pass - try unassigned with relaxed constraints (ignore preferred time, teacher limits, consecutive)
    # But STILL enforce: no subject repeat same day, no teacher clash, no double across break
    still_unassigned = []
    for need in unassigned:
        assigned = False
        slots = [(d, p) for d in range(5) for p in range(1, periods_per_day + 1) if timetable[d][p] is None]
        
        # Sort by teacher's availability on that day (prefer days where teacher is less busy)
        if need['teacher_id']:
            slots = sort_slots_for_teacher(slots, need['teacher_id'])
        else:
            shuffle(slots)
        
        for day, period in slots:
            if timetable[day][period]:
                continue
            # Must still check: teacher free (no clash)
            if not is_teacher_free(need['teacher_id'], day, period):
                continue
            # Must still check: no subject repeat same day AT ALL
            if subject_already_on_day(need['subject_id'], day):
                continue
            
            if need['is_double']:
                np = period + 1
                # No double across break
                if period == break_after:
                    continue
                if np > periods_per_day or timetable[day][np]:
                    continue
                if not is_teacher_free(need['teacher_id'], day, np):
                    continue
                
                timetable[day][period] = {'subject_id': need['subject_id'], 'teacher_id': need['teacher_id'], 'is_double': True}
                timetable[day][np] = {'subject_id': need['subject_id'], 'teacher_id': need['teacher_id'], 'is_double': True}
                
                if need['teacher_id']:
                    if need['teacher_id'] not in teacher_schedule:
                        teacher_schedule[need['teacher_id']] = {}
                    teacher_schedule[need['teacher_id']][(day, period)] = (cc.class_name, arm)
                    teacher_schedule[need['teacher_id']][(day, np)] = (cc.class_name, arm)
            else:
                timetable[day][period] = {'subject_id': need['subject_id'], 'teacher_id': need['teacher_id'], 'is_double': False}
                if need['teacher_id']:
                    if need['teacher_id'] not in teacher_schedule:
                        teacher_schedule[need['teacher_id']] = {}
                    teacher_schedule[need['teacher_id']][(day, period)] = (cc.class_name, arm)
            
            assigned = True
            break
        
        if not assigned:
            still_unassigned.append(need)
    
    # Log conflicts for truly unassigned subjects
    for need in still_unassigned:
        conflicts.append(f"Could not assign {need['name']} for {cc.class_name} {arm}")
    
    # Save
    for day in range(5):
        for period in range(1, periods_per_day + 1):
            entry = timetable[day][period]
            if entry and not entry.get('is_break'):
                db.session.add(GenTimetableResult(
                    batch_id=batch_id, class_name=cc.class_name, arm_name=arm,
                    day_of_week=day, period_number=period,
                    subject_id=entry.get('subject_id'), teacher_id=entry.get('teacher_id'),
                    is_double_period=entry.get('is_double', False)
                ))
    
    return {'success': len(conflicts) == 0, 'conflicts': conflicts}


# ============================================================================
# VIEW & OUTPUT
# ============================================================================





def _apply_batch(batch_id):
    """Publish a generated batch into the per-class timetable views
    (ClassTimetable) for the active term, replacing existing entries for the
    classes it covers. Returns ``(applied, message, category)``; ``applied`` is
    None when nothing could be published."""
    from models import (SchoolClass, ClassArm, ClassArmAssignment, ClassTimetable,
                        TimetableSlot)
    from utils.helpers import get_active_term
    from utils.branch_scope import can_access_branch
    from utils.audit import log_action

    level = get_current_level()
    results = GenTimetableResult.query.filter_by(batch_id=batch_id, school_level=level).all()
    if not results:
        return None, 'No results found for this batch.', 'error'

    term = get_active_term()
    if not term:
        return None, 'Set an active term first — class timetables are stored per term.', 'error'

    # Teaching periods, in school-day order (breaks excluded). The generator
    # numbers periods 1..N positionally, so we map a result's period_number to
    # the N-th teaching slot rather than relying on slot_number values matching.
    teaching = (TimetableSlot.query.filter_by(is_active=True, is_break=False)
                .order_by(TimetableSlot.order, TimetableSlot.slot_number).all())
    if not teaching:
        return None, ('No class periods are configured. Set them up under '
                      'Settings → Timetable Slots, then apply again.'), 'error'

    def slot_for_period(p):
        return teaching[p - 1] if isinstance(p, int) and 1 <= p <= len(teaching) else None

    # Back up whatever is currently published for this term BEFORE we replace it,
    # so an in-use timetable can be restored if this apply isn't wanted.
    from utils.timetable_backup import snapshot_term
    backup = snapshot_term(term.id, f'Auto-backup before applying batch {batch_id}')

    classes_by_name = {c.name.lower(): c for c in SchoolClass.query.all()}
    arms_by_name = {a.name.lower(): a for a in ClassArm.query.all()}

    # Lenient subject lookup: normalise case/spacing/punctuation, and index both
    # full name and short name so generator subjects line up with academic ones
    # even when they differ cosmetically.
    import re as _re

    def norm(s):
        return _re.sub(r'[^a-z0-9]', '', (s or '').lower())

    subject_index = {}
    for s in Subject.query.all():
        for key in (norm(s.name), norm(s.short_name)):
            if key:
                subject_index.setdefault(key, s)

    def resolve_subject(gs):
        """Academic Subject for a generator subject, creating one if there's no
        reasonable match — so no generated cell is dropped for a name mismatch."""
        if not gs:
            return None, False
        s = subject_index.get(norm(gs.name)) or subject_index.get(norm(gs.short_name))
        if s:
            return s, False
        s = Subject(name=gs.name, short_name=gs.short_name,
                    category=gs.category, is_active=True)
        db.session.add(s)
        db.session.flush()
        for key in (norm(s.name), norm(s.short_name)):
            if key:
                subject_index.setdefault(key, s)
        return s, True

    groups = {}
    for r in results:
        groups.setdefault((r.class_name, r.arm_name), []).append(r)

    applied = written = skipped_branch = 0
    unmatched_classes, missing_slots = set(), set()
    created_subjects = set()

    for (cname, aname), rows in groups.items():
        sc = classes_by_name.get((cname or '').lower())
        arm = arms_by_name.get((aname or '').lower())
        caa = None
        if sc and arm:
            caa = ClassArmAssignment.query.filter_by(
                class_id=sc.id, arm_id=arm.id, term_id=term.id).first()
        if not caa:
            unmatched_classes.add(f'{cname} {aname}')
            continue
        if not can_access_branch(caa.branch_id):
            skipped_branch += 1
            continue
        # Replace existing entries for this class arm.
        ClassTimetable.query.filter_by(class_arm_assignment_id=caa.id).delete()
        seen = set()
        for r in rows:
            slot = slot_for_period(r.period_number)
            if not slot:
                missing_slots.add(r.period_number)
                continue
            key = (slot.id, r.day_of_week)
            if key in seen:                       # unique (caa, slot, day)
                continue
            seen.add(key)
            subj, created = resolve_subject(r.subject)
            if created:
                created_subjects.add(subj.name)
            db.session.add(ClassTimetable(
                class_arm_assignment_id=caa.id, slot_id=slot.id,
                day_of_week=r.day_of_week,
                subject_id=subj.id if subj else None,
                teacher_name=(r.teacher.name if r.teacher else None),
                room=getattr(r.room, 'name', None),
                is_active=True))
            written += 1
        applied += 1

    db.session.commit()
    log_action('timetable.apply_batch',
               f'batch {batch_id}: {applied} class(es), {written} entries -> {term.full_name}')

    msg = f'Applied to {applied} class timetable(s) for {term.full_name} ({written} entries).'
    if backup:
        msg += (f' The previous timetable ({backup.entry_count} entries) was backed '
                f'up first — you can restore it from Timetable → Backups & Restore.')
    if created_subjects:
        msg += (f' Added {len(created_subjects)} new academic subject(s) that '
                f'weren\'t in the list yet: ' + ', '.join(sorted(created_subjects)) + '.')
    if unmatched_classes:
        msg += ' No class/arm match for this term: ' + ', '.join(sorted(unmatched_classes)) + '.'
    if missing_slots:
        msg += (' These generated period numbers have no matching class period '
                '(check that Settings → Timetable Slots has enough periods): '
                + ', '.join(str(p) for p in sorted(missing_slots)) + '.')
    if skipped_branch:
        msg += f' Skipped {skipped_branch} class(es) outside your branch.'
    return applied, msg, ('success' if applied else 'warning')


















# ============================================================================
# REPORTS
# ============================================================================











# ============================================================================
# SPECIAL VIEWS
# ============================================================================





# ============================================================================
# API
# ============================================================================













# ============================================================================
# IMAGE EXPORT
# ============================================================================











# ============================================================================
# SUBJECT CLASH RULES
# ============================================================================















# ============================================================================
# JSS QUICK SETUP
# ============================================================================

__all__ = [_n for _n in dir() if not _n.startswith('__')]

from . import teachers, subjects, structure, rules, generation, exports, api, subject_rules  # noqa: E402,F401  (registers routes)
