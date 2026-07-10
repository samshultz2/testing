"""Attendance Phase 4 — intervention workflow: open, follow up, resolve, recommend
and track improvement vs baseline."""
from datetime import date, timedelta

from config import Config
from models import (db, Branch, Student, ClassArmAssignment, SchoolClass, ClassArm,
                    Term, AcademicSession, StudentEnrollment, Week, Attendance,
                    AttendanceIntervention, InterventionNote)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    return c


def _seed(app, tag, marks):
    with app.app_context():
        sess = AcademicSession(name=f'IVSess{tag}', is_active=False)
        db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'IVTerm{tag}', is_active=False,
                    start_date=date(2025, 5, 5), end_date=date(2025, 5, 9))
        db.session.add(term); db.session.flush()
        wk = Week(term_id=term.id, week_number=1, start_date=date(2025, 5, 5), end_date=date(2025, 5, 11))
        db.session.add(wk); db.session.flush()
        sc = SchoolClass(name=f'IVC{tag}', level=1); arm = ClassArm(name=f'IVA{tag}', is_active=True)
        db.session.add_all([sc, arm]); db.session.flush()
        bid = Branch.get_default().id
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        st = Student(student_id=f'IV{tag}', first_name='Ivy', surname=f'Zz{tag}',
                     gender='Female', is_active=True, branch_id=bid)
        db.session.add(st); db.session.flush()
        en = StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True)
        db.session.add(en); db.session.flush()
        for off, m, a in marks:
            db.session.add(Attendance(enrollment_id=en.id, week_id=wk.id,
                                      date=date(2025, 5, 5) + timedelta(days=off),
                                      morning_present=m, afternoon_present=a))
        db.session.commit()
        return term.id, caa.id, st.id


def test_open_snapshots_baseline_and_is_idempotent(app):
    from utils import attendance_interventions as IV
    tid, caa_id, sid = _seed(app, 'OP1', [(d, False, False) for d in range(5)])  # 0%
    with app.app_context():
        term = db.session.get(Term, tid)
        iv, created = IV.open_intervention(sid, term, reason='Low attendance', opened_by='Head')
        assert created and iv.baseline_pct == 0.0 and iv.status == 'Open'
        iv2, created2 = IV.open_intervention(sid, term)      # already open
        assert created2 is False and iv2.id == iv.id


def test_add_note_moves_to_in_progress(app):
    from utils import attendance_interventions as IV
    tid, caa_id, sid = _seed(app, 'NT1', [(d, False, False) for d in range(5)])
    with app.app_context():
        term = db.session.get(Term, tid)
        iv, _ = IV.open_intervention(sid, term)
        IV.add_note(iv, kind='Parent meeting', body='Met parents', author='Head')
        assert iv.status == 'In progress'
        assert InterventionNote.query.filter_by(intervention_id=iv.id).count() == 1


def test_resolve_records_outcome_and_current_pct(app):
    from utils import attendance_interventions as IV
    tid, caa_id, sid = _seed(app, 'RS1', [(d, True, True) for d in range(5)])  # 100%
    with app.app_context():
        term = db.session.get(Term, tid)
        iv, _ = IV.open_intervention(sid, term)
        assert IV.set_status(iv, 'Resolved', outcome='Attending well')
        assert iv.status == 'Resolved' and iv.resolved_at is not None
        assert iv.outcome == 'Attending well' and iv.resolved_pct == 100.0


def test_recommendations_exclude_open_cases(app):
    from utils import attendance_interventions as IV
    tid, caa_id, sid = _seed(app, 'RC1', [(d, False, False) for d in range(5)])
    with app.app_context():
        term = db.session.get(Term, tid)
        recs = IV.recommendations(term, [caa_id], threshold=75.0)
        assert any(r['student_id'] == sid for r in recs)
        IV.open_intervention(sid, term)
        recs2 = IV.recommendations(term, [caa_id], threshold=75.0)
        assert not any(r['student_id'] == sid for r in recs2)   # now excluded


def test_dashboard_buckets_direction(app):
    from utils import attendance_interventions as IV
    # baseline captured while all-absent (0%) then we add present days so current > baseline
    tid, caa_id, sid = _seed(app, 'DB1', [(0, False, False)])
    with app.app_context():
        term = db.session.get(Term, tid)
        iv, _ = IV.open_intervention(sid, term)        # baseline ~ low
        # improve: mark remaining days present
        en = StudentEnrollment.query.filter_by(student_id=sid).first()
        wk = Week.query.filter_by(term_id=tid).first()
        for off in range(1, 5):
            db.session.add(Attendance(enrollment_id=en.id, week_id=wk.id,
                                      date=date(2025, 5, 5) + timedelta(days=off),
                                      morning_present=True, afternoon_present=True))
        db.session.commit()
        dash = IV.dashboard(term, [caa_id])
        assert dash['counts']['active'] == 1
        assert dash['counts']['improved'] == 1          # current >> baseline


def test_intervention_endpoints(app):
    tid, caa_id, sid = _seed(app, 'EP1', [(d, False, False) for d in range(5)])
    client = _admin(app)
    with client.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    hdrs = {'X-Requested-With': 'fetch', 'X-CSRFToken': 'a' * 64, 'Content-Type': 'application/json'}
    r = client.post('/attendance/api/interventions/open',
                    json={'student_id': sid, 'term_id': tid}, headers=hdrs).get_json()
    assert r['ok'] and r['created']
    with app.app_context():
        iv_id = AttendanceIntervention.query.filter_by(student_id=sid).first().id
    n = client.post(f'/attendance/api/interventions/{iv_id}/note',
                    json={'kind': 'Call', 'body': 'Called parent'}, headers=hdrs).get_json()
    assert n['ok']
    st = client.post(f'/attendance/api/interventions/{iv_id}/status',
                     json={'status': 'Escalated'}, headers=hdrs).get_json()
    assert st['ok']
    # dashboard + profile expose it
    dash = client.get(f'/attendance/api/interventions?term_id={tid}').get_json()
    assert dash['counts']['active'] >= 1
    prof = client.get(f'/attendance/api/student/{sid}').get_json()
    assert 'interventions' in prof and len(prof['interventions']) >= 1
