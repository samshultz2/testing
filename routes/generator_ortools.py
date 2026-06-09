"""
OR-Tools based timetable generator
Uses Google's constraint programming solver for optimal scheduling
V7: Added constraint to prevent same teacher teaching same class back-to-back
    Added randomization for different solutions each run
"""
from models import (
    db, GenClassConfig, GenClassArmStream, GenStreamSubject, GenSubjectConfig,
    GenClassSubjectConfig, GenClassStreamSubject, GenTeacher, GenTeacherAssignment,
    GenTeacherAvailability, GenTimetableRule, GenTimetableResult, GenSubject,
    GenSubjectClashRule, GenCombinedClassRule
)
from collections import defaultdict
import uuid
import random
import time

try:
    from ortools.sat.python import cp_model
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False
    print("Warning: OR-Tools not installed. Run: pip install ortools --break-system-packages")


# Class-specific period restrictions
CLASS_SPECIFIC_RESTRICTIONS = {
    'Mathematics': {
        'SSS1': {'not_first': True, 'not_last': False},
        'SSS2': {'not_first': True, 'not_last': False},
        'SSS3': {'not_first': True, 'not_last': False}
    }
}


def get_class_level(class_name):
    """Extract class level like SSS1, SSS2, SSS3 from class name"""
    class_name = class_name.upper().replace(' ', '')
    if 'SSS1' in class_name or 'SS1' in class_name:
        return 'SSS1'
    elif 'SSS2' in class_name or 'SS2' in class_name:
        return 'SSS2'
    elif 'SSS3' in class_name or 'SS3' in class_name:
        return 'SSS3'
    return class_name


def generate_with_ortools(class_ids, periods_per_day, time_limit=300, break_after=4):
    """
    Generate timetable using OR-Tools constraint programming solver.
    """
    if not ORTOOLS_AVAILABLE:
        return {'success': False, 'message': 'OR-Tools not installed'}
    
    # Valid double period start positions (cannot cross break)
    valid_double_starts = []
    for p in range(1, periods_per_day):
        if p != break_after:
            valid_double_starts.append(p)
    
    print(f"Valid double period starts: {valid_double_starts}")
    print(f"Break after period: {break_after}")
    
    global_subject_configs = {
        sc.subject_id: sc for sc in GenSubjectConfig.query.filter_by(is_active=True).all()
    }
    
    # ========== LOAD DATA ==========
    requirements = []
    class_arms = []
    subject_info = {}
    
    for class_id in class_ids:
        cc = GenClassConfig.query.get(class_id)
        if not cc or not cc.is_active:
            continue
        
        for arm in cc.arm_list:
            class_arms.append((cc.class_name, arm))
            class_level = get_class_level(cc.class_name)
            
            stream_id = None
            if cc.has_streams:
                cas = GenClassArmStream.query.filter_by(class_config_id=cc.id, arm_name=arm).first()
                if cas:
                    stream_id = cas.stream_id
            
            class_stream_configs = {}
            if stream_id:
                class_stream_configs = {
                    css.subject_id: css 
                    for css in GenClassStreamSubject.query.filter_by(
                        class_config_id=cc.id, stream_id=stream_id
                    ).all()
                }
            
            class_configs = {
                c.subject_id: c 
                for c in GenClassSubjectConfig.query.filter_by(
                    class_config_id=cc.id, is_active=True
                ).all()
            }
            
            subjects = []
            if cc.has_streams and stream_id:
                for ss in GenStreamSubject.query.filter_by(stream_id=stream_id).all():
                    class_cfg = class_configs.get(ss.subject_id)
                    if class_cfg and not class_cfg.is_enabled:
                        continue
                    css = class_stream_configs.get(ss.subject_id)
                    if css and not css.is_enabled:
                        continue
                    
                    if css and css.periods_per_week:
                        periods = css.periods_per_week
                    elif ss.periods_per_week:
                        periods = ss.periods_per_week
                    else:
                        cfg = global_subject_configs.get(ss.subject_id)
                        periods = cfg.periods_per_week if cfg else 2
                    
                    needs_double = False
                    double_count = 0
                    
                    # Priority: per-class config > class-stream config > stream config > global config
                    if class_cfg and class_cfg.needs_double_period:
                        # Per-class settings (what user sets in UI) take priority
                        needs_double = class_cfg.needs_double_period
                        double_count = class_cfg.double_period_count or 0
                    elif css and css.needs_double_period:
                        needs_double = css.needs_double_period
                        double_count = css.double_period_count or 0
                    elif ss.needs_double_period:
                        needs_double = ss.needs_double_period
                        double_count = ss.double_period_count or 0
                    else:
                        cfg = global_subject_configs.get(ss.subject_id)
                        if cfg:
                            needs_double = cfg.needs_double_period
                            double_count = cfg.double_period_count or 0
                    
                    not_first = False
                    not_last = False
                    cfg = global_subject_configs.get(ss.subject_id)
                    if cfg:
                        not_first = cfg.not_first_period
                        not_last = cfg.not_last_period
                    
                    subj_name = ss.subject.name
                    if subj_name in CLASS_SPECIFIC_RESTRICTIONS:
                        if class_level in CLASS_SPECIFIC_RESTRICTIONS[subj_name]:
                            restr = CLASS_SPECIFIC_RESTRICTIONS[subj_name][class_level]
                            not_first = not_first or restr.get('not_first', False)
                            not_last = not_last or restr.get('not_last', False)
                    
                    subjects.append({
                        'subject_id': ss.subject_id,
                        'subject_name': subj_name,
                        'periods': periods,
                        'needs_double': needs_double,
                        'double_count': double_count,
                        'not_first_period': not_first,
                        'not_last_period': not_last,
                    })
            else:
                for cfg in class_configs.values():
                    if not cfg.is_enabled:
                        continue
                    subj = GenSubject.query.get(cfg.subject_id)
                    if not subj:
                        print(f"Warning: Subject ID {cfg.subject_id} not found, skipping...")
                        continue
                    
                    needs_double = cfg.needs_double_period
                    double_count = cfg.double_period_count or 0
                    
                    if not needs_double:
                        gcfg = global_subject_configs.get(cfg.subject_id)
                        if gcfg:
                            needs_double = gcfg.needs_double_period
                            double_count = gcfg.double_period_count or 0
                    
                    not_first = False
                    not_last = False
                    gcfg = global_subject_configs.get(cfg.subject_id)
                    if gcfg:
                        not_first = gcfg.not_first_period
                        not_last = gcfg.not_last_period
                    
                    if subj.name in CLASS_SPECIFIC_RESTRICTIONS:
                        if class_level in CLASS_SPECIFIC_RESTRICTIONS[subj.name]:
                            restr = CLASS_SPECIFIC_RESTRICTIONS[subj.name][class_level]
                            not_first = not_first or restr.get('not_first', False)
                            not_last = not_last or restr.get('not_last', False)
                    
                    subjects.append({
                        'subject_id': cfg.subject_id,
                        'subject_name': subj.name,
                        'periods': cfg.periods_per_week,
                        'needs_double': needs_double,
                        'double_count': double_count,
                        'not_first_period': not_first,
                        'not_last_period': not_last,
                    })
            
            assignments = {}
            for ta in GenTeacherAssignment.query.filter_by(class_config_id=cc.id, is_active=True).all():
                if ta.arm_name is None or ta.arm_name == arm:
                    assignments[ta.subject_id] = ta.teacher_id
            
            for subj in subjects:
                teacher_id = assignments.get(subj['subject_id'])
                
                key = (cc.class_name, arm, subj['subject_id'])
                subject_info[key] = {
                    'name': subj['subject_name'],
                    'periods': subj['periods'],
                    'teacher_id': teacher_id,
                    'class_level': class_level,
                    'needs_double': subj['needs_double'],
                    'double_count': subj['double_count'],
                    'not_first_period': subj['not_first_period'],
                    'not_last_period': subj['not_last_period'],
                }
                
                for p_num in range(subj['periods']):
                    requirements.append({
                        'class_name': cc.class_name,
                        'arm': arm,
                        'subject_id': subj['subject_id'],
                        'subject_name': subj['subject_name'],
                        'teacher_id': teacher_id,
                        'class_level': class_level,
                        'req_id': len(requirements),
                        'period_index': p_num
                    })
    
    if not requirements:
        return {'success': False, 'message': 'No requirements found'}
    
    print(f"Loaded {len(requirements)} requirements for {len(class_arms)} class-arms")
    
    teachers = {t.id: t for t in GenTeacher.query.filter_by(is_active=True).all()}
    
    teacher_unavailable = defaultdict(set)
    for t in teachers.values():
        for ua in GenTeacherAvailability.query.filter_by(teacher_id=t.id, is_available=False).all():
            teacher_unavailable[t.id].add((ua.day_of_week, ua.period_number))
    
    teacher_reqs = defaultdict(list)
    for req in requirements:
        if req['teacher_id']:
            teacher_reqs[req['teacher_id']].append(req)
    
    subject_ca_reqs = defaultdict(list)
    for req in requirements:
        key = (req['class_name'], req['arm'], req['subject_id'])
        subject_ca_reqs[key].append(req)
    
    # Group requirements by teacher AND class-arm (for back-to-back different subject constraint)
    teacher_classarm_reqs = defaultdict(list)
    for req in requirements:
        if req['teacher_id']:
            key = (req['teacher_id'], req['class_name'], req['arm'])
            teacher_classarm_reqs[key].append(req)
    
    num_periods = periods_per_day
    num_slots = 5 * num_periods
    num_days = 5
    
    # ========== BUILD MODEL ==========
    print("Building OR-Tools model...")
    model = cp_model.CpModel()
    
    x = {}
    for req in requirements:
        for slot in range(num_slots):
            x[req['req_id'], slot] = model.NewBoolVar(f'x_{req["req_id"]}_{slot}')
    
    # Constraint 1: Each requirement assigned to exactly 1 slot
    for req in requirements:
        model.Add(sum(x[req['req_id'], slot] for slot in range(num_slots)) == 1)
    
    # Constraint 2: Each class-arm slot has at most 1 requirement
    for ca in class_arms:
        ca_reqs = [r for r in requirements if (r['class_name'], r['arm']) == ca]
        for slot in range(num_slots):
            model.Add(sum(x[r['req_id'], slot] for r in ca_reqs) <= 1)
    
    # Constraint 3: Teacher can't be in two places at once
    for tid, reqs in teacher_reqs.items():
        for slot in range(num_slots):
            model.Add(sum(x[r['req_id'], slot] for r in reqs) <= 1)
    
    # Constraint 4: Teacher unavailability
    for req in requirements:
        tid = req['teacher_id']
        if tid:
            for d, p in teacher_unavailable[tid]:
                forbidden_slot = d * num_periods + (p - 1)
                model.Add(x[req['req_id'], forbidden_slot] == 0)
    
    # Constraint 5: Teacher max per day
    for tid, t in teachers.items():
        t_reqs = teacher_reqs.get(tid, [])
        if not t_reqs:
            continue
        for day in range(num_days):
            day_slots = range(day * num_periods, (day + 1) * num_periods)
            model.Add(sum(x[r['req_id'], slot] for r in t_reqs for slot in day_slots) <= t.max_periods_per_day)
    
    # Constraint 6: Period restrictions (not first/last period)
    print("Adding period restrictions...")
    for key, info in subject_info.items():
        class_name, arm, subject_id = key
        reqs = subject_ca_reqs[key]
        
        if info['not_first_period']:
            print(f"  {class_name} {arm} {info['name']}: not first period")
            for day in range(num_days):
                first_period_slot = day * num_periods
                for req in reqs:
                    model.Add(x[req['req_id'], first_period_slot] == 0)
        
        if info['not_last_period']:
            print(f"  {class_name} {arm} {info['name']}: not last period")
            for day in range(num_days):
                last_period_slot = day * num_periods + (num_periods - 1)
                for req in reqs:
                    model.Add(x[req['req_id'], last_period_slot] == 0)
    
    # Constraint 7: No subject spanning break
    print(f"Adding no-subject-spanning-break constraint (break after P{break_after})...")
    for key, reqs in subject_ca_reqs.items():
        for day in range(num_days):
            slot_before_break = day * num_periods + (break_after - 1)
            slot_after_break = day * num_periods + break_after
            sum_around_break = sum(x[r['req_id'], slot_before_break] for r in reqs) + \
                               sum(x[r['req_id'], slot_after_break] for r in reqs)
            model.Add(sum_around_break <= 1)
    
    # Constraint 8: Teacher max 2 consecutive periods
    print("Adding teacher max 2 consecutive constraint...")
    constraint_count = 0
    
    for tid, t_reqs in teacher_reqs.items():
        if not t_reqs:
            continue
        
        for day in range(num_days):
            # Morning block windows
            for p in range(1, break_after - 1):
                p1, p2, p3 = p, p + 1, p + 2
                if p3 <= break_after:
                    slot1 = day * num_periods + (p1 - 1)
                    slot2 = day * num_periods + (p2 - 1)
                    slot3 = day * num_periods + (p3 - 1)
                    
                    teacher_in_3_slots = []
                    for r in t_reqs:
                        teacher_in_3_slots.append(x[r['req_id'], slot1])
                        teacher_in_3_slots.append(x[r['req_id'], slot2])
                        teacher_in_3_slots.append(x[r['req_id'], slot3])
                    
                    model.Add(sum(teacher_in_3_slots) <= 2)
                    constraint_count += 1
            
            # Afternoon block windows
            for p in range(break_after + 1, num_periods - 1):
                p1, p2, p3 = p, p + 1, p + 2
                if p3 <= num_periods:
                    slot1 = day * num_periods + (p1 - 1)
                    slot2 = day * num_periods + (p2 - 1)
                    slot3 = day * num_periods + (p3 - 1)
                    
                    teacher_in_3_slots = []
                    for r in t_reqs:
                        teacher_in_3_slots.append(x[r['req_id'], slot1])
                        teacher_in_3_slots.append(x[r['req_id'], slot2])
                        teacher_in_3_slots.append(x[r['req_id'], slot3])
                    
                    model.Add(sum(teacher_in_3_slots) <= 2)
                    constraint_count += 1
    
    print(f"  Added {constraint_count} consecutive period constraints")
    
    # Constraint 9: No same teacher teaching same class-arm back-to-back with different subjects
    # (unless it's a double period of the same subject)
    print("Adding no-same-teacher-same-class-back-to-back constraint...")
    back_to_back_count = 0
    
    for (tid, class_name, arm), reqs in teacher_classarm_reqs.items():
        # Group by subject
        subject_groups = defaultdict(list)
        for r in reqs:
            subject_groups[r['subject_id']].append(r)
        
        # Only apply if teacher teaches multiple subjects to same class-arm
        if len(subject_groups) > 1:
            for day in range(num_days):
                # Check consecutive periods (not crossing break)
                for p in range(1, num_periods):
                    # Skip if crossing break
                    if p == break_after:
                        continue
                    
                    slot1 = day * num_periods + (p - 1)
                    slot2 = day * num_periods + p
                    
                    # For each pair of DIFFERENT subjects
                    subject_ids = list(subject_groups.keys())
                    for i in range(len(subject_ids)):
                        for j in range(i + 1, len(subject_ids)):
                            subj1_reqs = subject_groups[subject_ids[i]]
                            subj2_reqs = subject_groups[subject_ids[j]]
                            
                            # subj1 in slot1 AND subj2 in slot2 is forbidden
                            # subj2 in slot1 AND subj1 in slot2 is forbidden
                            
                            for r1 in subj1_reqs:
                                for r2 in subj2_reqs:
                                    # r1 in slot1 and r2 in slot2 forbidden
                                    model.Add(x[r1['req_id'], slot1] + x[r2['req_id'], slot2] <= 1)
                                    # r2 in slot1 and r1 in slot2 forbidden
                                    model.Add(x[r2['req_id'], slot1] + x[r1['req_id'], slot2] <= 1)
                                    back_to_back_count += 2
    
    print(f"  Added {back_to_back_count} back-to-back constraints")
    
    # Constraint 10: Subject clash avoidance (database-driven)
    # Reads rules from GenSubjectClashRule table
    print("Adding subject clash constraints (from database)...")
    clash_count = 0
    
    clash_rules = GenSubjectClashRule.query.filter_by(is_active=True).all()
    
    if not clash_rules:
        print("  No subject clash rules configured")
    
    # Group rules by source (to consolidate output)
    source_groups = defaultdict(list)
    for rule in clash_rules:
        key = (rule.source_class_name, rule.source_arm_name, rule.source_subject_id)
        source_groups[key].append(rule)
    
    for (source_class, source_arm, source_subj_id), rules in source_groups.items():
        source_subj = GenSubject.query.get(source_subj_id)
        if not source_subj:
            print(f"  Warning: Source subject ID {source_subj_id} not found, skipping...")
            continue
        
        # Find source subject requirements
        source_reqs = [r for r in requirements 
                      if r['class_name'] == source_class 
                      and (source_arm is None or r['arm'] == source_arm)
                      and r['subject_id'] == source_subj_id]
        
        if not source_reqs:
            print(f"  Warning: No {source_subj.name} found for {source_class} {source_arm or '(All)'}")
            continue
        
        print(f"  {source_class} {source_arm or '(All)'} {source_subj.name} ({len(source_reqs)} periods) must not clash with:")
        
        for rule in rules:
            target_subj = GenSubject.query.get(rule.target_subject_id)
            if not target_subj:
                print(f"    Warning: Target subject ID {rule.target_subject_id} not found, skipping...")
                continue
            
            # Find all target requirements
            target_reqs = [r for r in requirements 
                         if (rule.target_class_name is None or r['class_name'] == rule.target_class_name)
                         and (rule.target_arm_name is None or r['arm'] == rule.target_arm_name)
                         and r['subject_id'] == rule.target_subject_id]
            
            if not target_reqs:
                continue
            
            print(f"    - {rule.target_class_name or '(All)'} {rule.target_arm_name or '(All)'} {target_subj.name} ({len(target_reqs)} periods)")
            
            # For each slot, source and target cannot both be scheduled
            for slot in range(num_slots):
                for s_req in source_reqs:
                    for t_req in target_reqs:
                        model.Add(x[s_req['req_id'], slot] + x[t_req['req_id'], slot] <= 1)
                        clash_count += 1
    
    print(f"  Added {clash_count} subject clash constraints")
    
    # Constraint 11: Combined class teacher consecutive period limit (database-driven)
    # Reads rules from GenCombinedClassRule table
    print("Adding combined class teacher consecutive constraints (from database)...")
    combined_consecutive_count = 0
    
    combined_rules = GenCombinedClassRule.query.filter_by(is_active=True).all()
    
    if not combined_rules:
        print("  No combined class rules configured")
    
    for rule in combined_rules:
        shadow_subj = GenSubject.query.get(rule.shadow_subject_id)
        teacher_subj = GenSubject.query.get(rule.teacher_subject_id)
        
        if not shadow_subj:
            print(f"  Warning: Shadow subject ID {rule.shadow_subject_id} not found, skipping...")
            continue
        if not teacher_subj:
            print(f"  Warning: Teacher subject ID {rule.teacher_subject_id} not found, skipping...")
            continue
        
        # Find the shadow subject requirements (e.g., Geography SSS3 Iris)
        source_reqs = [r for r in requirements 
                      if r['class_name'] == rule.shadow_class_name 
                      and (rule.shadow_arm_name is None or r['arm'] == rule.shadow_arm_name)
                      and r['subject_id'] == rule.shadow_subject_id]
        
        if not source_reqs:
            print(f"  Warning: No {shadow_subj.name} found for {rule.shadow_class_name} {rule.shadow_arm_name or '(All)'}")
            continue
        
        # Find the teacher who teaches the teacher_subject to the specified class
        shadow_teacher_id = None
        for ta in GenTeacherAssignment.query.filter_by(subject_id=rule.teacher_subject_id, is_active=True).all():
            cc = GenClassConfig.query.get(ta.class_config_id)
            if cc and cc.class_name == rule.teacher_class_name:
                if ta.arm_name is None or ta.arm_name == rule.teacher_arm_name:
                    shadow_teacher_id = ta.teacher_id
                    break
        
        if not shadow_teacher_id:
            print(f"  Warning: No teacher found for {teacher_subj.name} in {rule.teacher_class_name} {rule.teacher_arm_name or '(All)'}")
            continue
        
        shadow_teacher = GenTeacher.query.get(shadow_teacher_id)
        print(f"  {rule.shadow_class_name} {rule.shadow_arm_name or '(All)'} {shadow_subj.name}: {shadow_teacher.name} also teaching during these slots")
        
        # Get all of the shadow teacher's own requirements
        shadow_teacher_reqs = teacher_reqs.get(shadow_teacher_id, [])
        
        # Now apply the "max 2 consecutive" constraint treating source_reqs as if they're shadow teacher's
        # For every window of 3 consecutive periods, shadow teacher + source slots <= 2
        
        for day in range(num_days):
            # Morning block windows
            for p in range(1, break_after - 1):
                p1, p2, p3 = p, p + 1, p + 2
                if p3 <= break_after:
                    slot1 = day * num_periods + (p1 - 1)
                    slot2 = day * num_periods + (p2 - 1)
                    slot3 = day * num_periods + (p3 - 1)
                    
                    # Sum of: shadow teacher's own classes + source subject in these 3 slots
                    combined_slots = []
                    for r in shadow_teacher_reqs:
                        combined_slots.append(x[r['req_id'], slot1])
                        combined_slots.append(x[r['req_id'], slot2])
                        combined_slots.append(x[r['req_id'], slot3])
                    for r in source_reqs:
                        combined_slots.append(x[r['req_id'], slot1])
                        combined_slots.append(x[r['req_id'], slot2])
                        combined_slots.append(x[r['req_id'], slot3])
                    
                    model.Add(sum(combined_slots) <= 2)
                    combined_consecutive_count += 1
            
            # Afternoon block windows
            for p in range(break_after + 1, num_periods - 1):
                p1, p2, p3 = p, p + 1, p + 2
                if p3 <= num_periods:
                    slot1 = day * num_periods + (p1 - 1)
                    slot2 = day * num_periods + (p2 - 1)
                    slot3 = day * num_periods + (p3 - 1)
                    
                    combined_slots = []
                    for r in shadow_teacher_reqs:
                        combined_slots.append(x[r['req_id'], slot1])
                        combined_slots.append(x[r['req_id'], slot2])
                        combined_slots.append(x[r['req_id'], slot3])
                    for r in source_reqs:
                        combined_slots.append(x[r['req_id'], slot1])
                        combined_slots.append(x[r['req_id'], slot2])
                        combined_slots.append(x[r['req_id'], slot3])
                    
                    model.Add(sum(combined_slots) <= 2)
                    combined_consecutive_count += 1
    
    print(f"  Added {combined_consecutive_count} combined consecutive constraints")


    
    # ========== DOUBLE PERIOD CONSTRAINTS ==========
    print("Adding double period constraints...")
    double_vars = {}
    
    for key, reqs in subject_ca_reqs.items():
        class_name, arm, subject_id = key
        info = subject_info[key]
        
        num_doubles = info['double_count'] if info['needs_double'] else 0
        
        if num_doubles > 0:
            print(f"  {class_name} {arm} {info['name']}: {num_doubles} double(s)")
            
            for day in range(num_days):
                for start_p in valid_double_starts:
                    var_key = (key, day, start_p)
                    double_vars[var_key] = model.NewBoolVar(f'double_{class_name}_{arm}_{subject_id}_{day}_{start_p}')
            
            model.Add(
                sum(double_vars[(key, day, start_p)] 
                    for day in range(num_days) 
                    for start_p in valid_double_starts) == num_doubles
            )
            
            if num_doubles >= 2:
                for day in range(num_days):
                    model.Add(
                        sum(double_vars[(key, day, start_p)] for start_p in valid_double_starts) <= 1
                    )
            
            for day in range(num_days):
                for start_p in valid_double_starts:
                    slot1 = day * num_periods + (start_p - 1)
                    slot2 = day * num_periods + start_p
                    
                    double_var = double_vars[(key, day, start_p)]
                    
                    sum_slot1 = sum(x[r['req_id'], slot1] for r in reqs)
                    sum_slot2 = sum(x[r['req_id'], slot2] for r in reqs)
                    
                    model.Add(sum_slot1 == 1).OnlyEnforceIf(double_var)
                    model.Add(sum_slot2 == 1).OnlyEnforceIf(double_var)
            
            for day in range(num_days):
                day_slots = [day * num_periods + p for p in range(num_periods)]
                day_count = sum(x[r['req_id'], slot] for r in reqs for slot in day_slots)
                
                has_double_today = model.NewBoolVar(f'has_double_{key}_{day}')
                double_sum_today = sum(double_vars[(key, day, start_p)] for start_p in valid_double_starts)
                model.Add(double_sum_today >= 1).OnlyEnforceIf(has_double_today)
                model.Add(double_sum_today == 0).OnlyEnforceIf(has_double_today.Not())
                
                model.Add(day_count == 2).OnlyEnforceIf(has_double_today)
                model.Add(day_count <= 1).OnlyEnforceIf(has_double_today.Not())
        
        else:
            for day in range(num_days):
                day_slots = [day * num_periods + p for p in range(num_periods)]
                model.Add(sum(x[r['req_id'], slot] for r in reqs for slot in day_slots) <= 1)
    
    # ========== SOLVE WITH RANDOMIZATION ==========
    print("Solving with randomization...")
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 8
    
    # Add randomization - use current time as seed for different solutions
    random_seed = int(time.time() * 1000) % (2**31)
    solver.parameters.random_seed = random_seed
    print(f"  Random seed: {random_seed}")
    
    # Randomize variable selection and value selection
    solver.parameters.search_branching = cp_model.AUTOMATIC_SEARCH
    
    status = solver.Solve(model)
    
    print(f"Status: {solver.StatusName(status)}")
    
    if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        return {'success': False, 'message': f'No solution found. Status: {solver.StatusName(status)}'}
    
    # ========== BUILD TIMETABLE ==========
    timetable = {ca: {d: {p: None for p in range(1, num_periods + 1)} for d in range(5)} for ca in class_arms}
    
    double_period_info = {}
    for var_key, var in double_vars.items():
        if solver.Value(var):
            key, day, start_p = var_key
            double_period_info[(key, day, start_p)] = True
    
    for req in requirements:
        for slot in range(num_slots):
            if solver.Value(x[req['req_id'], slot]):
                day = slot // num_periods
                period = (slot % num_periods) + 1
                ca = (req['class_name'], req['arm'])
                
                key = (req['class_name'], req['arm'], req['subject_id'])
                
                is_double = False
                for start_p in valid_double_starts:
                    if (key, day, start_p) in double_period_info and period in [start_p, start_p + 1]:
                        is_double = True
                        break
                
                timetable[ca][day][period] = {
                    'subject_id': req['subject_id'],
                    'subject_name': req['subject_name'],
                    'teacher_id': req['teacher_id'],
                    'is_double': is_double
                }
    
    empty_count = sum(1 for ca in class_arms for d in range(5) for p in range(1, num_periods + 1) if timetable[ca][d][p] is None)
    
    return {
        'success': True,
        'timetable': timetable,
        'class_arms': class_arms,
        'empty_count': empty_count,
        'assigned_count': len(requirements),
        'total_requirements': len(requirements),
        'message': f'Assigned {len(requirements)} requirements. {empty_count} empty slots.'
    }


def save_ortools_result(result):
    if not result.get('success'):
        return None
    
    GenTimetableResult.query.delete()
    db.session.commit()
    
    batch_id = str(uuid.uuid4())[:8]
    
    for ca, days_data in result['timetable'].items():
        class_name, arm = ca
        for day, periods in days_data.items():
            for period, entry in periods.items():
                if entry:
                    db.session.add(GenTimetableResult(
                        batch_id=batch_id, class_name=class_name, arm_name=arm,
                        day_of_week=day, period_number=period,
                        subject_id=entry['subject_id'], teacher_id=entry['teacher_id'],
                        is_double_period=entry.get('is_double', False)
                    ))
    
    db.session.commit()
    return batch_id


def check_ortools_available():
    return ORTOOLS_AVAILABLE
