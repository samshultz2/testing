"""
Script to populate the database with test WAEC and JAMB results.
Run this from the project directory: python populate_test_results.py
Delete the data after testing with: python populate_test_results.py --delete
"""

import sys
import random
from app import create_app, db
from models import Student, WAECResult, JAMBResult

# WAEC Subjects
WAEC_SUBJECTS = [
    'English Language', 'Mathematics', 'Civic Education', 
    'Biology', 'Chemistry', 'Physics',
    'Economics', 'Government', 'Literature in English',
    'Agricultural Science', 'Geography', 'Commerce',
    'Financial Accounting', 'Further Mathematics', 'Computer Studies'
]

# WAEC Grades
WAEC_GRADES = ['A1', 'B2', 'B3', 'C4', 'C5', 'C6', 'D7', 'E8', 'F9']

# JAMB Subjects
JAMB_SUBJECTS = [
    'Use of English', 'Mathematics', 'Physics', 'Chemistry', 'Biology',
    'Economics', 'Government', 'Literature', 'Commerce', 'Accounting',
    'Geography', 'Agricultural Science', 'Computer Studies'
]


def get_grade_for_student(student_level):
    """Generate a grade based on student performance level (0-100)"""
    rand = random.random() * 100
    
    if student_level >= 80:  # Excellent student
        if rand < 40: return 'A1'
        elif rand < 70: return 'B2'
        elif rand < 85: return 'B3'
        elif rand < 95: return 'C4'
        else: return 'C5'
    elif student_level >= 60:  # Good student
        if rand < 15: return 'A1'
        elif rand < 35: return 'B2'
        elif rand < 55: return 'B3'
        elif rand < 70: return 'C4'
        elif rand < 82: return 'C5'
        elif rand < 92: return 'C6'
        else: return 'D7'
    elif student_level >= 40:  # Average student
        if rand < 5: return 'A1'
        elif rand < 15: return 'B2'
        elif rand < 30: return 'B3'
        elif rand < 45: return 'C4'
        elif rand < 60: return 'C5'
        elif rand < 75: return 'C6'
        elif rand < 88: return 'D7'
        else: return 'E8'
    else:  # Struggling student
        if rand < 5: return 'B3'
        elif rand < 15: return 'C4'
        elif rand < 30: return 'C5'
        elif rand < 45: return 'C6'
        elif rand < 65: return 'D7'
        elif rand < 85: return 'E8'
        else: return 'F9'


def get_subject_score(student_level, is_strong_subject=False):
    """Generate individual JAMB subject score (0-100)"""
    if is_strong_subject:
        base = student_level * 0.9
        variation = random.randint(-10, 15)
    else:
        base = student_level * 0.75
        variation = random.randint(-15, 10)
    
    score = int(base + variation)
    return max(10, min(100, score))


def get_existing_students():
    """Get all existing students from database"""
    students = Student.query.filter_by(is_active=True).all()
    print(f"Found {len(students)} existing students in database")
    return students


def populate_waec_results(students, year=2026):
    """Populate WAEC results for students"""
    count = 0
    skipped = 0
    
    for student in students:
        # Check if student already has WAEC results for this year
        existing = WAECResult.query.filter_by(
            student_id=student.id, 
            exam_year=year
        ).first()
        
        if existing:
            skipped += 1
            continue
        
        # Assign a performance level to each student (consistency across subjects)
        student_level = random.randint(20, 95)
        
        # Select 9 subjects for each student (typical WAEC)
        core_subjects = ['English Language', 'Mathematics', 'Civic Education']
        other_subjects = [s for s in WAEC_SUBJECTS if s not in core_subjects]
        selected_subjects = core_subjects + random.sample(other_subjects, 6)
        
        for subject in selected_subjects:
            grade = get_grade_for_student(student_level)
            
            result = WAECResult(
                student_id=student.id,
                exam_year=year,
                subject=subject,
                grade=grade
            )
            db.session.add(result)
            count += 1
    
    db.session.commit()
    print(f"Created {count} WAEC results for year {year} (skipped {skipped} students with existing data)")


def populate_jamb_results(students, year=2024):
    """Populate JAMB results for students"""
    count = 0
    skipped = 0
    
    for student in students:
        # Check if student already has JAMB results for this year
        existing = JAMBResult.query.filter_by(
            student_id=student.id, 
            exam_year=year
        ).first()
        
        if existing:
            skipped += 1
            continue
        
        # Assign a performance level
        student_level = random.randint(25, 95)
        
        # Use of English is compulsory, pick 3 others
        subject1 = 'Use of English'
        other_subjects = [s for s in JAMB_SUBJECTS if s != 'Use of English']
        selected = random.sample(other_subjects, 3)
        
        subject1_score = get_subject_score(student_level, is_strong_subject=True)
        subject2_score = get_subject_score(student_level, is_strong_subject=random.random() > 0.5)
        subject3_score = get_subject_score(student_level)
        subject4_score = get_subject_score(student_level)
        
        total_score = subject1_score + subject2_score + subject3_score + subject4_score
        
        result = JAMBResult(
            student_id=student.id,
            exam_year=year,
            total_score=total_score,
            subject1=subject1,
            subject1_score=subject1_score,
            subject2=selected[0],
            subject2_score=subject2_score,
            subject3=selected[1],
            subject3_score=subject3_score,
            subject4=selected[2],
            subject4_score=subject4_score
        )
        db.session.add(result)
        count += 1
    
    db.session.commit()
    print(f"Created {count} JAMB results for year {year} (skipped {skipped} students with existing data)")


def delete_test_data():
    """Delete all WAEC and JAMB test data"""
    waec_deleted = WAECResult.query.delete()
    jamb_deleted = JAMBResult.query.delete()
    
    db.session.commit()
    print(f"Deleted {waec_deleted} WAEC results")
    print(f"Deleted {jamb_deleted} JAMB results")


def main():
    app = create_app()
    
    with app.app_context():
        if len(sys.argv) > 1 and sys.argv[1] == '--delete':
            print("Deleting all WAEC and JAMB data...")
            delete_test_data()
            print("Done!")
        else:
            print("Populating test data...")
            print("-" * 40)
            
            # Get existing students
            students = get_existing_students()
            
            if not students:
                print("ERROR: No students found in database!")
                print("Please add some students first before running this script.")
                return
            
            # Populate WAEC for 2023 and 2024
            populate_waec_results(students, 2023)
            populate_waec_results(students, 2024)
            
            # Populate JAMB for 2023 and 2024
            populate_jamb_results(students, 2023)
            populate_jamb_results(students, 2024)
            
            print("-" * 40)
            print("Test data populated successfully!")
            print("\nTo delete all WAEC/JAMB data later, run:")
            print("  python populate_test_results.py --delete")


if __name__ == '__main__':
    main()
