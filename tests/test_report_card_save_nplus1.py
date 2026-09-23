"""Saving affective ratings / comments for a whole class used to run one
TermSummary SELECT per student inside the save loop (the GET/read side of
these same two routes already batched this correctly — only the POST/save
side still had the N+1). Regression: a class-sized save fires a small,
constant number of TermSummary SELECTs, not one per student."""
import re
from sqlalchemy import event
from config import Config
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment, TermSummary)
from tests.conftest import login_token

_CLASS_SIZE = 12
_SEQ = [0]


def _make_select_counter(table):
    pattern = re.compile(r'^select\b.*\bfrom\s+' + re.escape(table) + r'\b',
                         re.IGNORECASE | re.DOTALL)
    counts = {'n': 0}

    def before(conn, cursor, statement, params, context, executemany):
        if pattern.match(statement):
            counts['n'] += 1
    return counts, before


def _count_selects(app, table, fn):
    counts, before = _make_select_counter(table)
    with app.app_context():
        engine = db.engine
    event.listen(engine, 'before_cursor_execute', before)
    try:
        fn()
    finally:
        event.remove(engine, 'before_cursor_execute', before)
    return counts['n']


def _setup(app):
    with app.app_context():
        _SEQ[0] += 1
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'RCN-Sess-{_SEQ[0]}'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'RCN-Term-{_SEQ[0]}')
        db.session.add(term); db.session.flush()
        sc = SchoolClass.query.first(); arm = ClassArm.query.first()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        student_ids = []
        for i in range(_CLASS_SIZE):
            s = Student(student_id=f'RCN{_SEQ[0]}{i:03d}', first_name=f'S{i}', surname='Kid',
                       gender='Male', is_active=True, branch_id=bid)
            db.session.add(s); db.session.flush()
            db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id,
                                             is_active=True))
            student_ids.append(s.id)
        db.session.commit()
        return term.id, caa.id, student_ids


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _pt(c):
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get('/').get_data(as_text=True)).group(1)


def test_comments_save_does_not_scale_with_class_size(app):
    tid, aid, student_ids = _setup(app)
    c = _admin(app)
    tok = _pt(c)
    data = {'term_id': tid, 'assignment_id': aid, '_csrf_token': tok}
    for sid in student_ids:
        data[f't_{sid}'] = 'Good.'
        data[f'p_{sid}'] = 'Keep going.'

    n = _count_selects(app, 'term_summaries',
                       lambda: c.post('/subjects/comments', data=data, follow_redirects=True))
    # Batched: one bulk SELECT for existing TermSummary rows, not one per
    # student (would be _CLASS_SIZE=12 for the old per-row .first() lookup).
    assert n < _CLASS_SIZE, f'{n} TermSummary SELECTs for a {_CLASS_SIZE}-student save — looks like an N+1'

    with app.app_context():
        for sid in student_ids:
            ts = TermSummary.query.filter_by(student_id=sid, term_id=tid).first()
            assert ts.teacher_comment == 'Good.' and ts.principal_comment == 'Keep going.'


def test_affective_save_does_not_scale_with_class_size(app):
    tid, aid, student_ids = _setup(app)
    c = _admin(app)
    tok = _pt(c)
    data = {'term_id': tid, 'assignment_id': aid, '_csrf_token': tok}
    for sid in student_ids:
        data[f'r_{sid}_punctuality'] = '5'

    n = _count_selects(app, 'term_summaries',
                       lambda: c.post('/subjects/affective', data=data, follow_redirects=True))
    assert n < _CLASS_SIZE, f'{n} TermSummary SELECTs for a {_CLASS_SIZE}-student save — looks like an N+1'

    with app.app_context():
        for sid in student_ids:
            ts = TermSummary.query.filter_by(student_id=sid, term_id=tid).first()
            assert ts.affective_map.get('punctuality') == 5
