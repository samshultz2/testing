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
        micro = Course.query.filter_by(name='Microbiology').first()
        assert u and med and cs and micro
        # explicit departmental override (UNILAG Medicine = 300, Computer Science = 265)
        assert effective_cutoff(u, med) == 300
        assert effective_cutoff(u, cs) == 265
        # no UNILAG override for Microbiology → base (210) + UNILAG bump (20) = 230
        assert effective_cutoff(u, micro) == 230
        # course base alone when no university chosen
        assert effective_cutoff(None, cs) == 240
        assert 'English Language' in med.jamb_subject_list

        # A competitive department bumps well above the school's general line:
        # UNIBEN Engineering sits at 252, not the ~200 base line.
        uniben = University.query.filter_by(abbreviation='UNIBEN').first()
        eng = Course.query.filter_by(name='Mechanical Engineering').first()
        assert effective_cutoff(uniben, eng) == 252


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
            assert 'Biology' in s.jamb_subject_list          # JAMB subjects filled from course
            assert s.waec_subject_list == []                 # WAEC left untouched


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


def test_override_management(app):
    """Admin can add/upsert and remove a per-university course cut-off, and it
    drives effective_cutoff."""
    _seed(app)
    with app.app_context():
        u = University.query.filter_by(abbreviation='EKSU').first()   # no seeded overrides
        cs = Course.query.filter_by(name='Computer Science').first()
        uid, cid = u.id, cs.id
        base_plus_bump = effective_cutoff(u, cs)      # base 240 + EKSU bump 0 = 240
    assert base_plus_bump == 240
    c = _admin(app)
    r = c.post('/settings/admissions', data={'action': 'save_override', 'university_id': uid,
               'course_id': cid, 'jamb_cutoff': '255', '_csrf_token': c._csrf})
    assert r.status_code in (302, 303)
    with app.app_context():
        u = db.session.get(University, uid); cs = db.session.get(Course, cid)
        assert effective_cutoff(u, cs) == 255        # override now applies
        from models import UniversityCourse
        row = UniversityCourse.query.filter_by(university_id=uid, course_id=cid).first()
        oid = row.id
    # Upsert (same pair) updates in place, not duplicates.
    c.post('/settings/admissions', data={'action': 'save_override', 'university_id': uid,
           'course_id': cid, 'jamb_cutoff': '260', '_csrf_token': c._csrf})
    with app.app_context():
        from models import UniversityCourse
        rows = UniversityCourse.query.filter_by(university_id=uid, course_id=cid).all()
        assert len(rows) == 1 and rows[0].jamb_cutoff == 260
    # Delete removes it (falls back to base+bump).
    c.post('/settings/admissions', data={'action': 'delete_override', 'id': oid, '_csrf_token': c._csrf})
    with app.app_context():
        u = db.session.get(University, uid); cs = db.session.get(Course, cid)
        assert effective_cutoff(u, cs) == 240


def _mock_readiness(jamb_score, credited, threshold, meets_ssc=True):
    """A fabricated readiness dict shaped like exam_insights.admission_readiness,
    so eligibility logic can be tested without seeding mock results."""
    return {
        'jamb_threshold': threshold,
        'jamb': {'score': jamb_score, 'source': 'mock'},
        'waec': {'credits': len(credited), 'meets_ssc': meets_ssc,
                 'credited_subjects': list(credited), 'source': 'mock'},
    }


def test_course_eligibility_verdicts(app):
    _seed(app)
    from utils.aspiration import course_eligibility
    with app.app_context():
        bid = Branch.get_default().id
        med = Course.query.filter_by(name='Medicine and Surgery').first()
        req_jamb = ', '.join(med.jamb_subject_list)
        credited = med.waec_subject_list + ['English Language', 'Mathematics']
        s = Student(student_id='ELIG-1', first_name='E', surname='Lig', gender='Male',
                    is_active=True, branch_id=bid, target_course_id=med.id,
                    jamb_subjects=req_jamb, jamb_target=300)
        db.session.add(s); db.session.commit()
        # Meets subjects + credits + score → ON_TRACK.
        e = course_eligibility(s, readiness=_mock_readiness(310, credited, 300))
        assert e['status'] == 'ON_TRACK' and e['gap'] <= 0 and not e['missing_jamb']
        # Same combo, score just short but within the close margin → CLOSE.
        e = course_eligibility(s, readiness=_mock_readiness(285, credited, 300))
        assert e['status'] == 'CLOSE'
        # Missing a required JAMB subject → OFF_TRACK, and it is reported.
        s.jamb_subjects = 'English Language'
        e = course_eligibility(s, readiness=_mock_readiness(310, credited, 300))
        assert e['status'] == 'OFF_TRACK' and e['missing_jamb']
        # No target course at all.
        s2 = Student(student_id='ELIG-2', first_name='N', surname='One', gender='Male',
                     is_active=True, branch_id=bid)
        db.session.add(s2); db.session.commit()
        assert course_eligibility(s2)['status'] == 'NO_TARGET'


def test_recommend_courses(app):
    _seed(app)
    from utils import exam_insights as ei
    from utils.aspiration import recommend_courses
    with app.app_context():
        bid = Branch.get_default().id
        s = Student(student_id='REC-1', first_name='R', surname='Ec', gender='Male',
                    is_active=True, branch_id=bid,
                    jamb_subjects='English Language, Mathematics, Physics, Chemistry')
        db.session.add(s); db.session.commit()
        # No JAMB signal → no recommendations.
        assert recommend_courses(s) == []
        # With a strong projection, courses at/under the projection are suggested,
        # ranked with subject-fit first.
        real = ei.admission_readiness
        ei.admission_readiness = lambda stu, sess=None, **k: {'jamb': {'score': 320, 'source': 'mock'}}
        try:
            recs = recommend_courses(s, limit=5)
        finally:
            ei.admission_readiness = real
        assert recs and all(r['margin'] >= 0 for r in recs)
        assert recs == sorted(recs, key=lambda x: (x['subject_fit'], x['margin']), reverse=True)


def test_recommend_endpoint(app):
    _seed(app)
    with app.app_context():
        bid = Branch.get_default().id
        s = Student(student_id='REC-EP1', first_name='R', surname='Ep', gender='Male',
                    is_active=True, branch_id=bid)
        db.session.add(s); db.session.commit()
        sid = s.id
    c = _admin(app)
    r = c.get(f'/api/students/{sid}/recommend-courses')
    assert r.status_code == 200 and 'recommendations' in r.get_json()


def test_edit_saves_second_choice_career_admission_scholarships(app):
    _seed(app)
    with app.app_context():
        bid = Branch.get_default().id
        s = Student(student_id='ASP-2', first_name='Asp', surname='Two', gender='Female',
                    is_active=True, branch_id=bid)
        db.session.add(s); db.session.commit()
        sid = s.id
        u = University.query.filter_by(abbreviation='UNILAG').first()
        u2 = University.query.filter_by(abbreviation='UI').first()
        cs = Course.query.filter_by(name='Computer Science').first()
        law = Course.query.filter_by(name='Law').first()
        uid, u2id, cid, lid = u.id, u2.id, cs.id, law.id
    c = _admin(app)
    r = c.post(f'/students/{sid}/edit', data={
        'form_complete': '1', 'first_name': 'Asp', 'surname': 'Two', 'gender': 'Female',
        'target_university_id': uid, 'target_course_id': cid,
        'target2_university_id': u2id, 'target2_course_id': lid,
        'career_goal': 'Software Engineer', 'admission_status': 'Offered',
        'admitted_university_id': uid, 'admitted_course_id': cid,
        'scholarship_name[]': ['NNPC Scholarship', ''],
        'scholarship_provider[]': ['NNPC', ''],
        'scholarship_amount[]': ['500000', ''],
        'scholarship_status[]': ['Awarded', ''],
        '_csrf_token': c._csrf,
    }, headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        s = db.session.get(Student, sid)
        assert s.target2_university_id == u2id and s.target2_course_id == lid
        assert s.career_goal == 'Software Engineer' and s.admission_status == 'Offered'
        assert s.admitted_university_id == uid and s.admitted_course_id == cid
        schs = s.scholarships.all()
        assert len(schs) == 1                       # the blank second row is dropped
        assert schs[0].name == 'NNPC Scholarship' and schs[0].amount == 500000.0


def test_aspiration_overview(app):
    _seed(app)
    from utils.aspiration_analytics import aspiration_overview
    with app.test_request_context('/'):
        data = aspiration_overview()
        assert set(data) == {'totals', 'eligibility', 'top_universities',
                             'top_courses', 'mismatches', 'funnel'}
        assert isinstance(data['eligibility'], list) and len(data['eligibility']) == 4
        assert 'conversion' in data['funnel']


def test_aspiration_hub_page(app):
    _seed(app)
    c = _admin(app)
    r = c.get('/results/analytics/aspirations')
    assert r.status_code == 200 and 'University Aspirations' in r.get_data(as_text=True)


def test_bulk_import_cutoffs(app):
    """Pasting 'University, Course, Cut-off' rows upserts overrides; unmatched
    rows are skipped, and missing courses can be created on demand."""
    _seed(app)
    c = _admin(app)
    text = ('University, Course, Cutoff\n'          # header ignored
            'UNILAG, Law, 285\n'                     # match by abbreviation → update
            'University of Ibadan, Pharmacy, 288\n'  # match by full name
            'UNILAG | Basket Weaving | 210\n'        # unknown course, created
            'Nowhere Uni, Law, 250\n')               # unknown university → skipped
    r = c.post('/settings/admissions', data={'action': 'import_overrides', 'import_text': text,
                                            'create_missing': '1', '_csrf_token': c._csrf})
    assert r.status_code in (302, 303)
    with app.app_context():
        lag = University.query.filter_by(abbreviation='UNILAG').first()
        ui = University.query.filter_by(abbreviation='UI').first()
        law = Course.query.filter_by(name='Law').first()
        pharm = Course.query.filter_by(name='Pharmacy').first()
        assert effective_cutoff(lag, law) == 285          # updated by import
        assert effective_cutoff(ui, pharm) == 288
        weaving = Course.query.filter_by(name='Basket Weaving').first()
        assert weaving is not None                        # created on demand
        assert effective_cutoff(lag, weaving) == 210
