import re
import sqlite3
import os
from app import app
from models import db
# Ensure new models are loaded for the table creation
import models.user_models

def fix_files():
    print("--- 1. Patching models/models.py ---")
    path_models = 'models/models.py'
    with open(path_models, 'r') as f:
        content = f.read()
    
    # Flexible regex to find "class User" regardless of spacing or inheritance
    # Matches "class User(db.Model):", "class User (db.Model):", etc.
    pattern = r'^\s*class\s+User\s*[\(<]'
    
    if re.search(pattern, content, re.MULTILINE):
        # Rename the class so SQLAlchemy ignores it
        new_content = re.sub(pattern, 'class User_Old_Disabled(object): # WAS: class User', content, flags=re.MULTILINE)
        with open(path_models, 'w') as f:
            f.write(new_content)
        print("SUCCESS: Disabled old User class in models.py")
    else:
        print("NOTICE: 'class User' not found in models.py (might already be fixed).")

    print("\n--- 2. Patching models/__init__.py ---")
    path_init = 'models/__init__.py'
    with open(path_init, 'r') as f:
        init_content = f.read()
    
    # Remove 'User' from the 'from .models' import list
    # Matches "User," or ", User" or "User" in the import block
    init_content = re.sub(r'from \.models import \(.*?\)', 
                          lambda m: m.group(0).replace('User,', '').replace(', User', ''), 
                          init_content, flags=re.DOTALL)
    
    # Fix the bottom import to use "User" instead of "User as UserNew"
    init_content = init_content.replace('from models.user_models import User as UserNew', 'from models.user_models import User')
    
    with open(path_init, 'w') as f:
        f.write(init_content)
    print("SUCCESS: Cleaned up imports in __init__.py")

def rebuild_db():
    print("\n--- 3. Rebuilding Database Tables ---")
    # Drop the bad table
    conn = sqlite3.connect('school.db')
    conn.execute('DROP TABLE IF EXISTS users')
    conn.commit()
    conn.close()
    print("Dropped old 'users' table.")

    # Create new table using the correct model
    with app.app_context():
        # Force loading the new model
        from models.user_models import User
        print(f"Using User model with columns: {User.__table__.columns.keys()}")
        db.create_all()
        print("Created new tables successfully.")

if __name__ == "__main__":
    # Temporarily disable init_db check in app.py to prevent startup crash
    os.system("sed -i 's/init_db(app)/pass # init_db(app)/' app.py")
    
    try:
        fix_files()
        rebuild_db()
    finally:
        # Restore app.py
        os.system("sed -i 's/pass # init_db(app)/init_db(app)/' app.py")
