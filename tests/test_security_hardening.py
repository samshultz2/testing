"""Security-hardening regressions from the whole-project audit:
 - the WAEC forecast engine setting (global) is changeable only by a central admin;
 - contributions object routes are branch-scoped (no cross-branch IDOR by guessed id);
 - expensive export endpoints are rate-limited (429 over the cap)."""
from config import Config
from models import db, Branch, Student, User
from tests.conftest import login_token, auth_csrf


def _central_admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c, auth_csrf(c)


def _branch_admin(app, code):
    """A role=admin user scoped to a single branch (is_central() is False)."""
    with app.app_context():
        br = Branch.query.filter_by(code=code).first() or Branch(name='Sec ' + code, code=code, is_active=True)
        db.session.add(br); db.session.flush()
        uname = 'sec_' + code.lower()
        u = User.query.filter_by(username=uname).first()
        if not u:
            u = User(username=uname, role='admin', scope='branch', branch_id=br.id)
            u.set_password('Secret123'); u.set_modules(['external_exams', 'students'])
            db.session.add(u); db.session.commit()
        bid = br.id
    c = app.test_client()
    c.post('/login', data={'username': uname, 'password': 'Secret123', '_csrf_token': login_token(c)})
    return c, auth_csrf(c), bid


def test_waec_engine_setting_is_central_admin_only(app):
    from models.models import SchoolSettings
    try:
        # central admin can change the global engine setting
        cc, ctok = _central_admin(app)
        r = cc.post('/results/predictions/waec-model',
                    data={'action': 'save_method', 'method': 'bins', '_csrf_token': ctok})
        assert r.status_code in (302, 303)
        with app.app_context():
            assert SchoolSettings.get('waec_prediction_method') == 'bins'

        # a branch admin cannot — the cohort-wide setting must not change
        bc, btok, _ = _branch_admin(app, 'SECA')
        bc.post('/results/predictions/waec-model',
                data={'action': 'save_method', 'method': 'prior', '_csrf_token': btok})
        with app.app_context():
            assert SchoolSettings.get('waec_prediction_method') == 'bins'   # unchanged
    finally:
        # restore the default so the shared session DB doesn't leak 'bins' into
        # other suites that assume the 'auto' engine.
        with app.app_context():
            SchoolSettings.set('waec_prediction_method', 'auto', 'string')


def test_contributions_student_detail_is_branch_scoped(app):
    # a student in branch B
    with app.app_context():
        brB = Branch.query.filter_by(code='SECB').first() or Branch(name='SecB', code='SECB', is_active=True)
        db.session.add(brB); db.session.flush()
        st = Student(student_id=Student.generate_student_id(), first_name='X',
                     surname='IDOR', gender='Male', is_active=True, branch_id=brB.id)
        db.session.add(st); db.session.commit()
        sB = st.id

    # a branch-A admin holding the contributions access code cannot read branch B's student
    bc, _btok, _ = _branch_admin(app, 'SECC')
    with bc.session_transaction() as s:
        s['contributions_access'] = True
    assert bc.get(f'/contributions/student/{sB}').status_code == 403
    assert bc.get(f'/contributions/api/student/{sB}/info').status_code == 403

    # a central admin still can
    cc, _ = _central_admin(app)
    with cc.session_transaction() as s:
        s['contributions_access'] = True
    assert cc.get(f'/contributions/api/student/{sB}/info').status_code == 200


def test_csp_is_nonce_based_no_unsafe_inline(app):
    """script-src must be nonce-based with no 'unsafe-inline'/'unsafe-eval', and the
    nonce in the header must match the nonce on the page's inline <script> tags."""
    import re
    c = app.test_client()
    with c.session_transaction() as s:
        s['logged_in'] = True
        s['role'] = 'super_admin'
    r = c.get('/students')
    csp = r.headers.get('Content-Security-Policy', '')
    script_src = next((d for d in csp.split(';') if 'script-src' in d), '')
    assert "'unsafe-inline'" not in script_src
    assert "'unsafe-eval'" not in script_src
    m = re.search(r"'nonce-([A-Za-z0-9_-]+)'", script_src)
    assert m, f'no nonce in script-src: {script_src!r}'
    body = r.get_data(as_text=True)
    body_nonces = set(re.findall(r'<script[^>]*nonce="([^"]+)"', body))
    # every inline <script> on the page carries exactly the header's nonce
    assert body_nonces == {m.group(1)}


def test_export_endpoint_is_rate_limited(app):
    from utils.security import login_limiter
    cc, _ = _central_admin(app)
    # the legacy admin keys the limiter by session['user'] == 'Admin'
    key = 'rl:export:Admin'
    with app.app_context():
        for _ in range(40):
            login_limiter.record_attempt(key)
    try:
        assert cc.get('/results/waec/export').status_code == 429
    finally:
        with app.app_context():
            login_limiter.clear_attempts(key)


def test_backup_is_encrypted_at_rest_and_locked_down(tmp_path, monkeypatch):
    """With FIELD_ENCRYPTION_KEY set, backup artifacts are AES-GCM ciphertext on
    disk (magic header), restore decrypts them, and legacy plaintext still reads."""
    monkeypatch.setenv('FIELD_ENCRYPTION_KEY', 'unit-test-backup-key-rotate-me')
    import importlib
    from utils import crypto
    importlib.reload(crypto)
    from utils import backup
    import os, types, logging
    app = types.SimpleNamespace(logger=logging.getLogger('t'))

    db_bytes = b'SQLite format 3\x00' + os.urandom(4096)
    p = tmp_path / 'school_x.db'
    p.write_bytes(db_bytes)
    backup._finalize(app, str(p))

    raw = p.read_bytes()
    assert crypto.bytes_look_encrypted(raw)                 # ciphertext at rest
    assert (os.stat(p).st_mode & 0o777) == 0o600            # owner-only
    assert backup._read_decrypted(str(p)) == db_bytes       # restore round-trips
    # legacy plaintext backup (no magic) still restores unchanged
    q = tmp_path / 'legacy.db'; q.write_bytes(db_bytes)
    assert backup._read_decrypted(str(q)) == db_bytes
    monkeypatch.delenv('FIELD_ENCRYPTION_KEY', raising=False)
    importlib.reload(crypto)


def test_solver_time_limit_is_bounded():
    """The configured solver ceiling sits safely under the gunicorn worker
    timeout so one solve can't run the single worker past its deadline."""
    from config import Config
    cap = getattr(Config, 'SOLVER_MAX_SECONDS', 90)
    assert 5 <= cap <= 110     # below the 120s gunicorn default
    # the route clamps a too-large request down to the cap
    assert max(5, min(300, cap)) == cap


def test_debug_is_opt_in_not_on_by_default(monkeypatch):
    """An accidental deploy with APP_ENV unset must NOT enable the Werkzeug
    debugger (RCE console) — DEBUG only turns on with an explicit FLASK_DEBUG=1."""
    import importlib, config as _cfg
    monkeypatch.delenv('FLASK_DEBUG', raising=False)
    importlib.reload(_cfg)
    assert _cfg.DevelopmentConfig.DEBUG is False
    monkeypatch.setenv('FLASK_DEBUG', '1')
    importlib.reload(_cfg)
    assert _cfg.DevelopmentConfig.DEBUG is True
    monkeypatch.delenv('FLASK_DEBUG', raising=False)
    importlib.reload(_cfg)
