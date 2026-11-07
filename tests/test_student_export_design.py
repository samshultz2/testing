"""Students → Export: the branded documents (utils/student_list_export) and the
export route's options (columns/order, grouping, presets, layout, preview)."""
import io
import json
import uuid

from config import Config
from models import db, Student
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _enroll(app, class_name, student_id):
    """Enrol in ``class_name`` (arm Gold) for the active term, creating only
    what is missing — never a duplicate session name."""
    from models import (AcademicSession, Term, SchoolClass, ClassArm,
                        ClassArmAssignment, StudentEnrollment)
    with app.app_context():
        ssn = AcademicSession.query.filter_by(is_active=True).first()
        if not ssn:
            ssn = AcademicSession(name='EXP ' + uuid.uuid4().hex[:6], is_active=True)
            db.session.add(ssn); db.session.flush()
        term = Term.query.filter_by(is_active=True).first()
        if not term:
            term = Term(session_id=ssn.id, term_number=1, name='First Term', is_active=True)
            db.session.add(term); db.session.flush()
        cls = SchoolClass.query.filter_by(name=class_name).first() or SchoolClass(name=class_name, level=7)
        db.session.add(cls); db.session.flush()
        arm = ClassArm.query.filter_by(name='Gold').first() or ClassArm(name='Gold', is_active=True)
        db.session.add(arm); db.session.flush()
        caa = (ClassArmAssignment.query.filter_by(class_id=cls.id, arm_id=arm.id, term_id=term.id).first()
               or ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id))
        db.session.add(caa); db.session.flush()
        db.session.add(StudentEnrollment(student_id=student_id, class_arm_assignment_id=caa.id, is_active=True))
        db.session.commit()


def _students(app, n=4, **extra):
    ids = []
    with app.app_context():
        for i in range(n):
            s = Student(student_id='EX' + uuid.uuid4().hex[:6].upper(), first_name='Ada%d' % i,
                        surname='Zexport', gender='Female' if i % 2 else 'Male', is_active=True, **extra)
            db.session.add(s); db.session.flush()
            ids.append(s.id)
        db.session.commit()
    for sid in ids[:2]:
        _enroll(app, 'EXP1', sid)
    return ids


def _get(c, ids, fmt, **kw):
    q = {'format': fmt, 'fields': json.dumps(kw.pop('fields', ['student_id', 'name', 'gender', 'current_class'])),
         'student_ids': json.dumps(ids)}
    q.update({k: str(v) for k, v in kw.items()})
    return c.get('/students/export', query_string=q)


def _pdf_text(data):
    import fitz
    return '\n'.join(p.get_text() for p in fitz.open(stream=data, filetype='pdf'))


def test_pdf_has_letterhead_title_groups_and_page_numbers(app):
    ids = _students(app)
    c = _admin(app)
    r = _get(c, ids, 'pdf', title='Test Class List', subtitle='Session line', signatures=1)
    assert r.status_code == 200 and r.mimetype == 'application/pdf'
    assert 'Test_Class_List.pdf' in r.headers['Content-Disposition']
    t = _pdf_text(r.data)
    assert 'Test Class List' in t and 'Session line' in t and 'STUDENTLIST' in t.replace(' ', '')
    assert 'EXP1' in t and 'No class assigned' in t            # grouped by class
    assert 'Page 1 of 1' in t and 'Class teacher' in t
    assert 'Zexport' in t and 'STUDENTS' in t and 'MALE' in t   # name + count boxes


def test_exam_preset_flags_missing_numbers_and_goes_landscape(app):
    ids = _students(app, waec_reg_number='4250101001')
    with app.app_context():
        db.session.get(Student, ids[0]).waec_reg_number = None
        db.session.commit()
    c = _admin(app)
    fields = ['student_id', 'name', 'gender', 'date_of_birth', 'nin', 'jamb_reg_number', 'waec_reg_number', 'neco_reg_number']
    r = _get(c, ids, 'pdf', fields=fields, preset='exam')
    t = _pdf_text(r.data)
    assert 'EXAMNUMBERS' in t.replace(' ', '') and '— missing' in t and 'MISSING A NUMBER' in t
    import fitz
    page = fitz.open(stream=r.data, filetype='pdf')[0]
    assert page.rect.width > page.rect.height                     # auto → landscape


def test_image_preview_headers_and_empty_list(app):
    ids = _students(app)
    c = _admin(app)
    r = _get(c, ids, 'image', preview=1, page=1)
    assert r.status_code == 200 and r.mimetype == 'image/png'
    assert r.headers['X-Total-Pages'] == '1' and r.headers['X-Export-Orientation'] in ('portrait', 'landscape')
    assert r.headers['X-Export-Title']
    r = c.get('/students/export', query_string={'format': 'image', 'preview': '1', 'search': 'nobody-zz-' + uuid.uuid4().hex,
                                                 'fields': json.dumps(['name'])})
    assert r.status_code == 422


def test_excel_is_branded_filterable_and_keeps_text(app):
    from openpyxl import load_workbook
    ids = _students(app)
    c = _admin(app)
    r = _get(c, ids, 'excel', fields=['student_id', 'name', 'gender', 'current_class', 'parent_phone'])
    wb = load_workbook(io.BytesIO(r.data))
    assert wb.sheetnames == ['Students', 'Summary', 'About this export']
    ws = wb['Students']
    assert [c.value for c in ws[3]][:5] == ['#', 'Student ID', 'Surname', 'Other names', 'Gender']
    assert ws.freeze_panes == 'B4' and ws.auto_filter.ref.startswith('A3:')
    totals = [row for row in wb['Summary'].iter_rows(values_only=True) if row and row[0] == 'Total'][0]
    assert totals[1] == 4 and totals[2] + totals[3] == 4


def test_word_and_csv_and_old_field_names(app):
    from docx import Document
    ids = _students(app)
    c = _admin(app)
    r = _get(c, ids, 'word', title='Word List')
    doc = Document(io.BytesIO(r.data))
    text = '\n'.join(p.text for p in doc.paragraphs) + '\n'.join(c.text for t in doc.tables for row in t.rows for c in row.cells)
    assert 'Word List' in text and 'Zexport' in text and 'EXP1' in text
    # Old clients (surname + first_name) still work and become Surname / Other names.
    r = _get(c, ids, 'csv', fields=['student_id', 'surname', 'first_name', 'gender'])
    head = r.get_data(as_text=True).splitlines()[0]
    assert head.startswith('Student ID,Surname,Other names,Gender')


def test_column_order_is_respected(app):
    ids = _students(app)
    c = _admin(app)
    r = _get(c, ids, 'csv', fields=['gender', 'student_id', 'name'], group=0)
    assert r.get_data(as_text=True).splitlines()[0] == 'Gender,Student ID,Surname,Other names'
