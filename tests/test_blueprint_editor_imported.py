"""The paper blueprint page edits the same blueprint the draw uses: an imported
syllabus's sections, not the built-in default."""
import json
import uuid

from datetime import date

from models import db, MockJAMBExam, MockJAMBSyllabus, Subject, AcademicSession
from tests.conftest import auth_csrf


def test_blueprint_page_uses_imported_english_sections(app, auth_client):
    d = json.load(open('data/jamb_syllabi/english_language.json'))
    with app.app_context():
        s = Subject(name='English Language', is_active=False); db.session.add(s); db.session.flush()
        y = MockJAMBSyllabus(subject_id=s.id, subject_name='English Language', blueprint=json.dumps(d['blueprint']))
        sess = AcademicSession.query.first() or AcademicSession(name='2025/2026', is_active=True)
        db.session.add(sess); db.session.flush()
        e = MockJAMBExam(name='BP ' + uuid.uuid4().hex[:5], exam_number=90, session_id=sess.id, exam_date=date.today())
        db.session.add_all([y, e]); db.session.commit()
        eid, yid, sid = e.id, y.id, s.id
    try:
        html = auth_client.get('/mock-jamb/exam/%d/blueprint' % eid).get_data(as_text=True)
        assert 'name="english language__basic_grammar"' in html
        assert 'name="english language__vowels"' in html
        assert 'english language__lexis_structure' not in html and 'english language__oral"' not in html
        # saving the defaults stores no override; changing one stores just that
        form = {'_csrf_token': auth_csrf(auth_client), 'source_mode': 'bank',
                'english language__basic_grammar': '12'}
        for x in d['blueprint']:
            form.setdefault('english language__' + ('novel' if x['section'] == 'reading_text' else x['section']), str(x['count']))
        auth_client.post('/mock-jamb/exam/%d/blueprint' % eid, data=form)
        with app.app_context():
            ov = json.loads(db.session.get(MockJAMBExam, eid).blueprint or '{}')
            assert ov == {'english language': {'basic_grammar': 12}}
    finally:
        with app.app_context():
            db.session.delete(db.session.get(MockJAMBExam, eid))
            db.session.delete(db.session.get(MockJAMBSyllabus, yid))
            db.session.delete(db.session.get(Subject, sid)); db.session.commit()
