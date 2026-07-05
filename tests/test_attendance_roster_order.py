"""Attendance roster ordering: many schools list the register split by gender —
boys first, then girls, each group alphabetical by surname. ``roster_order()``
encodes exactly that, and every attendance roster query orders through it.
"""
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment)
from routes.attendance import roster_order


def _roster(app):
    """A class arm with a deliberately shuffled, mixed-gender roster."""
    with app.app_context():
        if Student.query.filter_by(student_id='RO-b-adams').first():
            caa = ClassArmAssignment.query.filter(
                ClassArmAssignment.id.in_(
                    db.session.query(StudentEnrollment.class_arm_assignment_id)
                    .join(Student).filter(Student.student_id.like('RO-%')))).first()
            return caa.id
        bid = Branch.get_default().id
        sess = AcademicSession(name='RO-Sess'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='RO-Term')
        db.session.add(term); db.session.flush()
        sc = SchoolClass.query.first(); arm = ClassArm.query.first()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        # Insertion order is intentionally NOT the expected display order.
        roster = [
            ('RO-g-brown', 'Brown', 'Grace', 'Female'),
            ('RO-b-adams', 'Adams', 'Bola', 'Male'),
            ('RO-g-allen', 'Allen', 'Amina', 'Female'),
            ('RO-b-cole',  'Cole',  'Chidi', 'Male'),
            ('RO-b-adeyemi', 'Adeyemi', 'Femi', 'Male'),
            ('RO-x-null',  'Zephyr', 'Pat',   'Other'),  # unrecognised gender -> sorts last
        ]
        for sid, sur, first, gender in roster:
            s = Student(student_id=sid, first_name=first, surname=sur,
                        gender=gender, is_active=True, branch_id=bid)
            db.session.add(s); db.session.flush()
            db.session.add(StudentEnrollment(
                student_id=s.id, class_arm_assignment_id=caa.id, is_active=True))
        db.session.commit()
        return caa.id


def test_boys_first_then_girls_each_alphabetical(app):
    caa_id = _roster(app)
    with app.app_context():
        enrollments = (StudentEnrollment.query
                       .filter_by(class_arm_assignment_id=caa_id, is_active=True)
                       .join(Student).order_by(*roster_order()).all())
        order = [(e.student.gender, e.student.surname) for e in enrollments]
        # Boys (alpha by surname) first, then girls (alpha by surname),
        # unknown-gender student last.
        assert order == [
            ('Male', 'Adams'),
            ('Male', 'Adeyemi'),
            ('Male', 'Cole'),
            ('Female', 'Allen'),
            ('Female', 'Brown'),
            ('Other', 'Zephyr'),
        ]


def test_gender_grouping_is_contiguous(app):
    """No interleaving: every boy comes before every girl."""
    caa_id = _roster(app)
    with app.app_context():
        enrollments = (StudentEnrollment.query
                       .filter_by(class_arm_assignment_id=caa_id, is_active=True)
                       .join(Student).order_by(*roster_order()).all())
        genders = [e.student.gender for e in enrollments]
        assert genders.index('Female') > max(
            i for i, g in enumerate(genders) if g == 'Male')
