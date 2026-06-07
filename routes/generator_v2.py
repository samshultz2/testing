"""
Timetable Generator V2 - Teacher-Centric Global Scheduling
Based on constraint satisfaction approach where teachers are the scarce resource.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict
import random


@dataclass
class TeacherSlot:
    """A time slot allocated to a teacher"""
    teacher_id: int
    day: int
    period: int
    class_arm: Optional[Tuple[str, str]] = None  # (class_name, arm_name)
    subject_id: Optional[int] = None
    is_double_start: bool = False
    is_double_end: bool = False


@dataclass 
class TeachingEvent:
    """A subject that needs to be scheduled for a class-arm"""
    teacher_id: int
    class_name: str
    arm_name: str
    subject_id: int
    subject_name: str
    periods_needed: int
    double_periods: int = 0  # How many of the periods are doubles
    not_first: bool = False
    not_last: bool = False
    preferred_time: str = 'any'  # 'morning', 'afternoon', 'any'


@dataclass
class Teacher:
    """Teacher with constraints"""
    id: int
    name: str
    max_per_day: int
    max_per_week: int
    max_consecutive: int = 3
    unavailable: Set[Tuple[int, int]] = field(default_factory=set)  # {(day, period)}
    total_load: int = 0  # Calculated from assignments
    difficulty_score: float = 0.0


class TimetableGeneratorV2:
    def __init__(self, periods_per_day: int = 8, break_after: int = 5, days: int = 5):
        self.periods_per_day = periods_per_day
        self.break_after = break_after  # Break is AFTER this period
        self.days = days
        
        self.teachers: Dict[int, Teacher] = {}
        self.events: List[TeachingEvent] = []
        self.class_arms: Set[Tuple[str, str]] = set()
        
        # Results
        self.teacher_slots: Dict[int, List[TeacherSlot]] = defaultdict(list)
        self.timetable: Dict[Tuple[str, str], Dict[int, Dict[int, dict]]] = {}
        
    def add_teacher(self, teacher: Teacher):
        self.teachers[teacher.id] = teacher
        
    def add_event(self, event: TeachingEvent):
        self.events.append(event)
        self.class_arms.add((event.class_name, event.arm_name))
        if event.teacher_id in self.teachers:
            self.teachers[event.teacher_id].total_load += event.periods_needed
    
    def calculate_teacher_difficulty(self):
        """Calculate difficulty score for each teacher"""
        for tid, teacher in self.teachers.items():
            # Base difficulty from load
            difficulty = teacher.total_load * 2
            
            # Add for unavailable slots
            difficulty += len(teacher.unavailable) * 1.5
            
            # Add for tight consecutive limit
            if teacher.max_consecutive <= 2:
                difficulty += 10
            
            # Add for tight daily limit
            if teacher.max_per_day <= 4:
                difficulty += 5
                
            # Count double periods for this teacher
            doubles = sum(e.double_periods for e in self.events if e.teacher_id == tid)
            difficulty += doubles * 3
            
            teacher.difficulty_score = difficulty
    
    def get_teachers_by_difficulty(self) -> List[Teacher]:
        """Return teachers sorted by difficulty (highest first)"""
        return sorted(self.teachers.values(), key=lambda t: -t.difficulty_score)
    
    def is_slot_valid_for_teacher(self, teacher: Teacher, day: int, period: int, 
                                   current_day_count: int, current_week_count: int,
                                   allocated_slots: Set[Tuple[int, int]]) -> bool:
        """Check if a slot is valid for a teacher"""
        # Check unavailability
        if (day, period) in teacher.unavailable:
            return False
        
        # Check daily limit
        if current_day_count >= teacher.max_per_day:
            return False
            
        # Check weekly limit
        if current_week_count >= teacher.max_per_week:
            return False
        
        # Check consecutive periods
        consecutive = 1
        # Count backwards
        p = period - 1
        while p >= 1 and (day, p) in allocated_slots:
            # Break resets consecutive
            if p == self.break_after:
                break
            consecutive += 1
            p -= 1
        # Count forwards
        p = period + 1
        while p <= self.periods_per_day and (day, p) in allocated_slots:
            if p == self.break_after + 1:
                break
            consecutive += 1
            p += 1
            
        if consecutive > teacher.max_consecutive:
            return False
            
        return True
    
    def allocate_teacher_slots(self):
        """STEP 3: Allocate time slots to each teacher"""
        teachers = self.get_teachers_by_difficulty()
        
        # Global tracking of which slots are taken by which teacher
        global_slots: Dict[Tuple[int, int], int] = {}  # (day, period) -> teacher_id
        
        for teacher in teachers:
            allocated: Set[Tuple[int, int]] = set()
            day_counts = {d: 0 for d in range(self.days)}
            week_count = 0
            
            # Calculate how many slots we need
            slots_needed = teacher.total_load
            
            # Try to distribute evenly across days
            slots_per_day_target = slots_needed / self.days
            
            # Create list of all possible slots, sorted by preference
            all_slots = []
            for day in range(self.days):
                for period in range(1, self.periods_per_day + 1):
                    all_slots.append((day, period))
            
            # Shuffle to add randomness but keep structure
            random.shuffle(all_slots)
            
            # Sort by day count (prefer days with fewer allocations)
            all_slots.sort(key=lambda s: day_counts[s[0]])
            
            attempts = 0
            max_attempts = len(all_slots) * 2
            
            while week_count < slots_needed and attempts < max_attempts:
                attempts += 1
                
                # Re-sort by current day counts
                available_slots = [s for s in all_slots if s not in allocated]
                available_slots.sort(key=lambda s: (day_counts[s[0]], s[1]))
                
                for day, period in available_slots:
                    if week_count >= slots_needed:
                        break
                        
                    if not self.is_slot_valid_for_teacher(
                        teacher, day, period, 
                        day_counts[day], week_count, allocated
                    ):
                        continue
                    
                    # Allocate this slot
                    allocated.add((day, period))
                    day_counts[day] += 1
                    week_count += 1
                    
                    self.teacher_slots[teacher.id].append(
                        TeacherSlot(teacher_id=teacher.id, day=day, period=period)
                    )
                    global_slots[(day, period)] = teacher.id
                    break
            
            if week_count < slots_needed:
                print(f"WARNING: {teacher.name} only got {week_count}/{slots_needed} slots")
    
    def bind_events_to_slots(self):
        """STEP 4: Bind subjects and class-arms to teacher slots"""
        # Initialize timetable structure
        for class_name, arm_name in self.class_arms:
            key = (class_name, arm_name)
            self.timetable[key] = {d: {p: None for p in range(1, self.periods_per_day + 1)} 
                                   for d in range(self.days)}
        
        # Group events by teacher
        events_by_teacher: Dict[int, List[TeachingEvent]] = defaultdict(list)
        for event in self.events:
            events_by_teacher[event.teacher_id].append(event)
        
        # Sort events: doubles first, then by periods needed (most first)
        for tid in events_by_teacher:
            events_by_teacher[tid].sort(key=lambda e: (-e.double_periods, -e.periods_needed))
        
        # Track what's assigned to each class-arm per day
        class_arm_day_subjects: Dict[Tuple[str, str, int], Set[int]] = defaultdict(set)
        
        # Process each teacher's events
        for tid, events in events_by_teacher.items():
            slots = self.teacher_slots.get(tid, [])
            if not slots:
                continue
            
            # Sort slots by day then period
            slots.sort(key=lambda s: (s.day, s.period))
            
            # Track which slots are used
            used_slots: Set[int] = set()
            
            for event in events:
                periods_to_assign = event.periods_needed
                doubles_to_assign = event.double_periods
                
                # First, try to assign double periods
                while doubles_to_assign > 0 and periods_to_assign >= 2:
                    assigned_double = False
                    
                    for i, slot in enumerate(slots):
                        if i in used_slots:
                            continue
                        
                        day, period = slot.day, slot.period
                        class_arm_key = (event.class_name, event.arm_name)
                        day_key = (event.class_name, event.arm_name, day)
                        
                        # Check if subject already on this day
                        if event.subject_id in class_arm_day_subjects[day_key]:
                            continue
                        
                        # Check if slot already has something for this class-arm
                        if self.timetable[class_arm_key][day][period] is not None:
                            continue
                        
                        # Check constraints
                        if event.not_first and period == 1:
                            continue
                        if event.not_last and period == self.periods_per_day:
                            continue
                        
                        # Double cannot start at break_after (would span break)
                        if period == self.break_after:
                            continue
                        
                        # Find adjacent slot for double
                        next_period = period + 1
                        if next_period > self.periods_per_day:
                            continue
                        
                        # Find the slot for next period
                        next_slot_idx = None
                        for j, s in enumerate(slots):
                            if j not in used_slots and s.day == day and s.period == next_period:
                                next_slot_idx = j
                                break
                        
                        if next_slot_idx is None:
                            continue
                        
                        # Check next slot is free for this class-arm
                        if self.timetable[class_arm_key][day][next_period] is not None:
                            continue
                        
                        # Assign double period
                        entry = {
                            'subject_id': event.subject_id,
                            'subject_name': event.subject_name,
                            'teacher_id': tid,
                            'is_double': True
                        }
                        self.timetable[class_arm_key][day][period] = entry
                        self.timetable[class_arm_key][day][next_period] = entry.copy()
                        
                        slots[i].class_arm = class_arm_key
                        slots[i].subject_id = event.subject_id
                        slots[i].is_double_start = True
                        slots[next_slot_idx].class_arm = class_arm_key
                        slots[next_slot_idx].subject_id = event.subject_id
                        slots[next_slot_idx].is_double_end = True
                        
                        used_slots.add(i)
                        used_slots.add(next_slot_idx)
                        class_arm_day_subjects[day_key].add(event.subject_id)
                        
                        periods_to_assign -= 2
                        doubles_to_assign -= 1
                        assigned_double = True
                        break
                    
                    if not assigned_double:
                        break  # Can't assign more doubles
                
                # Then assign single periods
                while periods_to_assign > 0:
                    assigned_single = False
                    
                    for i, slot in enumerate(slots):
                        if i in used_slots:
                            continue
                        
                        day, period = slot.day, slot.period
                        class_arm_key = (event.class_name, event.arm_name)
                        day_key = (event.class_name, event.arm_name, day)
                        
                        # Check if subject already on this day
                        if event.subject_id in class_arm_day_subjects[day_key]:
                            continue
                        
                        # Check if slot already has something for this class-arm
                        if self.timetable[class_arm_key][day][period] is not None:
                            continue
                        
                        # Check constraints
                        if event.not_first and period == 1:
                            continue
                        if event.not_last and period == self.periods_per_day:
                            continue
                        if event.preferred_time == 'morning' and period > self.break_after:
                            continue
                        if event.preferred_time == 'afternoon' and period <= self.break_after:
                            continue
                        
                        # Assign single period
                        entry = {
                            'subject_id': event.subject_id,
                            'subject_name': event.subject_name,
                            'teacher_id': tid,
                            'is_double': False
                        }
                        self.timetable[class_arm_key][day][period] = entry
                        
                        slots[i].class_arm = class_arm_key
                        slots[i].subject_id = event.subject_id
                        
                        used_slots.add(i)
                        class_arm_day_subjects[day_key].add(event.subject_id)
                        
                        periods_to_assign -= 1
                        assigned_single = True
                        break
                    
                    if not assigned_single:
                        print(f"WARNING: Could not assign {event.subject_name} for {event.class_name} {event.arm_name} ({periods_to_assign} periods remaining)")
                        break
    
    def local_repair(self, max_iterations: int = 1000):
        """STEP 5: Local constraint repair using min-conflicts"""
        for iteration in range(max_iterations):
            violations = self.find_violations()
            if not violations:
                break
            
            # Pick a random violation
            violation = random.choice(violations)
            
            # Try to fix it by swapping
            if self.try_repair_violation(violation):
                continue
        
        return self.find_violations()
    
    def find_violations(self) -> List[dict]:
        """Find all constraint violations"""
        violations = []
        
        for class_arm_key, days in self.timetable.items():
            for day, periods in days.items():
                # Check for subject repeats
                subjects_today = []
                for period, entry in periods.items():
                    if entry and entry.get('subject_id'):
                        sid = entry['subject_id']
                        if sid in subjects_today and not entry.get('is_double'):
                            violations.append({
                                'type': 'subject_repeat',
                                'class_arm': class_arm_key,
                                'day': day,
                                'subject_id': sid
                            })
                        subjects_today.append(sid)
        
        return violations
    
    def try_repair_violation(self, violation: dict) -> bool:
        """Try to repair a violation by swapping slots"""
        # Simple swap implementation
        return False  # Placeholder
    
    def count_empty_slots(self) -> int:
        """Count total empty slots"""
        empty = 0
        for class_arm_key, days in self.timetable.items():
            for day, periods in days.items():
                for period, entry in periods.items():
                    if entry is None:
                        empty += 1
        return empty
    
    def generate(self) -> Dict:
        """Main generation method"""
        print("Step 1: Calculating teacher difficulty...")
        self.calculate_teacher_difficulty()
        
        print("Step 2: Allocating teacher slots...")
        self.allocate_teacher_slots()
        
        print("Step 3: Binding events to slots...")
        self.bind_events_to_slots()
        
        print("Step 4: Running local repair...")
        remaining_violations = self.local_repair()
        
        empty = self.count_empty_slots()
        print(f"Generation complete. Empty slots: {empty}, Violations: {len(remaining_violations)}")
        
        return {
            'timetable': self.timetable,
            'empty_slots': empty,
            'violations': remaining_violations
        }


def run_generation_v2(class_ids, periods_per_day, break_after, db_models):
    """
    Run the V2 generator using data from database models
    """
    from models import (
        GenClassConfig, GenClassArmStream, GenStreamSubject, GenSubjectConfig,
        GenClassSubjectConfig, GenTeacher, GenTeacherAssignment, GenTeacherAvailability,
        GenTimetableRule
    )
    
    generator = TimetableGeneratorV2(
        periods_per_day=periods_per_day,
        break_after=break_after
    )
    
    # Get max consecutive from rules
    max_consecutive_rule = GenTimetableRule.query.filter_by(rule_type='max_consecutive').first()
    max_consecutive = int(max_consecutive_rule.value) if max_consecutive_rule else 3
    
    # Load teachers
    for t in GenTeacher.query.filter_by(is_active=True).all():
        unavailable = set()
        for ua in GenTeacherAvailability.query.filter_by(teacher_id=t.id, is_available=False).all():
            unavailable.add((ua.day_of_week, ua.period_number))
        
        generator.add_teacher(Teacher(
            id=t.id,
            name=t.name,
            max_per_day=t.max_periods_per_day,
            max_per_week=t.max_periods_per_week,
            max_consecutive=max_consecutive,
            unavailable=unavailable
        ))
    
    # Load events (teaching assignments)
    for class_id in class_ids:
        cc = GenClassConfig.query.get(class_id)
        if not cc:
            continue
        
        for arm in cc.arm_list:
            # Get stream if applicable
            stream_id = None
            if cc.has_streams:
                cas = GenClassArmStream.query.filter_by(class_config_id=cc.id, arm_name=arm).first()
                if cas:
                    stream_id = cas.stream_id
            
            # Get subjects for this arm
            class_configs = {c.subject_id: c for c in GenClassSubjectConfig.query.filter_by(
                class_config_id=cc.id, is_active=True
            ).all()}
            
            subjects = []
            if cc.has_streams and stream_id:
                for ss in GenStreamSubject.query.filter_by(stream_id=stream_id).all():
                    class_cfg = class_configs.get(ss.subject_id)
                    if class_cfg and not class_cfg.is_enabled:
                        continue
                    cfg = GenSubjectConfig.query.filter_by(subject_id=ss.subject_id, is_active=True).first()
                    if cfg:
                        subjects.append((ss.subject_id, ss.subject.name, cfg))
            else:
                for cfg in GenSubjectConfig.query.filter_by(is_active=True).all():
                    class_cfg = class_configs.get(cfg.subject_id)
                    if class_cfg and not class_cfg.is_enabled:
                        continue
                    subjects.append((cfg.subject_id, cfg.subject.name, cfg))
            
            # Create events for each subject
            for subject_id, subject_name, cfg in subjects:
                # Get teacher assignment
                ta = GenTeacherAssignment.query.filter_by(
                    class_config_id=cc.id, subject_id=subject_id, is_active=True
                ).filter(
                    (GenTeacherAssignment.arm_name == None) | (GenTeacherAssignment.arm_name == arm)
                ).first()
                
                if not ta or not ta.teacher_id:
                    continue
                
                # Get periods from class config or global
                class_cfg = class_configs.get(subject_id)
                if class_cfg:
                    periods = class_cfg.periods_per_week
                    needs_double = class_cfg.needs_double_period
                    double_count = class_cfg.double_period_count if needs_double else 0
                else:
                    periods = cfg.periods_per_week
                    needs_double = cfg.needs_double_period
                    double_count = cfg.double_period_count if needs_double else 0
                
                generator.add_event(TeachingEvent(
                    teacher_id=ta.teacher_id,
                    class_name=cc.class_name,
                    arm_name=arm,
                    subject_id=subject_id,
                    subject_name=subject_name,
                    periods_needed=periods,
                    double_periods=double_count,
                    not_first=cfg.not_first_period,
                    not_last=cfg.not_last_period,
                    preferred_time=cfg.preferred_time
                ))
    
    return generator.generate()
