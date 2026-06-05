"""
Migration script to add user management tables
Run this after updating the models
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, User, Teacher

def run_migration():
    with app.app_context():
        # Create all tables (will only create new ones)
        db.create_all()
        print("✓ Database tables created/updated")
        
        # Check if we need to create default admin
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                full_name='Administrator',
                role='admin',
                is_active=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("✓ Default admin user created:")
            print("  Username: admin")
            print("  Password: admin123")
        else:
            print("✓ Admin user already exists")

if __name__ == '__main__':
    run_migration()
    print("\n✓ Migration complete!")
