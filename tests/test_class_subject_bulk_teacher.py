"""One teacher usually takes the same subject across several classes/arms. The
bulk-teacher route sets the teacher name on many selected class-subject rows at
once instead of editing each individually.
"""
from config import Config
from tests.conftest import login_token, auth_csrf


def _rows(app):
    from models import db, ClassSubject, Subject, SchoolClass, Term, AcademicSession
    with app.app_context():
        term = Term.query.first()
        if not term:
            s = AcademicSession(name='2098/2099', is_active=True)
            db.session.add(s); db.session.flush()
            term = Term(session_id=s.id, term_number=1, name='T1', is_active=True)
            db.session.add(term); db.session.flush()
        sc = SchoolClass.query.first() or SchoolClass(name='CSB-Cls', level=1)
        db.session.add(sc); db.session.flush()
        ids = []
        for nm in ('CSB-Math', 'CSB-Eng'):
            subj = Subject(name=nm, is_active=True)
            db.session.add(subj); db.session.flush()
            cs = ClassSubject(subject_id=subj.id, class_id=sc.id, term_id=term.id,
                              teacher_name=None, is_active=True)
            db.session.add(cs); db.session.flush()
            ids.append(cs.id)
        db.session.commit()
        return ids


def test_bulk_teacher_applies_to_all_selected(app):
    from models import db, ClassSubject
    ids = _rows(app)
    try:
        c = app.test_client()
        c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
        r = c.post('/subjects/class-subjects/bulk-teacher',
                   data={'cs_ids[]': [str(i) for i in ids],
                         'teacher_name': 'Mr. Bulk', '_csrf_token': auth_csrf(c)})
        assert r.status_code in (200, 302, 303)
        with app.app_context():
            rows = ClassSubject.query.filter(ClassSubject.id.in_(ids)).all()
            assert all(x.teacher_name == 'Mr. Bulk' for x in rows)
    finally:
        with app.app_context():
            ClassSubject.query.filter(ClassSubject.id.in_(ids)).delete(synchronize_session=False)
            db.session.commit()
