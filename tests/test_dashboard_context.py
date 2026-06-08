"""Characterization test for the dashboard context.

Pins the values dashboard() puts in its template context against a known dataset,
so the function can be split into helpers without changing behaviour. Data lives
in a dedicated branch and a unique exam year and the test logs in as a branch
user, so the branch-scoped snapshots reflect only this fixture (not other tests).
"""
import datetime as dt
from flask import template_rendered
from models import db, Branch, User, Student, WAECResult, JAMBResult
from tests.conftest import login_token

YEAR = 2099  # guarantees this is the "latest year" the dashboard picks


def _seed(app):
    with app.app_context():
        b = Branch.query.filter_by(name='DSH-Branch').first()
        if b and Student.query.filter_by(student_id='DSH1').first():
            return b.id
        if not b:
            b = Branch(name='DSH-Branch', is_active=True)
            db.session.add(b); db.session.commit()
        bid = b.id
        today = dt.date.today()

        def dob(age):
            return today.replace(year=today.year - age)

        s1 = Student(student_id='DSH1', first_name='One', surname='Dash', gender='Male',
                     is_active=True, branch_id=bid, religion='Christianity', stream='Science',
                     date_of_birth=dob(15))
        s2 = Student(student_id='DSH2', first_name='Two', surname='Dash', gender='Female',
                     is_active=True, branch_id=bid, religion='Islam', stream='Arts',
                     date_of_birth=dob(12))
        s3 = Student(student_id='DSH3', first_name='Three', surname='Dash', gender='Male',
                     is_active=True, branch_id=bid, religion='Christianity',
                     date_of_birth=dob(20), is_graduated=True)
        db.session.add_all([s1, s2, s3]); db.session.flush()

        for sid, score in ((s1.id, 250), (s2.id, 180), (s3.id, 300)):
            db.session.add(JAMBResult(student_id=sid, exam_year=YEAR, total_score=score))
        for subj, g in (('English Language', 'A1'), ('Mathematics', 'B2'), ('Biology', 'C4')):
            db.session.add(WAECResult(student_id=s1.id, exam_year=YEAR, subject=subj, grade=g))
        for subj, g in (('English Language', 'D7'), ('Mathematics', 'E8')):
            db.session.add(WAECResult(student_id=s2.id, exam_year=YEAR, subject=subj, grade=g))

        if not User.query.filter_by(username='dsh_user').first():
            u = User(username='dsh_user', role='staff', scope='branch', branch_id=bid,
                     full_name='Dash User')
            u.set_password('secret123'); db.session.add(u)
        db.session.commit()
        return bid


def _capture(app):
    c = app.test_client()
    c.post('/login', data={'username': 'dsh_user', 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    recorded = []
    def record(sender, template, context, **extra):
        recorded.append((template.name, context))
    template_rendered.connect(record, app)
    try:
        assert c.get('/').status_code == 200
    finally:
        template_rendered.disconnect(record, app)
    for name, ctx in recorded:
        if name == 'dashboard.html':
            return ctx
    raise AssertionError('dashboard.html was not rendered')


def test_dashboard_context_values(app):
    _seed(app)
    ctx = _capture(app)

    # Branch-scoped: exactly our three DSH students.
    assert ctx['total_students'] == 3
    assert ctx['male_students'] == 2 and ctx['female_students'] == 1
    assert ctx['graduates_count'] == 1

    assert ctx['age_distribution'] == {'0-10': 0, '11-13': 1, '14-16': 1, '17-19': 0, '20+': 1}
    assert ctx['religion_stats'] == {'Christianity': 2, 'Islam': 1}
    assert ctx['stream_dist'].get('Science') == 1 and ctx['stream_dist'].get('Arts') == 1

    js = ctx['jamb_snapshot']
    assert js['year'] == YEAR and js['count'] == 3
    assert js['mean'] == round((250 + 180 + 300) / 3, 1)
    assert js['max'] == 300 and js['above_200'] == 2
    assert js['distribution'] == {'0-149': 0, '150-199': 1, '200-249': 0,
                                  '250-299': 1, '300+': 1}
    assert js['top'][0]['score'] == 300

    ws = ctx['waec_snapshot']
    assert ws['year'] == YEAR and ws['entries'] == 5 and ws['students'] == 2
    assert ws['pass_rate'] == 60.0

    # Keys the template relies on must all be present.
    for key in ('attendance_stats', 'attendance_trend', 'class_stats', 'recent_students',
                'birthdays_today', 'birthdays_week', 'total_subjects', 'total_school_classes',
                'total_classes', 'active_enrollments', 'mock_snapshot', 'announcements',
                'active_session', 'active_term', 'recent_activity'):
        assert key in ctx
