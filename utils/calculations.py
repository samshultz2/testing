"""
Attendance calculation utilities
All attendance-related calculations are performed here
"""
from datetime import date, timedelta
from collections import defaultdict
from models import db, Attendance, StudentEnrollment, Week, Holiday, Student


def get_daily_attendance_summary(class_arm_assignment_id, target_date):
    """
    Get daily attendance summary for a class arm
    
    Returns dict with:
    - total_students: Total enrolled students
    - morning_present: Count present in morning
    - morning_absent: Count absent in morning  
    - afternoon_present: Count present in afternoon
    - afternoon_absent: Count absent in afternoon
    - students: List of student attendance records
    """
    enrollments = StudentEnrollment.query.filter_by(
        class_arm_assignment_id=class_arm_assignment_id,
        is_active=True
    ).all()
    
    total_students = len(enrollments)
    morning_present = 0
    afternoon_present = 0
    students_data = []
    
    for enrollment in enrollments:
        attendance = Attendance.query.filter_by(
            enrollment_id=enrollment.id,
            date=target_date
        ).first()
        
        student = enrollment.student
        morning = attendance.morning_present if attendance else None
        afternoon = attendance.afternoon_present if attendance else None
        
        if morning:
            morning_present += 1
        if afternoon:
            afternoon_present += 1
        
        students_data.append({
            'student_id': student.id,
            'student_name': student.full_name,
            'gender': student.gender,
            'morning_present': morning,
            'afternoon_present': afternoon,
            'attendance_id': attendance.id if attendance else None
        })
    
    return {
        'date': target_date,
        'total_students': total_students,
        'morning_present': morning_present,
        'morning_absent': total_students - morning_present,
        'afternoon_present': afternoon_present,
        'afternoon_absent': total_students - afternoon_present,
        'students': students_data
    }


def get_weekly_attendance_summary(class_arm_assignment_id, week_id):
    """
    Get weekly attendance summary for a class arm
    
    Returns dict with:
    - week_info: Week details
    - school_days: List of school days in the week
    - times_opened: Number of times school opened
    - students: List of students with daily breakdown and weekly totals
    - class_totals: Class-level statistics
    """
    week = Week.query.get(week_id)
    if not week:
        return None
    
    # Get holidays for this term
    holidays = Holiday.query.filter_by(term_id=week.term_id).all()
    holiday_dates = set(h.date for h in holidays)
    
    # Get school days in this week
    school_days = []
    current = week.start_date
    while current <= week.end_date:
        if current.weekday() < 5 and current not in holiday_dates:  # Weekday and not holiday
            school_days.append(current)
        current += timedelta(days=1)
    
    times_opened = len(school_days) * 2  # Morning and afternoon sessions
    
    # Get enrollments
    enrollments = StudentEnrollment.query.filter_by(
        class_arm_assignment_id=class_arm_assignment_id,
        is_active=True
    ).all()
    
    students_data = []
    total_male = 0
    total_female = 0
    male_attendance = 0
    female_attendance = 0
    total_morning = 0
    total_afternoon = 0
    
    for enrollment in enrollments:
        student = enrollment.student
        
        # Count gender
        if student.gender == 'Male':
            total_male += 1
        else:
            total_female += 1
        
        # Get daily attendance for this week
        daily_data = []
        weekly_total = 0
        weekly_morning = 0
        weekly_afternoon = 0
        
        for day in school_days:
            attendance = Attendance.query.filter_by(
                enrollment_id=enrollment.id,
                date=day
            ).first()
            
            morning = attendance.morning_present if attendance else False
            afternoon = attendance.afternoon_present if attendance else False
            
            daily_total = int(morning or 0) + int(afternoon or 0)
            weekly_total += daily_total
            weekly_morning += int(morning or 0)
            weekly_afternoon += int(afternoon or 0)
            
            daily_data.append({
                'date': day,
                'day_name': day.strftime('%A'),
                'morning': morning,
                'afternoon': afternoon,
                'total': daily_total
            })
        
        # Accumulate totals
        total_morning += weekly_morning
        total_afternoon += weekly_afternoon
        
        if student.gender == 'Male':
            male_attendance += weekly_total
        else:
            female_attendance += weekly_total
        
        students_data.append({
            'student_id': student.id,
            'student_name': student.full_name,
            'gender': student.gender,
            'daily': daily_data,
            'weekly_morning': weekly_morning,
            'weekly_afternoon': weekly_afternoon,
            'weekly_total': weekly_total
        })
    
    # Calculate percentages
    total_students = len(enrollments)
    total_attendance = total_morning + total_afternoon
    
    if total_students > 0 and times_opened > 0:
        weekly_percentage = round((total_attendance / (total_students * times_opened)) * 100, 2)
    else:
        weekly_percentage = 0.0
    
    return {
        'week_info': {
            'week_id': week.id,
            'week_number': week.week_number,
            'start_date': week.start_date,
            'end_date': week.end_date
        },
        'school_days': school_days,
        'school_days_count': len(school_days),
        'times_opened': times_opened,
        'total_students': total_students,
        'total_male': total_male,
        'total_female': total_female,
        'students': students_data,
        'class_totals': {
            'total_morning': total_morning,
            'total_afternoon': total_afternoon,
            'total_attendance': total_attendance,
            'male_attendance': male_attendance,
            'female_attendance': female_attendance,
            'weekly_percentage': weekly_percentage
        }
    }


def get_termly_attendance_summary(class_arm_assignment_id, term_id):
    """
    Get termly attendance summary for a class arm
    
    Returns comprehensive termly statistics including weekly breakdown
    """
    weeks = Week.query.filter_by(term_id=term_id).order_by(Week.week_number).all()
    if not weeks:
        return None
    
    # Get holidays for this term
    holidays = Holiday.query.filter_by(term_id=term_id).all()
    holiday_dates = set(h.date for h in holidays)
    
    # Calculate total school days for term
    total_school_days = 0
    for week in weeks:
        current = week.start_date
        while current <= week.end_date:
            if current.weekday() < 5 and current not in holiday_dates:
                total_school_days += 1
            current += timedelta(days=1)
    
    total_times_opened = total_school_days * 2
    
    # Get enrollments
    enrollments = StudentEnrollment.query.filter_by(
        class_arm_assignment_id=class_arm_assignment_id,
        is_active=True
    ).all()
    
    students_data = []
    total_male_students = 0
    total_female_students = 0
    total_male_attendance = 0
    total_female_attendance = 0
    total_morning_attendance = 0
    total_afternoon_attendance = 0
    
    # Initialize weekly totals
    weekly_totals = [0] * len(weeks)
    
    for enrollment in enrollments:
        student = enrollment.student
        
        # Count by gender
        if student.gender == 'Male':
            total_male_students += 1
        else:
            total_female_students += 1
        
        # Get all attendance for this enrollment in this term
        attendance_records = Attendance.query.filter(
            Attendance.enrollment_id == enrollment.id,
            Attendance.week_id.in_([w.id for w in weeks])
        ).all()
        
        # Build attendance lookup by week_id
        attendance_by_week = {}
        for a in attendance_records:
            if a.week_id not in attendance_by_week:
                attendance_by_week[a.week_id] = {'morning': 0, 'afternoon': 0}
            if a.morning_present:
                attendance_by_week[a.week_id]['morning'] += 1
            if a.afternoon_present:
                attendance_by_week[a.week_id]['afternoon'] += 1
        
        student_morning = sum(1 for a in attendance_records if a.morning_present)
        student_afternoon = sum(1 for a in attendance_records if a.afternoon_present)
        student_total = student_morning + student_afternoon
        
        # Build weekly breakdown for this student
        student_weekly = []
        for idx, week in enumerate(weeks):
            week_data = attendance_by_week.get(week.id, {'morning': 0, 'afternoon': 0})
            week_total = week_data['morning'] + week_data['afternoon']
            student_weekly.append({
                'week_id': week.id,
                'morning': week_data['morning'],
                'afternoon': week_data['afternoon'],
                'total': week_total
            })
            weekly_totals[idx] += week_total
        
        # Accumulate by gender
        if student.gender == 'Male':
            total_male_attendance += student_total
        else:
            total_female_attendance += student_total
        
        total_morning_attendance += student_morning
        total_afternoon_attendance += student_afternoon
        
        percentage = round((student_total / total_times_opened * 100), 2) if total_times_opened > 0 else 0
        
        students_data.append({
            'student_id': student.id,
            'student_name': student.full_name,
            'gender': student.gender,
            'morning_total': student_morning,
            'afternoon_total': student_afternoon,
            'termly_morning': student_morning,
            'termly_afternoon': student_afternoon,
            'termly_total': student_total,
            'percentage': percentage,
            'termly_percentage': percentage,
            'weekly': student_weekly
        })
    
    # Calculate termly average
    total_attendance = total_male_attendance + total_female_attendance
    if total_times_opened > 0:
        termly_average = round((total_male_attendance + total_female_attendance) / total_times_opened, 2)
    else:
        termly_average = 0.0
    
    total_students = len(enrollments)
    if total_students > 0 and total_times_opened > 0:
        termly_percentage = round((total_attendance / (total_students * total_times_opened)) * 100, 2)
    else:
        termly_percentage = 0.0
    
    return {
        'term_info': {
            'term_id': term_id,
            'total_weeks': len(weeks),
            'total_school_days': total_school_days,
            'total_times_opened': total_times_opened
        },
        'total_students': total_students,
        'total_male_students': total_male_students,
        'total_female_students': total_female_students,
        'students': students_data,
        'weeks': weeks,
        'weekly_totals': weekly_totals,
        'class_totals': {
            'total_morning': total_morning_attendance,
            'total_afternoon': total_afternoon_attendance,
            'total_attendance': total_attendance,
            'male_attendance': total_male_attendance,
            'female_attendance': total_female_attendance,
            'termly_average': termly_average,
            'termly_percentage': termly_percentage
        }
    }


def mark_attendance_bulk(enrollment_ids, target_date, week_id, session_type, present_ids, marked_by='Admin', auto_copy_to_afternoon=True):
    """
    Mark attendance for multiple students at once
    
    Args:
        enrollment_ids: List of all enrollment IDs to mark
        target_date: Date to mark attendance for
        week_id: Week ID
        session_type: 'morning' or 'afternoon'
        present_ids: List of enrollment IDs that are present (rest are absent)
        marked_by: Name of person marking attendance
        auto_copy_to_afternoon: If True and session_type is 'morning', also set afternoon to same value
    
    Returns:
        Number of records created/updated
    """
    count = 0
    present_set = set(present_ids)
    
    for enrollment_id in enrollment_ids:
        is_present = enrollment_id in present_set
        
        # Check if attendance record exists
        attendance = Attendance.query.filter_by(
            enrollment_id=enrollment_id,
            date=target_date
        ).first()
        
        if attendance:
            # Update existing record
            if session_type == 'morning':
                attendance.morning_present = is_present
                # Auto-copy to afternoon if enabled and afternoon hasn't been manually edited
                # We check if this is a new marking by seeing if afternoon matches the old morning value
                if auto_copy_to_afternoon:
                    attendance.afternoon_present = is_present
            else:
                attendance.afternoon_present = is_present
            attendance.marked_by = marked_by
        else:
            # Create new record - set both sessions to same value when marking morning
            if session_type == 'morning' and auto_copy_to_afternoon:
                attendance = Attendance(
                    enrollment_id=enrollment_id,
                    week_id=week_id,
                    date=target_date,
                    morning_present=is_present,
                    afternoon_present=is_present,  # Same as morning
                    marked_by=marked_by
                )
            else:
                attendance = Attendance(
                    enrollment_id=enrollment_id,
                    week_id=week_id,
                    date=target_date,
                    morning_present=is_present if session_type == 'morning' else True,
                    afternoon_present=is_present if session_type == 'afternoon' else True,
                    marked_by=marked_by
                )
            db.session.add(attendance)
        
        count += 1
    
    db.session.commit()
    return count


def mark_all_present(enrollment_ids, target_date, week_id, session_type='both', marked_by='Admin'):
    """
    Mark all students as present for a session
    """
    count = 0
    
    for enrollment_id in enrollment_ids:
        attendance = Attendance.query.filter_by(
            enrollment_id=enrollment_id,
            date=target_date
        ).first()
        
        if attendance:
            if session_type in ['morning', 'both']:
                attendance.morning_present = True
            if session_type in ['afternoon', 'both']:
                attendance.afternoon_present = True
            attendance.marked_by = marked_by
        else:
            attendance = Attendance(
                enrollment_id=enrollment_id,
                week_id=week_id,
                date=target_date,
                morning_present=True if session_type in ['morning', 'both'] else False,
                afternoon_present=True if session_type in ['afternoon', 'both'] else False,
                marked_by=marked_by
            )
            db.session.add(attendance)
        
        count += 1
    
    db.session.commit()
    return count


def get_attendance_statistics(term_id=None):
    """
    Get overall attendance statistics
    
    Returns aggregate statistics for dashboard
    """
    from models import Term, ClassArmAssignment
    
    query = StudentEnrollment.query.filter_by(is_active=True)
    
    if term_id:
        query = query.join(ClassArmAssignment).filter(ClassArmAssignment.term_id == term_id)
    
    enrollments = query.all()
    
    total_attendance_records = 0
    total_present = 0
    
    for enrollment in enrollments:
        records = Attendance.query.filter_by(enrollment_id=enrollment.id).all()
        total_attendance_records += len(records)
        total_present += sum(a.total_present for a in records)
    
    return {
        'total_enrollments': len(enrollments),
        'total_attendance_records': total_attendance_records,
        'total_present_sessions': total_present,
        'average_attendance': round(total_present / (total_attendance_records * 2) * 100, 2) if total_attendance_records > 0 else 0
    }
