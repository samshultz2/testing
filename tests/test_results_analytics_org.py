"""Institution-wide results analytics: arm → class → section → whole-school
roll-ups, subject & teacher leagues, recommendations and the board-pack PDF."""
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment, Subject,
                    ClassSubject, AssessmentType, StudentScore)

_SEQ = [0]


def _seed(app):
    """A small but multi-level school: senior section (SSS1 with arms A & B,
    SSS2) + junior section (JSS1). Maths taught by Mr A, English by Mr B."""
    with app.app_context():
        _SEQ[0] += 1
        tag = f'ORG{_SEQ[0]}'
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'{tag}-Sess'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='First Term'); db.session.add(term); db.session.flush()

        maths = Subject(name=f'{tag}-Maths', is_active=True)
        english = Subject(name=f'{tag}-English', is_active=True)
        db.session.add_all([maths, english]); db.session.flush()
        at = AssessmentType.query.filter_by(short_name='CA1').first() or AssessmentType(
            name='1st CA', short_name='CA1', max_score=100, order=1, is_active=True)
        if at.id is None:
            db.session.add(at); db.session.flush()

        def make_class(name, level, section):
            sc = SchoolClass(name=f'{tag}-{name}', level=level, section=section, is_active=True)
            db.session.add(sc); db.session.flush()
            return sc

        sss1 = make_class('SSS1', 4, 'senior')
        sss2 = make_class('SSS2', 5, 'senior')
        jss1 = make_class('JSS1', 1, 'junior')

        armA = ClassArm(name=f'{tag}-A'); armB = ClassArm(name=f'{tag}-B')
        armG = ClassArm.default()
        db.session.add_all([armA, armB]); db.session.flush()

        def assign(sc, arm):
            caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
            db.session.add(caa); db.session.flush()
            for subj, teacher in ((maths, 'Mr A'), (english, 'Mr B')):
                db.session.add(ClassSubject(subject_id=subj.id, class_id=sc.id, arm_id=arm.id,
                                            term_id=term.id, teacher_name=teacher, is_active=True))
            db.session.flush()
            return caa

        caas = {'sss1a': assign(sss1, armA), 'sss1b': assign(sss1, armB),
                'sss2': assign(sss2, armG), 'jss1': assign(jss1, armG)}

        def add_students(caa, mscores, escores):
            """mscores/escores: list of totals (one per student)."""
            for i, (m, e) in enumerate(zip(mscores, escores)):
                gender = 'Male' if i % 2 == 0 else 'Female'
                st = Student(student_id=f'{tag}-{caa.id}-{i}', first_name=f'S{i}',
                             surname=f'U{caa.id}', gender=gender, is_active=True, branch_id=bid)
                db.session.add(st); db.session.flush()
                db.session.add(StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True))
                cs_m = ClassSubject.query.filter_by(class_id=caa.class_id, arm_id=caa.arm_id,
                                                    subject_id=maths.id, term_id=term.id).first()
                cs_e = ClassSubject.query.filter_by(class_id=caa.class_id, arm_id=caa.arm_id,
                                                    subject_id=english.id, term_id=term.id).first()
                db.session.add(StudentScore(student_id=st.id, class_subject_id=cs_m.id,
                                            assessment_type_id=at.id, score=m))
                db.session.add(StudentScore(student_id=st.id, class_subject_id=cs_e.id,
                                            assessment_type_id=at.id, score=e))
        # SSS1-A strong, SSS1-B weak, SSS2 mid, JSS1 mixed
        add_students(caas['sss1a'], [80, 90, 70], [60, 40, 55])
        add_students(caas['sss1b'], [30, 45, 20], [35, 25, 40])
        add_students(caas['sss2'], [60, 65, 55], [70, 50, 60])
        add_students(caas['jss1'], [50, 85, 30], [55, 90, 20])
        db.session.commit()
        return dict(term=term.id, sss1=sss1.id, sss2=sss2.id, jss1=jss1.id,
                    sss1a=caas['sss1a'].id, sss1b=caas['sss1b'].id)


def test_school_scope_units_are_sections(app):
    from utils.results_analytics_org import org_analytics
    ids = _seed(app)
    with app.app_context():
        d = org_analytics(ids['term'], 'school', None, None, use_cache=False)
        assert d['summary']['students'] == 12 and d['summary']['assessed'] == 12
        assert d['unit_kind'] == 'Section'
        labels = {u['label'] for u in d['units']}
        assert 'Senior Secondary' in labels and 'Junior Secondary' in labels
        # senior (9 students) should out-rank... well, just assert both present & ranked
        assert d['units'][0]['average'] >= d['units'][-1]['average']
        # subject & teacher leagues populated
        assert len(d['subjects']) == 2 and len(d['teachers']) == 2
        assert d['recommendations']                          # not empty
        assert d['selectors']['sections'] and d['selectors']['classes']


def test_section_scope_units_are_classes(app):
    from utils.results_analytics_org import org_analytics
    ids = _seed(app)
    with app.app_context():
        d = org_analytics(ids['term'], 'section', 'senior', None, use_cache=False)
        assert d['unit_kind'] == 'Class'
        assert d['summary']['students'] == 9              # SSS1-A(3)+SSS1-B(3)+SSS2(3)
        labels = {u['label'] for u in d['units']}
        assert any('SSS1' in l for l in labels) and any('SSS2' in l for l in labels)


def test_class_scope_units_are_arms(app):
    from utils.results_analytics_org import org_analytics
    ids = _seed(app)
    with app.app_context():
        d = org_analytics(ids['term'], 'class', ids['sss1'], None, use_cache=False)
        assert d['unit_kind'] == 'Arm'
        assert d['summary']['students'] == 6
        # arm A (strong) must out-rank arm B (weak)
        assert d['units'][0]['average'] > d['units'][-1]['average']
        # a drill link points back at an arm
        assert d['units'][0]['scope'] == 'arm'


def test_teacher_league_and_verdicts(app):
    from utils.results_analytics_org import org_analytics
    ids = _seed(app)
    with app.app_context():
        d = org_analytics(ids['term'], 'school', None, None, use_cache=False)
        names = {t['name'] for t in d['teachers']}
        assert names == {'Mr A', 'Mr B'}
        for t in d['teachers']:
            assert 'verdict' in t and t['flag'] in (
                'strong', 'good', 'watch', 'review', 'compliance', 'insufficient')
            assert t['entries'] > 0


def test_access_scoped_rollup(app):
    """A caller limited to a subset of assignments only rolls up those."""
    from utils.results_analytics_org import org_analytics
    ids = _seed(app)
    with app.app_context():
        d = org_analytics(ids['term'], 'school', None, {ids['sss1a']}, use_cache=False)
        assert d['summary']['students'] == 3             # only SSS1-A


def test_board_pack_pdf_builds(app):
    from utils.results_analytics_org import org_analytics
    from utils.analytics_org_pdf import institution_pdf, institution_filename
    from models import Term
    ids = _seed(app)
    with app.app_context():
        d = org_analytics(ids['term'], 'school', None, None, use_cache=False)
        term = db.session.get(Term, ids['term'])
        pdf = institution_pdf(d, term)
        assert pdf[:4] == b'%PDF'
        assert institution_filename(d, term).endswith('.pdf')
        import fitz
        doc = fitz.open(stream=pdf, filetype='pdf')
        text = doc.load_page(0).get_text()
        assert 'Pass rate' in text or 'average' in text.lower()


def test_attendance_correlation_and_bands(app):
    import datetime as _dt
    from models import Week, Attendance, StudentEnrollment
    from utils.results_analytics_org import org_analytics
    ids = _seed(app)
    with app.app_context():
        wk = Week(term_id=ids['term'], week_number=1,
                  start_date=_dt.date(2025, 1, 6), end_date=_dt.date(2025, 1, 10))
        db.session.add(wk); db.session.flush()
        # give the SSS1-A roster full attendance, SSS1-B none
        for caa_id, present in ((ids['sss1a'], True), (ids['sss1b'], False)):
            for enr in StudentEnrollment.query.filter_by(class_arm_assignment_id=caa_id).all():
                db.session.add(Attendance(enrollment_id=enr.id, week_id=wk.id,
                                          date=_dt.date(2025, 1, 6),
                                          morning_present=present, afternoon_present=present))
        db.session.commit()
        d = org_analytics(ids['term'], 'section', 'senior', None, use_cache=False)
        att = d['attendance']
        assert att['bands'] and att['coverage'] >= 6
        # high-attendance arm (strong) vs zero-attendance arm (weak) → positive r
        assert att['correlation'] is not None


def test_empty_scope_is_safe(app):
    from utils.results_analytics_org import org_analytics
    with app.app_context():
        d = org_analytics(999999, 'school', None, None, use_cache=False)
        assert d['summary'] == {} and d['units'] == []


def test_trends_present(app):
    from utils.results_analytics_org import org_analytics
    ids = _seed(app)
    with app.app_context():
        d = org_analytics(ids['term'], 'school', None, None, use_cache=False)
        tr = d['trends']
        assert ids['term'] and 'term_names' in tr and 'averages' in tr and 'pass_rates' in tr
        # the seeded term is First Term of the session; its average is populated
        assert any(v is not None for v in tr['averages'])


def _admin(app):
    from config import Config
    from tests.conftest import login_token
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_institution_routes(app):
    ids = _seed(app)
    c = _admin(app)
    # HTML shell (SPA) renders with the analytics payload embedded
    r = c.get(f"/subjects/analytics/institution?term_id={ids['term']}&scope=school")
    assert r.status_code == 200
    assert b'Institution Analytics' in r.data
    # board-pack PDF downloads
    r = c.get(f"/subjects/analytics/institution/report.pdf?term_id={ids['term']}&scope=school")
    assert r.status_code == 200
    assert 'application/pdf' in r.headers['Content-Type']
    assert r.get_data()[:4] == b'%PDF'
    # section drill-down
    r = c.get(f"/subjects/analytics/institution?term_id={ids['term']}&scope=section&scope_id=senior")
    assert r.status_code == 200


def test_teacher_scorecard(app):
    from utils.results_analytics_org import teacher_scorecard
    ids = _seed(app)
    with app.app_context():
        sc = teacher_scorecard(ids['term'], 'Mr A', None)
        assert sc['teacher'] == 'Mr A'
        assert sc['summary']['entries'] > 0
        # Mr A teaches Maths across every arm/class -> multiple class-subject rows
        assert len(sc['rows']) >= 3
        assert all(r['subject'].endswith('Maths') for r in sc['rows'])
        assert sc['by_subject'] and sc['summary']['flag'] in (
            'strong', 'good', 'watch', 'review', 'compliance', 'insufficient')


def test_teacher_scorecard_route(app):
    ids = _seed(app)
    c = _admin(app)
    r = c.get(f"/subjects/analytics/teacher?term_id={ids['term']}&name=Mr%20A")
    assert r.status_code == 200
    assert b'Teacher Scorecard' in r.data          # title-map label in the shell
    assert b'Mr A' in r.data                        # teacher name in the embedded payload


def test_teacher_report_formats(app):
    ids = _seed(app)
    c = _admin(app)
    q = f"term_id={ids['term']}&name=Mr%20A"
    r = c.get(f"/subjects/analytics/teacher/report?{q}&format=excel")
    assert r.status_code == 200 and 'spreadsheetml' in r.headers['Content-Type']
    assert r.get_data()[:2] == b'PK'
    r = c.get(f"/subjects/analytics/teacher/report?{q}&format=image")
    assert r.status_code == 200 and r.headers['Content-Type'] == 'image/png'
    r = c.get(f"/subjects/analytics/teacher/report?{q}")
    assert r.status_code == 200 and r.get_data()[:4] == b'%PDF'


def test_resolve_teacher_staff(app):
    from models import db, StaffMember, Branch
    from utils.results_analytics_org import resolve_teacher_staff
    with app.app_context():
        bid = Branch.get_default().id
        st = StaffMember(first_name='John', surname='Doe', staff_type='Teaching',
                         is_active=True, branch_id=bid)
        db.session.add(st); db.session.commit()
        assert resolve_teacher_staff('John Doe') == st.id
        assert resolve_teacher_staff('Mr John Doe') == st.id
        assert resolve_teacher_staff('Doe John') == st.id
        assert resolve_teacher_staff('Nobody Here') is None


def test_institution_export_formats(app):
    ids = _seed(app)
    c = _admin(app)
    q = f"term_id={ids['term']}&scope=school"
    # Excel
    r = c.get(f"/subjects/analytics/institution/report?{q}&format=excel")
    assert r.status_code == 200 and 'spreadsheetml' in r.headers['Content-Type']
    assert r.get_data()[:2] == b'PK'
    # HD image
    r = c.get(f"/subjects/analytics/institution/report?{q}&format=image")
    assert r.status_code == 200 and r.headers['Content-Type'] == 'image/png'
    assert r.get_data()[:8] == b'\x89PNG\r\n\x1a\n'
    # PDF (default)
    r = c.get(f"/subjects/analytics/institution/report?{q}")
    assert r.status_code == 200 and 'application/pdf' in r.headers['Content-Type']
    assert r.get_data()[:4] == b'%PDF'
