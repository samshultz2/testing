"""Attendance Phase 2 — analytics service (KPIs, trend, distribution, ranking,
chronic, heatmap) + endpoint + cache behaviour."""
from datetime import date, timedelta

from config import Config
from models import (db, Branch, Student, ClassArmAssignment, SchoolClass, ClassArm,
                    Term, AcademicSession, StudentEnrollment, Week, Attendance)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    return c


def _seed_term(app, tag, students):
    """A fresh term + class with the given students' present-session totals.
    ``students`` = list of (name, [ (date_offset, morning, afternoon) ])."""
    with app.app_context():
        sess = AcademicSession(name=f'ANSess{tag}', is_active=False)
        db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'ANTerm{tag}', is_active=False,
                    start_date=date(2025, 5, 5), end_date=date(2025, 5, 9))
        db.session.add(term); db.session.flush()
        wk = Week(term_id=term.id, week_number=1, start_date=date(2025, 5, 5),
                  end_date=date(2025, 5, 11))
        db.session.add(wk); db.session.flush()
        sc = SchoolClass(name=f'ANC{tag}', level=1); arm = ClassArm(name=f'ANA{tag}', is_active=True)
        db.session.add_all([sc, arm]); db.session.flush()
        bid = Branch.get_default().id
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        sids = []
        for i, (name, marks) in enumerate(students):
            st = Student(student_id=f'AN{tag}{i}', first_name=name, surname=f'Zz{tag}{i}',
                         gender='Male', is_active=True, branch_id=bid)
            db.session.add(st); db.session.flush()
            en = StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True)
            db.session.add(en); db.session.flush()
            for off, m, a in marks:
                db.session.add(Attendance(enrollment_id=en.id, week_id=wk.id,
                                          date=date(2025, 5, 5) + timedelta(days=off),
                                          morning_present=m, afternoon_present=a))
            sids.append(st.id)
        db.session.commit()
        return term.id, caa.id, sids


def test_analytics_kpis_and_distribution(app):
    from utils import attendance_analytics as AA
    # 5 school days (Mon–Fri). Student A: all present (100%). B: all absent (0%).
    marks_full = [(d, True, True) for d in range(5)]
    tid, caa_id, sids = _seed_term(app, 'K1', [('Ada', marks_full), ('Bo', [])])
    with app.app_context():
        term = db.session.get(Term, tid)
        caa = db.session.get(ClassArmAssignment, caa_id)
        data = AA.build(term, [caa], is_central=False, use_cache=False)
        assert data['kpis']['students'] == 2
        assert data['kpis']['overall'] == 50.0        # (10 + 0) / 20
        assert data['distribution']['excellent'] == 1  # Ada 100%
        assert data['distribution']['poor'] == 1        # Bo 0%
        assert data['kpis']['chronic'] == 1             # Bo < 50%
        assert any(c['percentage'] == 0.0 for c in data['chronic_list'])
        assert len(data['heatmap']) == 5
        assert len(data['trend']) == 1                  # one week


def test_class_ranking_orders_by_rate(app):
    from utils import attendance_analytics as AA
    tid, caa_id, sids = _seed_term(app, 'R1', [('Ada', [(d, True, True) for d in range(5)])])
    with app.app_context():
        term = db.session.get(Term, tid)
        caa = db.session.get(ClassArmAssignment, caa_id)
        data = AA.build(term, [caa], use_cache=False)
        assert data['class_rank'][0]['percentage'] == 100.0
        assert data['kpis']['best_class'] == caa.display_name


def test_analytics_endpoint(app):
    tid, caa_id, sids = _seed_term(app, 'E1', [('Ada', [(d, True, True) for d in range(5)])])
    client = _admin(app)
    r = client.get(f'/attendance/api/analytics?term_id={tid}')
    assert r.status_code == 200
    j = r.get_json()
    assert 'kpis' in j and 'class_rank' in j and 'distribution' in j


def test_cache_set_and_invalidate(app):
    from utils import attendance_analytics as AA
    from models.analytics_models import AnalyticsCache
    tid, caa_id, sids = _seed_term(app, 'C1', [('Ada', [(d, True, True) for d in range(5)])])
    with app.app_context():
        term = db.session.get(Term, tid)
        caa = db.session.get(ClassArmAssignment, caa_id)
        AA.build(term, [caa], use_cache=True)      # populates cache
        key = AA._cache_key(tid, [caa_id])
        assert AnalyticsCache.get(key) is not None
        AA.invalidate_term(tid)
        assert AnalyticsCache.get(key) is None
