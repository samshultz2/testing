"""University-aspiration feature: reference data + cut-off logic, the searchable
lookup / requirements APIs, saving on the student form, bulk assign, the admin
screen, and per-student JAMB target in predictions."""
from config import Config
from models import (db, Branch, Student, University, Course, UniversityCourse,
                    effective_cutoff)
from utils.university_seed import seed_university_data


def _admin(app):
    from tests.conftest import login_token, auth_csrf
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    c._csrf = auth_csrf(c)
    return c


def _seed(app):
    with app.app_context():
        if University.query.first() is None:
            seed_university_data()


def test_seed_and_effective_cutoff(app):
    _seed(app)
    with app.app_context():
        u = University.query.filter_by(abbreviation='UNILAG').first()
        med = Course.query.filter_by(name='Medicine and Surgery').first()
        cs = Course.query.filter_by(name='Computer Science').first()
        assert u and med and cs
        # explicit override (UNILAG Medicine = 300)
        assert effective_cutoff(u, med) == 300
        # base (240) + UNILAG bump (20) = 260, no explicit override
        assert effective_cutoff(u, cs) == 260
        # course base alone when no university chosen
        assert effective_cutoff(None, cs) == 240
        assert 'English Language' in med.jamb_subject_list


def test_lookup_and_requirements_apis(app):
    _seed(app)
    c = _admin(app)
    unis = c.get('/api/universities?q=lag').get_json()['universities']
    assert any('Lagos' in u['name'] for u in unis)
    courses = c.get('/api/courses?q=medicine').get_json()['courses']
    assert any(x['name'] == 'Medicine and Surgery' for x in courses)
    with app.app_context():
        u = University.query.filter_by(abbreviation='UNILAG').first()
        med = Course.query.filter_by(name='Medicine and Surgery').first()
        uid, cid = u.id, med.id
    r = c.get(f'/api/course-requirements?university_id={uid}&course_id={cid}').get_json()
    assert r['jamb_target'] == 300 and r['department'] == 'Medical Sciences'
    assert 'Biology' in r['jamb_subjects'] and 'Mathematics' in r['waec_subjects']


def test_edit_saves_aspiration(app):
    _seed(app)
    with app.app_context():
        bid = Branch.get_default().id
        s = Student(student_id='ASP-1', first_name='Asp', surname='One', gender='Male',
                    is_active=True, branch_id=bid)
        db.session.add(s); db.session.commit()
        sid = s.id
        u = University.query.filter_by(abbreviation='UI').first()
        law = Course.query.filter_by(name='Law').first()
        uid, cid = u.id, law.id
    c = _admin(app)
    r = c.post(f'/students/{sid}/edit', data={
        'form_complete': '1', 'first_name': 'Asp', 'surname': 'One', 'gender': 'Male',
        'target_university_id': uid, 'target_course_id': cid, 'target_department': 'Law',
        'jamb_target': '278', '_csrf_token': c._csrf,
    }, headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        s = db.session.get(Student, sid)
        assert s.target_university_id == uid and s.target_course_id == cid
        assert s.target_department == 'Law' and s.jamb_target == 278


def test_bulk_assign_fills_target_and_subjects(app):
    _seed(app)
    with app.app_context():
        bid = Branch.get_default().id
        a = Student(student_id='ASP-B1', first_name='A', surname='Bulk1', gender='Male', is_active=True, branch_id=bid)
        b = Student(student_id='ASP-B2', first_name='B', surname='Bulk2', gender='Female', is_active=True, branch_id=bid)
        db.session.add_all([a, b]); db.session.commit()
        ids = [a.id, b.id]
        u = University.query.filter_by(abbreviation='UNILAG').first()
        med = Course.query.filter_by(name='Medicine and Surgery').first()
        uid, cid = u.id, med.id
    c = _admin(app)
    r = c.post('/students/bulk-aspiration', data={
        'student_ids': ids, 'target_university_id': uid, 'target_course_id': cid, '_csrf_token': c._csrf,
    }, headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        for i in ids:
            s = db.session.get(Student, i)
            assert s.target_university_id == uid and s.target_course_id == cid
            assert s.jamb_target == 300                      # UNILAG Medicine override
            assert 'Biology' in s.jamb_subject_list          # filled from course
            assert 'Mathematics' in s.waec_subject_list


def test_prediction_uses_student_target(app):
    from utils import exam_insights as ei
    with app.app_context():
        s = Student(student_id='ASP-P1', first_name='P', surname='Pred', gender='Male', is_active=True)
        waec = {'credits': 6, 'missing_core': [], 'meets_ssc': True,
                'credited_subjects': ['English Language', 'Mathematics', 'Biology', 'Chemistry', 'Physics'],
                'credited_grades': {'English Language': 'B2', 'Mathematics': 'B3', 'Biology': 'C4',
                                    'Chemistry': 'C5', 'Physics': 'C6'}, 'source': 'mock'}
        jamb = {'score': 250, 'source': 'mock'}
        # No target → judged against the 180 baseline → READY at 250.
        s.jamb_target = None
        r = ei.admission_readiness(s, waec=waec, jamb=jamb)
        assert r['status'] == 'READY' and r['jamb_threshold'] == 180
        # Competitive target of 300 → 250 falls short → not READY, blocker cites 300.
        s.jamb_target = 300
        r = ei.admission_readiness(s, waec=waec, jamb=jamb)
        assert r['status'] != 'READY' and r['jamb_threshold'] == 300
        assert any('300' in b for b in r['blockers'])


def test_admissions_admin_screen(app):
    c = _admin(app)
    # Seed via the screen's button.
    r = c.post('/settings/admissions', data={'action': 'seed', '_csrf_token': c._csrf}, follow_redirects=False)
    assert r.status_code in (302, 303)
    page = c.get('/settings/admissions')
    assert page.status_code == 200 and 'Admissions data' in page.get_data(as_text=True)
    # Add a university.
    r = c.post('/settings/admissions', data={'action': 'save_university', 'name': 'Test Uni ASP', '_csrf_token': c._csrf,
                                             'abbreviation': 'TUA', 'ownership': 'Private', 'cutoff_bump': '7'})
    assert r.status_code in (302, 303)
    with app.app_context():
        assert University.query.filter_by(name='Test Uni ASP').first() is not None
