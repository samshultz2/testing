"""SSS3 is back in third-term internal results: their Mock WAEC scores are
recorded there as CBT + Theory, so score entry, broadsheets and the results
analytics include the SSS3 class arms in every term.
"""
from types import SimpleNamespace
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment)


def _sss3(app):
    with app.app_context():
        sc = SchoolClass.query.filter_by(name='SSS3').first()
        if not sc:
            sc = SchoolClass(name='SSS3', level=12); db.session.add(sc); db.session.commit()
        return sc.id


def test_is_third_term(app):
    from utils.helpers import is_third_term
    with app.app_context():
        sess = AcademicSession(name='STE-Sess'); db.session.add(sess); db.session.flush()
        t1 = Term(session_id=sess.id, term_number=1, name='STE-T1')
        t3 = Term(session_id=sess.id, term_number=3, name='STE-T3')
        db.session.add_all([t1, t3]); db.session.commit()
        assert is_third_term(t3.id) is True
        assert is_third_term(t1.id) is False


def test_org_analytics_scope_includes_sss3_third_term(app):
    """The institution rollup counts SSS3 arms in third term like any class."""
    from utils.results_analytics_org import _scope_assignments
    sss3_id = _sss3(app)
    with app.app_context():
        sess = AcademicSession(name='ORG-Sess'); db.session.add(sess); db.session.flush()
        t3 = Term(session_id=sess.id, term_number=3, name='ORG-T3')
        db.session.add(t3); db.session.flush()
        other_cls = SchoolClass.query.filter(SchoolClass.id != sss3_id).first() \
            or SchoolClass(name='SSS1', level=10)
        if not other_cls.id:
            db.session.add(other_cls); db.session.flush()
        arm = ClassArm.query.first() or ClassArm(name='A', is_active=True)
        if not arm.id:
            db.session.add(arm); db.session.flush()
        a_sss3 = ClassArmAssignment(class_id=sss3_id, arm_id=arm.id, term_id=t3.id)
        a_other = ClassArmAssignment(class_id=other_cls.id, arm_id=arm.id, term_id=t3.id)
        db.session.add_all([a_sss3, a_other]); db.session.commit()
        try:
            rows = _scope_assignments(t3.id, 'school', None, None)
            class_ids = {a.class_id for a in rows}
            assert sss3_id in class_ids              # SSS3 included in third term
            assert other_cls.id in class_ids         # other classes still counted
        finally:
            for o in (a_sss3, a_other):
                db.session.delete(o)
            db.session.delete(t3); db.session.delete(sess); db.session.commit()


def test_score_entry_lists_and_opens_sss3_in_third_term(app):
    from config import Config
    from tests.conftest import login_token
    sss3_id = _sss3(app)
    with app.app_context():
        sess = AcademicSession(name='SE3-Sess'); db.session.add(sess); db.session.flush()
        t3 = Term(session_id=sess.id, term_number=3, name='SE3-T3'); db.session.add(t3); db.session.flush()
        arm = ClassArm.query.first() or ClassArm(name='A', is_active=True)
        if not arm.id:
            db.session.add(arm); db.session.flush()
        a = ClassArmAssignment(class_id=sss3_id, arm_id=arm.id, term_id=t3.id)
        db.session.add(a); db.session.commit()
        t3_id, a_id = t3.id, a.id
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    r = c.get(f'/subjects/scores?term_id={t3_id}&assignment_id={a_id}')
    assert r.status_code == 200                       # no longer redirected away
    assert f'"id": {a_id}' in r.get_data(as_text=True) or f'value="{a_id}"' in r.get_data(as_text=True)
