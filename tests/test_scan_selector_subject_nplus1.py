"""_scan_selector_context() (shared by the scan, paste, broadsheet-import and
subject-sheet-import pages) and import_scores()'s own class_subjects query
both joined Subject for ordering but never eager-loaded it, so every
template rendering cs.subject.name in the dropdown (all four pages, plus
the plain Excel-import form) lazy-loaded one Subject row per class subject."""
import re
from sqlalchemy import event
from config import Config
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Subject, ClassSubject)
from tests.conftest import login_token

_N_SUBJECTS = 10
_SEQ = [0]


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


def _seed(app):
    with app.app_context():
        _SEQ[0] += 1
        tag = f'SSC{_SEQ[0]}'
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'{tag}-Sess'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'{tag}-Term'); db.session.add(term); db.session.flush()
        sc = SchoolClass(name=f'{tag}C', level=1); arm = ClassArm(name=f'{tag}A', is_active=True)
        db.session.add_all([sc, arm]); db.session.flush()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        for i in range(_N_SUBJECTS):
            subj = Subject(name=f'{tag}-Subj{i}', is_active=True)
            db.session.add(subj); db.session.flush()
            db.session.add(ClassSubject(subject_id=subj.id, class_id=sc.id, arm_id=arm.id,
                                        term_id=term.id, is_active=True))
        db.session.commit()
        return dict(term=term.id, asg=caa.id)


def test_scoresheet_scan_page_subject_lookups_do_not_scale(app):
    ids = _seed(app)
    c = _admin(app)
    url = f"/subjects/scores/scan?term_id={ids['term']}&assignment_id={ids['asg']}"
    n = _count_selects(app, 'subjects', lambda: c.get(url))
    assert n <= 2, f'{n} subjects SELECTs for a {_N_SUBJECTS}-subject scan page — looks like an N+1'


def test_scoresheet_paste_page_subject_lookups_do_not_scale(app):
    ids = _seed(app)
    c = _admin(app)
    url = f"/subjects/scores/paste?term_id={ids['term']}&assignment_id={ids['asg']}"
    n = _count_selects(app, 'subjects', lambda: c.get(url))
    assert n <= 2, f'{n} subjects SELECTs for a {_N_SUBJECTS}-subject paste page — looks like an N+1'


def test_import_scores_page_subject_lookups_do_not_scale(app):
    ids = _seed(app)
    c = _admin(app)
    url = f"/subjects/scores/import?term_id={ids['term']}&assignment_id={ids['asg']}"
    n = _count_selects(app, 'subjects', lambda: c.get(url))
    assert n <= 2, f'{n} subjects SELECTs for a {_N_SUBJECTS}-subject import page — looks like an N+1'
