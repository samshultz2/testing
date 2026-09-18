"""Results > Subject Enrolment: WAEC/JAMB subject-count mismatch lists."""
from config import Config
from models import db, Branch, Student
from tests.conftest import login_token, enroll_sss3


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _student(app, sid, waec_count, jamb_count):
    waec_pool = ['English Language', 'Mathematics', 'Physics', 'Chemistry', 'Biology',
                 'Civic Education', 'Government', 'Economics', 'Literature in English',
                 'Geography', 'Commerce']
    jamb_pool = ['English Language', 'Mathematics', 'Physics', 'Chemistry', 'Biology', 'Economics']
    with app.app_context():
        bid = Branch.get_default().id
        s = Student(student_id=sid, first_name='Mis', surname=sid, gender='Male',
                    is_active=True, branch_id=bid,
                    waec_subjects=', '.join(waec_pool[:waec_count]) or None,
                    jamb_subjects=', '.join(jamb_pool[:jamb_count]) or None)
        db.session.add(s); db.session.commit()
        student_pk = s.id
    enroll_sss3(app, student_pk)
    return student_pk


def test_exact_counts_are_not_flagged(app):
    pk = _student(app, 'ZZ_MIS_OK', 9, 4)
    c = _admin(app)
    body = c.get('/results/subject-enrolment').get_data(as_text=True)
    assert '"waec_expected": 9' in body and '"jamb_expected": 4' in body
    assert f'/students/{pk}/edit' not in body


def test_off_count_students_are_flagged_with_edit_link(app):
    under_waec = _student(app, 'ZZ_MIS_UNDER_W', 7, 4)
    over_waec = _student(app, 'ZZ_MIS_OVER_W', 11, 4)
    no_jamb = _student(app, 'ZZ_MIS_NO_J', 9, 0)
    over_jamb = _student(app, 'ZZ_MIS_OVER_J', 9, 5)

    c = _admin(app)
    page = c.get('/results/subject-enrolment')
    assert page.status_code == 200
    body = page.get_data(as_text=True)

    for pk in (under_waec, over_waec, no_jamb, over_jamb):
        assert f'/students/{pk}/edit' in body


def test_mismatches_are_scoped_to_sss3_cohort_even_on_all_scope(app):
    """The two mismatch lists always check the SSS3/exam-candidate cohort, even
    when the page's own scope tab is 'all active students' — a non-SSS3
    student with an odd subject count must never appear."""
    with app.app_context():
        bid = Branch.get_default().id
        s = Student(student_id='ZZ_MIS_NONSSS3', first_name='Not', surname='Sss3',
                    gender='Female', is_active=True, branch_id=bid,
                    waec_subjects='English Language, Mathematics')  # only 2, way off
        db.session.add(s); db.session.commit()
        pk = s.id
    c = _admin(app)
    body = c.get('/results/subject-enrolment?scope=all').get_data(as_text=True)
    assert f'/students/{pk}/edit' not in body
