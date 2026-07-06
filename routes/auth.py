"""
Enhanced Authentication routes for PosyHub
Supports both legacy password login and user-based login
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import hmac
from datetime import datetime, timedelta
from config import Config
from models import db, User
from werkzeug.security import generate_password_hash
from utils.security import login_limiter, is_password_strong
from utils.audit import log_action

auth_bp = Blueprint('auth', __name__)

# Login throttling via the shared DB-backed limiter, so the lockout holds across
# all gunicorn workers (an in-memory counter is bypassable by spreading attempts
# across processes).
def _client_key():
    return 'staff_login:' + (request.remote_addr or 'unknown')


def _account_key(ident):
    # Per-account throttle keyed by the submitted username, so a distributed
    # (IP-rotating) brute force against ONE known account still trips a lockout —
    # the IP key alone can't see it. Mirrors the parent/CBT portal pattern.
    return 'staff_login_acct:' + (ident or '').strip().lower()


def _login_locked(ident=None):
    if login_limiter.is_rate_limited(_client_key(), Config.LOGIN_MAX_ATTEMPTS,
                                     Config.LOGIN_LOCKOUT_MINUTES):
        return True
    if ident and login_limiter.is_rate_limited(
            _account_key(ident), Config.LOGIN_ACCT_MAX_ATTEMPTS, Config.LOGIN_LOCKOUT_MINUTES):
        return True
    return False


def _record_login_failure(ident=None):
    login_limiter.record_attempt(_client_key())
    if ident:
        login_limiter.record_attempt(_account_key(ident))
    # Audit every failed attempt (the attempted username goes in detail; the
    # actor is 'unknown' since no session identity exists yet). Central to all
    # failure paths, so it covers over-long-password, wrong-password and no-match.
    log_action('auth.login_failed', detail=ident or '(no username)')


def _clear_login_failures(ident=None):
    login_limiter.clear_attempts(_client_key())
    if ident:
        login_limiter.clear_attempts(_account_key(ident))


def _alert_lockout(ident):
    """Notify admins the first time an account/IP trips the lockout in a window,
    so a brute-force attempt is visible without waiting on external monitoring.
    Throttled (one alert per key per lockout window) so it can't itself be used
    to spam the notification feed."""
    who = (ident or '').strip() or (request.remote_addr or 'unknown')
    akey = f'lockout_alert:{who.lower()}'
    if login_limiter.is_rate_limited(akey, max_attempts=1, window_minutes=Config.LOGIN_LOCKOUT_MINUTES):
        return
    login_limiter.record_attempt(akey)
    try:
        from utils.notify import notify_admins
        notify_admins('Repeated failed logins',
                      f'Multiple failed sign-in attempts for "{who}" from '
                      f'{request.remote_addr or "an unknown address"}. The account/IP '
                      f'is temporarily locked out.',
                      url=url_for('auth.login'), category='warning')
    except Exception:
        pass


def _complete_login(user):
    """Finish a fully-authenticated login (password, and 2FA if enabled): drop
    any pre-login session, set identity, rotate the CSRF token, and land on the
    dashboard. Shared by the password path and the 2FA verify path."""
    from utils.branch_scope import set_session_scope
    from utils.org_scope import set_session_org
    from utils.csrf import rotate_csrf_token
    session.clear()
    session['logged_in'] = True
    session['user_id'] = user.id
    session['user'] = user.full_name or user.username
    session['role'] = user.role
    session['tv'] = user.token_version        # server-side session revocation
    from utils.tenant_runtime import bind_session_to_current_tenant
    bind_session_to_current_tenant()          # cookie valid only on this school's subdomain
    set_session_scope(user)
    set_session_org(user)
    if user.theme:
        session['theme'] = user.theme
    session['must_change_password'] = bool(user.must_change_password)
    rotate_csrf_token()
    session.permanent = True
    user.last_login = datetime.now()
    db.session.commit()
    log_action('auth.login', detail=user.username)   # session identity now set
    flash(f'Welcome back, {user.full_name or user.username}!', 'success')
    return redirect(url_for('main.dashboard'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login - supports username/password or legacy password"""
    if session.get('logged_in'):
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if _login_locked(username):
            log_action('auth.login_locked', detail=username or '(no username)')
            _alert_lockout(username)
            flash(f'Too many failed attempts. Try again in {Config.LOGIN_LOCKOUT_MINUTES} minutes.', 'error')
            return redirect(url_for('auth.login'))

        # DoS guard: never feed an unbounded password to scrypt (a multi-MB
        # value would pin the single worker). Treat as a normal failed attempt.
        from utils.security import MAX_PASSWORD_LEN
        if len(password) > MAX_PASSWORD_LEN:
            _record_login_failure(username or None)
            flash('Invalid credentials. Please try again.', 'error')
            return redirect(url_for('auth.login'))

        # Try user-based login first
        if username:
            user = User.query.filter_by(username=username).first()

            if user and user.check_password(password):
                if not user.is_active:
                    # Don't clear the throttle for a deactivated account.
                    flash('Your account has been deactivated. Contact administrator.', 'error')
                    return redirect(url_for('auth.login'))
                _clear_login_failures(username)

                # 2FA gate: when the user has TOTP enabled, the password is only
                # the first factor. Hold a short-lived "pending" session (NOT
                # logged_in, so every protected route still bounces) and require
                # a code on the next page before completing the login.
                if user.mfa_enabled and user.mfa_secret:
                    session.clear()
                    session['_pending_mfa_uid'] = user.id
                    session['_pending_mfa_ts'] = int(datetime.now().timestamp())
                    from utils.csrf import rotate_csrf_token
                    rotate_csrf_token()
                    session.permanent = True
                    return redirect(url_for('auth.verify_mfa'))

                return _complete_login(user)

            elif user:
                _record_login_failure(username)
                # Generic message — don't reveal that the username exists.
                flash('Invalid credentials. Please try again.', 'error')
                return redirect(url_for('auth.login'))

        # Legacy admin password login — only when explicitly enabled AND a
        # password is configured. There is no built-in/default password, so an
        # unconfigured deployment cannot be logged into via this path.
        if (Config.ENABLE_LEGACY_LOGIN and Config.ADMIN_PASSWORD and password
                and hmac.compare_digest(password, Config.ADMIN_PASSWORD)):
            _clear_login_failures()
            session.clear()           # prevent session fixation
            session['logged_in'] = True
            session['user'] = 'Admin'
            session['role'] = 'admin'
            from utils.tenant_runtime import bind_session_to_current_tenant
            bind_session_to_current_tenant()
            from utils.branch_scope import set_session_scope
            from utils.org_scope import set_session_org
            set_session_scope(None)   # legacy admin is central
            set_session_org(None)
            from utils.csrf import rotate_csrf_token
            rotate_csrf_token()
            session.permanent = True
            log_action('auth.login', detail='legacy-admin')
            flash('Welcome back, Admin!', 'success')
            return redirect(url_for('main.dashboard'))

        _record_login_failure(username or None)
        flash('Invalid credentials. Please try again.', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/login/verify', methods=['GET', 'POST'])
def verify_mfa():
    """Second factor: the password was already verified and a short-lived
    pending state set. Accept a TOTP code or a one-time backup code, then
    complete the login. No `logged_in` is set until this passes."""
    uid = session.get('_pending_mfa_uid')
    ts = session.get('_pending_mfa_ts') or 0
    if not uid or (datetime.now().timestamp() - ts) > 600:   # 10-minute window
        session.pop('_pending_mfa_uid', None)
        session.pop('_pending_mfa_ts', None)
        flash('Your sign-in step expired. Please log in again.', 'warning')
        return redirect(url_for('auth.login'))
    user = db.session.get(User, uid)
    if not user or not user.is_active or not user.mfa_enabled or not user.mfa_secret:
        session.clear()
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        rkey = f'mfa_verify:{uid}'
        if login_limiter.is_rate_limited(rkey, Config.LOGIN_ACCT_MAX_ATTEMPTS,
                                         Config.LOGIN_LOCKOUT_MINUTES):
            flash(f'Too many attempts. Try again in {Config.LOGIN_LOCKOUT_MINUTES} minutes.', 'error')
            return redirect(url_for('auth.verify_mfa'))
        from utils.security import MAX_PASSWORD_LEN
        code = (request.form.get('code') or '').strip()
        if len(code) > MAX_PASSWORD_LEN:
            code = ''
        from utils import totp
        ok = totp.verify(user.mfa_secret, code)
        used_backup = False
        if not ok and user.consume_backup_code(code):
            db.session.commit()
            ok = used_backup = True
        if ok:
            login_limiter.clear_attempts(rkey)
            session.pop('_pending_mfa_uid', None)
            session.pop('_pending_mfa_ts', None)
            if used_backup:
                flash('Backup code used — consider regenerating your backup codes.', 'info')
            return _complete_login(user)
        login_limiter.record_attempt(rkey)
        flash('Invalid code. Please try again.', 'error')
        return redirect(url_for('auth.verify_mfa'))

    return render_template('auth/verify_mfa.html', user_name=user.full_name or user.username)


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Self-service reset: emails a single-use, time-limited reset LINK. The live
    password is left intact until the user actually sets a new one (so triggering
    a reset for someone else can't lock them out)."""
    from utils import mailer
    if session.get('logged_in'):
        return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        # Throttle reset abuse (account probing + email bombing) by client IP.
        rkey = 'forgot_pw:' + (request.remote_addr or 'unknown')
        if login_limiter.is_rate_limited(rkey, max_attempts=8, window_minutes=15):
            flash('Too many reset requests. Please try again later.', 'error')
            return redirect(url_for('auth.login'))
        login_limiter.record_attempt(rkey)
        ident = (request.form.get('identifier') or '').strip()
        if ident:
            user = User.query.filter((User.username == ident) | (User.email == ident)).first()
            if user and user.email and user.is_active and mailer.is_configured():
                raw = user.set_reset_token(ttl_minutes=60)   # password untouched
                db.session.commit()
                link = url_for('auth.reset_password', uid=user.id, token=raw, _external=True)
                mailer.send_email(user.email, 'EduSyncra password reset',
                                  f'Hello {user.full_name or user.username},\n\n'
                                  f'We received a request to reset your password. Use this '
                                  f'link within 1 hour to set a new one:\n\n{link}\n\n'
                                  f'If you did not request this, you can ignore this email — '
                                  f'your current password still works.\n')
        # Generic response (avoid revealing whether an account exists).
        flash('If a matching account exists, a reset link has been sent.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<int:uid>/<token>', methods=['GET', 'POST'])
def reset_password(uid, token):
    """Set a new password via a single-use, time-limited token from the email."""
    if session.get('logged_in'):
        return redirect(url_for('main.dashboard'))
    user = User.query.get(uid)
    if not user or not user.is_active or not user.check_reset_token(token):
        flash('This reset link is invalid or has expired. Please request a new one.', 'error')
        return redirect(url_for('auth.forgot_password'))
    if request.method == 'POST':
        pw = request.form.get('password') or ''
        confirm = request.form.get('confirm') or ''
        if pw != confirm:
            flash('The two passwords do not match.', 'error')
            return render_template('auth/reset_password.html', uid=uid, token=token)
        ok, msg = is_password_strong(pw)
        if not ok:
            flash(msg, 'error')
            return render_template('auth/reset_password.html', uid=uid, token=token)
        user.set_password(pw)
        user.clear_reset_token()          # single use
        user.must_change_password = False
        db.session.commit()
        flash('Your password has been reset. Please sign in.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/reset_password.html', uid=uid, token=token)


@auth_bp.route('/logout')
def logout():
    """Handle user logout"""
    log_action('auth.logout')        # log before clearing so the actor is recorded
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/api/session/ping')
def session_ping():
    """Lightweight session keepalive. The global `enforce_idle_timeout`
    before_request already refreshes `last_seen` on every request, so hitting
    this cheap endpoint on real user activity keeps an actively-used tab from
    idling out mid-task (e.g. while reading/printing a broadsheet). Returns 204
    when alive, 401 when not — the client treats it as best-effort."""
    if not session.get('logged_in'):
        return ('', 401)
    return ('', 204)


@auth_bp.route('/change-password', methods=['GET', 'POST'])
def change_password():
    """Allow logged in user to change their password"""
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    
    user_id = session.get('user_id')
    if not user_id:
        flash('Password change not available for legacy login.', 'info')
        return redirect(url_for('main.dashboard'))
    
    user = db.session.get(User, user_id)
    if not user:
        return redirect(url_for('auth.logout'))
    
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not user.check_password(current_password):
            flash('Current password is incorrect.', 'error')
            return redirect(url_for('auth.change_password'))
        
        if new_password != confirm_password:
            flash('New passwords do not match.', 'error')
            return redirect(url_for('auth.change_password'))
        
        ok, msg = is_password_strong(new_password)
        if not ok:
            flash(msg, 'error')
            return redirect(url_for('auth.change_password'))
        
        user.set_password(new_password)   # bumps token_version (revokes sessions)
        user.must_change_password = False
        db.session.commit()
        session.pop('must_change_password', None)
        # Keep THIS device signed in; only other sessions are revoked.
        session['tv'] = user.token_version

        flash('Password changed successfully! Other devices have been signed out.', 'success')
        return redirect(url_for('main.dashboard'))
    
    return render_template('auth/change_password.html', user=user)


# --- Self-service 2FA (TOTP) -------------------------------------------------
def _self_user():
    """The logged-in real user (None for legacy-admin or anonymous)."""
    if not session.get('logged_in') or not session.get('user_id'):
        return None
    return db.session.get(User, session.get('user_id'))


def _totp_qr_svg(uri):
    """Inline, scalable SVG QR for an otpauth:// URI (reuses the share-panel
    pattern). Returns None if the qrcode lib is unavailable."""
    try:
        import io as _io
        import re as _re
        import qrcode
        import qrcode.image.svg as _svg
        buf = _io.BytesIO()
        qrcode.make(uri, image_factory=_svg.SvgPathImage, box_size=8, border=2).save(buf)
        svg = buf.getvalue().decode('utf-8')
        return _re.sub(r'(<svg[^>]*?)\s+width="[^"]*"\s+height="[^"]*"', r'\1', svg, count=1)
    except Exception:
        return None


def _make_backup_codes(n=10):
    """Return (display_codes, hashes). Display is dash-grouped for readability;
    the canonical (alnum-only) form is what gets hashed and matched."""
    import secrets
    alpha = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
    display, hashes = [], []
    for _ in range(n):
        raw = ''.join(secrets.choice(alpha) for _ in range(8))
        display.append(raw[:4] + '-' + raw[4:])
        hashes.append(generate_password_hash(raw))
    return display, hashes


@auth_bp.route('/security')
def security_settings():
    user = _self_user()
    if not user:
        if session.get('logged_in'):
            flash('Security settings aren’t available for the legacy admin login.', 'info')
            return redirect(url_for('main.dashboard'))
        return redirect(url_for('auth.login'))
    return render_template('auth/security.html', user=user)


@auth_bp.route('/security/2fa/setup')
def mfa_setup():
    user = _self_user()
    if not user:
        return redirect(url_for('auth.login'))
    if user.mfa_enabled:
        flash('Two-factor authentication is already enabled.', 'info')
        return redirect(url_for('auth.security_settings'))
    from utils import totp
    # Save a fresh (not-yet-active) secret on the user so it lives encrypted in
    # the DB, never in the signed-cookie session.
    user.mfa_secret = totp.generate_secret()
    user.mfa_enabled = False
    db.session.commit()
    uri = totp.provisioning_uri(user.mfa_secret, user.username or user.full_name or 'user')
    return render_template('auth/mfa_setup.html', user=user, secret=user.mfa_secret,
                           qr_svg=_totp_qr_svg(uri))


@auth_bp.route('/security/2fa/confirm', methods=['POST'])
def mfa_confirm():
    user = _self_user()
    if not user or not user.mfa_secret:
        return redirect(url_for('auth.security_settings'))
    from utils import totp
    code = (request.form.get('code') or '').strip()
    if not totp.verify(user.mfa_secret, code):
        flash('That code didn’t match. Make sure your phone’s time is correct and try again.', 'error')
        return redirect(url_for('auth.mfa_setup'))
    display, hashes = _make_backup_codes()
    user.mfa_enabled = True
    user.set_mfa_backup_codes(hashes)
    db.session.commit()
    flash('Two-factor authentication is now on.', 'success')
    return render_template('auth/mfa_codes.html', codes=display, fresh=True)


@auth_bp.route('/security/2fa/disable', methods=['POST'])
def mfa_disable():
    user = _self_user()
    if not user:
        return redirect(url_for('auth.login'))
    if not user.check_password(request.form.get('password') or ''):
        flash('Password is incorrect — 2FA was not changed.', 'error')
        return redirect(url_for('auth.security_settings'))
    user.disable_mfa()
    db.session.commit()
    flash('Two-factor authentication has been turned off.', 'success')
    return redirect(url_for('auth.security_settings'))


@auth_bp.route('/security/2fa/backup-codes', methods=['POST'])
def mfa_backup_codes():
    user = _self_user()
    if not user or not user.mfa_enabled:
        return redirect(url_for('auth.security_settings'))
    if not user.check_password(request.form.get('password') or ''):
        flash('Password is incorrect — codes were not regenerated.', 'error')
        return redirect(url_for('auth.security_settings'))
    display, hashes = _make_backup_codes()
    user.set_mfa_backup_codes(hashes)
    db.session.commit()
    flash('New backup codes generated. Your old codes no longer work.', 'success')
    return render_template('auth/mfa_codes.html', codes=display, fresh=False)


def get_current_user():
    """Get the current logged-in user object"""
    user_id = session.get('user_id')
    if user_id:
        return db.session.get(User, user_id)
    return None


def is_admin():
    """Check if current user is admin"""
    role = session.get('role')
    return role in ('super_admin', 'admin')


def is_teacher():
    """Check if current user is teacher"""
    role = session.get('role')
    return role == 'teacher'


def can_access_class(class_arm_assignment_id):
    """Check if current user can access a specific class"""
    if is_admin():
        return True
    
    user = get_current_user()
    if user and user.is_teacher and user.teacher_profile:
        return user.teacher_profile.can_access_class(class_arm_assignment_id)
    
    return False
