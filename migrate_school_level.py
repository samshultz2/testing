"""
Migration script for FULL JSS/SSS isolation in timetable generator.
Creates gen_subjects table and migrates existing data.

Usage:
    python migrate_school_level.py
"""

import sqlite3
import sys
import os

def migrate_database(db_path):
    """Add school_level columns and create gen_subjects table"""
    
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # ============================================================
        # STEP 1: Create gen_subjects table
        # ============================================================
        print("\n1. Creating gen_subjects table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gen_subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL,
                short_name VARCHAR(20),
                school_level VARCHAR(10) DEFAULT 'sss',
                category VARCHAR(50),
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(name, school_level)
            )
        """)
        print("  ✓ gen_subjects table created")
        
        # ============================================================
        # STEP 2: Copy existing subjects to gen_subjects for SSS
        # ============================================================
        print("\n2. Copying existing subjects to gen_subjects (as SSS)...")
        cursor.execute("""
            INSERT OR IGNORE INTO gen_subjects (name, short_name, school_level, category, is_active)
            SELECT name, short_name, 'sss', category, is_active FROM subjects WHERE is_active = 1
        """)
        copied = cursor.rowcount
        print(f"  ✓ Copied {copied} subjects to SSS level")
        
        # ============================================================
        # STEP 3: Add school_level to tables that need it
        # ============================================================
        tables_to_migrate = [
            'gen_teachers',
            'gen_class_configs',
            'gen_timetable_rules',
            'gen_timetable_results',
            'gen_subject_configs'
        ]
        
        print("\n3. Adding school_level column to tables...")
        for table in tables_to_migrate:
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'school_level' not in columns:
                print(f"  Adding school_level to {table}...")
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN school_level VARCHAR(10) DEFAULT 'sss'")
                cursor.execute(f"UPDATE {table} SET school_level = 'sss' WHERE school_level IS NULL")
                print(f"  ✓ {table} updated")
            else:
                print(f"  - {table} already has school_level column")
        
        # ============================================================
        # STEP 4: Update foreign keys to point to gen_subjects
        # ============================================================
        print("\n4. Updating subject references...")
        
        # Get mapping from old subject IDs to new gen_subject IDs
        cursor.execute("""
            SELECT s.id as old_id, g.id as new_id 
            FROM subjects s 
            JOIN gen_subjects g ON s.name = g.name AND g.school_level = 'sss'
        """)
        subject_mapping = {row[0]: row[1] for row in cursor.fetchall()}
        
        if subject_mapping:
            # Update gen_subject_configs
            for old_id, new_id in subject_mapping.items():
                cursor.execute("""
                    UPDATE gen_subject_configs SET subject_id = ? WHERE subject_id = ?
                """, (new_id, old_id))
            
            # Update gen_teacher_subjects
            for old_id, new_id in subject_mapping.items():
                cursor.execute("""
                    UPDATE gen_teacher_subjects SET subject_id = ? WHERE subject_id = ?
                """, (new_id, old_id))
            
            # Update gen_teacher_assignments  
            for old_id, new_id in subject_mapping.items():
                cursor.execute("""
                    UPDATE gen_teacher_assignments SET subject_id = ? WHERE subject_id = ?
                """, (new_id, old_id))
            
            # Update gen_timetable_results
            for old_id, new_id in subject_mapping.items():
                cursor.execute("""
                    UPDATE gen_timetable_results SET subject_id = ? WHERE subject_id = ?
                """, (new_id, old_id))
            
            # Update gen_class_subject_configs
            for old_id, new_id in subject_mapping.items():
                cursor.execute("""
                    UPDATE gen_class_subject_configs SET subject_id = ? WHERE subject_id = ?
                """, (new_id, old_id))
            
            # Update gen_stream_subjects
            for old_id, new_id in subject_mapping.items():
                cursor.execute("""
                    UPDATE gen_stream_subjects SET subject_id = ? WHERE subject_id = ?
                """, (new_id, old_id))
            
            print(f"  ✓ Updated {len(subject_mapping)} subject references")
        else:
            print("  - No subject mappings needed")
        
        conn.commit()
        
        print("\n" + "=" * 50)
        print("✓ Migration completed successfully!")
        print("=" * 50)
        print("\nYour existing SSS data has been preserved.")
        print("JSS and SSS are now COMPLETELY ISOLATED:")
        print("  - Separate subjects for each level")
        print("  - Separate teachers for each level")
        print("  - Separate classes for each level")
        print("  - Separate timetables for each level")
        print("\nTo add JSS subjects, go to:")
        print("  Timetable Generator → JSS → Subjects → Add Subject")
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"\n✗ Migration failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    # Default database path
    db_path = 'instance/school.db'
    
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    
    print("=" * 50)
    print("FULL JSS/SSS Isolation Migration")
    print("=" * 50)
    print(f"\nDatabase: {db_path}")
    print("\nThis will:")
    print("  1. Create gen_subjects table (separate from academic subjects)")
    print("  2. Copy existing subjects as SSS subjects")
    print("  3. Add school_level to all generator tables")
    print("  4. Update all references to use gen_subjects")
    print("\nExisting SSS data will be preserved.\n")
    
    confirm = input("Continue? (y/n): ").lower().strip()
    if confirm == 'y':
        migrate_database(db_path)
    else:
        print("Migration cancelled.")
