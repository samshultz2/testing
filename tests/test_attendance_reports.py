"""Attendance Phase 5 — presentation-ready analytics export (Excel/CSV) and
audit coverage for intervention + notify operations."""
from datetime import date, timedelta

from config import Config
from models import (db, Branch, Student, ClassArmAssignment, SchoolClass, ClassArm,
                    Term, AcademicSession, StudentEnrollment, Week, Attendance, AuditLog)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    return c


def _seed(app, tag):
    with app.app_context():
        sess = AcademicSession(name=f'RPSess{tag}', is_active=False)
        db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'RPTerm{tag}', is_active=False,
                    start_date=date(2025, 5, 5), end_date=date(2025, 5, 9))
        db.session.add(term); db.session.flush()
        wk = Week(term_id=term.id, week_number=1, start_date=date(2025, 5, 5), end_date=date(2025, 5, 11))
        db.session.add(wk); db.session.flush()
        sc = SchoolClass(name=f'RPC{tag}', level=1); arm = ClassArm(name=f'RPA{tag}', is_active=True)
        db.session.add_all([sc, arm]); db.session.flush()
        bid = Branch.get_default().id
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        st = Student(student_id=f'RP{tag}', first_name='Rep', surname=f'Zz{tag}',
                     gender='Female', is_active=True, branch_id=bid)
        db.session.add(st); db.session.flush()
        en = StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True)
        db.session.add(en); db.session.flush()
        for off in range(5):
            db.session.add(Attendance(enrollment_id=en.id, week_id=wk.id,
                                      date=date(2025, 5, 5) + timedelta(days=off),
                                      morning_present=(off % 2 == 0), afternoon_present=True))
        db.session.commit()
        return term.id, caa.id, st.id


def test_analytics_export_xlsx(app):
    tid, caa_id, sid = _seed(app, 'X1')
    client = _admin(app)
    r = client.get(f'/attendance/analytics/export?term_id={tid}&format=xlsx')
    assert r.status_code == 200
    assert 'spreadsheet' in r.headers['Content-Type']
    assert r.headers['Content-Disposition'].endswith('.xlsx')
    assert len(r.data) > 0


def test_analytics_export_csv_and_audit(app):
    tid, caa_id, sid = _seed(app, 'C1')
    client = _admin(app)
    r = client.get(f'/attendance/analytics/export?term_id={tid}&format=csv')
    assert r.status_code == 200 and 'text/csv' in r.headers['Content-Type']
    body = r.get_data(as_text=True)
    assert 'Executive summary' in body and 'Class ranking' in body
    with app.app_context():
        assert AuditLog.query.filter(AuditLog.action == 'attendance.analytics_export').count() >= 1


def test_intervention_open_is_audited(app):
    tid, caa_id, sid = _seed(app, 'A1')
    client = _admin(app)
    with client.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    hdrs = {'X-Requested-With': 'fetch', 'X-CSRFToken': 'a' * 64, 'Content-Type': 'application/json'}
    r = client.post('/attendance/api/interventions/open',
                    json={'student_id': sid, 'term_id': tid}, headers=hdrs).get_json()
    assert r['ok']
    with app.app_context():
        assert AuditLog.query.filter(AuditLog.action == 'attendance.intervention_open').count() >= 1
