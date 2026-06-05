"""
Diagnostic script for SSS1 timetable generation issues
"""

import sqlite3
import sys

def diagnose(db_path='instance/school.db'):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("=" * 60)
    print("SSS1 TIMETABLE DIAGNOSTIC")
    print("=" * 60)
    
    # 1. Check SSS1 classes
    print("\n1. SSS1 CLASSES:")
    cursor.execute("""
        SELECT id, class_name, is_active 
        FROM gen_class_configs 
        WHERE class_name = 'SSS1' AND school_level = 'sss'
    """)
    sss1_classes = cursor.fetchall()
    if sss1_classes:
        for row in sss1_classes:
            status = "✓ Active" if row[2] else "✗ Inactive"
            print(f"   [{row[0]}] {row[1]} - {status}")
    else:
        print("   ❌ NO SSS1 CLASSES FOUND!")
    
    # 2. Check SSS teachers
    print("\n2. SSS TEACHERS:")
    cursor.execute("""
        SELECT id, name, is_active 
        FROM gen_teachers 
        WHERE school_level = 'sss' AND is_active = 1
    """)
    teachers = cursor.fetchall()
    print(f"   Found {len(teachers)} active SSS teachers")
    
    # 3. Check SSS subjects
    print("\n3. SSS SUBJECTS (gen_subjects):")
    cursor.execute("""
        SELECT id, name, is_active 
        FROM gen_subjects 
        WHERE school_level = 'sss' AND is_active = 1
    """)
    subjects = cursor.fetchall()
    if subjects:
        for row in subjects:
            print(f"   [{row[0]}] {row[1]}")
    else:
        print("   ❌ NO SSS SUBJECTS FOUND!")
    
    # 4. Check subject configs
    print("\n4. SSS SUBJECT CONFIGS:")
    cursor.execute("""
        SELECT sc.id, s.name, sc.periods_per_week, sc.is_active
        FROM gen_subject_configs sc
        LEFT JOIN gen_subjects s ON sc.subject_id = s.id
        WHERE sc.school_level = 'sss'
    """)
    configs = cursor.fetchall()
    if configs:
        for row in configs:
            status = "✓" if row[3] else "✗"
            subj_name = row[1] if row[1] else f"[MISSING SUBJECT ID]"
            print(f"   {status} {subj_name}: {row[2]} periods/week")
    else:
        print("   ❌ NO SUBJECT CONFIGS FOUND!")
    
    # 5. Check teacher assignments for SSS1
    print("\n5. SSS1 TEACHER ASSIGNMENTS:")
    cursor.execute("""
        SELECT ta.id, t.name, c.class_name, s.name as subject_name
        FROM gen_teacher_assignments ta
        JOIN gen_teachers t ON ta.teacher_id = t.id
        JOIN gen_class_configs c ON ta.class_config_id = c.id
        LEFT JOIN gen_subjects s ON ta.subject_id = s.id
        WHERE c.class_name = 'SSS1' AND ta.is_active = 1
    """)
    assignments = cursor.fetchall()
    if assignments:
        for row in assignments:
            subj = row[3] if row[3] else "[MISSING SUBJECT]"
            print(f"   {row[1]} → {row[2]} ({subj})")
    else:
        print("   ❌ NO SSS1 TEACHER ASSIGNMENTS!")
    
    # 6. Check if subject_ids in assignments are valid
    print("\n6. CHECKING FOR ORPHANED SUBJECT REFERENCES:")
    cursor.execute("""
        SELECT ta.id, ta.subject_id, t.name
        FROM gen_teacher_assignments ta
        JOIN gen_teachers t ON ta.teacher_id = t.id
        WHERE ta.subject_id NOT IN (SELECT id FROM gen_subjects WHERE is_active = 1)
        AND ta.is_active = 1
    """)
    orphaned = cursor.fetchall()
    if orphaned:
        print(f"   ⚠️ Found {len(orphaned)} assignments with invalid subject_id:")
        for row in orphaned:
            print(f"      Assignment {row[0]}: subject_id={row[1]} (Teacher: {row[2]})")
    else:
        print("   ✓ All assignments have valid subject references")
    
    # 7. Check timetable results
    print("\n7. EXISTING TIMETABLE RESULTS:")
    cursor.execute("""
        SELECT class_name, COUNT(*) 
        FROM gen_timetable_results 
        WHERE school_level = 'sss'
        GROUP BY class_name
        ORDER BY class_name
    """)
    results = cursor.fetchall()
    if results:
        for row in results:
            print(f"   {row[0]}: {row[1]} slots")
    else:
        print("   No timetable results yet")
    
    # 8. Compare all SSS classes
    print("\n8. ALL SSS CLASSES:")
    cursor.execute("""
        SELECT class_name, arm_names, is_active 
        FROM gen_class_configs 
        WHERE school_level = 'sss'
        ORDER BY class_name
    """)
    all_classes = cursor.fetchall()
    for row in all_classes:
        status = "✓" if row[2] else "✗"
        print(f"   {status} {row[0]} Arms: {row[1]}")
    
    # 9. Check orphaned class subject configs
    print("\n9. ORPHANED CLASS SUBJECT CONFIGS:")
    cursor.execute("""
        SELECT csc.id, csc.subject_id, c.class_name
        FROM gen_class_subject_configs csc
        JOIN gen_class_configs c ON csc.class_config_id = c.id
        WHERE csc.subject_id NOT IN (SELECT id FROM gen_subjects WHERE is_active = 1)
        AND csc.is_active = 1
    """)
    orphaned_csc = cursor.fetchall()
    if orphaned_csc:
        print(f"   ⚠️ Found {len(orphaned_csc)} class configs with invalid subject_id:")
        for row in orphaned_csc:
            print(f"      Config {row[0]}: subject_id={row[1]} (Class: {row[2]})")
    else:
        print("   ✓ All class subject configs have valid subject references")
    
    conn.close()
    
    print("\n" + "=" * 60)
    print("RECOMMENDATIONS:")
    print("=" * 60)
    
    if not sss1_classes:
        print("• Add SSS1 classes in Generator → SSS → Classes")
    if not subjects:
        print("• Add SSS subjects in Generator → SSS → Subjects")
    if not configs:
        print("• Configure subject periods in Generator → SSS → Subjects → Save Configuration")
    if not assignments:
        print("• Create teacher assignments in Generator → SSS → Assignments")
    if orphaned:
        print("• Run full_cleanup.py to remove orphaned references")
        print("• Then re-assign teachers to subjects")
    if orphaned_csc:
        print("• Run full_cleanup.py to remove orphaned class subject configs")


if __name__ == '__main__':
    db_path = 'instance/school.db'
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    diagnose(db_path)
