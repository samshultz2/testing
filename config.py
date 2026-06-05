"""
Configuration settings for PosyHub Student Management System
"""
import os
from datetime import timedelta


class Config:
    """Base configuration class"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'posyhub-student-management-secret-key-2024'
    
    # Database configuration
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'school.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Application settings
    APP_NAME = "PosyHub Student Manager"
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD') or "posyhubcomng"
    
    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    
    # Pagination
    STUDENTS_PER_PAGE = 20
    
    # Upload settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    ALLOWED_EXTENSIONS = {'xlsx', 'xls'}


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
