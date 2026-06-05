"""
Full cleanup script - clears ALL orphaned data from generator tables.
Run this after deleting subjects to fix count mismatches.

Usage:
    python full_cleanup.py
"""

import sqlite3
import sys
import os

def cleanup_database(db_path):
    """Clean up all orphaned references"""
    
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("=" * 60)
    print("FULL GENERATOR CLEANUP")
    print("=" * 60)
    
    try:
        # Show current state
        print("\n📊 CURRENT STATE:")
        
        cursor.execute("SELECT COUNT(*) FROM gen_subjects WHERE is_active = 1 AND school_level = 'sss'")
        print(f"   SSS Subjects: {cursor.fetchone()[0]}")
        
        cursor.execute("SELECT COUNT(*) FROM gen_subjects WHERE is_active = 1 AND school_level = 'jss'")
        print(f"   JSS Subjects: {cursor.fetchone()[0]}")
        
        cursor.execute("SELECT COUNT(*) FROM gen_subject_configs WHERE is_active = 1 AND school_level = 'sss'")
        print(f"   SSS Subject Configs: {cursor.fetchone()[0]}")
        
        cursor.execute("SELECT COUNT(*) FROM gen_subject_configs WHERE is_active = 1 AND school_level = 'jss'")
        print(f"   JSS Subject Configs: {cursor.fetchone()[0]}")
        
        cursor.execute("SELECT COUNT(*) FROM gen_teacher_assignments WHERE is_active = 1")
        print(f"   Teacher Assignments: {cursor.fetchone()[0]}")
        
        cursor.execute("SELECT COUNT(*) FROM gen_class_subject_configs WHERE is_active = 1")
        print(f"   Class Subject Configs: {cursor.fetchone()[0]}")
        
        # Cleanup orphaned configs
        print("\n🧹 CLEANING UP...")
        
        # 1. Delete subject configs that reference non-existent subjects
        cursor.execute("""
            DELETE FROM gen_subject_configs 
            WHERE subject_id NOT IN (SELECT id FROM gen_subjects WHERE is_active = 1)
        """)
        print(f"   ✓ Removed {cursor.rowcount} orphaned subject configs")
        
        # 2. Delete class subject configs that reference non-existent subjects
        cursor.execute("""
            DELETE FROM gen_class_subject_configs 
            WHERE subject_id NOT IN (SELECT id FROM gen_subjects WHERE is_active = 1)
        """)
        print(f"   ✓ Removed {cursor.rowcount} orphaned class subject configs")
        
        # 3. Delete teacher assignments that reference non-existent subjects
        cursor.execute("""
            DELETE FROM gen_teacher_assignments 
            WHERE subject_id NOT IN (SELECT id FROM gen_subjects WHERE is_active = 1)
        """)
        print(f"   ✓ Removed {cursor.rowcount} orphaned teacher assignments")
        
        # 4. Delete teacher subjects that reference non-existent subjects
        cursor.execute("""
            DELETE FROM gen_teacher_subjects 
            WHERE subject_id NOT IN (SELECT id FROM gen_subjects WHERE is_active = 1)
        """)
        print(f"   ✓ Removed {cursor.rowcount} orphaned teacher subjects")
        
        # 5. Delete stream subjects that reference non-existent subjects
        cursor.execute("""
            DELETE FROM gen_stream_subjects 
            WHERE subject_id NOT IN (SELECT id FROM gen_subjects WHERE is_active = 1)
        """)
        print(f"   ✓ Removed {cursor.rowcount} orphaned stream subjects")
        
        # 6. Clean up timetable results with non-existent subjects
        cursor.execute("""
            UPDATE gen_timetable_results 
            SET subject_id = NULL 
            WHERE subject_id NOT IN (SELECT id FROM gen_subjects WHERE is_active = 1)
            AND subject_id IS NOT NULL
        """)
        print(f"   ✓ Cleared {cursor.rowcount} timetable entries with missing subjects")
        
        conn.commit()
        
        # Show final state
        print("\n📊 AFTER CLEANUP:")
        
        cursor.execute("SELECT COUNT(*) FROM gen_subjects WHERE is_active = 1 AND school_level = 'sss'")
        print(f"   SSS Subjects: {cursor.fetchone()[0]}")
        
        cursor.execute("SELECT COUNT(*) FROM gen_subjects WHERE is_active = 1 AND school_level = 'jss'")
        print(f"   JSS Subjects: {cursor.fetchone()[0]}")
        
        cursor.execute("SELECT COUNT(*) FROM gen_subject_configs WHERE is_active = 1 AND school_level = 'sss'")
        print(f"   SSS Subject Configs: {cursor.fetchone()[0]}")
        
        cursor.execute("SELECT COUNT(*) FROM gen_subject_configs WHERE is_active = 1 AND school_level = 'jss'")
        print(f"   JSS Subject Configs: {cursor.fetchone()[0]}")
        
        cursor.execute("SELECT COUNT(*) FROM gen_teacher_assignments WHERE is_active = 1")
        print(f"   Teacher Assignments: {cursor.fetchone()[0]}")
        
        print("\n" + "=" * 60)
        print("✅ CLEANUP COMPLETE!")
        print("=" * 60)
        print("\nNow restart the app: python app.py")
        
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    db_path = 'instance/school.db'
    
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    
    cleanup_database(db_path)
