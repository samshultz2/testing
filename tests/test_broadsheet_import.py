"""Whole-class broadsheet import: parse an Excel/CSV of subject totals, map
columns to subjects, and break each total into the term's components on save.
"""
import io
import json
from config import Config
from tests.conftest import login_token, auth_csrf


def test_parse_table_finds_header_and_rows():
    from utils.broadsheet_import import parse_table, guess_name_column
    csv = b"MERIT LIST FOR SS1\n,,,\nStudent Name,MTH,ENG,P/W\nAda Obi,82,70,9\nBola Eze,55,60,8\n"
    out = parse_table(csv, 'sheet.csv')
    assert out['headers'] == ['Student Name', 'MTH', 'ENG', 'P/W']
    assert out['rows'][0] == ['Ada Obi', '82', '70', '9']
    assert guess_name_column(out['headers']) == 0


def test_match_subject_by_name_short_and_alias(app):
    from utils.broadsheet_import import match_subject
    from models import Subject

    class _S:
        def __init__(self, name, short=None):
            self.name = name; self.short_name = short
    subs = [_S('Mathematics', 'MTH'), _S('English Language', 'ENG'),
            _S('Further Mathematics', 'F/MTH')]
    assert match_subject('MTH', subs).name == 'Mathematics'
    assert match_subject('English Language', subs).name == 'English Language'
    assert match_subject('FM', subs).name == 'Further Mathematics'   # alias
    assert match_subject('AV', subs) is None                          # non-subject


def _setup_class_with_subject(app):
    """A term, class-arm assignment, one enrolled student, one class-subject."""
    import uuid
    from models import (db, Term, AcademicSession, SchoolClass, ClassArm,
                        ClassArmAssignment, Subject, ClassSubject, Student,
                        StudentEnrollment, AssessmentType)
    tag = uuid.uuid4().hex[:6]
    with app.app_context():
        # Ensure a couple of assessment types exist (CA + Exam) with maxes.
        if AssessmentType.query.count() == 0:
            db.session.add_all([
                AssessmentType(name='CA1', short_name='CA1', max_score=20, order=1),
                AssessmentType(name='Exam', short_name='EXAM', max_score=80, order=2)])
            db.session.flush()
        sess = AcademicSession.query.filter_by(is_active=True).first() or \
            AcademicSession(name='2097/2098', is_active=True)
        db.session.add(sess); db.session.flush()
        term = Term.query.filter_by(session_id=sess.id, term_number=1).first() or \
            Term(session_id=sess.id, term_number=1, name='First', is_active=True)
        db.session.add(term); db.session.flush()
        sc = SchoolClass(name=f'BI-CLS-{tag}', level=1); db.session.add(sc); db.session.flush()
        arm = ClassArm.default()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id)
        db.session.add(caa); db.session.flush()
        subj = Subject(name=f'BI-Maths-{tag}', is_active=True); db.session.add(subj); db.session.flush()
        cs = ClassSubject(subject_id=subj.id, class_id=sc.id, term_id=term.id, is_active=True)
        db.session.add(cs); db.session.flush()
        stu = Student(student_id=f'BI-STU1-{tag}', first_name='Ada', surname='Obi',
                      gender='Female', is_active=True)
        db.session.add(stu); db.session.flush()
        db.session.add(StudentEnrollment(student_id=stu.id, class_arm_assignment_id=caa.id, is_active=True))
        db.session.commit()
        return {'term_id': term.id, 'assignment_id': caa.id, 'cs_id': cs.id,
                'student_id': stu.id, 'subject_id': subj.id, 'subject_name': subj.name}


def test_upload_renders_review(app):
    ids = _setup_class_with_subject(app)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    csv = ('Student Name,%s\nAda Obi,82\n' % ids['subject_name']).encode()
    data = {'term_id': str(ids['term_id']), 'assignment_id': str(ids['assignment_id']),
            '_csrf_token': auth_csrf(c),
            'file': (io.BytesIO(csv), 'sheet.csv')}
    r = c.post('/subjects/scores/broadsheet-import', data=data,
               content_type='multipart/form-data')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Review import' in body and 'Ada Obi' in body


def test_image_upload_uses_ocr(app, monkeypatch):
    """An image upload is read via the OCR engine into the same review flow."""
    ids = _setup_class_with_subject(app)
    # Simulate an available engine + a successful table read.
    import utils.ocr_engine as oe
    import utils.table_ocr as to
    monkeypatch.setattr(oe, 'engine_order', lambda: ['claude'])
    monkeypatch.setattr(to, 'ocr_table_rich',
                        lambda data, mt='image/png', expected_headers=None, max_scores=None: {
                            'headers': ['Student Name', ids['subject_name']],
                            'rows': [['Ada Obi', '82']], 'cell_flags': {'0,1': {'status': 'REVIEW_REQUIRED', 'reasons': ['low_confidence']}},
                            'review_count': 1, 'engine': 'paddle', 'warnings': []})
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    data = {'term_id': str(ids['term_id']), 'assignment_id': str(ids['assignment_id']),
            '_csrf_token': auth_csrf(c),
            'file': (io.BytesIO(b'\x89PNG\r\n\x1a\n fake'), 'sheet.png')}
    r = c.post('/subjects/scores/broadsheet-import', data=data,
               content_type='multipart/form-data')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Review import' in body and 'Ada Obi' in body


def test_save_breaks_total_into_components(app):
    from models import db, StudentScore
    ids = _setup_class_with_subject(app)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    payload = [{'student_id': ids['student_id'], 'cells': {str(ids['cs_id']): '82'}}]
    r = c.post('/subjects/scores/broadsheet-import/save',
               data={'term_id': ids['term_id'], 'assignment_id': ids['assignment_id'],
                     'payload': json.dumps(payload), '_csrf_token': auth_csrf(c)})
    assert r.status_code in (200, 302, 303)
    with app.app_context():
        scores = StudentScore.query.filter_by(
            student_id=ids['student_id'], class_subject_id=ids['cs_id']).all()
        assert scores, 'component scores were written'
        assert sum(int(s.score) for s in scores) == 82   # components sum to the total
        # cleanup
        for s in scores:
            db.session.delete(s)
        db.session.commit()
