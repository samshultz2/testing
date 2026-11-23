"""The question bank pages list only the subjects SSS3 offers (Class Subjects
for the SSS3 class), with ?all=1 to see every subject, and open the subject
with the most bank questions by default."""
import re
import uuid

from config import Config
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_bank_lists_sss3_subjects_only(app):
    from models import db, Subject, SchoolClass, Term, ClassSubject, MockJAMBQuestion
    from utils.helpers import get_sss3_class
    with app.app_context():
        sss3 = get_sss3_class()
        if sss3 is None:
            sss3 = SchoolClass(name='SSS3', level=12); db.session.add(sss3); db.session.flush()
        term = Term.query.first()
        if term is None:
            from models import AcademicSession
            ses = AcademicSession(name='SP ' + uuid.uuid4().hex[:4], is_active=False)
            db.session.add(ses); db.session.flush()
            term = Term(session_id=ses.id, term_number=1, name='First Term', is_active=False)
            db.session.add(term); db.session.flush()
        tag = uuid.uuid4().hex[:5]
        offered = Subject(name='Offered ' + tag, is_active=True)
        other = Subject(name='NotOffered ' + tag, is_active=True)
        db.session.add_all([offered, other]); db.session.flush()
        db.session.add(ClassSubject(subject_id=offered.id, class_id=sss3.id, term_id=term.id, is_active=True))
        for i in range(400):                      # make it the busiest SSS3 subject
            db.session.add(MockJAMBQuestion(mock_exam_id=None, subject_id=offered.id, question_text='Q%d %s' % (i, tag),
                                            option_a='a', option_b='b', option_c='c', option_d='d', correct_option='A', marks=1))
        db.session.commit()
        names = (offered.name, other.name)
    c = _admin(app)
    html = c.get('/mock-jamb/bank').get_data(as_text=True)
    opts = re.findall(r'class="sp-opt[^"]*"[^>]*data-name="([^"]+)"', html)
    assert names[0] in opts and names[1] not in opts
    assert re.search(r'<span class="sp-name">%s</span>' % re.escape(names[0]), html)   # busiest opens by default
    html = c.get('/mock-jamb/bank?all=1').get_data(as_text=True)
    assert names[1] in re.findall(r'data-name="([^"]+)"', html)
    for url in ('/mock-jamb/bank/syllabus', '/mock-jamb/bank/analytics'):
        page = c.get(url).get_data(as_text=True)
        opts = re.findall(r'class="sp-opt[^"]*"[^>]*data-name="([^"]+)"', page)
        assert names[0] in opts and names[1] not in opts, url
