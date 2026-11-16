"""Bulk entry for JAMB / WAEC / NECO from the new entry page."""
from models import db, Student, WAECResult, JAMBResult, NECOResult
from tests.conftest import enroll_sss3
from tests.test_neco import _student, _admin, auth_csrf

FETCH = {'X-Requested-With': 'fetch'}


def test_waec_bulk_save_upserts_and_removes_cleared(app):
    a = _student(app, 'Xebulk', 'Ada'); enroll_sss3(app, a)
    b = _student(app, 'Xebulk', 'Ben'); enroll_sss3(app, b)
    c = _admin(app)
    r = c.post('/results/waec/add', headers=FETCH, data={
        '_csrf_token': auth_csrf(c), 'bulk': '1', 'exam_year': 2041, 'sids': [a, b],
        f'subj_{a}': ['English Language', 'Mathematics', 'Physics'], f'grade_{a}': ['B3', 'A1', ''],
        f'subj_{b}': ['English Language', 'Mathematics'], f'grade_{b}': ['C4', 'C5']}).get_json()
    assert r['ok'] and r['added'] == 2 and not r['problems']
    with app.app_context():
        assert {(x.subject, x.grade) for x in WAECResult.query.filter_by(student_id=a, exam_year=2041)} == {
            ('English Language', 'B3'), ('Mathematics', 'A1')}
    # Clearing Maths and swapping in Physics removes Maths.
    r = c.post('/results/waec/add', headers=FETCH, data={
        '_csrf_token': auth_csrf(c), 'bulk': '1', 'exam_year': 2041, 'sids': [a],
        f'subj_{a}': ['English Language', 'Mathematics', 'Physics'], f'grade_{a}': ['B2', '', 'C6']}).get_json()
    assert r['ok'] and r['updated'] == 1
    with app.app_context():
        assert {(x.subject, x.grade) for x in WAECResult.query.filter_by(student_id=a, exam_year=2041)} == {
            ('English Language', 'B2'), ('Physics', 'C6')}


def test_waec_bulk_rejects_bad_rows(app):
    a = _student(app, 'Xebad', 'Ada'); enroll_sss3(app, a)
    c = _admin(app)
    r = c.post('/results/waec/add', headers=FETCH, data={
        '_csrf_token': auth_csrf(c), 'bulk': '1', 'exam_year': 2042, 'sids': [a],
        f'subj_{a}': ['Mathematics', 'Mathematics'], f'grade_{a}': ['A1', 'B2']}).get_json()
    assert r['problems'] and r['added'] == 0


def test_neco_bulk_goes_to_neco_table(app):
    a = _student(app, 'Xeneco', 'Ada'); enroll_sss3(app, a)
    c = _admin(app)
    r = c.post('/results/neco/add', headers=FETCH, data={
        '_csrf_token': auth_csrf(c), 'bulk': '1', 'exam_year': 2043, 'sids': [a],
        f'subj_{a}': ['Mathematics'], f'grade_{a}': ['A1']}).get_json()
    assert r['ok'] and 'NECO' in r['message']
    with app.app_context():
        assert NECOResult.query.filter_by(student_id=a, exam_year=2043).count() == 1
        assert WAECResult.query.filter_by(student_id=a, exam_year=2043).count() == 0


def test_jamb_bulk_subjects_total_and_total_only(app):
    a = _student(app, 'Xejamb', 'Ada'); enroll_sss3(app, a)
    c = _admin(app)
    f = {'_csrf_token': auth_csrf(c), 'bulk': '1', 'exam_year': 2044, 'sids': [a]}
    for n, (sb, sc) in enumerate([('English Language', 70), ('Mathematics', 65), ('Physics', 60), ('Chemistry', 55)], 1):
        f[f'subject{n}_{a}'] = sb; f[f'subject{n}_score_{a}'] = sc
    r = c.post('/results/jamb/add', headers=FETCH, data=f).get_json()
    assert r['ok'] and r['added'] == 1
    with app.app_context():
        j = JAMBResult.query.filter_by(student_id=a, exam_year=2044).one()
        assert j.total_score == 250 and j.subject2 == 'Mathematics'
    r = c.post('/results/jamb/add', headers=FETCH, data={
        '_csrf_token': auth_csrf(c), 'bulk': '1', 'exam_year': 2044, 'sids': [a], f'total_{a}': '262'}).get_json()
    assert r['ok'] and r['updated'] == 1
    with app.app_context():
        j = JAMBResult.query.filter_by(student_id=a, exam_year=2044).one()
        assert j.total_score == 262 and j.subject1_score == 70        # breakdown kept
    r = c.post('/results/jamb/add', headers=FETCH, data={
        '_csrf_token': auth_csrf(c), 'bulk': '1', 'exam_year': 2044, 'sids': [a],
        f'subject1_{a}': 'English Language', f'subject1_score_{a}': '140'}).get_json()
    assert r['problems']
