"""The WAEC dashboard export (/results/waec/export) renders the same branded
pattern as the students exports — PDF, per-page A4 image, and Word — for both
the students and subjects views, plus the original Excel."""
from config import Config
from models import db, Student, WAECResult, Branch
from tests.conftest import login_token


def _seed(app):
    with app.app_context():
        bid = Branch.get_default().id
        a = Student(student_id='WX-A', first_name='Ada', surname='Obi',
                    gender='Female', is_active=True, stream='Science', branch_id=bid)
        b = Student(student_id='WX-B', first_name='Musa', surname='Bello',
                    gender='Male', is_active=True, stream='Arts', branch_id=bid)
        db.session.add_all([a, b]); db.session.flush()
        for st, subs in [(a, [('Mathematics', 'A1'), ('English Language', 'B2'),
                              ('Biology', 'C4'), ('Chemistry', 'A1')]),
                         (b, [('Mathematics', 'C6'), ('English Language', 'B3'),
                              ('Government', 'B2')])]:
            for subj, grade in subs:
                db.session.add(WAECResult(student_id=st.id, exam_year=2033, subject=subj, grade=grade))
        db.session.commit()
        return a.id, b.id


def test_waec_branded_exports_all_formats(app):
    ids = _seed(app)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})

    # PDF — students view
    r = c.get('/results/waec/export', query_string={'year': 2033, 'format': 'pdf', 'type': 'students'})
    assert r.status_code == 200 and r.data[:4] == b'%PDF'

    # Image — per-page A4 PNG with the total-pages header for the client loop
    r = c.get('/results/waec/export', query_string={'year': 2033, 'format': 'image', 'type': 'students'})
    assert r.status_code == 200 and r.data[:8] == b'\x89PNG\r\n\x1a\n'
    assert int(r.headers.get('X-Total-Pages', '1')) >= 1

    # Word (.docx is a zip → 'PK' magic)
    r = c.get('/results/waec/export', query_string={'year': 2033, 'format': 'word', 'type': 'students'})
    assert r.status_code == 200 and r.data[:2] == b'PK'

    # Subjects view renders too
    r = c.get('/results/waec/export', query_string={'year': 2033, 'format': 'pdf', 'type': 'subjects'})
    assert r.status_code == 200 and r.data[:4] == b'%PDF'

    # The results design: ranked by credits, WAEC grade key, subject codes,
    # benchmark; subject analysis with grade columns, totals and highlights.
    import fitz
    r = c.get('/results/waec/export', query_string={
        'year': 2033, 'format': 'pdf', 'type': 'students',
        'cols': 'rank,student_id,a1,b2,b3,credits,avg,grades,benchmark'})
    with fitz.open(stream=r.data, filetype='pdf') as d:
        txt = ' '.join(' '.join(p.get_text() for p in d).split())
    assert 'WASSCE 2033 — Results' in txt and 'A1–B3' in txt and 'C4–C6' in txt and 'F9' in txt
    assert txt.index('Obi Ada') < txt.index('Bello Musa') or txt.index('Ada Obi') < txt.index('Musa Bello')
    assert 'Subject codes:' in txt and 'Not met' in txt and 'WX-A' in txt
    r = c.get('/results/waec/export', query_string={
        'year': 2033, 'format': 'pdf', 'type': 'subjects', 'cols': 'total,a1,c456,passrate,chart'})
    with fitz.open(stream=r.data, filetype='pdf') as d:
        txt = ' '.join(' '.join(p.get_text() for p in d).split())
    head = txt.split('Fail', 1)[1].split('All subjects')[0]
    assert 'Subject Analysis' in txt and 'All subjects' in txt
    assert 'ENTRIES A1 C4 C5 C6 CREDIT' in head          # only the picked grade columns
    assert 'STRONGEST SUBJECT' in txt
    # NECO uses the same document with its own title.
    r = c.get('/results/neco/export', query_string={'year': 2033, 'format': 'pdf', 'type': 'students'})
    assert r.status_code in (200, 302)

    # Excel path still works
    r = c.get('/results/waec/export', query_string={'year': 2033, 'format': 'excel'})
    assert r.status_code == 200 and r.data[:2] == b'PK'

    with app.app_context():
        WAECResult.query.filter(WAECResult.student_id.in_(ids)).delete(synchronize_session=False)
        for sid in ids:
            o = db.session.get(Student, sid)
            if o:
                db.session.delete(o)
        db.session.commit()
