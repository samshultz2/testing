"""
Configuration settings for PosyHub Student Management System
"""
import os
import secrets
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Load settings from a .env file in the project root (if python-dotenv is
# installed). Real OS environment variables still take precedence.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, '.env'))
except Exception:
    pass


def _load_secret_key():
    """
    Use SECRET_KEY from the environment when set; otherwise persist a random key
    in the instance folder so sessions survive restarts without shipping a
    hard-coded secret in source.
    """
    env_key = os.environ.get('SECRET_KEY')
    if env_key:
        return env_key
    key_path = os.path.join(BASE_DIR, 'instance', '.secret_key')
    try:
        if os.path.exists(key_path):
            with open(key_path) as f:
                saved = f.read().strip()
                if saved:
                    return saved
        os.makedirs(os.path.dirname(key_path), exist_ok=True)
        new_key = secrets.token_hex(32)
        with open(key_path, 'w') as f:
            f.write(new_key)
        try:
            os.chmod(key_path, 0o600)
        except Exception:
            pass
        return new_key
    except Exception:
        # Last resort for read-only environments — still random per process.
        return secrets.token_hex(32)


def _as_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


class Config:
    """Base configuration class"""
    SECRET_KEY = _load_secret_key()

    # Database configuration
    BASE_DIR = BASE_DIR
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'school.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Application settings
    APP_NAME = "PosyHub Student Manager"
    # Legacy shared-password login (kept for backwards compatibility). Set
    # ADMIN_PASSWORD via the environment in production and disable legacy login
    # once real user accounts exist (ENABLE_LEGACY_LOGIN=0).
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD') or "posyhubcomng"
    ENABLE_LEGACY_LOGIN = _as_bool(os.environ.get('ENABLE_LEGACY_LOGIN'), default=True)

    # Online payments (Paystack). Empty keys => the feature stays disabled.
    PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY', '')
    PAYSTACK_PUBLIC_KEY = os.environ.get('PAYSTACK_PUBLIC_KEY', '')

    # Login throttling
    LOGIN_MAX_ATTEMPTS = int(os.environ.get('LOGIN_MAX_ATTEMPTS', '8'))
    LOGIN_LOCKOUT_MINUTES = int(os.environ.get('LOGIN_LOCKOUT_MINUTES', '15'))

    # Backups
    BACKUP_RETENTION = int(os.environ.get('BACKUP_RETENTION', '10'))

    # Optional Claude-vision OCR fallback (needs ANTHROPIC_API_KEY + the
    # `anthropic` package). Off by default — Tesseract is the default engine.
    OCR_VISION_FALLBACK = _as_bool(os.environ.get('OCR_VISION_FALLBACK'), default=False)
    OCR_VISION_MODEL = os.environ.get('OCR_VISION_MODEL', 'claude-opus-4-8')

    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    # Auto-logout after this many minutes of inactivity (0 disables).
    SESSION_IDLE_MINUTES = int(os.environ.get('SESSION_IDLE_MINUTES', '60'))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = _as_bool(os.environ.get('SESSION_COOKIE_SECURE'), default=False)

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
