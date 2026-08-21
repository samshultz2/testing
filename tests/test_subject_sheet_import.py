"""Single-subject sheet import: columns are the assessment components already
broken out (CA1, Exam…). Map columns to assessment types, resolve students,
save each component directly (no breakdown)."""
import io
import json
import uuid
from config import Config
from tests.conftest import login_token, auth_csrf


def _setup(app):
    from models import (db, Term, AcademicSession, SchoolClass, ClassArm,
                        ClassArmAssignment, Subject, ClassSubject, Student,
                        StudentEnrollment, AssessmentType)
    tag = uuid.uuid4().hex[:6]
    with app.app_context():
        ca1 = AssessmentType.query.filter_by(short_name='CA1').first() or \
            AssessmentType(name='CA1', short_name='CA1', max_score=20, order=1)
        exam = AssessmentType.query.filter_by(short_name='EXAM').first() or \
            AssessmentType(name='Exam', short_name='EXAM', max_score=80, order=2)
        db.session.add_all([ca1, exam]); db.session.flush()
        sess = AcademicSession.query.filter_by(is_active=True).first() or \
            AcademicSession(name='2096/2097', is_active=True)
        db.session.add(sess); db.session.flush()
        term = Term.query.filter_by(session_id=sess.id, term_number=1).first() or \
            Term(session_id=sess.id, term_number=1, name='First', is_active=True)
        db.session.add(term); db.session.flush()
        sc = SchoolClass(name=f'SSI-{tag}', level=1); db.session.add(sc); db.session.flush()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=ClassArm.default().id, term_id=term.id)
        db.session.add(caa); db.session.flush()
        subj = Subject(name=f'SSI-Bio-{tag}', is_active=True); db.session.add(subj); db.session.flush()
        cs = ClassSubject(subject_id=subj.id, class_id=sc.id, term_id=term.id, is_active=True)
        db.session.add(cs); db.session.flush()
        stu = Student(student_id=f'SSI-{tag}', first_name='Ada', surname='Obi',
                      gender='Female', is_active=True); db.session.add(stu); db.session.flush()
        db.session.add(StudentEnrollment(student_id=stu.id, class_arm_assignment_id=caa.id, is_active=True))
        db.session.commit()
        return {'term_id': term.id, 'assignment_id': caa.id, 'cs_id': cs.id,
                'student_id': stu.id, 'ca1_id': ca1.id, 'exam_id': exam.id,
                'subject_name': subj.name}


def test_upload_maps_components_and_renders(app):
    ids = _setup(app)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    csv = b'Student Name,CA1,Exam\nAda Obi,15,70\n'
    r = c.post('/subjects/scores/subject-sheet-import',
               data={'term_id': str(ids['term_id']), 'assignment_id': str(ids['assignment_id']),
                     'class_subject_id': str(ids['cs_id']), '_csrf_token': auth_csrf(c),
                     'file': (io.BytesIO(csv), 'bio.csv')},
               content_type='multipart/form-data')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Review' in body and 'Ada Obi' in body


def test_save_writes_component_scores(app):
    from models import db, StudentScore
    ids = _setup(app)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    payload = [{'student_id': ids['student_id'],
                'cells': {str(ids['ca1_id']): '4', str(ids['exam_id']): '30'}}]
    r = c.post('/subjects/scores/subject-sheet-import/save',
               data={'term_id': ids['term_id'], 'assignment_id': ids['assignment_id'],
                     'class_subject_id': ids['cs_id'], 'payload': json.dumps(payload),
                     '_csrf_token': auth_csrf(c)})
    assert r.status_code in (200, 302, 303)
    with app.app_context():
        scores = {s.assessment_type_id: s.score for s in StudentScore.query.filter_by(
            student_id=ids['student_id'], class_subject_id=ids['cs_id']).all()}
        assert scores.get(ids['ca1_id']) == 4 and scores.get(ids['exam_id']) == 30
        for s in StudentScore.query.filter_by(student_id=ids['student_id'], class_subject_id=ids['cs_id']).all():
            db.session.delete(s)
        db.session.commit()
