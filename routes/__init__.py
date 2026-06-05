"""
Routes package initialization
"""
from .auth import auth_bp
from .main import main_bp
from .academics import academics_bp
from .attendance import attendance_bp
from .results import results_bp
from .reports import reports_bp
from .settings import settings_bp
from .subjects import subjects_bp
from .timetable import timetable_bp
from .promotion import promotion_bp
from .users import users_bp

__all__ = [
    'auth_bp', 'main_bp', 'academics_bp', 
    'attendance_bp', 'results_bp', 'reports_bp',
    'settings_bp', 'subjects_bp', 'timetable_bp', 'promotion_bp',
    'users_bp'
]
