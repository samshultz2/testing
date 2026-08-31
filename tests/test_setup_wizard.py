"""First-run setup wizard: live checklist + one-click class/subject seeders."""


def test_wizard_requires_admin(app):
    c = app.test_client()                        # anonymous
    r = c.get('/setup/')
    assert r.status_code in (301, 302)           # redirect to login


def test_wizard_renders_for_admin(auth_client):
    r = auth_client.get('/setup/')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Set up your school' in body
    assert 'Classes' in body and 'Subjects' in body and 'Invite staff' in body


def _csrf(c):
    import re
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get('/students').get_data(as_text=True)).group(1)


def test_seed_classes_idempotent(auth_client, app):
    from models import SchoolClass
    tok = _csrf(auth_client)
    auth_client.post('/setup/seed-classes', data={'_csrf_token': tok}, follow_redirects=True)
    with app.app_context():
        names = {c.name for c in SchoolClass.query.all()}
        assert {'JSS1', 'JSS2', 'JSS3', 'SSS1', 'SSS2', 'SSS3'} <= names
        n = SchoolClass.query.count()
    # running again adds nothing (idempotent)
    auth_client.post('/setup/seed-classes', data={'_csrf_token': tok}, follow_redirects=True)
    with app.app_context():
        from models import SchoolClass as SC
        assert SC.query.count() == n


def test_seed_subjects_idempotent(auth_client, app):
    from models import Subject
    tok = _csrf(auth_client)
    auth_client.post('/setup/seed-subjects', data={'_csrf_token': tok}, follow_redirects=True)
    with app.app_context():
        names = {s.name for s in Subject.query.all()}
        assert 'English Language' in names and 'Mathematics' in names
        n = Subject.query.count()
    auth_client.post('/setup/seed-subjects', data={'_csrf_token': tok}, follow_redirects=True)
    with app.app_context():
        from models import Subject as S
        assert S.query.count() == n


def test_wizard_reflects_progress(auth_client, app):
    """After seeding classes + subjects, those steps show as done."""
    tok = _csrf(auth_client)
    auth_client.post('/setup/seed-classes', data={'_csrf_token': tok}, follow_redirects=True)
    auth_client.post('/setup/seed-subjects', data={'_csrf_token': tok}, follow_redirects=True)
    from routes.setup import _status
    with app.test_request_context():
        steps, done, total, _ = _status()
        by = {s['key']: s for s in steps}
        assert by['classes']['done'] is True
        assert by['subjects']['done'] is True
