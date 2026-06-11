"""Header-driven student Excel import: flexible columns, gender default,
phone leading-zero restore, and per-row isolation."""
import io

from openpyxl import Workbook

from models import db, Student, ParentContact
from utils.excel_utils import import_students_from_excel, create_student_import_template


def _xlsx(rows):
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def test_register_style_import(app):
    """A register-style sheet (no Gender column, phone as a number) imports."""
    sheet = _xlsx([
        ['Surname', 'First Name', 'Middle Name', 'Date of Birth', 'Address',
         'Phone Number', 'Religion', 'Name of Primary Contact'],
        ['MESHACH', 'JEFFREY', None, '16/12/2010', 'Goshen Estate',
         7070239917, 'Christianity', 'Mrs. MESHACH'],          # phone lost its 0
        ['OMITIE', 'DOMINION', None, '08/12/2010', 'Lucky way',
         None, 'Christianity', 'Mrs. OMITIE'],                 # name but no phone
    ])
    with app.app_context():
        n, msgs = import_students_from_excel(sheet, db, Student, ParentContact)
        assert n == 2
        m = Student.query.filter_by(surname='MESHACH').order_by(Student.id.desc()).first()
        assert m.gender == 'Unknown'                  # no gender column -> defaulted
        assert str(m.date_of_birth) == '2010-12-16'   # day-first parsed
        assert m.parent_contacts.first().phone_number == '07070239917'  # 0 restored
        o = Student.query.filter_by(surname='OMITIE').order_by(Student.id.desc()).first()
        assert o.parent_contacts.count() == 0          # name-only -> no broken contact
        assert any('Unknown' in s for s in msgs)       # defaulting is reported
        db.session.rollback()


def test_columns_any_order_and_gender_normalised(app):
    sheet = _xlsx([
        ['First Name', 'Surname', 'Sex'],   # reordered + 'Sex' alias
        ['Ada', 'Obi', 'female'],
    ])
    with app.app_context():
        n, _ = import_students_from_excel(sheet, db, Student, ParentContact)
        assert n == 1
        s = Student.query.filter_by(surname='Obi').order_by(Student.id.desc()).first()
        assert s.first_name == 'Ada' and s.gender == 'Female'
        db.session.rollback()


def test_missing_required_headers_rejected(app):
    sheet = _xlsx([['Name', 'Phone'], ['x', '0800']])
    with app.app_context():
        n, msgs = import_students_from_excel(sheet, db, Student, ParentContact)
        assert n == 0 and any('Surname' in m for m in msgs)


def test_duplicate_guard_skips_reimport(app):
    """Re-importing the same sheet adds nobody the second time."""
    sheet_rows = [
        ['Surname', 'First Name', 'Date of Birth'],
        ['Dupe', 'Tester', '2011-01-02'],
    ]
    with app.app_context():
        n1, _ = import_students_from_excel(_xlsx(sheet_rows), db, Student, ParentContact)
        assert n1 == 1
        n2, msgs = import_students_from_excel(_xlsx(sheet_rows), db, Student, ParentContact)
        assert n2 == 0
        assert any('duplicate' in m.lower() for m in msgs)
        # in-file duplicate (same row twice) is also caught
        n3, _ = import_students_from_excel(
            _xlsx(sheet_rows[:1] + [sheet_rows[1], sheet_rows[1]]),
            db, Student, ParentContact)
        assert n3 == 0
        db.session.rollback()


def test_generated_template_imports_without_junk(app):
    """The downloadable template's EXAMPLE row must not create a student."""
    with app.app_context():
        before = Student.query.count()
        n, _ = import_students_from_excel(
            create_student_import_template(), db, Student, ParentContact)
        assert n == 0 and Student.query.count() == before
