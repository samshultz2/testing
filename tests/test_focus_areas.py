"""Teaching focus-areas diagnostics: cohort/class trends, model-weighted severity,
content-vs-format divergence, at-risk flags, real-JAMB fold-in, and the route."""
from datetime import date

from models import (db, Branch, Student, AcademicSession, Term, SchoolClass,
                    ClassArm, ClassArmAssignment, StudentEnrollment, JAMBResult)
from models.mock_waec import MockWAECExam, MockWAECResult, waec_grade_from_score
from models.mock_jamb import MockJAMBExam, MockJAMBResult
import utils.focus_areas as F


def _seed(app, tag, *, waec_sittings, jamb_sittings, real_jamb=None, n=10,
          classes=('Rose', 'Lily')):
    """Build an isolated branch with an ACTIVE session/term + SSS3 cohort, then add
    mock WAEC / mock JAMB sittings (and optionally real JAMB). `waec_sittings` and
    `jamb_sittings` are {subject: [score_mock1, score_mock2, ...]} cohort means; each
    student gets that score +/- a small per-student spread so dispersion is non-zero."""
    with app.app_context():
        br = Branch.query.filter_by(code=tag).first() or Branch(name=f'F {tag}', code=tag, is_active=True)
        db.session.add(br); db.session.flush()
        # make THIS session active (deactivate others) so build_focus_report picks it
        AcademicSession.query.update({AcademicSession.is_active: False})
        Term.query.update({Term.is_active: False})
        ssn = AcademicSession.query.filter_by(name=f'F {tag} 25/26').first() \
            or AcademicSession(name=f'F {tag} 25/26', is_active=True)
        ssn.is_active = True
        db.session.add(ssn); db.session.flush()
        term = Term.query.filter_by(session_id=ssn.id, term_number=2).first() \
            or Term(session_id=ssn.id, term_number=2, name='Second Term', is_active=True)
        term.is_active = True
        db.session.add(term); db.session.flush()
        sss3 = SchoolClass.query.filter_by(name='SSS3').first() or SchoolClass(name='SSS3', level=6)
        db.session.add(sss3); db.session.flush()

        caas = []
        for cl in classes:
            arm = ClassArm.query.filter_by(name=cl).first() or ClassArm(name=cl, is_active=True)
            db.session.add(arm); db.session.flush()
            caa = ClassArmAssignment.query.filter_by(class_id=sss3.id, arm_id=arm.id, term_id=term.id).first() \
                or ClassArmAssignment(class_id=sss3.id, arm_id=arm.id, term_id=term.id, branch_id=br.id)
            db.session.add(caa); db.session.flush()
            caas.append(caa)

        sids = []
        for i in range(n):
            st = Student(student_id=Student.generate_student_id(), first_name=f'F{i}',
                         surname=f'Foc{tag}', gender='Male', is_active=True, branch_id=br.id,
                         stream='Science', jamb_target=250)
            db.session.add(st); db.session.flush()
            db.session.add(StudentEnrollment(student_id=st.id,
                           class_arm_assignment_id=caas[i % len(caas)].id, is_active=True))
            sids.append(st.id)

        def add_mock_waec(num, means):
            ex = MockWAECExam(name=f'FW{tag}{num}', exam_number=num, session_id=ssn.id,
                              exam_date=date(2026, num, 1), branch_id=br.id)
            db.session.add(ex); db.session.flush()
            for k, sid in enumerate(sids):
                for subj, score in means.items():
                    s = max(0, min(100, score + (k % 5) - 2))   # small per-student spread
                    db.session.add(MockWAECResult(student_id=sid, mock_exam_id=ex.id,
                                   subject=subj, score=s, grade=waec_grade_from_score(s)))

        def add_mock_jamb(num, means):
            ex = MockJAMBExam(name=f'FJ{tag}{num}', exam_number=num, session_id=ssn.id,
                              exam_date=date(2026, num, 2), branch_id=br.id)
            db.session.add(ex); db.session.flush()
            subs = list(means)
            for k, sid in enumerate(sids):
                kw = {}
                for j, subj in enumerate(subs[:4]):
                    kw[f'subject{j+1}'] = subj
                    kw[f'subject{j+1}_score'] = max(0, min(100, means[subj] + (k % 5) - 2))
                total = sum(v for key, v in kw.items() if key.endswith('_score'))
                db.session.add(MockJAMBResult(student_id=sid, mock_exam_id=ex.id,
                               total_score=total, **kw))

        for num, sitting in enumerate(zip(*waec_sittings.values()), start=1):
            add_mock_waec(num, {s: sitting[i] for i, s in enumerate(waec_sittings)})
        for num, sitting in enumerate(zip(*jamb_sittings.values()), start=1):
            add_mock_jamb(num, {s: sitting[i] for i, s in enumerate(jamb_sittings)})

        if real_jamb:
            for k, sid in enumerate(sids):
                kw = {}
                subs = list(real_jamb)
                for j, subj in enumerate(subs[:4]):
                    kw[f'subject{j+1}'] = subj
                    kw[f'subject{j+1}_score'] = max(0, min(100, real_jamb[subj] + (k % 5) - 2))
                total = sum(v for key, v in kw.items() if key.endswith('_score'))
                db.session.add(JAMBResult(student_id=sid, exam_year=2026,
                               total_score=total, **kw))
        db.session.commit()
        return br.id, ssn.id, sids


def test_report_trends_and_severity(app):
    # Maths declining and weak; English improving and strong.
    bid, sid, _ = _seed(app, 'FA',
        waec_sittings={'Mathematics': [52, 47, 42], 'English Language': [55, 62, 70],
                       'Biology': [60, 60, 60]},
        jamb_sittings={'Mathematics': [40, 38, 35], 'Use of English': [55, 60, 66],
                       'Biology': [58, 58, 58], 'Chemistry': [50, 50, 50]})
    with app.app_context():
        rep = F.build_focus_report(sid, bid)
        assert rep['cohort_size'] == 10
        subs = {(e['source'], e['subject']): e for e in rep['focus']}
        maths = subs[('mock_waec', 'Mathematics')]
        eng = subs[('mock_waec', 'English Language')]
        assert maths['trend']['label'] == 'declining'
        assert eng['trend']['label'] == 'improving'
        # weak declining Maths must outrank strong improving English
        assert maths['focus_score'] > eng['focus_score']
        # core subjects flagged
        assert maths['is_core'] and eng['is_core']
        # Maths weak in both tests -> content gap
        assert maths['fix_type'] == 'content gap'


def test_per_class_breakdown_present(app):
    bid, sid, _ = _seed(app, 'FC',
        waec_sittings={'Mathematics': [48, 48, 48]},
        jamb_sittings={'Mathematics': [45, 45, 45], 'Biology': [55, 55, 55],
                       'Chemistry': [55, 55, 55], 'Physics': [55, 55, 55]},
        classes=('Rose', 'Lily'))
    with app.app_context():
        rep = F.build_focus_report(sid, bid)
        maths = next(e for e in rep['focus'] if e['subject'] == 'Mathematics' and e['source'] == 'mock_waec')
        cls = {c['class'] for c in maths['per_class']}
        assert {'Rose', 'Lily'} <= cls
        assert all('delta_vs_cohort' in c for c in maths['per_class'])


def test_at_risk_flags_declining_student(app):
    bid, sid, sids = _seed(app, 'FR',
        waec_sittings={'Mathematics': [44, 40, 36]},   # everyone below credit & declining
        jamb_sittings={'Mathematics': [40, 38, 36], 'Biology': [55, 55, 55],
                       'Chemistry': [55, 55, 55], 'Physics': [55, 55, 55]})
    with app.app_context():
        rep = F.build_focus_report(sid, bid)
        waec_flags = [f for f in rep['at_risk'] if f['source'] == 'Mock WAEC']
        assert waec_flags                      # at least some students flagged
        assert all(f['subject'] == 'Mathematics' for f in waec_flags)
        assert any(f['reason'] in ('declining', 'always below credit') for f in waec_flags)


def test_real_jamb_blind_spot(app):
    bid, sid, _ = _seed(app, 'FRJ',
        waec_sittings={'Biology': [60, 60, 60]},
        jamb_sittings={'Biology': [62, 62, 62], 'Chemistry': [60, 60, 60],
                       'Physics': [60, 60, 60], 'Mathematics': [60, 60, 60]},
        real_jamb={'Biology': 45, 'Chemistry': 60, 'Physics': 60, 'Mathematics': 60})
    with app.app_context():
        rep = F.build_focus_report(sid, bid)
        assert rep['has_real_jamb'] is True
        bio = next(e for e in rep['focus'] if e['subject'] == 'Biology' and e['source'] == 'mock_jamb')
        assert bio['reality'] is not None
        assert bio['reality']['blind_spot'] is True   # real 45 well below mock 62


def test_focus_route_admin_ok(app):
    bid, sid, _ = _seed(app, 'FRT',
        waec_sittings={'Mathematics': [48, 46, 44]},
        jamb_sittings={'Mathematics': [45, 45, 45], 'Biology': [55, 55, 55],
                       'Chemistry': [55, 55, 55], 'Physics': [55, 55, 55]})
    from config import Config
    from tests.conftest import login_token
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    r = c.get('/results/predictions/focus')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'Teaching focus areas' in html
    assert 'focus-card' in html          # a real ranked card rendered
    assert 'Mathematics' in html
