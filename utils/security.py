"""
Security utilities for PosyHub Student Management System
Provides authentication, authorization, input validation, and protection utilities
"""
import re
import html
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import session, redirect, url_for, flash, request, abort, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from collections import defaultdict
import threading


# =============================================================================
# RATE LIMITING
# =============================================================================

class RateLimiter:
    """Rate limiter for login/abuse protection.

    Uses the database when an app context is available, so the limit is shared
    across all gunicorn workers (a per-process in-memory counter is bypassable
    by spreading attempts across workers). Falls back to an in-memory counter
    when there's no app/DB context (e.g. outside a request). DB access goes
    through an independent engine connection so it never commits or rolls back
    the request's own session.
    """

    def __init__(self):
        self._attempts = defaultdict(list)
        self._lock = threading.Lock()

    # -- DB backend -----------------------------------------------------------
    def _engine(self):
        try:
            from flask import has_app_context
            if not has_app_context():
                return None
            from models import db
            return db.engine
        except Exception:
            return None

    def is_rate_limited(self, key, max_attempts=5, window_minutes=15):
        import time as _t
        from sqlalchemy import text
        eng = self._engine()
        if eng is not None:
            try:
                cutoff = _t.time() - window_minutes * 60
                with eng.connect() as conn:
                    n = conn.execute(text(
                        'SELECT COUNT(*) FROM rate_limit_hits WHERE rkey=:k AND ts>=:c'),
                        {'k': key, 'c': cutoff}).scalar()
                return (n or 0) >= max_attempts
            except Exception:
                pass  # table missing / db hiccup → fall back
        with self._lock:
            now = datetime.now()
            cutoff = now - timedelta(minutes=window_minutes)
            self._attempts[key] = [t for t in self._attempts[key] if t > cutoff]
            return len(self._attempts[key]) >= max_attempts

    def record_attempt(self, key):
        import os
        import time as _t
        from sqlalchemy import text
        eng = self._engine()
        if eng is not None:
            try:
                now = _t.time()
                with eng.begin() as conn:
                    conn.execute(text(
                        'INSERT INTO rate_limit_hits (rkey, ts) VALUES (:k, :t)'),
                        {'k': key, 't': now})
                    # Opportunistic cleanup of old rows (~1 in 20 inserts).
                    if os.urandom(1)[0] < 13:
                        conn.execute(text('DELETE FROM rate_limit_hits WHERE ts < :c'),
                                     {'c': now - 3600})
                return
            except Exception:
                pass
        with self._lock:
            self._attempts[key].append(datetime.now())

    def clear_attempts(self, key):
        from sqlalchemy import text
        eng = self._engine()
        if eng is not None:
            try:
                with eng.begin() as conn:
                    conn.execute(text('DELETE FROM rate_limit_hits WHERE rkey=:k'),
                                 {'k': key})
            except Exception:
                pass
        with self._lock:
            self._attempts[key] = []

    def get_remaining_time(self, key, window_minutes=15):
        import time as _t
        from sqlalchemy import text
        eng = self._engine()
        if eng is not None:
            try:
                now = _t.time()
                cutoff = now - window_minutes * 60
                with eng.connect() as conn:
                    oldest = conn.execute(text(
                        'SELECT MIN(ts) FROM rate_limit_hits WHERE rkey=:k AND ts>=:c'),
                        {'k': key, 'c': cutoff}).scalar()
                if not oldest:
                    return 0
                return max(0, int(oldest + window_minutes * 60 - now))
            except Exception:
                pass
        with self._lock:
            if not self._attempts[key]:
                return 0
            oldest = min(self._attempts[key])
            unlock_time = oldest + timedelta(minutes=window_minutes)
            return max(0, int((unlock_time - datetime.now()).total_seconds()))


# Global rate limiter instance
login_limiter = RateLimiter()


def rate_limited(bucket, max_requests=10, window_minutes=15):
    """Decorator: throttle an expensive/abusable endpoint per user+IP.

    Backed by the shared DB limiter, so the cap holds across all workers. Use on
    CPU/IO-heavy routes (OCR, full exports, DB downloads) so one client can't
    stall the single-worker app. Returns HTTP 429 when the cap is hit.
    """
    from functools import wraps
    from flask import request, session, abort

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            who = session.get('user_id') or session.get('user') or (request.remote_addr or 'anon')
            key = f'rl:{bucket}:{who}'
            if login_limiter.is_rate_limited(key, max_requests, window_minutes):
                abort(429, description='You are doing that too often. Please wait a moment and try again.')
            login_limiter.record_attempt(key)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# =============================================================================
# PASSWORD MANAGEMENT
# =============================================================================

def hash_password(password: str) -> str:
    """Hash a password using werkzeug's secure method"""
    return generate_password_hash(password, method='scrypt')


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash"""
    if not password_hash:
        return False
    return check_password_hash(password_hash, password)


def is_password_strong(password: str) -> tuple[bool, str]:
    """
    Check password strength
    Returns (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    return True, ""


# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

def generate_session_token() -> str:
    """Generate a secure session token"""
    return secrets.token_urlsafe(32)


def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'warning')
            # Store the requested URL for redirect after login
            session['next_url'] = request.url
            return redirect(url_for('auth.login'))
        
        # Check session expiry
        if 'login_time' in session:
            login_time = datetime.fromisoformat(session['login_time'])
            max_age = current_app.config.get('PERMANENT_SESSION_LIFETIME', timedelta(hours=8))
            if datetime.now() - login_time > max_age:
                session.clear()
                flash('Your session has expired. Please log in again.', 'warning')
                return redirect(url_for('auth.login'))
        
        # Refresh session token periodically (every 30 minutes)
        if 'last_refresh' in session:
            last_refresh = datetime.fromisoformat(session['last_refresh'])
            if datetime.now() - last_refresh > timedelta(minutes=30):
                session['session_token'] = generate_session_token()
                session['last_refresh'] = datetime.now().isoformat()
        
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator to require admin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if session.get('role') != 'admin':
            flash('You do not have permission to access this page.', 'error')
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


# =============================================================================
# INPUT SANITIZATION
# =============================================================================

def sanitize_string(value: str, max_length: int = 500) -> str:
    """Sanitize a string input"""
    if not value:
        return ''
    # Remove null bytes
    value = value.replace('\x00', '')
    # Escape HTML entities
    value = html.escape(value.strip())
    # Truncate to max length
    return value[:max_length]


def sanitize_html(value: str) -> str:
    """Remove all HTML tags from a string"""
    if not value:
        return ''
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', '', value)
    return html.escape(clean.strip())


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename for safe storage"""
    if not filename:
        return ''
    # Remove path separators
    filename = filename.replace('/', '_').replace('\\', '_')
    # Remove null bytes and other dangerous characters
    filename = re.sub(r'[<>:"|?*\x00-\x1f]', '_', filename)
    # Limit length
    name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
    name = name[:100]
    return f"{name}.{ext}" if ext else name


def validate_integer(value, min_val=None, max_val=None, default=None):
    """Validate and convert to integer"""
    try:
        result = int(value)
        if min_val is not None and result < min_val:
            return default
        if max_val is not None and result > max_val:
            return default
        return result
    except (ValueError, TypeError):
        return default


def validate_phone_number(phone: str) -> tuple[bool, str]:
    """
    Validate Nigerian phone number
    Returns (is_valid, normalized_number)
    """
    if not phone:
        return False, ''
    
    # Remove spaces, dashes, and other formatting
    phone = re.sub(r'[\s\-\(\)]+', '', phone)
    
    # Nigerian format: 11 digits starting with 0
    if re.match(r'^0[789][01]\d{8}$', phone):
        return True, phone
    
    # International format: +234 followed by 10 digits
    if re.match(r'^\+234[789][01]\d{8}$', phone):
        return True, '0' + phone[4:]  # Convert to local format
    
    # 234 without + followed by 10 digits
    if re.match(r'^234[789][01]\d{8}$', phone):
        return True, '0' + phone[3:]
    
    return False, phone


def validate_email(email: str) -> bool:
    """Validate email format"""
    if not email:
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


# =============================================================================
# CSRF PROTECTION
# =============================================================================

def generate_csrf_token() -> str:
    """Generate a CSRF token for the session"""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


def validate_csrf_token(token: str) -> bool:
    """Validate a CSRF token"""
    session_token = session.get('_csrf_token')
    if not session_token or not token:
        return False
    return secrets.compare_digest(session_token, token)


def csrf_protect(f):
    """Decorator to enforce CSRF protection on POST requests"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'POST':
            token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
            if not validate_csrf_token(token):
                flash('Invalid request. Please try again.', 'error')
                abort(400)
        return f(*args, **kwargs)
    return decorated_function


# =============================================================================
# SECURITY HEADERS
# =============================================================================

def add_security_headers(response):
    """Add security headers to response"""
    # Prevent clickjacking
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    # Prevent MIME type sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # Enable XSS filter
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # Referrer policy
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    # Content Security Policy.
    # NOTE: script-src still allows 'unsafe-inline'/'unsafe-eval' because the app
    # has many inline <script> blocks; removing them safely requires a per-request
    # nonce on every inline script (tracked as audit H5 — deferred to avoid
    # breaking the UI). The directives below add the *non-breaking* hardening:
    # block plugins/objects, lock <base>, and forbid being framed or posting forms
    # cross-origin.
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        # Allow our own pages plus blob: PDFs (the Mock-WAEC result/broadsheet
        # previews embed a server-generated PDF as a blob in an <iframe>).
        "frame-src 'self' blob:; "
        "base-uri 'self'; "
        "frame-ancestors 'self'; "
        "form-action 'self';"
    )
    return response


# =============================================================================
# AUDIT LOGGING
# =============================================================================

def log_security_event(event_type: str, details: str = '', user: str = None):
    """Log security-relevant events"""
    timestamp = datetime.now().isoformat()
    ip = request.remote_addr if request else 'N/A'
    user = user or session.get('user', 'anonymous')
    
    log_entry = f"[{timestamp}] [{event_type}] User: {user} IP: {ip} - {details}"
    
    # In production, this should write to a proper logging system
    current_app.logger.info(log_entry)


# =============================================================================
# CONTRIBUTIONS MODULE ACCESS
# =============================================================================

def contributions_access_required(f):
    """Decorator for contributions module access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('contributions_access'):
            return redirect(url_for('contributions.access_page'))
        return f(*args, **kwargs)
    return decorated_function


def verify_contributions_access(code: str) -> bool:
    """Verify contributions access code"""
    correct_code = current_app.config.get('CONTRIBUTIONS_ACCESS_CODE', '')
    if not correct_code:
        return False
    return secrets.compare_digest(code, correct_code)
