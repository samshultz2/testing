"""Merge duplicate students: ALL-CAPS / middle-name duplicates are found, and
everything saved for the duplicate moves onto the kept record."""
import uuid
from datetime import date, datetime, timedelta

from config import Config
from models import (db, Student, WAECResult, JAMBResult, AcademicSession, Term, SchoolClass,
                    ClassArm, ClassArmAssignment, StudentEnrollment, TermSummary)
from models.models_school_exams import SchoolExamResult, SchoolExamCandidate
from tests.conftest import login_token, auth_csrf


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _pair(app, tag):
    """A proper-case keeper and an ALL-CAPS duplicate (with a middle name),
    both enrolled in the same class arm, each with saved results."""
    with app.app_context():
        from models import Branch
        bid = Branch.get_default().id
        ssn = AcademicSession(name=f'M{tag}/S', is_active=False)
        db.session.add(ssn); db.session.flush()
        term = Term(session_id=ssn.id, term_number=1, name='First Term')
        db.session.add(term); db.session.flush()
        cls = SchoolClass.query.filter_by(name='JSS3').first() or SchoolClass(name='JSS3', level=3)
        db.session.add(cls); db.session.flush()
        arm = ClassArm.query.first() or ClassArm(name='A', is_active=True)
        db.session.add(arm); db.session.flush()
        caa = ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        keep = Student(student_id='MK' + uuid.uuid4().hex[:6], first_name=f'Ada{tag}', surname=f'Merge{tag}',
                       gender='Female', branch_id=bid)
        dup = Student(student_id='MD' + uuid.uuid4().hex[:6], first_name=f'MERGE{tag}'.upper(),
                      surname=f'ADA{tag}'.upper(), middle_name='CHIOMA', gender='Female', branch_id=bid)
        db.session.add_all([keep, dup]); db.session.flush()
        e_keep = StudentEnrollment(student_id=keep.id, class_arm_assignment_id=caa.id, is_active=True)
        e_dup = StudentEnrollment(student_id=dup.id, class_arm_assignment_id=caa.id, is_active=True)
        db.session.add_all([e_keep, e_dup]); db.session.flush()
        # A term summary hangs off the duplicate's (clashing) enrolment.
        db.session.add(TermSummary(student_id=dup.id, term_id=term.id, enrollment_id=e_dup.id, average_score=61))
        old = datetime(2020, 1, 1)
        db.session.add_all([
            # Clash: both have Maths 2048 — the duplicate's is newer, so it wins.
            WAECResult(student_id=keep.id, exam_year=2048, subject='Mathematics', grade='F9',
                       updated_at=old, created_at=old),
            WAECResult(student_id=dup.id, exam_year=2048, subject='Mathematics', grade='B3'),
            WAECResult(student_id=dup.id, exam_year=2048, subject='Biology', grade='C4'),
            JAMBResult(student_id=dup.id, exam_year=2048, total_score=251),
            SchoolExamResult(student_id=dup.id, level='jss3', body='state', exam_year=2047,
                             subject='English Studies', grade='A'),
            SchoolExamCandidate(student_id=dup.id, level='jss3', body='state', exam_year=2047,
                                exam_number='BECE/9'),
        ])
        db.session.commit()
        return keep.id, dup.id, caa.id, cls.id


def test_finds_all_caps_and_middle_name_duplicates_and_keeps_proper_case(app):
    from utils.student_merge import find_groups
    keep, dup, _caa, cls_id = _pair(app, 'fa')
    from flask import session
    with app.test_request_context():
        session['role'] = 'super_admin'
        groups = [g for g in find_groups() if {m['id'] for m in g['members']} == {keep, dup}]
        assert len(groups) == 1
        g = groups[0]
        assert g['keeper_id'] == keep and g['has_caps_dup']
        caps = {m['id']: m['all_caps'] for m in g['members']}
        assert caps == {keep: False, dup: True}
        assert any(g2['key'] == g['key'] for g2 in find_groups(class_id=cls_id))


def test_merge_moves_everything_and_resolves_clashes(app):
    from utils.student_merge import merge_students
    keep, dup, caa, _ = _pair(app, 'mv')
    with app.app_context():
        merge_students(keep, [dup])
        db.session.commit()
        assert db.session.get(Student, dup) is None
        k = db.session.get(Student, keep)
        assert k.middle_name == 'Chioma'                       # blank filled, title-cased
        waec = {w.subject: w.grade for w in WAECResult.query.filter_by(student_id=keep, exam_year=2048)}
        assert waec == {'Mathematics': 'B3', 'Biology': 'C4'}  # newer duplicate row won
        assert JAMBResult.query.filter_by(student_id=keep).one().total_score == 251
        assert SchoolExamResult.query.filter_by(student_id=keep, level='jss3').count() == 1
        assert SchoolExamCandidate.query.filter_by(student_id=keep).one().exam_number == 'BECE/9'
        enr = StudentEnrollment.query.filter_by(student_id=keep, class_arm_assignment_id=caa).all()
        assert len(enr) == 1                                   # clashing enrolment collapsed
        ts = TermSummary.query.filter_by(student_id=keep).one()
        assert ts.enrollment_id == enr[0].id                   # dependent moved to the survivor
        assert StudentEnrollment.query.filter_by(student_id=dup).count() == 0


def test_merge_page_select_caps_and_merge(app):
    keep, dup, _caa, _ = _pair(app, 'pg')
    c = _admin(app)
    html = c.get('/students/duplicates?q=Mergepg').get_data(as_text=True)
    key = '-'.join(sorted([str(keep), str(dup)]))
    assert 'ALL CAPS' in html and f'value="{key}"' in html
    assert f'name="keep_{key}" value="{keep}" checked' in html
    r = c.post('/students/duplicates/merge', data={'_csrf_token': auth_csrf(c), 'group': key,
                                                   f'keep_{key}': keep, 'q': 'Mergepg'})
    assert r.status_code == 302
    with app.app_context():
        assert db.session.get(Student, dup) is None
        assert WAECResult.query.filter_by(student_id=keep).count() == 2
    assert 'No duplicates found' in c.get('/students/duplicates?q=Mergepg').get_data(as_text=True)


def test_keeper_must_be_one_of_the_group(app):
    keep, dup, _caa, _ = _pair(app, 'kk')
    c = _admin(app)
    key = '-'.join(sorted([str(keep), str(dup)]))
    c.post('/students/duplicates/merge', data={'_csrf_token': auth_csrf(c), 'group': key,
                                               f'keep_{key}': 999999})
    with app.app_context():
        assert db.session.get(Student, dup) is not None and db.session.get(Student, keep) is not None


def test_namesakes_in_different_classes_are_flagged_not_auto_selected(app):
    from utils.student_merge import find_groups
    from flask import session
    with app.app_context():
        from models import Branch
        bid = Branch.get_default().id
        term = Term.query.first()
        arm = ClassArm.query.first()
        c1 = SchoolClass.query.filter_by(name='JSS1').first() or SchoolClass(name='JSS1', level=1)
        c2 = SchoolClass.query.filter_by(name='SSS1').first() or SchoolClass(name='SSS1', level=4)
        db.session.add_all([c1, c2]); db.session.flush()
        ids = []
        for cls, first in ((c1, 'Twinrp'), (c2, 'TWINRP')):
            caa = ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
            db.session.add(caa); db.session.flush()
            st = Student(student_id='NS' + uuid.uuid4().hex[:6], first_name=first,
                         surname='Namesakerp' if first == 'Twinrp' else 'NAMESAKERP', gender='Male', branch_id=bid)
            db.session.add(st); db.session.flush()
            db.session.add(StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True))
            ids.append(st.id)
        db.session.commit()
    with app.test_request_context():
        session['role'] = 'super_admin'
        g = next(g for g in find_groups(search='Namesakerp') if {m['id'] for m in g['members']} == set(ids))
        assert g['warnings'] and not g['has_caps_dup']
