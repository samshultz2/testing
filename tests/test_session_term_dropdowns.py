"""Term-picker dropdowns show only the active session's terms.

Switching the active academic session must change what every term dropdown
offers across the platform (finance, subjects, attendance, CBT, …), so a user
can never pick a term that belongs to a different session. session_terms() is the
single helper all those routes use to build the dropdown; these tests pin it."""
from models import db, AcademicSession, Term
from utils.helpers import session_terms


def _session(name, active, terms):
    s = AcademicSession(name=name, is_active=active)
    db.session.add(s); db.session.flush()
    for n in terms:
        db.session.add(Term(session_id=s.id, term_number=n,
                            name=f'{name} T{n}', is_active=False))
    db.session.commit()
    return s


def test_session_terms_returns_only_active_session(app):
    with app.app_context():
        AcademicSession.query.update({AcademicSession.is_active: False}, synchronize_session=False)
        db.session.commit()
        old = _session('2023/2024', active=False, terms=(1, 2, 3))
        new = _session('2024/2025', active=True, terms=(1, 2))

        got = session_terms()
        assert {t.session_id for t in got} == {new.id}     # nothing from the old session
        assert [t.term_number for t in got] == [2, 1]      # this session's terms, newest first
        # the old session's terms exist in the DB but are never offered
        assert old.id not in {t.session_id for t in got}


def test_session_terms_follows_a_switch(app):
    with app.app_context():
        AcademicSession.query.update({AcademicSession.is_active: False}, synchronize_session=False)
        db.session.commit()
        a = _session('2021/2022', active=True, terms=(1, 2, 3))
        b = _session('2022/2023', active=False, terms=(1, 2, 3))
        assert {t.session_id for t in session_terms()} == {a.id}

        # activate B → dropdowns must now offer B's terms, not A's
        AcademicSession.query.update({AcademicSession.is_active: False}, synchronize_session=False)
        db.session.get(AcademicSession, b.id).is_active = True
        db.session.commit()
        assert {t.session_id for t in session_terms()} == {b.id}


def test_session_terms_falls_back_when_no_active_session(app):
    """No active session (fresh/misconfigured install) — never hide everything."""
    with app.app_context():
        AcademicSession.query.update({AcademicSession.is_active: False}, synchronize_session=False)
        db.session.commit()
        _session('2020/2021', active=False, terms=(1, 2))
        assert len(session_terms()) >= 2                   # all terms, rather than empty
