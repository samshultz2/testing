"""Applying a generated batch publishes it into the per-class timetable views."""
import re
from datetime import time

from config import Config
from models import (db, SchoolClass, ClassArm, ClassArmAssignment, ClassTimetable,
                    TimetableSlot, Subject, AcademicSession, Term, Branch,
                    GenSubject, GenTeacher, GenTimetableResult)
from tests.conftest import login_token


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def _setup(app):
    with app.app_context():
        term = Term.query.filter_by(is_active=True).first()
        if not term:
            s = AcademicSession(name='TTA-Sess', is_active=True)
            db.session.add(s); db.session.flush()
            term = Term(session_id=s.id, term_number=1, name='TTA-Term', is_active=True)
            db.session.add(term); db.session.commit()
        sc = SchoolClass.query.first()
        arm = ClassArm.query.first()
        caa = ClassArmAssignment.query.filter_by(
            class_id=sc.id, arm_id=arm.id, term_id=term.id).first()
        if not caa:
            caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id)
            db.session.add(caa); db.session.flush()
        # Two teaching periods (1, 2).
        for n in (1, 2):
            if not TimetableSlot.query.filter_by(slot_number=n, is_break=False).first():
                db.session.add(TimetableSlot(
                    slot_number=n, name=f'Period {n}', start_time=time(8 + n, 0),
                    end_time=time(8 + n, 40), is_break=False, order=n, is_active=True))
        # Academic subject that matches the gen subject by name.
        subj = Subject.query.filter_by(name='TTA-Math').first()
        if not subj:
            subj = Subject(name='TTA-Math', is_active=True)
            db.session.add(subj)
        gsub = GenSubject.query.filter_by(name='TTA-Math', school_level='sss').first()
        if not gsub:
            gsub = GenSubject(name='TTA-Math', school_level='sss')
            db.session.add(gsub)
        gteach = GenTeacher.query.filter_by(name='TTA Teacher', school_level='sss').first()
        if not gteach:
            gteach = GenTeacher(name='TTA Teacher', school_level='sss')
            db.session.add(gteach)
        db.session.flush()
        batch = 'TTAB1'
        if not GenTimetableResult.query.filter_by(batch_id=batch).first():
            for period in (1, 2):
                db.session.add(GenTimetableResult(
                    batch_id=batch, school_level='sss',
                    branch_id=Branch.get_default().id,
                    class_name=sc.name, arm_name=arm.name,
                    day_of_week=0, period_number=period,
                    subject_id=gsub.id, teacher_id=gteach.id))
        db.session.commit()
        return dict(caa=caa.id, batch=batch, subj=subj.id)


def test_apply_batch_fills_class_timetable(app):
    ids = _setup(app)
    client = _admin(app)

    page = client.get(f'/generator/results/{ids["batch"]}').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', page)
    token = m.group(1)
    assert 'Apply to Class Timetables' in page

    resp = client.post(f'/generator/results/{ids["batch"]}/apply',
                       data={'_csrf_token': token}, follow_redirects=False)
    assert resp.status_code in (302, 303)

    with app.app_context():
        rows = ClassTimetable.query.filter_by(class_arm_assignment_id=ids['caa']).all()
        assert len(rows) == 2
        assert all(r.subject_id == ids['subj'] for r in rows)
        assert all(r.teacher_name == 'TTA Teacher' for r in rows)
        assert {r.day_of_week for r in rows} == {0}


def test_apply_autocreates_subject_on_name_mismatch(app):
    """A generated subject with no academic match is created (cell not dropped)."""
    base = _setup(app)
    with app.app_context():
        sc = SchoolClass.query.get(
            ClassArmAssignment.query.get(base['caa']).class_id)
        arm = ClassArm.query.get(ClassArmAssignment.query.get(base['caa']).arm_id)
        assert Subject.query.filter_by(name='Astro-Nav 9000').first() is None
        gsub = GenSubject.query.filter_by(name='Astro-Nav 9000', school_level='sss').first()
        if not gsub:
            gsub = GenSubject(name='Astro-Nav 9000', school_level='sss')
            db.session.add(gsub)
        gteach = GenTeacher.query.filter_by(name='TTA Teacher', school_level='sss').first()
        db.session.flush()
        batch = 'TTAB2'
        if not GenTimetableResult.query.filter_by(batch_id=batch).first():
            db.session.add(GenTimetableResult(
                batch_id=batch, school_level='sss', branch_id=Branch.get_default().id,
                class_name=sc.name, arm_name=arm.name,
                day_of_week=1, period_number=1, subject_id=gsub.id,
                teacher_id=gteach.id if gteach else None))
        db.session.commit()

    client = _admin(app)
    page = client.get('/generator/results/TTAB2').get_data(as_text=True)
    token = re.search(r'name="csrf-token" content="([0-9a-f]+)"', page).group(1)
    client.post('/generator/results/TTAB2/apply', data={'_csrf_token': token})

    with app.app_context():
        created = Subject.query.filter_by(name='Astro-Nav 9000').first()
        assert created is not None       # auto-created so the cell isn't blank
        entry = ClassTimetable.query.filter_by(
            class_arm_assignment_id=base['caa'], day_of_week=1).first()
        assert entry is not None and entry.subject_id == created.id


def test_apply_backs_up_live_timetable_and_restore_works(app):
    ids = _setup(app)
    from models import TimetableBackup
    with app.app_context():
        slot = TimetableSlot.query.filter_by(slot_number=1, is_break=False).first()
        db.session.add(ClassTimetable(
            class_arm_assignment_id=ids['caa'], slot_id=slot.id, day_of_week=2,
            teacher_name='LIVE-KEEP', is_active=True))
        db.session.commit()
        term_id = ClassArmAssignment.query.get(ids['caa']).term_id
        before = TimetableBackup.query.filter_by(term_id=term_id).count()

    client = _admin(app)
    page = client.get(f'/generator/results/{ids["batch"]}').get_data(as_text=True)
    token = re.search(r'name="csrf-token" content="([0-9a-f]+)"', page).group(1)
    client.post(f'/generator/results/{ids["batch"]}/apply', data={'_csrf_token': token})

    with app.app_context():
        backups = (TimetableBackup.query.filter_by(term_id=term_id)
                   .order_by(TimetableBackup.id.desc()).all())
        assert len(backups) > before                     # apply made a backup
        latest = backups[0]
        assert latest.entry_count >= 1
        # the live entry was replaced by the applied batch
        assert ClassTimetable.query.filter_by(
            class_arm_assignment_id=ids['caa'], teacher_name='LIVE-KEEP').first() is None
        bid = latest.id

    bpage = client.get(f'/timetable/backups?term_id={term_id}').get_data(as_text=True)
    btok = re.search(r'name="csrf-token" content="([0-9a-f]+)"', bpage).group(1)
    client.post(f'/timetable/backups/{bid}/restore', headers={'X-Requested-With': 'fetch'},
                data={'_csrf_token': btok})

    with app.app_context():
        assert ClassTimetable.query.filter_by(
            class_arm_assignment_id=ids['caa'], teacher_name='LIVE-KEEP').first() is not None


def test_apply_replaces_existing_entries(app):
    ids = _setup(app)
    # Pre-seed a stale entry that should be wiped by the replace-mode apply.
    with app.app_context():
        slot = TimetableSlot.query.filter_by(slot_number=1, is_break=False).first()
        db.session.add(ClassTimetable(
            class_arm_assignment_id=ids['caa'], slot_id=slot.id, day_of_week=4,
            teacher_name='STALE', is_active=True))
        db.session.commit()
    client = _admin(app)
    page = client.get(f'/generator/results/{ids["batch"]}').get_data(as_text=True)
    token = re.search(r'name="csrf-token" content="([0-9a-f]+)"', page).group(1)
    client.post(f'/generator/results/{ids["batch"]}/apply', data={'_csrf_token': token})
    with app.app_context():
        rows = ClassTimetable.query.filter_by(class_arm_assignment_id=ids['caa']).all()
        assert all(r.teacher_name != 'STALE' for r in rows)   # stale entry replaced
        assert len(rows) == 2
