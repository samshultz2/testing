"""The printable blank score-entry sheet (/subjects/broadsheet/blank-sheet)
printed its roster First Name / Middle Name / Surname — this fix reorders it
to the convention the school actually wants: S/N, Surname, Middle Name,
First Name."""
import io
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment)

_SEQ = [0]


def _seed(app):
    with app.app_context():
        _SEQ[0] += 1
        tag = f'BSN{_SEQ[0]}'
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'{tag}-Sess'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='First Term'); db.session.add(term); db.session.flush()
        sc = SchoolClass(name=f'{tag}C', level=1); arm = ClassArm(name=f'{tag}A', is_active=True)
        db.session.add_all([sc, arm]); db.session.flush()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        s = Student(student_id=f'{tag}-1', first_name='Zebediah', middle_name='Quincy',
                    surname='Abioduneka', gender='Male', is_active=True, branch_id=bid)
        db.session.add(s); db.session.flush()
        db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id, is_active=True))
        db.session.commit()
        return dict(term=term.id, asg=caa.id)


def _extract_text(pdf_bytes):
    import fitz   # PyMuPDF
    doc = fitz.open(stream=pdf_bytes, filetype='pdf')
    try:
        return doc[0].get_text()
    finally:
        doc.close()


def test_header_order_is_sn_surname_middle_first(app):
    from utils.broadsheet_export import blank_sheet_pdf
    ids = _seed(app)
    with app.app_context():
        pdf_bytes = blank_sheet_pdf(ids['term'], ids['asg'], subject_name='Maths')
    text = _extract_text(pdf_bytes)
    assert 'S/N' in text
    sn_pos = text.index('S/N')
    sur_pos = text.index('Surname')
    mid_pos = text.index('Middle Name')
    first_pos = text.index('First Name')
    assert sn_pos < sur_pos < mid_pos < first_pos, (
        f'expected header order S/N, Surname, Middle Name, First Name; got '
        f'positions {sn_pos}, {sur_pos}, {mid_pos}, {first_pos} in:\n{text}')


def test_row_order_is_surname_middle_first(app):
    from utils.broadsheet_export import blank_sheet_pdf
    ids = _seed(app)
    with app.app_context():
        pdf_bytes = blank_sheet_pdf(ids['term'], ids['asg'], subject_name='Maths')
    text = _extract_text(pdf_bytes)
    sur_pos = text.index('Abioduneka')
    mid_pos = text.index('Quincy')
    first_pos = text.index('Zebediah')
    assert sur_pos < mid_pos < first_pos, (
        f'expected row order Surname, Middle, First for the student; got '
        f'positions surname={sur_pos}, middle={mid_pos}, first={first_pos} in:\n{text}')


def test_roster_student_lookups_do_not_scale_with_class_size(app):
    """students = [e.student for e in ...] lazy-loaded Student per enrollment
    despite already joining it for ordering."""
    import re
    from sqlalchemy import event
    from models import db as _db
    from utils.broadsheet_export import blank_sheet_pdf

    with app.app_context():
        _SEQ[0] += 1
        tag = f'BSNL{_SEQ[0]}'
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'{tag}-Sess'); _db.session.add(sess); _db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='First Term'); _db.session.add(term); _db.session.flush()
        sc = SchoolClass(name=f'{tag}C', level=1); arm = ClassArm(name=f'{tag}A', is_active=True)
        _db.session.add_all([sc, arm]); _db.session.flush()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        _db.session.add(caa); _db.session.flush()
        for i in range(15):
            s = Student(student_id=f'{tag}-{i}', first_name=f'F{i}', middle_name='M',
                       surname=f'S{i}', gender='Male', is_active=True, branch_id=bid)
            _db.session.add(s); _db.session.flush()
            _db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id, is_active=True))
        _db.session.commit()
        term_id, asg_id = term.id, caa.id

    pattern = re.compile(r'^select\b.*\bfrom\s+students\b', re.IGNORECASE | re.DOTALL)
    counts = {'n': 0}

    def before(conn, cursor, statement, params, context, executemany):
        if pattern.match(statement):
            counts['n'] += 1
    with app.app_context():
        engine = _db.engine
    event.listen(engine, 'before_cursor_execute', before)
    try:
        with app.app_context():
            blank_sheet_pdf(term_id, asg_id, subject_name='Maths')
    finally:
        event.remove(engine, 'before_cursor_execute', before)
    assert counts['n'] <= 2, (
        f"{counts['n']} students SELECTs for a 15-student blank sheet — looks "
        f"like an N+1 (e.student lazy-loaded per enrollment instead of eager-loaded)")
