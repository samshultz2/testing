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

    # Connection-pool hardening. pool_pre_ping transparently recovers from
    # dropped connections (important for Postgres, which closes idle ones);
    # pool_recycle avoids stale sockets. Sizing only applies to real pools
    # (Postgres) — SQLite ignores it.
    _IS_POSTGRES = SQLALCHEMY_DATABASE_URI.startswith('postgresql')
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': int(os.environ.get('DB_POOL_RECYCLE', '1800')),
    }
    if _IS_POSTGRES:
        SQLALCHEMY_ENGINE_OPTIONS.update({
            'pool_size': int(os.environ.get('DB_POOL_SIZE', '5')),
            'max_overflow': int(os.environ.get('DB_MAX_OVERFLOW', '10')),
            'pool_timeout': int(os.environ.get('DB_POOL_TIMEOUT', '30')),
        })

    # Reverse-proxy awareness. Set TRUST_PROXY=1 when running behind nginx so
    # the app honours X-Forwarded-For/-Proto (correct client IPs + https).
    TRUST_PROXY = _as_bool(os.environ.get('TRUST_PROXY'), default=False)

    # Security headers. CSP is opt-in because a too-strict policy can break
    # inline scripts/styles in existing templates — enable once verified.
    SECURITY_HEADERS = _as_bool(os.environ.get('SECURITY_HEADERS'), default=True)
    ENABLE_HSTS = _as_bool(os.environ.get('ENABLE_HSTS'), default=False)
    CONTENT_SECURITY_POLICY = os.environ.get('CONTENT_SECURITY_POLICY', '')

    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
    LOG_FILE = os.environ.get('LOG_FILE', '')  # empty => stderr only

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

    # Email (SMTP). Empty host/from => email features stay disabled.
    SMTP_HOST = os.environ.get('SMTP_HOST', '')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
    SMTP_USER = os.environ.get('SMTP_USER', '')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
    SMTP_FROM = os.environ.get('SMTP_FROM', '')
    SMTP_USE_TLS = _as_bool(os.environ.get('SMTP_USE_TLS'), default=True)

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
    # In production, sessions should not survive a secret-key change, and we
    # want secure defaults. Cookies are only marked Secure when served over
    # HTTPS — keep SESSION_COOKIE_SECURE=1 in the environment once TLS is in
    # front (e.g. behind nginx). It is left configurable because LAN/Termux
    # deployments may run plain HTTP initially.
    ENABLE_HSTS = _as_bool(os.environ.get('ENABLE_HSTS'), default=True)

    @staticmethod
    def warnings():
        """Return a list of production-readiness warnings (non-fatal)."""
        msgs = []
        if not os.environ.get('SECRET_KEY'):
            msgs.append('SECRET_KEY is not set in the environment; using a '
                        'generated/persisted key. Set SECRET_KEY for production.')
        if Config.ENABLE_LEGACY_LOGIN and not os.environ.get('ADMIN_PASSWORD'):
            msgs.append('Legacy shared-password login is enabled with the '
                        'default password. Set ADMIN_PASSWORD or '
                        'ENABLE_LEGACY_LOGIN=0.')
        if not Config._IS_POSTGRES:
            msgs.append('Running on SQLite. PostgreSQL is recommended for '
                        'production (set DATABASE_URL).')
        return msgs


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DEBUG = False
    WTF_CSRF_ENABLED = False


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig,
}


def get_config():
    """Select a config class from APP_ENV / FLASK_ENV (default: development)."""
    name = (os.environ.get('APP_ENV')
            or os.environ.get('FLASK_ENV')
            or 'default').strip().lower()
    return config.get(name, config['default'])
