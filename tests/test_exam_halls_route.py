"""The Exam Hall Allocator tool: form loads, allocation spreads candidates and
respects capacity, and the PDF renders."""
from models import db, Student, Branch, ClassArmAssignment
from tests.conftest import login_token, auth_csrf, enroll_sss3
from config import Config


import itertools
_SEQ = itertools.count()


def _seed(app, n=20):
    with app.app_context():
        bid = Branch.get_default().id
        ids = []
        for i in range(n):
            uid = next(_SEQ)
            s = Student(student_id=f'EH{uid:05d}', first_name=f'Cand{uid}', surname='Test',
                        gender='Male' if i % 2 else 'Female', is_active=True, branch_id=bid)
            db.session.add(s); db.session.flush()
            ids.append(s.id)
        db.session.commit()
        for sid in ids:
            enroll_sss3(app, sid)
        # The assignment enroll_sss3 uses (SSS3, active term) — not query.first(),
        # which in the full suite may be some other class created by another test.
        from models import Term, SchoolClass
        term = Term.query.filter_by(is_active=True).first()
        sss3 = SchoolClass.query.filter_by(name='SSS3').first()
        caa = ClassArmAssignment.query.filter_by(class_id=sss3.id, term_id=term.id).first()
        return ids, caa.id


def test_form_loads(app):
    _seed(app, 6)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    r = c.get('/tools/exam-halls/')
    assert r.status_code == 200
    assert b'Exam Hall Allocator' in r.data


def test_allocate_and_pdf(app):
    _ids, caa_id = _seed(app, 24)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    token = auth_csrf(c)
    form = {
        '_csrf_token': token,
        'assignments': str(caa_id),
        'hall_name': ['Main Hall', 'Hall 2'],
        # Huge, so accumulated SSS3 enrolments from the rest of the suite can't
        # trip the capacity check.
        'hall_capacity': ['100000', '50000'],
        'main_hall': '0',
        'balance_gender': 'on',
    }
    r = c.post('/tools/exam-halls/allocate', data=form)
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Main Hall' in body and 'Hall 2' in body
    assert 'EXAM HALL ALLOCATION' in body
    assert 'FRONT OF HALL' in body          # seating chart rendered
    assert 'Same-arm neighbours' in body    # adjacency stat shown

    # PDF renders from the same inputs.
    r = c.post('/tools/exam-halls/pdf', data=form)
    assert r.status_code == 200 and r.data[:4] == b'%PDF'


def test_candidate_set_filter_excludes_unregistered(app):
    # Students seeded without a WAEC reg number -> WAEC set yields nobody.
    _ids, caa_id = _seed(app, 8)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    token = auth_csrf(c)
    r = c.post('/tools/exam-halls/allocate', data={
        '_csrf_token': token, 'assignments': str(caa_id),
        'hall_name': ['Main'], 'hall_capacity': ['100000'], 'main_hall': '0',
        'candidate_set': 'waec',
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b'Select at least one class/arm that has students' in r.data


def test_allocate_insufficient_capacity_flashes(app):
    _ids, caa_id = _seed(app, 30)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    token = auth_csrf(c)
    r = c.post('/tools/exam-halls/allocate', data={
        '_csrf_token': token, 'assignments': str(caa_id),
        'hall_name': ['Tiny'], 'hall_capacity': ['5'], 'main_hall': '0',
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b'Not enough seats' in r.data
