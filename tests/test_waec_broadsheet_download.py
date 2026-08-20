"""The WAEC broadsheet custom download filters by stream + subject and renders
in the chosen format (pdf / image / excel / csv)."""
from config import Config
from models import db, Student, WAECResult, Branch
from tests.conftest import login_token


def _seed(app):
    with app.app_context():
        bid = Branch.get_default().id
        sci = Student(student_id='BD-SCI', first_name='Sci', surname='Ata',
                      gender='Male', is_active=True, stream='Science', branch_id=bid)
        art = Student(student_id='BD-ART', first_name='Art', surname='Bee',
                      gender='Female', is_active=True, stream='Arts', branch_id=bid)
        db.session.add_all([sci, art]); db.session.flush()
        for st, subs in [(sci, [('Mathematics', 'B2'), ('Physics', 'A1'), ('English Language', 'C4')]),
                         (art, [('Mathematics', 'C6'), ('Literature in English', 'B3'), ('English Language', 'B2')])]:
            for subj, grade in subs:
                db.session.add(WAECResult(student_id=st.id, exam_year=2031, subject=subj, grade=grade))
        db.session.commit()
        return sci.id, art.id


def test_download_formats_and_stream_filter(app):
    ids = _seed(app)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})

    # PDF
    r = c.get('/results/waec/broadsheet/download', query_string={'year': 2031, 'format': 'pdf'})
    assert r.status_code == 200 and r.data[:4] == b'%PDF'
    # Image (PNG)
    r = c.get('/results/waec/broadsheet/download', query_string={'year': 2031, 'format': 'image'})
    assert r.status_code == 200 and r.data[:8] == b'\x89PNG\r\n\x1a\n'
    # CSV limited to Science stream → only the science student's row present.
    r = c.get('/results/waec/broadsheet/download',
              query_string={'year': 2031, 'format': 'csv', 'streams': 'Science'})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Ata' in body and 'Bee' not in body        # only the Science student
    # Subject subset limits the columns.
    r = c.get('/results/waec/broadsheet/download',
              query_string={'year': 2031, 'format': 'csv', 'subjects': 'Mathematics'})
    assert r.status_code == 200
    head = r.get_data(as_text=True).splitlines()[0]
    assert 'Mathematics' in head and 'Physics' not in head

    with app.app_context():
        WAECResult.query.filter(WAECResult.student_id.in_(ids)).delete(synchronize_session=False)
        for sid in ids:
            o = db.session.get(Student, sid)
            if o:
                db.session.delete(o)
        db.session.commit()
