"""
Cleanup script for gen_subjects table.
Use this to clear out unwanted subjects.

Usage:
    python cleanup_gen_subjects.py
"""

import sqlite3
import sys
import os

def show_subjects(db_path):
    """Show current gen_subjects"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("\n" + "=" * 60)
    print("CURRENT GEN_SUBJECTS")
    print("=" * 60)
    
    # SSS Subjects
    print("\n📘 SSS SUBJECTS:")
    cursor.execute("""
        SELECT id, name, short_name, category, is_active 
        FROM gen_subjects 
        WHERE school_level = 'sss'
        ORDER BY name
    """)
    sss = cursor.fetchall()
    if sss:
        for row in sss:
            status = "✓" if row[4] else "✗"
            print(f"   {status} [{row[0]}] {row[1]} ({row[3] or 'N/A'})")
    else:
        print("   (none)")
    
    # JSS Subjects
    print("\n📗 JSS SUBJECTS:")
    cursor.execute("""
        SELECT id, name, short_name, category, is_active 
        FROM gen_subjects 
        WHERE school_level = 'jss'
        ORDER BY name
    """)
    jss = cursor.fetchall()
    if jss:
        for row in jss:
            status = "✓" if row[4] else "✗"
            print(f"   {status} [{row[0]}] {row[1]} ({row[3] or 'N/A'})")
    else:
        print("   (none)")
    
    conn.close()
    return len(sss), len(jss)


def cleanup_options(db_path):
    """Show cleanup options"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("\n" + "=" * 60)
    print("CLEANUP OPTIONS")
    print("=" * 60)
    print("\n1. Delete ALL SSS subjects (start fresh)")
    print("2. Delete ALL JSS subjects (start fresh)")
    print("3. Delete ALL subjects (both levels)")
    print("4. Delete only inactive subjects")
    print("5. Exit without changes")
    
    choice = input("\nEnter choice (1-5): ").strip()
    
    if choice == '1':
        cursor.execute("DELETE FROM gen_subjects WHERE school_level = 'sss'")
        # Also clear related configs
        cursor.execute("DELETE FROM gen_subject_configs WHERE school_level = 'sss'")
        conn.commit()
        print("\n✓ Deleted all SSS subjects")
    elif choice == '2':
        cursor.execute("DELETE FROM gen_subjects WHERE school_level = 'jss'")
        cursor.execute("DELETE FROM gen_subject_configs WHERE school_level = 'jss'")
        conn.commit()
        print("\n✓ Deleted all JSS subjects")
    elif choice == '3':
        cursor.execute("DELETE FROM gen_subjects")
        cursor.execute("DELETE FROM gen_subject_configs")
        conn.commit()
        print("\n✓ Deleted all subjects from both levels")
    elif choice == '4':
        cursor.execute("DELETE FROM gen_subjects WHERE is_active = 0")
        conn.commit()
        print("\n✓ Deleted inactive subjects")
    else:
        print("\nNo changes made.")
    
    conn.close()


def add_jss_subjects(db_path):
    """Add standard JSS subjects"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    jss_subjects = [
        ('Mathematics', 'MATH', 'core'),
        ('English Language', 'ENG', 'core'),
        ('Basic Science', 'B.SCI', 'core'),
        ('Basic Technology', 'B.TECH', 'core'),
        ('Social Studies', 'SOC', 'core'),
        ('Civic Education', 'CIVIC', 'core'),
        ('Computer Studies', 'COMP', 'core'),
        ('Agricultural Science', 'AGRIC', 'core'),
        ('Home Economics', 'H.ECON', 'vocational'),
        ('Physical Health Education', 'PHE', 'core'),
        ('Christian Religious Studies', 'CRS', 'core'),
        ('Islamic Religious Studies', 'IRS', 'core'),
        ('French', 'FRE', 'core'),
        ('Yoruba', 'YOR', 'core'),
        ('Igbo', 'IGB', 'core'),
        ('Hausa', 'HAU', 'core'),
        ('Music', 'MUS', 'arts'),
        ('Fine Art', 'ART', 'arts'),
        ('Business Studies', 'BUS', 'commercial'),
    ]
    
    print("\nAdding standard JSS subjects...")
    added = 0
    for name, short_name, category in jss_subjects:
        try:
            cursor.execute("""
                INSERT INTO gen_subjects (name, short_name, school_level, category, is_active)
                VALUES (?, ?, 'jss', ?, 1)
            """, (name, short_name, category))
            added += 1
        except sqlite3.IntegrityError:
            pass  # Already exists
    
    conn.commit()
    conn.close()
    print(f"✓ Added {added} JSS subjects")


def add_sss_subjects(db_path):
    """Add standard SSS subjects"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    sss_subjects = [
        ('Mathematics', 'MATH', 'core'),
        ('English Language', 'ENG', 'core'),
        ('Physics', 'PHY', 'science'),
        ('Chemistry', 'CHEM', 'science'),
        ('Biology', 'BIO', 'science'),
        ('Further Mathematics', 'F.MATH', 'science'),
        ('Agricultural Science', 'AGRIC', 'science'),
        ('Geography', 'GEO', 'arts'),
        ('Economics', 'ECON', 'commercial'),
        ('Government', 'GOVT', 'arts'),
        ('Literature in English', 'LIT', 'arts'),
        ('Christian Religious Studies', 'CRS', 'arts'),
        ('Islamic Religious Studies', 'IRS', 'arts'),
        ('History', 'HIST', 'arts'),
        ('Civic Education', 'CIVIC', 'core'),
        ('Computer Studies', 'COMP', 'core'),
        ('Commerce', 'COMM', 'commercial'),
        ('Accounting', 'ACC', 'commercial'),
        ('Marketing', 'MKT', 'commercial'),
        ('French', 'FRE', 'arts'),
        ('Yoruba', 'YOR', 'arts'),
        ('Music', 'MUS', 'arts'),
        ('Fine Art', 'ART', 'arts'),
        ('Technical Drawing', 'T.DRW', 'vocational'),
        ('Food and Nutrition', 'F&N', 'vocational'),
        ('Data Processing', 'D.PRO', 'commercial'),
    ]
    
    print("\nAdding standard SSS subjects...")
    added = 0
    for name, short_name, category in sss_subjects:
        try:
            cursor.execute("""
                INSERT INTO gen_subjects (name, short_name, school_level, category, is_active)
                VALUES (?, ?, 'sss', ?, 1)
            """, (name, short_name, category))
            added += 1
        except sqlite3.IntegrityError:
            pass  # Already exists
    
    conn.commit()
    conn.close()
    print(f"✓ Added {added} SSS subjects")


if __name__ == '__main__':
    db_path = 'instance/school.db'
    
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        sys.exit(1)
    
    while True:
        sss_count, jss_count = show_subjects(db_path)
        
        print(f"\nTotal: {sss_count} SSS subjects, {jss_count} JSS subjects")
        
        print("\n" + "=" * 60)
        print("ACTIONS")
        print("=" * 60)
        print("1. Cleanup (delete subjects)")
        print("2. Add standard JSS subjects")
        print("3. Add standard SSS subjects")
        print("4. Refresh view")
        print("5. Exit")
        
        action = input("\nEnter action (1-5): ").strip()
        
        if action == '1':
            cleanup_options(db_path)
        elif action == '2':
            add_jss_subjects(db_path)
        elif action == '3':
            add_sss_subjects(db_path)
        elif action == '4':
            continue
        elif action == '5':
            print("\nGoodbye!")
            break
        else:
            print("\nInvalid choice")
