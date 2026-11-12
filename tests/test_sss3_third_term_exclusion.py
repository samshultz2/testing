"""SSS3 sit no internal exams in third term (only WAEC/NECO/JAMB), so third-term
internal score entry, broadsheet and analytics must exclude the SSS3 class arms.
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


def test_is_third_term_and_strip(app):
    from utils.helpers import is_third_term, strip_sss3_third_term
    sss3_id = _sss3(app)
    with app.app_context():
        sess = AcademicSession(name='STE-Sess'); db.session.add(sess); db.session.flush()
        t1 = Term(session_id=sess.id, term_number=1, name='STE-T1')
        t3 = Term(session_id=sess.id, term_number=3, name='STE-T3')
        db.session.add_all([t1, t3]); db.session.commit()
        assert is_third_term(t3.id) is True
        assert is_third_term(t1.id) is False

        other_cls = SchoolClass.query.filter(SchoolClass.id != sss3_id).first()
        other_id = other_cls.id if other_cls else sss3_id
        # Build assignment-like objects (only .class_id is used by the filter).
        sss3_a = SimpleNamespace(id=1, class_id=sss3_id)
        other_a = SimpleNamespace(id=2, class_id=other_id)
        both = [sss3_a, other_a]

        # Third term: SSS3 dropped.
        kept3 = strip_sss3_third_term(both, t3.id)
        assert sss3_a not in kept3 and other_a in kept3
        # First term: unchanged.
        kept1 = strip_sss3_third_term(both, t1.id)
        assert sss3_a in kept1 and other_a in kept1


def test_org_analytics_scope_excludes_sss3_third_term(app):
    """The institution rollup must not count SSS3 arms in third term, so no SSS3
    subject appears and no SSS3 teacher is flagged for 'incomplete' entry."""
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
            assert sss3_id not in class_ids          # SSS3 excluded in third term
            assert other_cls.id in class_ids         # other classes still counted
        finally:
            for o in (a_sss3, a_other):
                db.session.delete(o)
            db.session.delete(t3); db.session.delete(sess); db.session.commit()
