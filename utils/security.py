"""
Security utilities for PosyHub Student Management System
Provides authentication, authorization, input validation, and protection utilities
"""
import re
from utils import timeutil
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
            now = timeutil.now()
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
            self._attempts[key].append(timeutil.now())

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
            return max(0, int((unlock_time - timeutil.now()).total_seconds()))


# Global rate limiter instance
login_limiter = RateLimiter()


def _rl_identity():
    """Best-effort caller identity for per-user throttling: the logged-in user,
    else the session's legacy user, else the client IP. Imports flask names
    locally so callers don't need a request-context import of their own."""
    from flask import session, request
    return session.get('user_id') or session.get('user') or (request.remote_addr or 'anon')


def rate_limited(bucket, max_requests=10, window_minutes=15, *,
                 global_max=None, global_window_minutes=None):
    """Decorator: throttle an expensive/abusable endpoint.

    Two layers, both backed by the shared DB limiter (so caps hold across all
    workers):

    * **Per-identity** (``max_requests``): keyed by user, else session, else IP.
      Stops one client hammering the endpoint.
    * **Global** (``global_max``, optional): a single counter for ALL callers
      combined. This is the defence for a *distributed* flood — an attacker
      spreading requests across a thousand IPs defeats the per-IP cap, but every
      request still increments the one global counter, so the endpoint trips its
      circuit breaker and sheds load instead of stalling the single worker. The
      limiter table is per-tenant, so one school's flood can't affect another.
      Size ``global_max`` well above normal aggregate use for that endpoint.

    Returns HTTP 429 when either cap is hit.
    """
    from functools import wraps
    from flask import abort
    gwin = global_window_minutes or window_minutes

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = f'rl:{bucket}:{_rl_identity()}'
            if login_limiter.is_rate_limited(key, max_requests, window_minutes):
                abort(429, description='You are doing that too often. Please wait a moment and try again.')
            if global_max is not None:
                gkey = f'rl:GLOBAL:{bucket}'
                if login_limiter.is_rate_limited(gkey, global_max, gwin):
                    abort(429, description='This service is busy right now. Please try again shortly.')
                login_limiter.record_attempt(gkey)
            login_limiter.record_attempt(key)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def charge_bucket(bucket, max_requests, window_minutes, n=1):
    """Charge ``n`` hits to a per-user throttle bucket, sharing the key scheme
    used by :func:`rate_limited` (so e.g. per-file work and per-request work
    draw down the *same* budget). Returns ``True`` if the bucket is already at
    its cap (nothing is recorded in that case), else records ``n`` hits and
    returns ``False``. Lets a loop meter real work — one OCR unit per file —
    instead of letting a single request smuggle unbounded work past a
    per-request limit."""
    key = f'rl:{bucket}:{_rl_identity()}'
    if login_limiter.is_rate_limited(key, max_requests, window_minutes):
        return True
    for _ in range(max(1, n)):
        login_limiter.record_attempt(key)
    return False


# =============================================================================
# GLOBAL PER-IP REQUEST THROTTLE (in-memory)
# =============================================================================
#
# A coarse, always-on ceiling on requests-per-IP, wired as a before_request
# guard. Deliberately in-memory (no DB write per request): the app runs a single
# gunicorn worker, so one process-wide counter already spans every request, and
# writing a rate_limit_hits row on *every* hit would itself be a load problem.
# This is a blunt backstop against request floods / scraping / API hammering —
# the per-endpoint DB limiters above stay the precise, cross-restart controls.
_global_hits = defaultdict(list)
_global_lock = threading.Lock()


def global_rate_exceeded(key, max_requests, window_seconds):
    """Sliding-window check+record for the global throttle. Returns True once
    ``key`` has been seen more than ``max_requests`` times in the last
    ``window_seconds``. Uses a monotonic clock so a clock step can't widen the
    window, and opportunistically evicts idle keys to bound memory."""
    import time as _t
    now = _t.monotonic()
    cutoff = now - window_seconds
    with _global_lock:
        hits = [t for t in _global_hits[key] if t > cutoff]
        hits.append(now)
        _global_hits[key] = hits
        if len(_global_hits) > 4096:
            for k in [k for k, v in _global_hits.items() if not v or v[-1] < cutoff]:
                del _global_hits[k]
        return len(hits) > max_requests


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


# Upper bound on any password we will hash/verify. scrypt is intentionally
# CPU-heavy, so an unbounded password is a cheap DoS on the single worker —
# login views reject longer values before hashing.
MAX_PASSWORD_LEN = 128

# Very common / weak base passwords, checked offline (no HIBP network call, which
# would be unreliable on the poor connections this app targets). We compare after
# stripping trailing digits/symbols so "Password123!" and "Qwerty@2024" are also
# caught — the complexity rules alone happily pass those.
_COMMON_PASSWORDS = frozenset({
    'password', 'passw0rd', 'welcome', 'admin', 'administrator', 'letmein',
    'qwerty', 'qwertyuiop', 'azerty', 'iloveyou', 'monkey', 'dragon', 'football',
    'baseball', 'sunshine', 'princess', 'superman', 'trustno1', 'master', 'login',
    'abc123', 'abcd1234', 'password1', 'changeme', 'secret', 'default', 'test123',
    'school', 'student', 'teacher', 'nigeria', 'access', 'money', 'god', 'jesus',
})


def _looks_common(password: str) -> bool:
    """True if the password reduces to a well-known weak base."""
    low = password.lower()
    # Strip a trailing run of digits/symbols (the usual "make it pass" suffix)
    # and any leading/trailing non-letters, then test the core word.
    core = re.sub(r'[^a-z]+$', '', low)
    core = re.sub(r'^[^a-z]+', '', core)
    return low in _COMMON_PASSWORDS or core in _COMMON_PASSWORDS


PASSWORD_MIN_LENGTH = 12

# Single source of truth for the password policy. The server enforces these in
# is_password_strong(); the browser (Jinja password pages + the React user form)
# renders the SAME rules for its live checklist by consuming password_rules()
# below — so the client can never drift from what the server accepts.
#
# Each rule is either a min-length rule or a regex that is valid in BOTH Python's
# `re` and JavaScript's `RegExp` (the char-class patterns below are identical in
# both), so one spec drives server checks and client-side validation alike.
PASSWORD_RULES = [
    {'id': 'len', 'label': f'At least {PASSWORD_MIN_LENGTH} characters',
     'min_length': PASSWORD_MIN_LENGTH,
     'message': f'Password must be at least {PASSWORD_MIN_LENGTH} characters long'},
    {'id': 'upper', 'label': 'An uppercase letter (A–Z)', 'regex': r'[A-Z]',
     'message': 'Password must contain at least one uppercase letter'},
    {'id': 'lower', 'label': 'A lowercase letter (a–z)', 'regex': r'[a-z]',
     'message': 'Password must contain at least one lowercase letter'},
    {'id': 'digit', 'label': 'A number (0–9)', 'regex': r'\d',
     'message': 'Password must contain at least one number'},
    {'id': 'symbol', 'label': 'A symbol (!, @, #, …)', 'regex': r'[^A-Za-z0-9]',
     'message': 'Password must contain at least one symbol'},
]


def _rule_ok(rule: dict, password: str) -> bool:
    if 'min_length' in rule:
        return len(password) >= rule['min_length']
    return re.search(rule['regex'], password) is not None


def password_rules() -> list[dict]:
    """The public, JSON-serialisable password policy for the browser (Jinja +
    React). Each entry has `id`, `label`, and either `min_length` or `regex`;
    the server-only `message` is dropped."""
    return [{k: v for k, v in r.items() if k != 'message'} for r in PASSWORD_RULES]


def is_password_strong(password: str) -> tuple[bool, str]:
    """
    Check password strength
    Returns (is_valid, error_message)
    """
    if len(password) > MAX_PASSWORD_LEN:
        return False, f"Password must be at most {MAX_PASSWORD_LEN} characters long"
    for rule in PASSWORD_RULES:
        if not _rule_ok(rule, password):
            return False, rule['message']
    if _looks_common(password):
        return False, "That password is too common or guessable — choose something unique."
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
            from utils.nav import login_url
            return redirect(login_url())
        
        # Check session expiry
        if 'login_time' in session:
            login_time = datetime.fromisoformat(session['login_time'])
            max_age = current_app.config.get('PERMANENT_SESSION_LIFETIME', timedelta(hours=8))
            if timeutil.now() - login_time > max_age:
                session.clear()
                flash('Your session has expired. Please log in again.', 'warning')
                return redirect(url_for('auth.login'))
        
        # Refresh session token periodically (every 30 minutes)
        if 'last_refresh' in session:
            last_refresh = datetime.fromisoformat(session['last_refresh'])
            if timeutil.now() - last_refresh > timedelta(minutes=30):
                session['session_token'] = generate_session_token()
                session['last_refresh'] = timeutil.now().isoformat()
        
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


# Matches an HTML-tag-looking sequence: '<' or '</' immediately followed by a
# letter, up to the next '>'. Requiring a letter right after '<' means ordinary
# text such as "score < 5 > 3" or "a<b (no close)" is preserved, while any real
# tag ("<img …>", "<script>", "</b>") — i.e. every XSS payload — is stripped.
_TAG_RE = re.compile(r'</?[a-zA-Z][^>]*>')
_CTRL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')


def strip_tags(value, max_length: int = None) -> str:
    """Defense-in-depth input cleaner for free-text fields (names, comments,
    notes, messages, announcements). Removes HTML tags and control characters but
    — crucially — does NOT HTML-escape, so it can be stored and later rendered
    through the normal autoescaping layer without double-encoding (a name like
    ``O'Brien & Sons`` round-trips unchanged; ``<script>x</script>`` becomes
    ``x``). Preserves ``&``, quotes and apostrophes as literal text."""
    if value is None:
        return ''
    value = _CTRL_RE.sub('', str(value))
    value = _TAG_RE.sub('', value).strip()
    if max_length:
        value = value[:max_length]
    return value


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

def get_csp_nonce():
    """Per-request CSP nonce, created lazily and memoised on ``g``. The template
    context processor and the response-header builder both call this, so the
    `<script nonce>` value in the HTML matches the `script-src 'nonce-…'` header."""
    from flask import g, has_request_context
    import secrets
    if not has_request_context():
        return ''
    n = getattr(g, '_csp_nonce', None)
    if n is None:
        n = secrets.token_urlsafe(16)
        g._csp_nonce = n
    return n


def add_security_headers(response):
    """Add security headers to response"""
    # Prevent clickjacking
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    # Prevent MIME type sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # X-XSS-Protection is deliberately DISABLED (0): the legacy browser auditor is
    # deprecated and has itself been a source of vulnerabilities. Our real XSS
    # defence is the nonce-based CSP below (OWASP Secure Headers guidance).
    response.headers['X-XSS-Protection'] = '0'
    # Referrer policy
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    # Lock down powerful browser features to only what the app actually uses:
    # geolocation (HR GPS attendance / CBT), camera (barcode scanning in
    # Sales & Library). Everything else is denied so a future XSS/embed can't
    # reach the mic, USB, payment API, etc.
    response.headers['Permissions-Policy'] = (
        'geolocation=(self), camera=(self), microphone=(), payment=(), '
        'usb=(), magnetometer=(), gyroscope=(), accelerometer=(), '
        'interest-cohort=()'
    )
    # Isolate our browsing context from any window we open / that opens us.
    response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
    # Content Security Policy.
    # script-src is nonce-based: inline <script> blocks carry nonce="{{ csp_nonce }}"
    # and all former inline on* handlers were moved to event listeners
    # (static/js/csp-behaviors.js), so 'unsafe-inline' and 'unsafe-eval' are gone —
    # an injected <script> or inline handler no longer executes. style-src keeps
    # 'unsafe-inline' (many inline style="" attributes; nonces don't cover those and
    # the XSS value is far lower for styles).
    nonce = get_csp_nonce()
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        # script-src is 'self'+nonce plus jsdelivr (MathJax in the CBT module is
        # the only external script). cdnjs is intentionally NOT allowed for
        # scripts — it only serves stylesheets/fonts here (see style-src/font-src).
        f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        # Images may load over https from anywhere: the Website Builder lets a
        # school use stock photos and paste external image URLs, and admins embed
        # remote images in rich content. Images can't execute code, so this is a
        # safe relaxation; scripts/styles/frames stay locked down above/below.
        "img-src 'self' data: blob: https:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        # Allow our own pages plus blob: PDFs (the Mock-WAEC result/broadsheet
        # previews embed a server-generated PDF as a blob in an <iframe>).
        "frame-src 'self' blob:; "
        "base-uri 'self'; "
        "frame-ancestors 'self'; "
        # 'self' plus Paystack: the subscription billing form POSTs to our own
        # /billing/pay, which 302-redirects to checkout.paystack.com. Browsers
        # enforce form-action across the whole redirect chain, so without the
        # Paystack host here the redirect to the card page is silently blocked.
        "form-action 'self' https://checkout.paystack.com https://*.paystack.com;"
    )
    return response


# =============================================================================
# AUDIT LOGGING
# =============================================================================

def log_security_event(event_type: str, details: str = '', user: str = None):
    """Log security-relevant events"""
    timestamp = timeutil.now().isoformat()
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
