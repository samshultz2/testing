"""Shared pytest fixtures. Each test run uses a fresh temporary database."""
import os
import re
import tempfile

import pytest

os.environ['POSYHUB_TESTING'] = '1'
# Legacy shared-password login now has no built-in password and is off by
# default; the suite exercises it, so opt in with a known test password before
# config is imported (real env vars still win via setdefault).
os.environ.setdefault('ENABLE_LEGACY_LOGIN', '1')
os.environ.setdefault('ADMIN_PASSWORD', 'test-admin-secret-pw')

from app import create_app  # noqa: E402
from config import Config  # noqa: E402


@pytest.fixture(scope='session')
def app():
    tmpdir = tempfile.mkdtemp()

    class TestConfig(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(tmpdir, 'test.db')
        BACKUP_RETENTION = 0

    return create_app(TestConfig)


@pytest.fixture()
def client(app):
    return app.test_client()


def login_token(client):
    html = client.get('/login').get_data(as_text=True)
    m = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def page_token(client):
    html = client.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def auth_csrf(client):
    """The session CSRF token AFTER login. Logins now rotate the token (session-
    fixation fix), so a token captured before login is no longer valid for
    post-login POSTs — read the current one straight from the session."""
    with client.session_transaction() as sess:
        return sess.get('_csrf_token')


@pytest.fixture()
def auth_client(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def enroll_sss3(app, student_id):
    """Enrol a student into SSS3 for an active term, so they count as an
    exam-eligible (WAEC / JAMB / Mock) student. Only SSS3 sit these exams, so
    ``get_sss3_students`` returns nobody until a student is actually enrolled.
    Idempotent; creates the term / SSS3 class / assignment if missing."""
    from models import (db, AcademicSession, Term, SchoolClass, ClassArm,
                        ClassArmAssignment, StudentEnrollment)
    with app.app_context():
        # The term the app itself treats as current (it keeps the active term
        # inside the active session); a term merely flagged active in some
        # other session would leave the student invisible to SSS3 lookups.
        from utils.helpers import get_active_term
        term = get_active_term()
        if term is None:
            ssn = (AcademicSession.query.filter_by(is_active=True).first()
                   or AcademicSession(name='ENR 25/26', is_active=True))
            db.session.add(ssn); db.session.flush()
            term = Term(session_id=ssn.id, term_number=1, name='First Term', is_active=True)
            db.session.add(term); db.session.flush()
        sss3 = SchoolClass.query.filter_by(name='SSS3').first() or SchoolClass(name='SSS3', level=6)
        db.session.add(sss3); db.session.flush()
        arm = ClassArm.query.first() or ClassArm(name='A', is_active=True)
        db.session.add(arm); db.session.flush()
        caa = (ClassArmAssignment.query.filter_by(class_id=sss3.id, term_id=term.id).first()
               or ClassArmAssignment(class_id=sss3.id, arm_id=arm.id, term_id=term.id))
        db.session.add(caa); db.session.flush()
        if not StudentEnrollment.query.filter_by(
                student_id=student_id, class_arm_assignment_id=caa.id).first():
            db.session.add(StudentEnrollment(
                student_id=student_id, class_arm_assignment_id=caa.id, is_active=True))
        db.session.commit()


@pytest.fixture(autouse=True)
def _fresh_rate_limits(request):
    """Every test starts with an empty rate-limit history. The session-wide app
    shares one database, and every test signs in as the same admin, so per-user
    caps on exports (PDF/Excel/…) used to fill up part-way through a full run
    and later tests got 429s depending on test order. Tests that exercise a
    limiter make their own hits inside the test, so clearing first is safe."""
    if 'app' in request.fixturenames or 'auth_client' in request.fixturenames or 'client' in request.fixturenames:
        app = request.getfixturevalue('app')
        from sqlalchemy import text
        from models import db
        from utils.security import login_limiter
        with app.app_context():
            try:
                with db.engine.begin() as conn:
                    conn.execute(text('DELETE FROM rate_limit_hits'))
            except Exception:
                pass
        with login_limiter._lock:
            login_limiter._attempts.clear()
    yield


def activate_term(term_id):
    """Make ``term_id`` and its session the only active term/session (the app
    keeps the active term inside the active session, so flagging the term alone
    isn't enough if another test left a different session active). Returns a
    restore() that puts the previous flags back. Call inside an app context."""
    from models import db, Term, AcademicSession
    prev_terms = [t.id for t in Term.query.filter_by(is_active=True).all()]
    prev_sess = [s.id for s in AcademicSession.query.filter_by(is_active=True).all()]
    term = db.session.get(Term, term_id)
    Term.query.update({Term.is_active: False}, synchronize_session=False)
    AcademicSession.query.update({AcademicSession.is_active: False}, synchronize_session=False)
    Term.query.filter_by(id=term_id).update({Term.is_active: True}, synchronize_session=False)
    AcademicSession.query.filter_by(id=term.session_id).update({AcademicSession.is_active: True}, synchronize_session=False)
    db.session.commit()

    def restore():
        Term.query.update({Term.is_active: False}, synchronize_session=False)
        AcademicSession.query.update({AcademicSession.is_active: False}, synchronize_session=False)
        if prev_terms:
            Term.query.filter(Term.id.in_(prev_terms)).update({Term.is_active: True}, synchronize_session=False)
        if prev_sess:
            AcademicSession.query.filter(AcademicSession.id.in_(prev_sess)).update(
                {AcademicSession.is_active: True}, synchronize_session=False)
        db.session.commit()
    return restore
