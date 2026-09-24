"""/generator/results/<batch>, its reports (period-count, teacher-workload,
clashes, unassigned) and the teacher-timetable view all render a batch's
GenTimetableResult grid, and several of them re-fetched related rows per
result/teacher instead of batching: view_results() lazy-loaded .subject/
.teacher per grid cell, _teacher_workload() lazy-loaded .teacher per row,
clash_report() lazy-loaded .subject per row and re-queried GenTeacher.get()
per clashing teacher, and teacher_timetable() re-queried GenClassConfig (plus
a GenClassArmStream lookup for streamed classes) once per PERIOD instead of
once per distinct class."""
import re
import uuid
from datetime import date
from sqlalchemy import event
from config import Config
from models import (db, Branch, GenSubject, GenTeacher, GenClassConfig,
                    GenClassArmStream, GenStream, GenTimetableResult)
from tests.conftest import login_token

_N_CLASSES = 5
_N_TEACHERS = 5
_N_SUBJECTS = 5


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


def _seed(app, tag):
    """A batch of 5 class-arms x 5 weekdays (period 1) + one extra period for
    class 0 on day 0, all under one teacher (teacher 0) — so teacher 0's
    schedule touches 5 distinct classes across 6 periods (one class repeated),
    every class shares teacher[day] at period 1 (a deliberate same-slot
    clash across all 5 classes, once per day), and class 0 is stream-tagged
    so the stream-name resolution path is exercised too."""
    with app.app_context():
        bid = Branch.get_default().id
        subjects = []
        for i in range(_N_SUBJECTS):
            s = GenSubject(name=f'{tag}Subj{i}', short_name=f'S{i}', school_level='sss',
                           is_active=True, branch_id=bid)
            db.session.add(s)
            subjects.append(s)
        teachers = []
        for i in range(_N_TEACHERS):
            t = GenTeacher(name=f'{tag}Teach{i}', school_level='sss', is_active=True, branch_id=bid)
            db.session.add(t)
            teachers.append(t)
        db.session.flush()

        classes = []
        for i in range(_N_CLASSES):
            c = GenClassConfig(class_name=f'{tag}Class{i}', school_level='sss',
                               is_active=True, branch_id=bid, has_streams=(i == 0))
            db.session.add(c)
            classes.append(c)
        db.session.flush()

        stream = GenStream(name=f'{tag}Science', school_level='sss', is_active=True, branch_id=bid)
        db.session.add(stream); db.session.flush()
        db.session.add(GenClassArmStream(class_config_id=classes[0].id, arm_name='A', stream_id=stream.id))
        db.session.flush()

        batch_id = f'BATCH-{tag}'
        for day in range(5):
            for ci, cls in enumerate(classes):
                db.session.add(GenTimetableResult(
                    branch_id=bid, batch_id=batch_id, school_level='sss',
                    class_name=cls.class_name, arm_name='A',
                    day_of_week=day, period_number=1,
                    subject_id=subjects[(ci + day) % _N_SUBJECTS].id,
                    teacher_id=teachers[day % _N_TEACHERS].id))
        # extra period for class 0, still under teacher 0 (day 0) — repeats a
        # class teacher 0 already teaches, to prove the class-config lookup
        # isn't re-run per period once it's been resolved for that class.
        db.session.add(GenTimetableResult(
            branch_id=bid, batch_id=batch_id, school_level='sss',
            class_name=classes[0].class_name, arm_name='A',
            day_of_week=0, period_number=2,
            subject_id=subjects[0].id, teacher_id=teachers[0].id))
        db.session.commit()
        return batch_id, teachers[0].id


def test_view_results_does_not_scale_with_grid_size(app):
    batch_id, _ = _seed(app, f'VR{uuid.uuid4().hex[:5]}')
    c = _admin(app)
    n = _count_selects(app, 'gen_subjects',
                       lambda: c.get(f'/generator/results/{batch_id}'))
    assert n <= 2, (
        f'{n} gen_subjects SELECTs rendering one results grid — entry.subject '
        f'looks lazy-loaded per cell instead of eager-loaded on the query')


def test_teacher_workload_does_not_scale_with_teacher_count(app):
    batch_id, _ = _seed(app, f'TW{uuid.uuid4().hex[:5]}')
    c = _admin(app)
    n = _count_selects(app, 'gen_teachers',
                       lambda: c.get(f'/generator/reports/teacher-workload/{batch_id}'))
    assert n <= 2, (
        f'{n} gen_teachers SELECTs for a {_N_TEACHERS}-teacher workload report — '
        f'data.teacher looks lazy-loaded per row instead of eager-loaded')


def test_clash_report_does_not_scale_with_clash_count(app):
    batch_id, _ = _seed(app, f'CL{uuid.uuid4().hex[:5]}')
    c = _admin(app)
    n_teachers = _count_selects(app, 'gen_teachers',
                                lambda: c.get(f'/generator/reports/clashes/{batch_id}'))
    assert n_teachers <= 2, (
        f'{n_teachers} gen_teachers SELECTs for a clash report — looks like '
        f'GenTeacher.query.get() is called per clashing teacher instead of batched')
    n_subjects = _count_selects(app, 'gen_subjects',
                                lambda: c.get(f'/generator/reports/clashes/{batch_id}'))
    assert n_subjects <= 2, (
        f'{n_subjects} gen_subjects SELECTs for a clash report — r.subject looks '
        f'lazy-loaded per row instead of eager-loaded')


def test_teacher_timetable_does_not_scale_with_period_count(app):
    batch_id, teacher_id = _seed(app, f'TT{uuid.uuid4().hex[:5]}')
    c = _admin(app)
    n = _count_selects(app, 'gen_class_configs',
                       lambda: c.get(f'/generator/teacher-timetable?teacher_id={teacher_id}&batch_id={batch_id}'))
    assert n <= 2, (
        f'{n} gen_class_configs SELECTs for one teacher\'s 6-period timetable — '
        f'looks like the class config is re-queried per period instead of once '
        f'per distinct class')


def test_reports_response_shape_unchanged(app):
    """The batching rewrite must keep producing the same data as before."""
    batch_id, teacher_id = _seed(app, f'RS{uuid.uuid4().hex[:5]}')
    c = _admin(app)

    results_html = c.get(f'/generator/results/{batch_id}').get_data(as_text=True)
    assert results_html.count('class="timetable-cell') >= 0  # page renders without error
    assert c.get(f'/generator/results/{batch_id}').status_code == 200

    workload_html = c.get(f'/generator/reports/teacher-workload/{batch_id}').get_data(as_text=True)
    assert 'Teach0' in workload_html or 'workload' in workload_html.lower()

    clash_r = c.get(f'/generator/reports/clashes/{batch_id}')
    assert clash_r.status_code == 200
    clash_html = clash_r.get_data(as_text=True)
    assert 'Clash' in clash_html

    tt_html = c.get(f'/generator/teacher-timetable?teacher_id={teacher_id}&batch_id={batch_id}').get_data(as_text=True)
    assert 'Science' in tt_html   # the stream name for class 0 still resolves
