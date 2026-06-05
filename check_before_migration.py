"""
Safety check script - Run BEFORE migration to verify everything is safe.
This script only READS the database, makes NO changes.

Usage:
    python check_before_migration.py
"""

import sqlite3
import sys
import os

def check_database(db_path):
    """Check database state before migration"""
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("=" * 60)
    print("PRE-MIGRATION SAFETY CHECK")
    print("=" * 60)
    
    issues = []
    warnings = []
    
    try:
        # Check 1: Subjects table exists
        print("\n1. Checking subjects table...")
        cursor.execute("SELECT COUNT(*) FROM subjects WHERE is_active = 1")
        subject_count = cursor.fetchone()[0]
        print(f"   ✓ Found {subject_count} active subjects")
        
        # Check 2: gen_subjects doesn't exist yet (or is empty)
        print("\n2. Checking gen_subjects table...")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='gen_subjects'")
        if cursor.fetchone():
            cursor.execute("SELECT COUNT(*) FROM gen_subjects")
            gen_count = cursor.fetchone()[0]
            if gen_count > 0:
                warnings.append(f"gen_subjects already has {gen_count} records - migration may skip copying")
            print(f"   ⚠ gen_subjects exists with {gen_count} records")
        else:
            print("   ✓ gen_subjects doesn't exist yet (will be created)")
        
        # Check 3: Existing timetable data
        print("\n3. Checking existing timetable data...")
        
        tables_to_check = [
            ('gen_teachers', 'Teachers'),
            ('gen_class_configs', 'Classes'),
            ('gen_subject_configs', 'Subject Configs'),
            ('gen_teacher_assignments', 'Teacher Assignments'),
            ('gen_timetable_results', 'Generated Timetables'),
        ]
        
        for table, name in tables_to_check:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                if count > 0:
                    print(f"   • {name}: {count} records")
                else:
                    print(f"   • {name}: empty")
            except:
                print(f"   • {name}: table doesn't exist")
        
        # Check 4: Subject references in generator tables
        print("\n4. Checking subject references...")
        
        try:
            cursor.execute("""
                SELECT COUNT(DISTINCT subject_id) FROM gen_subject_configs
            """)
            config_subjects = cursor.fetchone()[0]
            print(f"   • Subjects in configs: {config_subjects}")
        except:
            print("   • No subject configs yet")
        
        try:
            cursor.execute("""
                SELECT COUNT(DISTINCT subject_id) FROM gen_teacher_assignments
            """)
            assignment_subjects = cursor.fetchone()[0]
            print(f"   • Subjects in assignments: {assignment_subjects}")
        except:
            print("   • No assignments yet")
        
        try:
            cursor.execute("""
                SELECT COUNT(DISTINCT subject_id) FROM gen_timetable_results WHERE subject_id IS NOT NULL
            """)
            result_subjects = cursor.fetchone()[0]
            print(f"   • Subjects in timetables: {result_subjects}")
        except:
            print("   • No timetable results yet")
        
        # Check 5: Verify subject names are unique (for mapping)
        print("\n5. Checking for duplicate subject names...")
        cursor.execute("""
            SELECT name, COUNT(*) as cnt FROM subjects 
            WHERE is_active = 1 
            GROUP BY name HAVING cnt > 1
        """)
        duplicates = cursor.fetchall()
        if duplicates:
            for name, cnt in duplicates:
                issues.append(f"Duplicate subject name: '{name}' ({cnt} times)")
            print(f"   ❌ Found {len(duplicates)} duplicate names")
        else:
            print("   ✓ All subject names are unique")
        
        # Summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        
        if issues:
            print("\n❌ ISSUES FOUND (fix before migrating):")
            for issue in issues:
                print(f"   • {issue}")
        
        if warnings:
            print("\n⚠ WARNINGS (migration will handle these):")
            for warning in warnings:
                print(f"   • {warning}")
        
        if not issues:
            print("\n✅ DATABASE IS SAFE TO MIGRATE")
            print("\nYour existing data:")
            print(f"   • {subject_count} academic subjects (will NOT be modified)")
            print("   • SSS timetable data will be preserved")
            print("   • A new gen_subjects table will be created")
            print("\nRun: python migrate_school_level.py")
        else:
            print("\n❌ FIX ISSUES BEFORE MIGRATING")
        
        return len(issues) == 0
        
    except Exception as e:
        print(f"\n❌ Error during check: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    db_path = 'instance/school.db'
    
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    
    check_database(db_path)
