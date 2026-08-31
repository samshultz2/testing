"""
Global Timetable Generator - Based on manual scheduling approach
Key insight: Schedule ALL class-arms simultaneously, not one by one
"""
from collections import defaultdict
from random import shuffle, seed as random_seed
import uuid


def generate_global_timetable(class_ids, periods_per_day, break_after, db_session):
    """
    Generate timetable for all classes simultaneously.
    This mimics how humans manually create timetables - considering all classes at once.
    """
    from models import (
        GenClassConfig, GenClassArmStream, GenStreamSubject, GenSubjectConfig,
        GenClassSubjectConfig, GenClassStreamSubject, GenTeacher, GenTeacherAssignment,
        GenTeacherAvailability, GenTimetableRule, GenTimetableResult, Subject
    )
    
    # Get rules
    rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(is_active=True).all()}
    max_consecutive = int(rules.get('max_consecutive', 3))
    
    # Collect ALL teaching events (subject-class-arm-teacher combinations)
    all_events = []  # List of {class_name, arm, subject_id, subject_name, teacher_id, periods, doubles}
    class_arms = []  # List of (class_name, arm) tuples
    
    for class_id in class_ids:
        cc = GenClassConfig.query.get(class_id)
        if not cc:
            continue
        
        for arm in cc.arm_list:
            class_arms.append((cc.class_name, arm, cc.id))
            
            # Get stream if applicable
            stream_id = None
            if cc.has_streams:
                cas = GenClassArmStream.query.filter_by(class_config_id=cc.id, arm_name=arm).first()
                if cas:
                    stream_id = cas.stream_id
            
            # Get per-class configs
            class_configs = {c.subject_id: c for c in GenClassSubjectConfig.query.filter_by(
                class_config_id=cc.id, is_active=True
            ).all()}
            
            # Get subjects for this arm
            subjects = []
            if cc.has_streams and stream_id:
                # Get class-stream specific configs
                class_stream_configs = {
                    css.subject_id: css 
                    for css in GenClassStreamSubject.query.filter_by(
                        class_config_id=cc.id, stream_id=stream_id
                    ).all()
                }
                
                for ss in GenStreamSubject.query.filter_by(stream_id=stream_id).all():
                    class_cfg = class_configs.get(ss.subject_id)
                    if class_cfg and not class_cfg.is_enabled:
                        continue
                    
                    # Check class-stream config for enabled status
                    class_stream_cfg = class_stream_configs.get(ss.subject_id)
                    if class_stream_cfg and not class_stream_cfg.is_enabled:
                        continue
                    
                    cfg = GenSubjectConfig.query.filter_by(subject_id=ss.subject_id, is_active=True).first()
                    if cfg:
                        # Pass all configs for priority resolution
                        subjects.append((ss.subject_id, ss.subject.name, cfg, class_cfg, ss, class_stream_cfg))
            else:
                for cfg in GenSubjectConfig.query.filter_by(is_active=True).all():
                    class_cfg = class_configs.get(cfg.subject_id)
                    if class_cfg and not class_cfg.is_enabled:
                        continue
                    subjects.append((cfg.subject_id, cfg.subject.name, cfg, class_cfg, None, None))
            
            # Get teacher assignments for this class
            assignments = {}
            for ta in GenTeacherAssignment.query.filter_by(class_config_id=cc.id, is_active=True).filter(
                (GenTeacherAssignment.arm_name == None) | (GenTeacherAssignment.arm_name == arm)
            ).all():
                assignments[ta.subject_id] = ta.teacher_id
            
            # Create events for each subject
            for subject_id, subject_name, cfg, class_cfg, stream_subj, class_stream_cfg in subjects:
                teacher_id = assignments.get(subject_id)
                
                # Priority: class-stream > stream > class > global
                if class_stream_cfg and class_stream_cfg.periods_per_week is not None:
                    periods = class_stream_cfg.periods_per_week
                    needs_double = class_stream_cfg.needs_double_period or False
                    double_count = class_stream_cfg.double_period_count if needs_double else 0
                elif stream_subj and stream_subj.periods_per_week is not None:
                    periods = stream_subj.periods_per_week
                    needs_double = stream_subj.needs_double_period if stream_subj.needs_double_period is not None else False
                    double_count = stream_subj.double_period_count if needs_double else 0
                elif class_cfg:
                    periods = class_cfg.periods_per_week
                    needs_double = class_cfg.needs_double_period
                    double_count = class_cfg.double_period_count if needs_double else 0
                else:
                    periods = cfg.periods_per_week
                    needs_double = cfg.needs_double_period
                    double_count = cfg.double_period_count if needs_double else 0
                
                all_events.append({
                    'class_name': cc.class_name,
                    'arm': arm,
                    'subject_id': subject_id,
                    'subject_name': subject_name,
                    'teacher_id': teacher_id,
                    'periods': periods,
                    'doubles': double_count,
                    'not_first': cfg.not_first_period,
                    'not_last': cfg.not_last_period,
                    'preferred': cfg.preferred_time
                })
    
    # Load teacher constraints
    teacher_unavailable = defaultdict(set)  # {teacher_id: {(day, period)}}
    teachers = {}  # {id: Teacher object}
    for t in GenTeacher.query.filter_by(is_active=True).all():
        teachers[t.id] = t
        for ua in GenTeacherAvailability.query.filter_by(teacher_id=t.id, is_available=False).all():
            teacher_unavailable[t.id].add((ua.day_of_week, ua.period_number))
    
    # Initialize empty timetables for all class-arms
    timetables = {}  # {(class_name, arm): {day: {period: entry}}}
    for class_name, arm, _ in class_arms:
        timetables[(class_name, arm)] = {d: {p: None for p in range(1, periods_per_day + 1)} for d in range(5)}
    
    # Track teacher schedule globally: {teacher_id: {(day, period): (class_name, arm)}}
    teacher_schedule = defaultdict(dict)
    
    # Track teacher daily/weekly counts
    teacher_day_count = defaultdict(lambda: defaultdict(int))  # {tid: {day: count}}
    teacher_week_count = defaultdict(int)  # {tid: count}
    
    # Expand events into individual period assignments
    # Sort by: periods per week (most first), then doubles, then by teacher load
    teacher_total_load = defaultdict(int)
    for event in all_events:
        if event['teacher_id']:
            teacher_total_load[event['teacher_id']] += event['periods']
    
    # Create list of individual period needs
    needs = []
    for event in all_events:
        singles = event['periods'] - (event['doubles'] * 2)
        
        # Add double period needs
        for _ in range(event['doubles']):
            needs.append({
                **event,
                'is_double': True,
                'teacher_load': teacher_total_load.get(event['teacher_id'], 0)
            })
        
        # Add single period needs
        for _ in range(singles):
            needs.append({
                **event,
                'is_double': False,
                'teacher_load': teacher_total_load.get(event['teacher_id'], 0)
            })
    
    # Sort needs:
    # 1. By periods per subject (subjects with more periods first - they need more days)
    # 2. Doubles before singles
    # 3. By teacher load (busier teachers first - fewer slot options)
    # Add some randomization within same priority to explore different orderings
    from random import random
    needs.sort(key=lambda x: (
        -x['periods'],  # More periods first
        -1 if x['is_double'] else 0,  # Doubles first
        -x['teacher_load'],  # Busier teachers first
        random()  # Randomize within same priority
    ))
    
    # Helper functions
    def is_teacher_free(tid, day, period):
        if not tid:
            return True
        if (day, period) in teacher_unavailable[tid]:
            return False
        if (day, period) in teacher_schedule[tid]:
            return False
        return True
    
    def can_teacher_take_more(tid, day):
        if not tid or tid not in teachers:
            return True
        t = teachers[tid]
        if teacher_day_count[tid][day] >= t.max_periods_per_day:
            return False
        if teacher_week_count[tid] >= t.max_periods_per_week:
            return False
        return True
    
    def subject_on_day(class_name, arm, subject_id, day):
        tt = timetables[(class_name, arm)]
        for p in range(1, periods_per_day + 1):
            if tt[day][p] and tt[day][p].get('subject_id') == subject_id:
                return True
        return False
    
    def get_teacher_consecutive(tid, day, period):
        """Count consecutive periods before this slot"""
        if not tid:
            return 0
        count = 0
        p = period - 1
        while p >= 1:
            if (day, p) in teacher_schedule[tid]:
                count += 1
                p -= 1
            else:
                break
        return count
    
    def would_exceed_consecutive(tid, day, period, adding=1):
        if not tid:
            return False
        before = get_teacher_consecutive(tid, day, period)
        # Count after
        after = 0
        p = period + adding
        while p <= periods_per_day:
            if (day, p) in teacher_schedule[tid]:
                after += 1
                p += 1
            else:
                break
        return (before + adding + after) > max_consecutive
    
    def assign_slot(need, day, period, is_double=False):
        """Assign a slot and update all tracking"""
        key = (need['class_name'], need['arm'])
        entry = {
            'subject_id': need['subject_id'],
            'subject_name': need['subject_name'],
            'teacher_id': need['teacher_id'],
            'is_double': is_double
        }
        timetables[key][day][period] = entry
        
        if need['teacher_id']:
            teacher_schedule[need['teacher_id']][(day, period)] = key
            teacher_day_count[need['teacher_id']][day] += 1
            teacher_week_count[need['teacher_id']] += 1
    
    # Assign all needs
    unassigned = []
    
    for need in needs:
        assigned = False
        key = (need['class_name'], need['arm'])
        tid = need['teacher_id']
        
        # Get all empty slots for this class-arm
        empty_slots = []
        for d in range(5):
            for p in range(1, periods_per_day + 1):
                if timetables[key][d][p] is None:
                    empty_slots.append((d, p))
        
        # Sort slots by teacher's load on that day (prefer days with fewer teacher periods)
        # Also prioritize filling later periods (P7, P8) first since they tend to be left empty
        def slot_score(slot):
            d, p = slot
            teacher_load_on_day = teacher_day_count[tid][d] if tid else 0
            # Count how many slots are filled for this class-arm on this day
            class_slots_on_day = sum(1 for pp in range(1, periods_per_day + 1) if timetables[key][d][pp] is not None)
            # Prefer: days with fewer class slots, then days with fewer teacher slots, then later periods
            return (class_slots_on_day, teacher_load_on_day, -p)  # -p means later periods first
        
        empty_slots.sort(key=slot_score)
        
        for day, period in empty_slots:
            # Skip if subject already on this day for this arm
            if subject_on_day(need['class_name'], need['arm'], need['subject_id'], day):
                continue
            
            # Check constraints
            if need['not_first'] and period == 1:
                continue
            if need['not_last'] and period == periods_per_day:
                continue
            if need['preferred'] == 'morning' and period > break_after:
                continue
            if need['preferred'] == 'afternoon' and period <= break_after:
                continue
            
            # Check teacher availability
            if not is_teacher_free(tid, day, period):
                continue
            if not can_teacher_take_more(tid, day):
                continue
            if would_exceed_consecutive(tid, day, period, 1):
                continue
            
            if need['is_double']:
                # Need adjacent slot
                next_period = period + 1
                if period == break_after:  # Can't span break
                    continue
                if next_period > periods_per_day:
                    continue
                if timetables[key][day][next_period] is not None:
                    continue
                if not is_teacher_free(tid, day, next_period):
                    continue
                if would_exceed_consecutive(tid, day, period, 2):
                    continue
                
                # Assign double
                assign_slot(need, day, period, is_double=True)
                assign_slot(need, day, next_period, is_double=True)
                assigned = True
                break
            else:
                # Single period
                assign_slot(need, day, period, is_double=False)
                assigned = True
                break
        
        if not assigned:
            unassigned.append(need)
    
    # Second pass - relaxed constraints for unassigned
    still_unassigned = []
    for need in unassigned:
        assigned = False
        key = (need['class_name'], need['arm'])
        tid = need['teacher_id']
        
        empty_slots = []
        for d in range(5):
            for p in range(1, periods_per_day + 1):
                if timetables[key][d][p] is None:
                    empty_slots.append((d, p))
        
        # Sort to prefer later periods (they tend to be left empty)
        empty_slots.sort(key=lambda s: (-s[1], s[0]))  # Later periods first, then by day
        
        for day, period in empty_slots:
            # Still enforce: no subject repeat, teacher free
            if subject_on_day(need['class_name'], need['arm'], need['subject_id'], day):
                continue
            if not is_teacher_free(tid, day, period):
                continue
            
            if need['is_double']:
                next_period = period + 1
                if period == break_after:
                    continue
                if next_period > periods_per_day:
                    continue
                if timetables[key][day][next_period] is not None:
                    continue
                if not is_teacher_free(tid, day, next_period):
                    continue
                
                assign_slot(need, day, period, is_double=True)
                assign_slot(need, day, next_period, is_double=True)
                assigned = True
                break
            else:
                assign_slot(need, day, period, is_double=False)
                assigned = True
                break
        
        if not assigned:
            still_unassigned.append(need)
    
    # Third pass - try to fill remaining empty slots by finding ANY subject that can go there
    # This reverses the approach: instead of finding slots for subjects, find subjects for slots
    for (class_name, arm), days_dict in timetables.items():
        for day in range(5):
            for period in range(1, periods_per_day + 1):
                if days_dict[day][period] is not None:
                    continue  # Slot already filled
                
                # Find any unassigned need for this class-arm that can fit here
                for i, need in enumerate(still_unassigned):
                    if need['class_name'] != class_name or need['arm'] != arm:
                        continue
                    if need['is_double']:
                        continue  # Skip doubles in this pass
                    
                    tid = need['teacher_id']
                    
                    # Check if subject already on this day
                    if subject_on_day(class_name, arm, need['subject_id'], day):
                        continue
                    
                    # Check teacher availability
                    if not is_teacher_free(tid, day, period):
                        continue
                    
                    # Assign it!
                    assign_slot(need, day, period, is_double=False)
                    still_unassigned.pop(i)
                    break
    
    # Count results
    total_filled = 0
    total_slots = len(class_arms) * periods_per_day * 5
    
    for key, days in timetables.items():
        for day, periods in days.items():
            for period, entry in periods.items():
                if entry:
                    total_filled += 1
    
    empty_count = total_slots - total_filled
    
    return {
        'timetables': timetables,
        'empty_count': empty_count,
        'total_slots': total_slots,
        'unassigned': still_unassigned,
        'class_arms': class_arms
    }


def run_global_generation(class_ids, periods_per_day, break_after, num_attempts=100):
    """
    Run multiple attempts and return the best result
    """
    from models import db, GenTimetableResult
    
    best_result = None
    best_empty = float('inf')
    
    for attempt in range(num_attempts):
        random_seed(attempt * 42 + 13)
        
        result = generate_global_timetable(class_ids, periods_per_day, break_after, db.session)
        
        if result['empty_count'] < best_empty:
            best_empty = result['empty_count']
            best_result = result
        
        # If perfect, stop early
        if best_empty == 0:
            break
    
    return best_result
