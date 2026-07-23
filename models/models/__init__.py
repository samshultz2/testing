"""
Database models for the Student Management System
All models use SQLAlchemy ORM for database operations
"""
import os
from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy.session import Session as _FSQLASession
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.types import TypeDecorator, Text


class _TenantRoutingSession(_FSQLASession):
    """Routes every query/flush to the current request's tenant database when
    multi-tenancy is active. If no tenant engine is bound (single-school mode, or
    outside a request), it falls through to the normal Flask-SQLAlchemy binding —
    so with MULTI_TENANT off this behaves identically to the stock session."""

    def get_bind(self, *args, **kwargs):
        try:
            from flask import g, has_app_context
            if has_app_context():
                eng = g.__dict__.get('tenant_engine')
                if eng is not None:
                    return eng
        except Exception:
            pass
        return super().get_bind(*args, **kwargs)


db = SQLAlchemy(session_options={'class_': _TenantRoutingSession})


class EncryptedString(TypeDecorator):
    """A text column transparently AES-256-GCM encrypted at rest.

    Crypto helpers are imported lazily to avoid a circular import at model load
    time (the utils package imports models). When FIELD_ENCRYPTION_KEY is unset
    the helpers pass values through unchanged.
    """
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        from utils.crypto import encrypt
        return encrypt(value)

    def process_result_value(self, value, dialect):
        from utils.crypto import decrypt
        return decrypt(value)


def local_now():
    """Current datetime in the configured site timezone (naive wall-clock)."""
    try:
        from utils.timeutil import now as _now
        return _now()
    except Exception:
        return datetime.now()


# ============================================================================
# STUDENT MODELS
# ============================================================================





# ============================================================================
# ACADEMIC STRUCTURE MODELS
# ============================================================================













# ============================================================================
# ATTENDANCE MODELS
# ============================================================================







# ============================================================================
# RESULTS MODELS
# ============================================================================





# ============================================================================
# SCHOOL SETTINGS & CONFIGURATION
# ============================================================================







# ============================================================================
# SUBJECTS & ASSESSMENT SYSTEM
# ============================================================================















# ============================================================================
# TIMETABLE SYSTEM
# ============================================================================







# ============================================================================
# PROMOTION SYSTEM
# ============================================================================





# ============================================================================
# USER AUTHENTICATION
# ============================================================================













# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def _adapt_ddl(stmt, dialect):
    """Adapt a (SQLite-flavoured) ALTER TABLE statement to the active dialect.

    The lightweight migrations below are written with SQLite type names. On
    PostgreSQL ``DATETIME`` is not a real type and BOOLEAN columns reject integer
    literal defaults, so translate those before executing. (Most of these ALTERs
    are skipped on an established DB because the column already exists; this only
    matters the first time a genuinely new column is added on Postgres.)
    """
    if dialect == 'sqlite':
        return stmt
    import re
    out = re.sub(r'\bDATETIME\b', 'TIMESTAMP', stmt)
    out = re.sub(r'\bBOOLEAN DEFAULT 1\b', 'BOOLEAN DEFAULT TRUE', out)
    out = re.sub(r'\bBOOLEAN DEFAULT 0\b', 'BOOLEAN DEFAULT FALSE', out)
    return out


def _ensure_student_exam_columns():
    """
    Lightweight migration: add the optional WAEC/JAMB enrolment columns to the
    existing ``students`` table if they are not present yet. ``db.create_all()``
    only creates missing tables, never missing columns, so older databases need
    this ALTER TABLE to pick up new fields.
    """
    from sqlalchemy import inspect, text
    try:
        existing = {c['name'] for c in inspect(db.engine).get_columns('students')}
    except Exception:
        return
    statements = []
    if 'waec_subjects' not in existing:
        statements.append('ALTER TABLE students ADD COLUMN waec_subjects TEXT')
    if 'jamb_subjects' not in existing:
        statements.append('ALTER TABLE students ADD COLUMN jamb_subjects TEXT')
    if 'stream' not in existing:
        statements.append('ALTER TABLE students ADD COLUMN stream VARCHAR(20)')
    if 'jamb_target' not in existing:
        statements.append('ALTER TABLE students ADD COLUMN jamb_target INTEGER')
    if 'portal_password_hash' not in existing:
        statements.append('ALTER TABLE students ADD COLUMN portal_password_hash VARCHAR(256)')
    try:
        subj_cols = {c['name'] for c in inspect(db.engine).get_columns('subjects')}
        if 'has_practical' not in subj_cols:
            statements.append('ALTER TABLE subjects ADD COLUMN has_practical BOOLEAN DEFAULT 1')
    except Exception:
        pass

    # class_arms.is_default (the hidden 'General' arm for arm-less schools).
    try:
        ca_cols = {c['name'] for c in inspect(db.engine).get_columns('class_arms')}
        if 'is_default' not in ca_cols:
            statements.append('ALTER TABLE class_arms ADD COLUMN is_default BOOLEAN DEFAULT 0')
    except Exception:
        pass

    # message_recipients.error (added with the SMS gateway).
    try:
        mr_cols = {c['name'] for c in inspect(db.engine).get_columns('message_recipients')}
        if 'error' not in mr_cols:
            statements.append('ALTER TABLE message_recipients ADD COLUMN error TEXT')
    except Exception:
        pass

    # messages.status / scheduled_at (added with scheduled sends).
    try:
        m_cols = {c['name'] for c in inspect(db.engine).get_columns('messages')}
        if 'status' not in m_cols:
            statements.append("ALTER TABLE messages ADD COLUMN status VARCHAR(15) DEFAULT 'Draft'")
        if 'scheduled_at' not in m_cols:
            statements.append('ALTER TABLE messages ADD COLUMN scheduled_at DATETIME')
    except Exception:
        pass

    # cbt_exams time window + scaled total (added after initial release).
    try:
        ce_cols = {c['name'] for c in inspect(db.engine).get_columns('cbt_exams')}
        if 'start_time' not in ce_cols:
            statements.append('ALTER TABLE cbt_exams ADD COLUMN start_time VARCHAR(5)')
        if 'end_time' not in ce_cols:
            statements.append('ALTER TABLE cbt_exams ADD COLUMN end_time VARCHAR(5)')
        if 'max_score' not in ce_cols:
            statements.append('ALTER TABLE cbt_exams ADD COLUMN max_score FLOAT')
        if 'strict_mode' not in ce_cols:
            statements.append('ALTER TABLE cbt_exams ADD COLUMN strict_mode BOOLEAN DEFAULT 1')
        if 'violation_limit' not in ce_cols:
            statements.append('ALTER TABLE cbt_exams ADD COLUMN violation_limit INTEGER DEFAULT 3')
    except Exception:
        pass

    # cbt_questions.topic / subtopic (syllabus tags for topic-mastery analytics).
    try:
        cq_cols = {c['name'] for c in inspect(db.engine).get_columns('cbt_questions')}
        if 'topic' not in cq_cols:
            statements.append('ALTER TABLE cbt_questions ADD COLUMN topic VARCHAR(100)')
        if 'subtopic' not in cq_cols:
            statements.append('ALTER TABLE cbt_questions ADD COLUMN subtopic VARCHAR(120)')
    except Exception:
        pass

    # question_bank.subtopic (finer-grained syllabus tag).
    try:
        qb_cols = {c['name'] for c in inspect(db.engine).get_columns('question_bank')}
        if 'subtopic' not in qb_cols:
            statements.append('ALTER TABLE question_bank ADD COLUMN subtopic VARCHAR(120)')
    except Exception:
        pass

    # mock_jamb_exams online-sitting columns.
    try:
        mj_cols = {c['name'] for c in inspect(db.engine).get_columns('mock_jamb_exams')}
        if 'is_published' not in mj_cols:
            statements.append('ALTER TABLE mock_jamb_exams ADD COLUMN is_published BOOLEAN DEFAULT 0')
        if 'duration_minutes' not in mj_cols:
            statements.append('ALTER TABLE mock_jamb_exams ADD COLUMN duration_minutes INTEGER DEFAULT 120')
        if 'questions_per_subject' not in mj_cols:
            statements.append('ALTER TABLE mock_jamb_exams ADD COLUMN questions_per_subject INTEGER')
        if 'blueprint' not in mj_cols:
            statements.append('ALTER TABLE mock_jamb_exams ADD COLUMN blueprint TEXT')
        if 'novel_title' not in mj_cols:
            statements.append('ALTER TABLE mock_jamb_exams ADD COLUMN novel_title VARCHAR(150)')
        if 'source_mode' not in mj_cols:
            statements.append("ALTER TABLE mock_jamb_exams ADD COLUMN source_mode VARCHAR(10) DEFAULT 'bank'")
    except Exception:
        pass

    # mock_jamb_questions / mock_jamb_passages central-bank columns.
    try:
        mq_cols = {c['name'] for c in inspect(db.engine).get_columns('mock_jamb_questions')}
        if 'section' not in mq_cols:
            statements.append('ALTER TABLE mock_jamb_questions ADD COLUMN section VARCHAR(40)')
        if 'exam_body' not in mq_cols:
            statements.append("ALTER TABLE mock_jamb_questions ADD COLUMN exam_body VARCHAR(10) DEFAULT 'JAMB'")
        if 'difficulty' not in mq_cols:
            statements.append('ALTER TABLE mock_jamb_questions ADD COLUMN difficulty VARCHAR(10)')
        if 'source' not in mq_cols:
            statements.append('ALTER TABLE mock_jamb_questions ADD COLUMN source VARCHAR(20)')
        if 'source_ref' not in mq_cols:
            statements.append('ALTER TABLE mock_jamb_questions ADD COLUMN source_ref VARCHAR(40)')
        if 'exam_year' not in mq_cols:
            statements.append('ALTER TABLE mock_jamb_questions ADD COLUMN exam_year VARCHAR(8)')
    except Exception:
        pass
    try:
        mp_cols = {c['name'] for c in inspect(db.engine).get_columns('mock_jamb_passages')}
        if 'section' not in mp_cols:
            statements.append('ALTER TABLE mock_jamb_passages ADD COLUMN section VARCHAR(40)')
    except Exception:
        pass

    # cbt_attempts raw score columns.
    try:
        ca_cols = {c['name'] for c in inspect(db.engine).get_columns('cbt_attempts')}
        if 'raw_score' not in ca_cols:
            statements.append('ALTER TABLE cbt_attempts ADD COLUMN raw_score FLOAT DEFAULT 0')
        if 'raw_total' not in ca_cols:
            statements.append('ALTER TABLE cbt_attempts ADD COLUMN raw_total FLOAT DEFAULT 0')
        if 'violations' not in ca_cols:
            statements.append('ALTER TABLE cbt_attempts ADD COLUMN violations INTEGER DEFAULT 0')
        if 'paused_until' not in ca_cols:
            statements.append('ALTER TABLE cbt_attempts ADD COLUMN paused_until DATETIME')
        if 'last_seen' not in ca_cols:
            statements.append('ALTER TABLE cbt_attempts ADD COLUMN last_seen DATETIME')
        if 'ip_address' not in ca_cols:
            statements.append('ALTER TABLE cbt_attempts ADD COLUMN ip_address VARCHAR(50)')
        if 'user_agent' not in ca_cols:
            statements.append('ALTER TABLE cbt_attempts ADD COLUMN user_agent VARCHAR(255)')
    except Exception:
        pass

    # students.portal_password_plain (export student portal passwords later).
    try:
        if 'portal_password_plain' not in existing:
            statements.append('ALTER TABLE students ADD COLUMN portal_password_plain TEXT')
    except Exception:
        pass

    # users.allowed_modules (fine-grained module permissions).
    try:
        u_cols = {c['name'] for c in inspect(db.engine).get_columns('users')}
        if 'allowed_modules' not in u_cols:
            statements.append('ALTER TABLE users ADD COLUMN allowed_modules TEXT')
        if 'view_only' not in u_cols:
            statements.append('ALTER TABLE users ADD COLUMN view_only BOOLEAN DEFAULT 0')
        if 'permissions' not in u_cols:
            statements.append('ALTER TABLE users ADD COLUMN permissions TEXT')
        if 'rank' not in u_cols:
            statements.append('ALTER TABLE users ADD COLUMN rank INTEGER DEFAULT 0')
        if 'manage_scope' not in u_cols:
            statements.append("ALTER TABLE users ADD COLUMN manage_scope VARCHAR(10) DEFAULT 'none'")
        if 'theme' not in u_cols:
            statements.append('ALTER TABLE users ADD COLUMN theme VARCHAR(20)')
        if 'must_change_password' not in u_cols:
            statements.append('ALTER TABLE users ADD COLUMN must_change_password BOOLEAN DEFAULT 0')
        if 'dashboard_prefs' not in u_cols:
            statements.append('ALTER TABLE users ADD COLUMN dashboard_prefs TEXT')
        if 'reset_token_hash' not in u_cols:
            statements.append('ALTER TABLE users ADD COLUMN reset_token_hash VARCHAR(256)')
        if 'reset_token_expires' not in u_cols:
            statements.append('ALTER TABLE users ADD COLUMN reset_token_expires DATETIME')
        if 'permission_group_id' not in u_cols:
            statements.append('ALTER TABLE users ADD COLUMN permission_group_id INTEGER')
        if 'mfa_enabled' not in u_cols:
            statements.append('ALTER TABLE users ADD COLUMN mfa_enabled BOOLEAN DEFAULT 0')
        if 'mfa_secret' not in u_cols:
            statements.append('ALTER TABLE users ADD COLUMN mfa_secret TEXT')
        if 'mfa_backup_codes' not in u_cols:
            statements.append('ALTER TABLE users ADD COLUMN mfa_backup_codes TEXT')
    except Exception:
        pass

    # terms.results_published (release results to the parent/student portal).
    try:
        t_cols = {c['name'] for c in inspect(db.engine).get_columns('terms')}
        if 'results_published' not in t_cols:
            statements.append('ALTER TABLE terms ADD COLUMN results_published BOOLEAN DEFAULT 0')
    except Exception:
        pass

    # cbt question image columns (figures in questions).
    for tbl in ('cbt_questions', 'question_bank'):
        try:
            cols = {c['name'] for c in inspect(db.engine).get_columns(tbl)}
            if 'image_url' not in cols:
                statements.append(f'ALTER TABLE {tbl} ADD COLUMN image_url VARCHAR(300)')
        except Exception:
            pass

    # audit_logs target tracking (who did what, to what).
    try:
        al_cols = {c['name'] for c in inspect(db.engine).get_columns('audit_logs')}
        for col, ddl in (('target_type', 'VARCHAR(40)'), ('target_id', 'INTEGER'),
                         ('target_label', 'VARCHAR(150)'), ('branch_id', 'INTEGER'),
                         ('user_agent', 'VARCHAR(300)'), ('user_id', 'INTEGER')):
            if col not in al_cols:
                statements.append(f'ALTER TABLE audit_logs ADD COLUMN {col} {ddl}')
    except Exception:
        pass

    # cbt_login_events.device_model (device name, e.g. Redmi 13C).
    try:
        le_cols = {c['name'] for c in inspect(db.engine).get_columns('cbt_login_events')}
        if 'device_model' not in le_cols:
            statements.append('ALTER TABLE cbt_login_events ADD COLUMN device_model VARCHAR(80)')
    except Exception:
        pass

    # payslips.attendance_deduction (separates auto attendance vs manual deductions).
    try:
        ps_cols = {c['name'] for c in inspect(db.engine).get_columns('payslips')}
        if 'attendance_deduction' not in ps_cols:
            statements.append('ALTER TABLE payslips ADD COLUMN attendance_deduction FLOAT DEFAULT 0')
    except Exception:
        pass

    # Multi-branch: branch_id on branch-owned tables + users.scope (Stage 1).
    for tbl in ('students', 'teachers', 'class_arm_assignments', 'staff_members', 'users'):
        try:
            cols = {c['name'] for c in inspect(db.engine).get_columns(tbl)}
            if 'branch_id' not in cols:
                statements.append(f'ALTER TABLE {tbl} ADD COLUMN branch_id INTEGER')
        except Exception:
            pass
    # Stage 2b: branch_id on the remaining module root tables.
    for tbl in ('fee_payments', 'expenses', 'cbt_exams', 'library_books', 'applicants'):
        try:
            cols = {c['name'] for c in inspect(db.engine).get_columns(tbl)}
            if 'branch_id' not in cols:
                statements.append(f'ALTER TABLE {tbl} ADD COLUMN branch_id INTEGER')
        except Exception:
            pass
    # mock_jamb_exams.branch_id (per-branch mock exams). Backfill existing rows
    # to a branch so they aren't left unbranched — can_access_branch(None) is
    # permissive, which would leave old exams readable across branches.
    try:
        mj_cols = {c['name'] for c in inspect(db.engine).get_columns('mock_jamb_exams')}
        if 'branch_id' not in mj_cols:
            statements.append('ALTER TABLE mock_jamb_exams ADD COLUMN branch_id INTEGER')
            statements.append('UPDATE mock_jamb_exams SET branch_id = '
                              '(SELECT MIN(id) FROM branches) WHERE branch_id IS NULL')
    except Exception:
        pass
    # messages.branch_id (per-branch SMS/WhatsApp campaigns) + backfill.
    try:
        msg_cols = {c['name'] for c in inspect(db.engine).get_columns('messages')}
        if 'branch_id' not in msg_cols:
            statements.append('ALTER TABLE messages ADD COLUMN branch_id INTEGER')
            statements.append('UPDATE messages SET branch_id = '
                              '(SELECT MIN(id) FROM branches) WHERE branch_id IS NULL')
    except Exception:
        pass
    try:
        u_cols = {c['name'] for c in inspect(db.engine).get_columns('users')}
        if 'scope' not in u_cols:
            statements.append("ALTER TABLE users ADD COLUMN scope VARCHAR(10) DEFAULT 'branch'")
        if 'section' not in u_cols:
            statements.append('ALTER TABLE users ADD COLUMN section VARCHAR(20)')
        if 'stream' not in u_cols:
            statements.append('ALTER TABLE users ADD COLUMN stream VARCHAR(20)')
    except Exception:
        pass
    try:
        sc_cols = {c['name'] for c in inspect(db.engine).get_columns('school_classes')}
        if 'section' not in sc_cols:
            statements.append('ALTER TABLE school_classes ADD COLUMN section VARCHAR(20)')
    except Exception:
        pass
    try:
        ts_cols = {c['name'] for c in inspect(db.engine).get_columns('term_summaries')}
        if 'affective' not in ts_cols:
            statements.append('ALTER TABLE term_summaries ADD COLUMN affective TEXT')
    except Exception:
        pass

    # gen_teachers.user_id — links a timetable-generator teacher to a login
    # account, so a user can see the personal timetable published under that name.
    try:
        gt_cols = {c['name'] for c in inspect(db.engine).get_columns('gen_teachers')}
        if 'user_id' not in gt_cols:
            statements.append('ALTER TABLE gen_teachers ADD COLUMN user_id INTEGER')
    except Exception:
        pass

    if statements:
        dialect = db.engine.dialect.name
        with db.engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(_adapt_ddl(stmt, dialect)))

    # Make audit_logs append-only at the DB level too (Postgres): a BEFORE
    # DELETE/UPDATE trigger blocks tampering even from direct SQL, not just the
    # ORM guard. Idempotent + best-effort (skipped on SQLite, or if the DB role
    # lacks rights — the ORM-level guard still applies everywhere).
    try:
        if db.engine.dialect.name == 'postgresql':
            with db.engine.begin() as conn:
                conn.execute(text(
                    "CREATE OR REPLACE FUNCTION audit_logs_append_only() "
                    "RETURNS trigger AS $$ BEGIN "
                    "RAISE EXCEPTION 'audit_logs is append-only; % is not permitted', TG_OP; "
                    "END; $$ LANGUAGE plpgsql;"))
                conn.execute(text(
                    "DROP TRIGGER IF EXISTS audit_logs_no_delete ON audit_logs;"))
                conn.execute(text(
                    "CREATE TRIGGER audit_logs_no_delete "
                    "BEFORE DELETE OR UPDATE ON audit_logs "
                    "FOR EACH ROW EXECUTE FUNCTION audit_logs_append_only();"))
    except Exception:
        pass

    _ensure_indexes()




# Indexes on hot filter / foreign-key / sort columns. Created idempotently on
# startup so existing databases pick them up (student_id columns are deliberately
# left to the composite unique constraints that already cover them).
_INDEXES = [
    ('ix_ratelimit_key_ts', 'rate_limit_hits', 'rkey, ts'),
    ('ix_waec_exam_year', 'waec_results', 'exam_year'),
    ('ix_waec_subject', 'waec_results', 'subject'),
    ('ix_jamb_exam_year', 'jamb_results', 'exam_year'),
    ('ix_attendance_enrollment', 'attendance', 'enrollment_id'),
    ('ix_attendance_date', 'attendance', 'date'),
    ('ix_attendance_week', 'attendance', 'week_id'),
    ('ix_enrollment_caa', 'student_enrollments', 'class_arm_assignment_id'),
    ('ix_enrollment_active', 'student_enrollments', 'is_active'),
    ('ix_caa_term', 'class_arm_assignments', 'term_id'),
    ('ix_caa_branch', 'class_arm_assignments', 'branch_id'),
    # Per-class timetable lookups (view/print/apply all filter by class arm, and
    # the grid is keyed by day) and score lookups for result compilation.
    ('ix_classtt_caa', 'class_timetables', 'class_arm_assignment_id'),
    ('ix_classtt_caa_day', 'class_timetables', 'class_arm_assignment_id, day_of_week'),
    ('ix_ttbackup_term', 'timetable_backups', 'term_id'),
    ('ix_score_student', 'student_scores', 'student_id'),
    ('ix_score_classsubject', 'student_scores', 'class_subject_id'),
    ('ix_student_branch', 'students', 'branch_id'),
    ('ix_student_active', 'students', 'is_active'),
    ('ix_feepayment_term', 'fee_payments', 'term_id'),
    ('ix_feepayment_branch', 'fee_payments', 'branch_id'),
    ('ix_feepayment_receipt', 'fee_payments', 'receipt_no'),
    ('ix_expense_term', 'expenses', 'term_id'),
    ('ix_expense_branch', 'expenses', 'branch_id'),
    ('ix_feediscount_term', 'fee_discounts', 'term_id'),
    ('ix_cbt_attempt_exam', 'cbt_attempts', 'exam_id'),
    ('ix_cbt_attempt_student', 'cbt_attempts', 'student_id'),
    ('ix_cbt_answer_attempt', 'cbt_answers', 'attempt_id'),      # autosave lookup
    ('ix_cbt_violation_attempt', 'cbt_violations', 'attempt_id'),
    ('ix_cbt_login_exam', 'cbt_login_events', 'exam_id'),
    ('ix_cbt_login_exam_created', 'cbt_login_events', 'exam_id, created_at'),
    ('ix_cbt_device_exam', 'cbt_device_sessions', 'exam_id'),
    ('ix_audit_created', 'audit_logs', 'created_at'),
    ('ix_audit_action', 'audit_logs', 'action'),
    ('ix_mockresult_exam', 'mock_jamb_results', 'mock_exam_id'),
    # Perf pass 2 — only indexes NOT already covered by a leftmost unique-constraint
    # column (student_id on term_results/term_summaries/mock_waec_results is already
    # covered by their unique constraints, so not repeated here):
    ('ix_term_result_term', 'term_results', 'term_id'),          # all results in a term
    ('ix_term_summary_term', 'term_summaries', 'term_id'),       # term reports / dashboards
    ('ix_feepayment_student', 'fee_payments', 'student_id'),     # student fee history/statement
    ('ix_mockwaec_result_exam', 'mock_waec_results', 'mock_exam_id'),  # broadsheet/exam loads
    # Branch-scope indexes: branch_id is the primary access-control filter applied
    # on every list/search of a branch-owned table (scope_query). Index it on the
    # remaining branch-scoped tables so that filter never forces a full scan.
    ('ix_user_branch', 'users', 'branch_id'),
    ('ix_teacher_branch', 'teachers', 'branch_id'),
    ('ix_staff_branch', 'staff_members', 'branch_id'),
    ('ix_cbtexam_branch', 'cbt_exams', 'branch_id'),
    ('ix_book_branch', 'library_books', 'branch_id'),
    ('ix_applicant_branch', 'applicants', 'branch_id'),
    ('ix_message_branch', 'messages', 'branch_id'),
    ('ix_permgroup_branch', 'permission_groups', 'branch_id'),
    ('ix_mockjamb_exam_branch', 'mock_jamb_exams', 'branch_id'),
    ('ix_mockwaec_exam_branch', 'mock_waec_exams', 'branch_id'),
]


def _ensure_indexes():
    """Create the performance indexes if they don't exist (best-effort).

    On PostgreSQL, build CONCURRENTLY (and outside any transaction) so a deploy
    against a populated production table never takes a write-blocking lock — index
    creation is additive and can't lose data, but a plain CREATE INDEX would briefly
    block writes. SQLite (dev/test) doesn't support CONCURRENTLY, so it uses a plain
    transactional CREATE INDEX IF NOT EXISTS.
    """
    from sqlalchemy import inspect, text
    try:
        inspector = inspect(db.engine)
        tables = set(inspector.get_table_names())
    except Exception:
        return
    is_pg = db.engine.dialect.name == 'postgresql'
    for name, table, column in _INDEXES:
        if table not in tables:
            continue
        try:
            if is_pg:
                # CONCURRENTLY cannot run inside a transaction block.
                conn = db.engine.connect()
                try:
                    conn = conn.execution_options(isolation_level='AUTOCOMMIT')
                    conn.execute(text(
                        f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} ({column})'))
                finally:
                    conn.close()
            else:
                with db.engine.begin() as conn:
                    conn.execute(text(
                        f'CREATE INDEX IF NOT EXISTS {name} ON {table} ({column})'))
        except Exception:
            # Best-effort: a failed/interrupted CONCURRENTLY build leaves an INVALID
            # index that a later run (or the Alembic migration) can drop+rebuild.
            pass


def _classify_section(school_class):
    """Best-effort section for a class from its name, falling back to level."""
    name = (school_class.name or '').upper()
    if name.startswith('SS'):
        return 'senior'
    if name.startswith('JS'):
        return 'junior'
    if 'NUR' in name or name.startswith('KG') or 'CREC' in name or name.startswith('PRE'):
        return 'nursery'
    if 'PRI' in name or name.startswith('BAS'):
        return 'primary'
    lvl = school_class.level or 0
    if lvl >= 4:
        return 'senior'
    if lvl >= 1:
        return 'junior'
    return 'primary'


def _seed_branches():
    """Create the default branch and assign any unbranched data to it.

    Idempotent: only seeds the branch once, only backfills NULL branch_ids.
    Existing admins become 'central' so they keep seeing every branch.
    """
    from sqlalchemy import text
    from models.models_branch import Branch
    try:
        default = Branch.get_default()
        if default is None:
            # POSYHUB_DEFAULT_BRANCH lets a fresh install name its first branch;
            # this install's existing data belongs to the "Jemila" branch.
            name = os.environ.get('POSYHUB_DEFAULT_BRANCH', 'Jemila')
            default = Branch(name=name, is_default=True, is_active=True)
            db.session.add(default)
            db.session.commit()
        bid = default.id
        with db.engine.begin() as conn:
            for tbl in ('students', 'teachers', 'class_arm_assignments',
                        'staff_members', 'users', 'expenses', 'cbt_exams',
                        'library_books', 'applicants'):
                conn.execute(text(
                    f'UPDATE {tbl} SET branch_id = :bid WHERE branch_id IS NULL'),
                    {'bid': bid})
            # Records owned by a student inherit that student's branch.
            conn.execute(text(
                'UPDATE fee_payments SET branch_id = '
                '(SELECT branch_id FROM students WHERE students.id = fee_payments.student_id) '
                'WHERE branch_id IS NULL'))
            conn.execute(text(
                'UPDATE fee_payments SET branch_id = :bid WHERE branch_id IS NULL'),
                {'bid': bid})
            # Existing admins keep cross-branch visibility + can manage users.
            conn.execute(text(
                "UPDATE users SET scope = 'central', manage_scope = 'central', "
                "rank = 100 WHERE role IN ('super_admin', 'admin')"))
        # Classify any unsectioned classes (junior/senior/primary/nursery).
        for c in SchoolClass.query.filter(SchoolClass.section.is_(None)).all():
            c.section = _classify_section(c)
        db.session.commit()
    except Exception:
        db.session.rollback()


def init_db(app):
    """Initialize database with default data"""
    # Pure-Alembic deployments (and the Alembic baseline-generation step) set
    # SKIP_CREATE_ALL=1: Alembic owns the schema, so don't create_all or seed
    # here (seeding runs against a schema that may not exist yet).
    if os.environ.get('SKIP_CREATE_ALL') == '1':
        return
    with app.app_context():
        db.create_all()
        _ensure_student_exam_columns()
        _seed_branches()

        # Seed the default behavioural traits (idempotent).
        try:
            if BehaviouralTrait.query.count() == 0:
                from utils.report_card import AFFECTIVE_TRAITS
                for i, (key, label) in enumerate(AFFECTIVE_TRAITS):
                    db.session.add(BehaviouralTrait(key=key, label=label, order=i, is_active=True))
                db.session.commit()
        except Exception:
            db.session.rollback()

        # Seed standard course admission requirements (idempotent).
        try:
            from models.analytics_models import UniversityCutoff
            from utils.cutoff_seed import seed_cutoffs
            seed_cutoffs(db, UniversityCutoff)
        except Exception:
            db.session.rollback()

        # Create default classes if none exist
        if SchoolClass.query.count() == 0:
            default_classes = [
                ('JSS1', 1, 'Junior Secondary School 1'),
                ('JSS2', 2, 'Junior Secondary School 2'),
                ('JSS3', 3, 'Junior Secondary School 3'),
                ('SSS1', 4, 'Senior Secondary School 1'),
                ('SSS2', 5, 'Senior Secondary School 2'),
                ('SSS3', 6, 'Senior Secondary School 3'),
            ]
            for name, level, desc in default_classes:
                db.session.add(SchoolClass(
                    name=name, level=level, description=desc,
                    section='junior' if level <= 3 else 'senior'))
            db.session.commit()

        # Classify any class still missing a section (covers fresh installs where
        # default classes are created after the branch seeder ran).
        for c in SchoolClass.query.filter(SchoolClass.section.is_(None)).all():
            c.section = _classify_section(c)

        # Create default arms if none exist
        if ClassArm.query.count() == 0:
            default_arms = ['Rose', 'Lily', 'Iris', 'Daisy', 'Ivy', 'Violet']
            for arm_name in default_arms:
                db.session.add(ClassArm(name=arm_name))
        
        # Create default grade scale if none exists
        if GradeScale.query.count() == 0:
            default_grades = [
                ('A+', 80, 100, 'Excellent', 5.0, 1),
                ('A', 70, 79, 'Very Good', 4.0, 2),
                ('B', 60, 69, 'Good', 3.0, 3),
                ('C', 50, 59, 'Fair', 2.0, 4),
                ('F', 0, 49, 'Fail', 0.0, 5),
            ]
            for grade, min_s, max_s, remark, points, order in default_grades:
                db.session.add(GradeScale(
                    grade=grade, min_score=min_s, max_score=max_s,
                    remark=remark, points=points, order=order
                ))
        
        # Create default school settings if none exist
        if SchoolSettings.query.count() == 0:
            default_settings = [
                ('school_name', 'My School', 'string', 'Name of the school'),
                ('school_address', '', 'string', 'School address'),
                ('school_phone', '', 'string', 'School phone number'),
                ('school_email', '', 'string', 'School email'),
                ('school_motto', '', 'string', 'School motto'),
                ('school_day_start', '08:20', 'string', 'School day start time (HH:MM)'),
                ('school_day_end', '14:10', 'string', 'School day end time (HH:MM)'),
                ('period_duration', '40', 'int', 'Duration of each period in minutes'),
                ('break_duration', '30', 'int', 'Duration of break in minutes'),
                ('periods_per_day', '8', 'int', 'Number of periods per day'),
                ('promotion_threshold', '50', 'float', 'Minimum average score for promotion'),
                ('pass_mark', '50', 'int', 'Minimum score to pass a subject'),
            ]
            for key, value, vtype, desc in default_settings:
                db.session.add(SchoolSettings(
                    key=key, value=value, value_type=vtype, description=desc
                ))
        
        # Create default assessment types if none exist
        if AssessmentType.query.count() == 0:
            default_assessments = [
                ('Holiday Assignment', 'HA', 5, 1),
                ('1st CA', 'CA1', 5, 2),
                ('2nd CA', 'CA2', 5, 3),
                ('3rd CA', 'CA3', 5, 4),
                ('Midterm/Practicals', 'MID', 10, 5),
                ('CBT/Objectives', 'CBT', 30, 6),
                ('Theory Exam', 'EXAM', 40, 7),
            ]
            for name, short, max_score, order in default_assessments:
                db.session.add(AssessmentType(
                    name=name, short_name=short, max_score=max_score, order=order
                ))

        # Seed default expense categories for the finance module.
        try:
            from models.models_finance import ExpenseCategory
            if ExpenseCategory.query.count() == 0:
                for cat in ['Salaries & Wages', 'Utilities', 'Maintenance',
                            'Teaching Materials', 'Transport', 'Examinations',
                            'Administration', 'Miscellaneous']:
                    db.session.add(ExpenseCategory(name=cat))
        except Exception:
            db.session.rollback()

        # Seed default HR departments.
        try:
            from models.models_hr import Department
            if Department.query.count() == 0:
                for d in ['Academics', 'Administration', 'Bursary / Finance',
                          'Library', 'ICT', 'Security', 'Support / Cleaning', 'Health']:
                    db.session.add(Department(name=d))
        except Exception:
            db.session.rollback()

        # Seed default parent-communication templates.
        try:
            from models.models_comms import MessageTemplate
            if MessageTemplate.query.count() == 0:
                seed_templates = [
                    ('Fee Reminder', 'Fees',
                     'Dear {parent}, this is a reminder that {first_name} ({class}) '
                     'has an outstanding fee balance of {balance} for {term}. '
                     'Kindly make payment. Thank you. - {school}'),
                    ('Absence Notice', 'Attendance',
                     'Dear {parent}, our records show {first_name} ({class}) was '
                     'absent today. Please contact the school if this is unexpected. - {school}'),
                    ('Resumption Notice', 'General',
                     'Dear Parent, this is to inform you that school resumes on [DATE]. '
                     'Please ensure {first_name} resumes promptly. - {school}'),
                    ('PTA Meeting', 'Event',
                     'Dear Parent of {first_name} ({class}), there will be a PTA '
                     'meeting on [DATE] by [TIME]. Your presence is highly valued. - {school}'),
                    ('Result Notification', 'General',
                     'Dear {parent}, {first_name}\'s {term} result is now available. '
                     'Kindly visit the school to collect the report card. - {school}'),
                ]
                for name, cat, body in seed_templates:
                    db.session.add(MessageTemplate(name=name, category=cat, body=body))
        except Exception:
            db.session.rollback()

        # Create default admin user if none exists
        if User.query.count() == 0:
            admin = User(
                username='admin',
                email='admin@school.com',
                full_name='Administrator',
                role='admin',
                # The default password is public knowledge (it ships in source), so
                # force a change on first login — the account can't be left sitting
                # on the shipped credential.
                must_change_password=True,
            )
            admin.set_password('posyhubcomng')  # Default password — must be changed on first login
            db.session.add(admin)
        
        db.session.commit()


# ============================================================================
# TIMETABLE GENERATOR MODELS (Separate from main timetable)
# ============================================================================



































# ============================================================================
# TIMETABLE CONSTRAINT RULES (Database-driven)
# ============================================================================

# Re-export the model classes (split into submodules) so the public surface of
# `from models.models import X` is unchanged for the ~25 modules that import it.
from .student import *  # noqa: E402,F401,F403
from .academics import *  # noqa: E402,F401,F403
from .attendance import *  # noqa: E402,F401,F403
from .external_exams import *  # noqa: E402,F401,F403
from .subjects import *  # noqa: E402,F401,F403
from .scores import *  # noqa: E402,F401,F403
from .timetable import *  # noqa: E402,F401,F403
from .promotion import *  # noqa: E402,F401,F403
from .users import *  # noqa: E402,F401,F403
from .settings import *  # noqa: E402,F401,F403
from .generator import *  # noqa: E402,F401,F403

__all__ = [_n for _n in dir() if not _n.startswith('__')]
