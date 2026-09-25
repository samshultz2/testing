"""The scratch-cards admin list (/scratch-cards/) and check log
(/scratch-cards/logs) pages lazy-loaded relationships per row with no eager
loading: the card list accessed c.term.name per card (up to 200/page), and
the log page accessed r.student, r.term AND r.card per row — up to 500 rows,
three lazy loads each."""
import re
import uuid
from datetime import date
from sqlalchemy import event
from config import Config
from models import (db, Branch, ScratchCard, ResultCheckLog, Term, AcademicSession, Student)
from tests.conftest import login_token

_N_CARDS = 20
_N_LOGS = 20


def _count_selects(app, table, fn):
    pattern = re.compile(r'^select\b.*\bfrom\s+' + re.escape(table) + r'\b',
                         re.IGNORECASE | re.DOTALL)
    counts = {'n': 0}

    def before(conn, cursor, statement, params, context, executemany):
        if pattern.match(statement):
            counts['n'] += 1
    with app.app_context():
        engine = db.engine
    event.listen(engine, 'before_cursor_execute', before)
    try:
        fn()
    finally:
        event.remove(engine, 'before_cursor_execute', before)
    return counts['n']


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _seed_cards(app, tag):
    """_N_CARDS cards, each restricted to its OWN distinct term (worst case
    for the .term lazy load — no repeats to benefit from identity-map reuse).

    Also seeds a disjoint, dedicated active session/term — index()'s own
    session_terms() dropdown query falls back to fetching EVERY term in the
    DB when there's no active session, which would pre-warm the identity map
    and accidentally mask the very N+1 this test exists to catch. Callers
    MUST deactivate the returned session (via _clear_active) once done, so
    this doesn't leak "the active session" into later tests."""
    with app.app_context():
        decoy_sess = AcademicSession(name=f'{tag}-DecoyActiveSess', is_active=True)
        db.session.add(decoy_sess); db.session.flush()
        db.session.add(Term(session_id=decoy_sess.id, term_number=1,
                            name=f'{tag}-DecoyActiveTerm', is_active=True))
        for i in range(_N_CARDS):
            sess = AcademicSession(name=f'{tag}-Sess{i}', is_active=False)
            db.session.add(sess); db.session.flush()
            term = Term(session_id=sess.id, term_number=1, name=f'{tag}-Term{i}', is_active=False)
            db.session.add(term); db.session.flush()
            db.session.add(ScratchCard(serial=f'{tag}SER{i}', pin=f'{tag}PIN{i}',
                                       max_uses=5, used_count=0, is_active=True,
                                       term_id=term.id, batch_label=tag))
        db.session.commit()
        return decoy_sess.id


def _clear_active(app, session_id):
    """Undo _seed_cards' decoy active session/term so it doesn't leak into
    other tests sharing this session-scoped test DB."""
    with app.app_context():
        AcademicSession.query.filter_by(id=session_id).update({'is_active': False})
        Term.query.filter_by(session_id=session_id).update({'is_active': False})
        db.session.commit()


def _seed_logs(app, tag):
    """_N_LOGS check-log rows, each with its OWN distinct student/term/card
    (worst case — no repeats)."""
    with app.app_context():
        bid = Branch.get_default().id
        for i in range(_N_LOGS):
            sess = AcademicSession(name=f'{tag}-LSess{i}', is_active=False)
            db.session.add(sess); db.session.flush()
            term = Term(session_id=sess.id, term_number=1, name=f'{tag}-LTerm{i}', is_active=False)
            db.session.add(term); db.session.flush()
            st = Student(student_id=f'{tag}STU{i}', first_name=f'S{i}', surname=tag,
                        gender='Male', is_active=True, branch_id=bid)
            db.session.add(st); db.session.flush()
            card = ScratchCard(serial=f'{tag}LSER{i}', pin=f'{tag}LPIN{i}',
                               max_uses=5, used_count=1, is_active=True, term_id=term.id)
            db.session.add(card); db.session.flush()
            db.session.add(ResultCheckLog(card_id=card.id, student_id=st.id, term_id=term.id,
                                          success=True, detail='OK', ip_address='127.0.0.1'))
        db.session.commit()


def test_card_list_term_lookups_do_not_scale_with_card_count(app):
    tag = f'SCN{uuid.uuid4().hex[:5]}'
    decoy_id = _seed_cards(app, tag)
    try:
        c = _admin(app)
        n = _count_selects(app, 'terms', lambda: c.get(f'/scratch-cards/?batch={tag}&per_page=200'))
        # A fixed ~3 'terms' SELECTs happen on every page in the app (nav/
        # active-term context processors) regardless of scratch-cards —
        # confirmed by probing an unrelated route. What must NOT scale with
        # card count is any SELECT beyond that fixed baseline.
        assert n <= 5, (
            f'{n} terms SELECTs for a {_N_CARDS}-card list (baseline ~3 expected) — '
            f'looks like an N+1 (c.term.name lazy-loaded per card instead of eager-loaded)')
    finally:
        _clear_active(app, decoy_id)


def test_logs_page_relationship_lookups_do_not_scale_with_row_count(app):
    tag = f'SCL{uuid.uuid4().hex[:5]}'
    _seed_logs(app, tag)
    c = _admin(app)
    n_students = _count_selects(app, 'students', lambda: c.get('/scratch-cards/logs'))
    n_terms = _count_selects(app, 'terms', lambda: c.get('/scratch-cards/logs'))
    n_cards = _count_selects(app, 'scratch_cards', lambda: c.get('/scratch-cards/logs'))
    assert n_students < _N_LOGS, f'{n_students} students SELECTs for {_N_LOGS} log rows — looks like an N+1'
    assert n_terms < _N_LOGS, f'{n_terms} terms SELECTs for {_N_LOGS} log rows — looks like an N+1'
    assert n_cards < _N_LOGS, f'{n_cards} scratch_cards SELECTs for {_N_LOGS} log rows — looks like an N+1'


def test_card_list_response_shape_unchanged(app):
    tag = f'SCR{uuid.uuid4().hex[:5]}'
    decoy_id = _seed_cards(app, tag)
    try:
        c = _admin(app)
        data = c.get(f'/scratch-cards/?batch={tag}&per_page=200',
                    headers={'X-Requested-With': 'fetch'}).get_json()
        cards = {row['serial']: row for row in data['cards']}
        assert len(cards) == _N_CARDS
        assert cards[f'{tag}SER0']['term_name'] == f'{tag}-Term0'
    finally:
        _clear_active(app, decoy_id)


def test_logs_page_response_shape_unchanged(app):
    tag = f'SCL2{uuid.uuid4().hex[:5]}'
    _seed_logs(app, tag)
    c = _admin(app)
    data = c.get('/scratch-cards/logs', headers={'X-Requested-With': 'fetch'}).get_json()
    match = f'{tag} S0'
    row = next((r for r in data['rows'] if r['student'] == match), None)
    assert row is not None, data['rows'][:3]
    assert row['term'] and row['card']
