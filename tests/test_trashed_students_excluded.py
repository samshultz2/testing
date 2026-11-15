"""Students moved to the trash (soft-deleted: is_active=False) keep their class
enrolment so a restore puts them straight back — but until then they must not
count anywhere: the school summary, attendance, results, fees and defaulters."""
from datetime import date

from flask import session

from config import Config
from models import (db, Student, SchoolClass, ClassArm, ClassArmAssignment, StudentEnrollment,
                    Attendance, FeeItem, FeeStructure, WAECResult, Branch)
from tests.conftest import login_token
from utils.helpers import get_active_term


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _summary(c):
    d = c.get('/reports/summary', headers={'X-Requested-With': 'fetch'}).get_json()
    return d.get('data', d)['blocks']


def test_trashed_student_leaves_every_count(app):
    c = _admin(app)
    with app.app_context():
        term = get_active_term()
        if term is None:
            from models import AcademicSession, Term
            ss = AcademicSession.query.filter_by(is_active=True).first() or AcademicSession(name='2098/2099', is_active=True)
            db.session.add(ss); db.session.flush()
            term = Term(session_id=ss.id, term_number=1, name='First Term', is_active=True, start_date=date(2000, 1, 1))
            db.session.add(term); db.session.flush()
        cls = SchoolClass(name='Trash Test Class', level=77); db.session.add(cls)
        arm = ClassArm.query.first() or ClassArm(name='Gold', is_active=True); db.session.add(arm)
        db.session.flush()
        asg = ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id); db.session.add(asg)
        item = FeeItem(name='Tuition (trash test)'); db.session.add(item); db.session.flush()
        db.session.add(FeeStructure(term_id=term.id, class_id=cls.id, arm_id=None, fee_item_id=item.id, amount=10000))
        from models import Week
        wk = Week(term_id=term.id, week_number=99, start_date=date.today(), end_date=date.today())
        db.session.add(wk); db.session.flush()
        bid = Branch.get_default().id
        ids = []
        for n in ('Keep', 'Gone'):
            s = Student(student_id=Student.generate_student_id(), first_name=n, surname='Trashtest',
                        gender='Male', is_active=True, branch_id=bid)
            db.session.add(s); db.session.flush(); ids.append(s.id)
            e = StudentEnrollment(student_id=s.id, class_arm_assignment_id=asg.id, is_active=True)
            db.session.add(e); db.session.flush()
            db.session.add(Attendance(enrollment_id=e.id, week_id=wk.id, date=date.today(), morning_present=(n == 'Keep'),
                                      afternoon_present=(n == 'Keep')))
            db.session.add(WAECResult(student_id=s.id, exam_year=2099, subject='Mathematics', grade='A1'))
        db.session.commit()
        keep_id, gone_id = ids

    before = _summary(c)
    row = next(r for r in before['students']['by_class'] if r['name'] == 'Trash Test Class')
    assert row['total'] == 2

    # move one to the trash the normal way
    from tests.conftest import auth_csrf
    c.post(f'/students/{gone_id}/delete', data={'_csrf_token': auth_csrf(c)})
    with app.app_context():
        assert db.session.get(Student, gone_id).is_active is False

    after = _summary(c)
    row = next(r for r in after['students']['by_class'] if r['name'] == 'Trash Test Class')
    assert row['total'] == 1                                            # per-class count
    assert after['students']['enrolled'] == before['students']['enrolled'] - 1
    assert after['students']['total'] == before['students']['total'] - 1
    assert after['results']['with_waec'] == before['results']['with_waec'] - 1
    assert after['attendance']['today_marked'] == before['attendance']['today_marked'] - 1
    assert after['attendance']['today_rate'] >= before['attendance']['today_rate']   # the absent one left
    # fees: the trashed student no longer owes the ₦10,000
    assert after['finance']['payable'] == before['finance']['payable'] - 10000
    assert after['finance']['defaulters'] == before['finance']['defaulters'] - 1

    with app.test_request_context('/'):
        session['logged_in'] = True
        session['role'] = 'super_admin'
        from utils.finance import defaulters_summary
        d = defaulters_summary(get_active_term().id)
        assert d['count'] == after['finance']['defaulters']

    # restoring brings them straight back
    with app.app_context():
        db.session.get(Student, gone_id).is_active = True
        db.session.commit()
    again = _summary(c)
    assert next(r for r in again['students']['by_class'] if r['name'] == 'Trash Test Class')['total'] == 2
