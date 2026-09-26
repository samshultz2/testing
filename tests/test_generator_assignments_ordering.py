"""/generator/assignments: subjects within each class's assignment table
must list alphabetically by subject name, and doing so shouldn't reopen the
N+1 lazy-load per row that eager-loading is meant to avoid."""
import re
import uuid
from sqlalchemy import event
from config import Config
from models import db, Branch, GenSubject, GenTeacher, GenTeacherAssignment, GenClassConfig
from tests.conftest import login_token


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


def _seed(app, tag, subject_names, active=True):
    """One class with one teacher-assignment per given subject name, added
    in the given (deliberately unsorted) order. `active=False` makes the
    subjects/teachers themselves inactive — the assignments page's own
    "Add Assignment" dropdowns only pull active subjects/teachers, and
    loading those first incidentally warms the session's identity map,
    which masks a real per-row lazy load for anything that happens to
    already be active. Using inactive rows sidesteps that false negative."""
    with app.app_context():
        bid = Branch.get_default().id
        cc = GenClassConfig(branch_id=bid, class_name=f'Zz{tag}', school_level='sss',
                            num_arms=1, arm_names=f'Zz{tag}Arm')
        db.session.add(cc); db.session.flush()

        for name in subject_names:
            subj = GenSubject(branch_id=bid, name=f'Zz{tag}{name}', school_level='sss',
                              is_active=active)
            teacher = GenTeacher(branch_id=bid, name=f'Zz{tag}{name}Teacher', school_level='sss',
                                 max_periods_per_day=6, max_periods_per_week=30, is_active=active)
            db.session.add_all([subj, teacher]); db.session.flush()
            db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=teacher.id,
                                                subject_id=subj.id, class_config_id=cc.id,
                                                arm_name=None))
        db.session.commit()
        return cc.id


def test_assignments_listed_alphabetically_by_subject_within_a_class(app):
    tag = f'Ord{uuid.uuid4().hex[:5]}'
    # Seeded Zebra, Apple, Mango — must render Apple, Mango, Zebra.
    _seed(app, tag, ['Zebra', 'Apple', 'Mango'])
    c = _admin(app)
    r = c.get('/generator/assignments')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    # The "Add Assignment" form's own Subject <select> already lists every
    # subject alphabetically regardless of this bug, and it renders before
    # the "Existing Assignments" table — search only the latter, or a
    # passing test wouldn't mean anything.
    body = body.split('Existing Assignments by Class')[1]

    apple_idx = body.index(f'Zz{tag}Apple')
    mango_idx = body.index(f'Zz{tag}Mango')
    zebra_idx = body.index(f'Zz{tag}Zebra')
    assert apple_idx < mango_idx < zebra_idx, (
        'subjects on /generator/assignments are not in alphabetical order within their class')


def test_assignments_page_does_not_scale_with_assignment_count(app):
    tag = f'N1{uuid.uuid4().hex[:5]}'
    # Inactive subjects/teachers: see _seed()'s docstring for why active
    # ones would incidentally mask a real lazy-load via the identity map.
    _seed(app, tag, ['Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon'], active=False)
    c = _admin(app)

    n_subjects = _count_selects(app, 'gen_subjects',
                                lambda: c.get('/generator/assignments'))
    assert n_subjects <= 3, (
        f'{n_subjects} gen_subjects SELECTs rendering the assignments page — '
        f'assignment.subject looks lazy-loaded per row instead of eager-loaded')

    n_teachers = _count_selects(app, 'gen_teachers',
                                lambda: c.get('/generator/assignments'))
    assert n_teachers <= 3, (
        f'{n_teachers} gen_teachers SELECTs rendering the assignments page — '
        f'assignment.teacher looks lazy-loaded per row instead of eager-loaded')
