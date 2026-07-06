"""
Configuration settings for PosyHub Student Management System
"""
import os
import secrets
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Load settings from a .env file in the project root so deployments keep secrets
# out of source. Real OS environment variables still take precedence. Auth and
# crypto now depend on these values being loaded, so a failure is surfaced
# loudly instead of being silently swallowed.
_ENV_FILE = os.path.join(BASE_DIR, '.env')
ENV_FILE_LOADED = False
try:
    from dotenv import load_dotenv
    ENV_FILE_LOADED = load_dotenv(_ENV_FILE)   # True only when the file exists
except ImportError:
    if os.path.exists(_ENV_FILE):
        import sys
        print('SECURITY WARNING: python-dotenv is not installed, so .env is '
              'being IGNORED. Run: pip install -r requirements.txt',
              file=sys.stderr)


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
        # Defaults suit a small VPS. For a large concurrent CBT exam, raise these
        # (e.g. DB_POOL_SIZE=30 DB_MAX_OVERFLOW=50) AND raise Postgres
        # max_connections to match (pool is per worker process).
        SQLALCHEMY_ENGINE_OPTIONS.update({
            'pool_size': int(os.environ.get('DB_POOL_SIZE', '10')),
            'max_overflow': int(os.environ.get('DB_MAX_OVERFLOW', '20')),
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

    # Error monitoring. Errors are persisted to a JSONL file (so the in-app Error
    # Log survives restarts) and, when ALERT_EMAIL is set, server errors trigger
    # a throttled email alert. Sentry is opt-in via SENTRY_DSN.
    ERROR_LOG_FILE = os.environ.get(
        'ERROR_LOG_FILE', os.path.join(BASE_DIR, 'instance', 'errors.jsonl'))
    ERROR_LOG_MAX = int(os.environ.get('ERROR_LOG_MAX', '2000'))  # lines kept
    ALERT_EMAIL = os.environ.get('ALERT_EMAIL', '')  # recipient(s); comma-separated
    # Minimum seconds between alert emails, so an error storm can't flood inboxes.
    ERROR_ALERT_MIN_INTERVAL = int(os.environ.get('ERROR_ALERT_MIN_INTERVAL', '900'))
    SENTRY_DSN = os.environ.get('SENTRY_DSN', '')  # empty => Sentry disabled
    SENTRY_TRACES_SAMPLE_RATE = float(os.environ.get('SENTRY_TRACES_SAMPLE_RATE', '0') or 0)
    SENTRY_ENVIRONMENT = os.environ.get('SENTRY_ENVIRONMENT', os.environ.get('APP_ENV', ''))

    # Field-level encryption at rest (AES-256-GCM). When set, sensitive
    # recoverable fields (e.g. student portal passwords) are encrypted in the
    # database. Generate a key with:
    #   python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())"
    # Losing the key makes those fields unrecoverable (portal passwords can be
    # regenerated, so the blast radius is small). Empty => feature disabled.
    FIELD_ENCRYPTION_KEY = os.environ.get('FIELD_ENCRYPTION_KEY', '')

    # Application settings
    APP_NAME = "EduSyncra"
    # Legacy shared-password login (backwards compatibility only). There is NO
    # built-in password: legacy login is inert unless you both enable it and set
    # a strong ADMIN_PASSWORD in the environment / .env. Prefer real user
    # accounts and leave this disabled.
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD') or None
    ENABLE_LEGACY_LOGIN = _as_bool(os.environ.get('ENABLE_LEGACY_LOGIN'), default=False)

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

    # Login throttling. The per-IP cap stops one host hammering the form; the
    # lower per-account cap stops a distributed (IP-rotating) brute force against
    # a single known username.
    LOGIN_MAX_ATTEMPTS = int(os.environ.get('LOGIN_MAX_ATTEMPTS', '8'))
    LOGIN_ACCT_MAX_ATTEMPTS = int(os.environ.get('LOGIN_ACCT_MAX_ATTEMPTS', '6'))
    LOGIN_LOCKOUT_MINUTES = int(os.environ.get('LOGIN_LOCKOUT_MINUTES', '15'))

    # Backups
    BACKUP_RETENTION = int(os.environ.get('BACKUP_RETENTION', '10'))

    # Include the uploads/ media folder (logos, question images, scans) in the
    # daily backup — it is NOT part of the database dump. Cheap; on by default.
    BACKUP_MEDIA = _as_bool(os.environ.get('BACKUP_MEDIA'), default=True)

    # --- Offsite backup shipping (opt-in; nothing configured by default) -------
    # Leave these blank and behaviour is unchanged — backups stay local. When you
    # get offsite storage, set ONE destination below and every NEW daily DB dump
    # + media archive is automatically copied off the server. This is the single
    # biggest disaster-recovery win: ransomware / disk loss / a compromised host
    # can no longer take the backups down with the primary. Configure WORM /
    # object-lock / versioning on the remote for true immutability.
    #   OFFSITE_DIR            — copy to a mounted volume / NFS / external disk.
    #   OFFSITE_RCLONE_REMOTE  — `rclone copyto` to any rclone remote (S3, B2,
    #                            Google Drive, SFTP…); run `rclone config` once.
    #   OFFSITE_COMMAND        — escape hatch: a command with {path} / {name}
    #                            tokens, e.g. "aws s3 cp {path} s3://bkt/{name}".
    OFFSITE_DIR = os.environ.get('OFFSITE_DIR', '')
    OFFSITE_RCLONE_REMOTE = os.environ.get('OFFSITE_RCLONE_REMOTE', '')
    OFFSITE_RCLONE_FLAGS = os.environ.get('OFFSITE_RCLONE_FLAGS', '')
    OFFSITE_COMMAND = os.environ.get('OFFSITE_COMMAND', '')

    # Automated fee reminders. Opt-in: when enabled, a background job prepares a
    # Draft SMS campaign to fee defaulters for the active term and bells admins to
    # review and send it. Nothing is sent automatically — the human send-gate is
    # kept. A new draft is prepared at most once per FEE_REMINDER_INTERVAL_DAYS.
    FEE_REMINDER_ENABLED = _as_bool(os.environ.get('FEE_REMINDER_ENABLED'), default=False)
    FEE_REMINDER_INTERVAL_DAYS = int(os.environ.get('FEE_REMINDER_INTERVAL_DAYS', '7'))

    # Persistent-absence alerts: bell admins when a student is absent this many
    # consecutive school days in a row. 0 disables the alerts.
    ABSENCE_ALERT_DAYS = int(os.environ.get('ABSENCE_ALERT_DAYS', '3'))

    # Optional Claude-vision OCR fallback (needs ANTHROPIC_API_KEY + the
    # `anthropic` package). Off by default — Tesseract is the default engine.
    # Defaults to the cheapest vision-capable model (Haiku); OCR of result slips
    # doesn't need a frontier model, and Haiku is ~5x cheaper than Opus.
    OCR_VISION_FALLBACK = _as_bool(os.environ.get('OCR_VISION_FALLBACK'), default=False)
    OCR_VISION_MODEL = os.environ.get('OCR_VISION_MODEL', 'claude-haiku-4-5')

    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    # Auto-logout after this many minutes of inactivity (0 disables).
    SESSION_IDLE_MINUTES = int(os.environ.get('SESSION_IDLE_MINUTES', '60'))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = _as_bool(os.environ.get('SESSION_COOKIE_SECURE'), default=False)
    # Hard ceiling for the OR-Tools timetable solver, kept safely below the
    # gunicorn worker timeout (default 120s) so one solve can't run the worker
    # past its deadline and stall the whole single-worker app.
    SOLVER_MAX_SECONDS = int(os.environ.get('SOLVER_MAX_SECONDS', '90'))

    # Global per-IP request ceiling (in-memory backstop against floods/scraping/
    # API hammering). ~5 req/sec sustained per client — far above real human use,
    # below what a script needs to stress the single worker. 0 disables it.
    GLOBAL_RATE_PER_MIN = int(os.environ.get('GLOBAL_RATE_PER_MIN', '300'))

    # --- Multi-tenancy (Stage 0 routing) --------------------------------------
    # OFF by default: the app runs as a single-school install and the current
    # database is untouched. When ON, each request is routed to its school's
    # database by the host subdomain (see utils/tenant_runtime.py). Turning this
    # on requires TENANT_BASE_DOMAIN and a populated control plane.
    MULTI_TENANT = _as_bool(os.environ.get('MULTI_TENANT'), default=False)
    TENANT_BASE_DOMAIN = os.environ.get('TENANT_BASE_DOMAIN', '')   # e.g. 'edusyncra.site'
    # The school served on the BARE apex host (so the pre-existing school keeps
    # edusyncra.site with no URL change). Empty = apex is the marketing site.
    APEX_TENANT = os.environ.get('APEX_TENANT', '')
    # Hosts that are the platform itself, not a school (marketing + registration).
    RESERVED_SUBDOMAINS = set(filter(None, (s.strip().lower() for s in os.environ.get(
        'RESERVED_SUBDOMAINS', 'www,signup,app,admin,api').split(','))))

    # Billing: new schools get a free trial, then must pay or their database is
    # deleted after a grace period. The owner school (plan='owner') is exempt.
    TENANT_TRIAL_DAYS = int(os.environ.get('TENANT_TRIAL_DAYS', '3'))
    TENANT_PLAN_DAYS = int(os.environ.get('TENANT_PLAN_DAYS', '30'))    # days added per payment
    TENANT_BILLING_GRACE_DAYS = int(os.environ.get('TENANT_BILLING_GRACE_DAYS', '7'))
    TENANT_PRICE_KOBO = int(os.environ.get('TENANT_PRICE_KOBO', '0'))   # monthly base, kobo
    # Subscription tiers: monthly (base), termly and annual. Termly/annual prices
    # default to a discounted multiple of the monthly base but can be set outright.
    TENANT_TERM_DAYS = int(os.environ.get('TENANT_TERM_DAYS', '120'))   # one school term
    TENANT_TERMLY_PRICE_KOBO = int(os.environ.get('TENANT_TERMLY_PRICE_KOBO', '0') or 0)
    TENANT_ANNUAL_PRICE_KOBO = int(os.environ.get('TENANT_ANNUAL_PRICE_KOBO', '0') or 0)
    # Platform (SaaS) Paystack account that collects school subscriptions —
    # separate from each school's own parent-payment keys.
    PLATFORM_PAYSTACK_SECRET_KEY = os.environ.get('PLATFORM_PAYSTACK_SECRET_KEY', '')
    PLATFORM_PAYSTACK_PUBLIC_KEY = os.environ.get('PLATFORM_PAYSTACK_PUBLIC_KEY', '')
    # Dev/testing only: "pay" without a real Paystack charge (simulated). Forced
    # OFF in production so a school can't self-extend for free.
    BILLING_TEST_MODE = _as_bool(os.environ.get('BILLING_TEST_MODE'), default=False)

    # Registration. Default: a school must CONFIRM its email (a verification link)
    # before anything is provisioned — no database is created until the link is
    # clicked. Set REGISTRATION_AUTO_PROVISION=1 to instead create the school
    # instantly on signup (no email step). Either way signups are per-IP rate
    # limited and daily-banned on abuse. Verification emails need SMTP_* set.
    REGISTRATION_AUTO_PROVISION = _as_bool(os.environ.get('REGISTRATION_AUTO_PROVISION'), default=False)
    REGISTRATION_MAX_PER_HOUR = int(os.environ.get('REGISTRATION_MAX_PER_HOUR', '2'))
    REGISTRATION_MAX_PER_DAY = int(os.environ.get('REGISTRATION_MAX_PER_DAY', '5'))

    # Pagination
    STUDENTS_PER_PAGE = 20

    # Upload settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    ALLOWED_EXTENSIONS = {'xlsx', 'xls'}


    # When True (ProductionConfig), security_errors() block startup. Base/dev/
    # test leave it False so local work isn't gated on a full .env.
    ENFORCE_SECURITY = False

    @classmethod
    def security_errors(cls):
        """Fatal misconfigurations that must block a production boot."""
        e = []
        if not os.environ.get('SECRET_KEY'):
            e.append('SECRET_KEY must be set in the environment (.env) for production.')
        if not cls.FIELD_ENCRYPTION_KEY:
            e.append('FIELD_ENCRYPTION_KEY must be set so student/parent portal '
                     'passwords are encrypted at rest.')
        return e

    @classmethod
    def security_warnings(cls):
        """Operational security advisories for the active configuration.

        Returned at startup by the app factory (see app.py) and logged, so
        misconfigurations are visible instead of silent. Hard failures live in
        security_errors() and are enforced when ENFORCE_SECURITY is True.
        """
        w = []
        if not os.environ.get('SECRET_KEY'):
            w.append('SECRET_KEY is not set — using a generated/persisted key. '
                     'Set SECRET_KEY in .env for stable, secure sessions.')
        if cls.ENABLE_LEGACY_LOGIN and not cls.ADMIN_PASSWORD:
            w.append('ENABLE_LEGACY_LOGIN is on but ADMIN_PASSWORD is unset — '
                     'legacy login is inert (no password to match).')
        if cls.ENABLE_LEGACY_LOGIN and cls.ADMIN_PASSWORD:
            w.append('Legacy shared-password login is ENABLED. Disable it '
                     '(ENABLE_LEGACY_LOGIN=0) once real user accounts exist.')
        if not cls.FIELD_ENCRYPTION_KEY:
            w.append('FIELD_ENCRYPTION_KEY is not set — database backups will be '
                     'written UNENCRYPTED at rest. Set it in .env to encrypt them. '
                     '(Portal passwords are hash-only and unaffected.)')
        if not cls._IS_POSTGRES:
            w.append('Running on SQLite — PostgreSQL is recommended for '
                     'production (set DATABASE_URL).')
        return w


class DevelopmentConfig(Config):
    """Development configuration"""
    # Opt-in only: the Werkzeug interactive debugger is a remote-code-execution
    # console. APP_ENV being unset falls back to this config, which might be an
    # actual deployment — so don't turn the debugger on unless FLASK_DEBUG=1 is
    # set explicitly. (Dev autoreload/debugger is one env var away.)
    DEBUG = _as_bool(os.environ.get('FLASK_DEBUG'), default=False)


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    ENFORCE_SECURITY = True   # security_errors() block startup
    BILLING_TEST_MODE = False  # never allow simulated (free) payments in production
    # Secure by default in production; flip SESSION_COOKIE_SECURE=0 in the
    # environment only for a plain-HTTP LAN/Termux deployment (the cookie is
    # otherwise not sent over HTTP and login would appear to "not work").
    SESSION_COOKIE_SECURE = _as_bool(os.environ.get('SESSION_COOKIE_SECURE'), default=True)
    ENABLE_HSTS = _as_bool(os.environ.get('ENABLE_HSTS'), default=True)
    # Strict in production (base/dev stays 'Lax'): the session cookie is not sent
    # on cross-site top-level navigations, removing the residual CSRF surface.
    # The password-reset link carries its own token (not the session), so it is
    # unaffected; an inbound deep link just shows the login page on first hit.
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Strict')


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
    name = (os.environ.get('APP_ENV') or os.environ.get('FLASK_ENV') or '').strip().lower()
    if not name:
        # Defaulting to development means DEBUG=True — dangerous if this is
        # actually a deployment. Make the implicit choice visible.
        import sys
        print('SECURITY: APP_ENV/FLASK_ENV is not set — defaulting to '
              'DEVELOPMENT (DEBUG on). Set APP_ENV=production for deployments.',
              file=sys.stderr)
        name = 'default'
    return config.get(name, config['default'])
