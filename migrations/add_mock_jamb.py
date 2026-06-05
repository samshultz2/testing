"""
Database Migration Script for PosyHub
Adds Mock JAMB tables

Run: python migrations/add_mock_jamb.py
"""
import os
import sqlite3

def get_db_path():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, 'instance', 'school.db')

def run_migration():
    db_path = get_db_path()
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return False
    
    print(f"Connecting to: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mock_jamb_exams'")
        if cursor.fetchone():
            print("Mock JAMB tables already exist.")
            return True
        
        print("Creating Mock JAMB tables...")
        
        cursor.execute('''
            CREATE TABLE mock_jamb_exams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL,
                exam_number INTEGER NOT NULL,
                session_id INTEGER NOT NULL,
                exam_date DATE NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                is_completed BOOLEAN DEFAULT 0,
                description TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES academic_sessions(id),
                UNIQUE (session_id, exam_number)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE mock_jamb_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                mock_exam_id INTEGER NOT NULL,
                total_score INTEGER NOT NULL,
                subject1 VARCHAR(50), subject1_score INTEGER,
                subject2 VARCHAR(50), subject2_score INTEGER,
                subject3 VARCHAR(50), subject3_score INTEGER,
                subject4 VARCHAR(50), subject4_score INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(id),
                FOREIGN KEY (mock_exam_id) REFERENCES mock_jamb_exams(id) ON DELETE CASCADE,
                UNIQUE (student_id, mock_exam_id)
            )
        ''')
        
        cursor.execute('CREATE INDEX idx_mock_results_student ON mock_jamb_results(student_id)')
        cursor.execute('CREATE INDEX idx_mock_results_exam ON mock_jamb_results(mock_exam_id)')
        
        conn.commit()
        print("✅ Migration completed!")
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error: {e}")
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    run_migration()
