"""Classes that have never marked attendance in a term are "no data", not 0% —
they're left out of analytics, alerts, low-attendance lists and student %s,
and listed separately so the office can chase them."""
from datetime import date

from models import db, Term, ClassArmAssignment, SchoolClass, ClassArm, Branch, Student, StudentEnrollment
from tests.test_attendance_analytics import _seed_term


def _add_unmarked_class(app, term_id, tag, n=3):
    with app.app_context():
        sc = SchoolClass(name=f'UMC{tag}', level=2); arm = ClassArm(name=f'UMA{tag}', is_active=True)
        db.session.add_all([sc, arm]); db.session.flush()
        bid = Branch.get_default().id
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term_id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        sids = []
        for i in range(n):
            st = Student(student_id=f'UM{tag}{i}', first_name='Un', surname=f'Marked{tag}{i}',
                         gender='Female', is_active=True, branch_id=bid)
            db.session.add(st); db.session.flush()
            db.session.add(StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True))
            sids.append(st.id)
        db.session.commit()
        return caa.id, sids


def test_analytics_skips_never_marked_class(app):
    from utils import attendance_analytics as AA
    tid, marked_id, _ = _seed_term(app, 'UM1', [('Ada', [(d, True, True) for d in range(5)])])
    unmarked_id, _ = _add_unmarked_class(app, tid, 'UM1')
    with app.app_context():
        term = db.session.get(Term, tid)
        caas = [db.session.get(ClassArmAssignment, marked_id), db.session.get(ClassArmAssignment, unmarked_id)]
        data = AA.build(term, caas, use_cache=False)
        assert data['kpis']['overall'] == 100.0          # not dragged down by 3 "0%" students
        assert data['kpis']['students'] == 1
        assert data['kpis']['classes'] == 1
        assert data['kpis']['chronic'] == 0
        assert [r['caa_id'] for r in data['class_rank']] == [marked_id]
        assert data['kpis']['worst_class'] == caas[0].display_name
        assert data['kpis']['classes_unmarked'] == 1
        assert data['unmarked_classes'][0]['caa_id'] == unmarked_id
        assert data['unmarked_classes'][0]['students'] == 3


def test_low_attendance_and_student_pct_ignore_unmarked(app):
    from utils.attendance_notify import _low_attendance_student_ids
    from utils.attendance_profile import bulk_term_percentages, student_term_percentage, marked_class_ids
    tid, marked_id, _ = _seed_term(app, 'UM2', [('Bo', [])])   # enrolled, marked class but no own marks
    unmarked_id, um_sids = _add_unmarked_class(app, tid, 'UM2')
    with app.app_context():
        term = db.session.get(Term, tid)
        assert marked_class_ids(tid, [marked_id, unmarked_id]) == set()   # nobody marked yet at all
    # mark someone in the first class so it counts as marked
    tid2, m2, _ = _seed_term(app, 'UM3', [('Cy', [(0, True, False)]), ('Di', [])])
    u2, um2 = _add_unmarked_class(app, tid2, 'UM3')
    with app.app_context():
        term = db.session.get(Term, tid2)
        assert marked_class_ids(tid2, [m2, u2]) == {m2}
        low = _low_attendance_student_ids(term, [m2, u2], 75)
        assert not set(um2) & set(low)
        pcts = bulk_term_percentages(um2, tid2)
        assert pcts == {}
        assert student_term_percentage(um2[0], tid2) is None


def test_alerts_api_lists_unmarked_separately(app):
    from tests.test_attendance_analytics import _admin
    tid, m, _ = _seed_term(app, 'UM4', [('Ed', [(0, True, False)])])
    u, _ = _add_unmarked_class(app, tid, 'UM4')
    c = _admin(app)
    r = c.get(f'/attendance/api/report/alerts?term_id={tid}&threshold=75')
    assert r.status_code == 200, r.data[:200]
    j = r.get_json()
    with app.app_context():
        uname = db.session.get(ClassArmAssignment, u).display_name
    assert uname in j['unmarked_classes']
    assert all(a['class_name'] != uname for a in j['alerts'])
