"""The redesigned class broadsheet exports: one document in PDF / image / Word /
Excel with options, a live-preview page endpoint, and averages that match the page."""
import io

import fitz
from docx import Document
from openpyxl import load_workbook

from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm, ClassArmAssignment,
                    Student, StudentEnrollment, Subject, ClassSubject, AssessmentType, StudentScore)
from tests.test_broadsheet_export import _admin

_SEQ = [0]


def _seed(app, n=4, scores=((80, 45), (70, 60), (40, 30), (90, 95))):
    with app.app_context():
        _SEQ[0] += 1
        tag = f'BD{_SEQ[0]}'
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'{tag}-Sess'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='First Term'); db.session.add(term); db.session.flush()
        sc = SchoolClass.query.first(); arm = ClassArm.query.first()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        # Reuse an existing assessment type: adding one would change other tests'
        # score-sheet columns in the shared database.
        at = AssessmentType.query.filter_by(is_active=True).order_by(AssessmentType.id).first()
        css = []
        for name in (f'Mathematics', f'Civic Education'):
            subj = Subject.query.filter_by(name=name).first() or Subject(name=name, is_active=True)
            db.session.add(subj); db.session.flush()
            cs = ClassSubject(subject_id=subj.id, class_id=sc.id, arm_id=arm.id, term_id=term.id, is_active=True)
            db.session.add(cs); db.session.flush(); css.append(cs)
        for i in range(n):
            s = Student(student_id=f'{tag}-{i}', first_name=f'Pupil{i}', surname=f'{tag}Sur{chr(68 - i) if i < 4 else "Z%02d" % i}',
                        gender='Male' if i % 2 else 'Female', is_active=True, branch_id=bid)
            db.session.add(s); db.session.flush()
            db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id, is_active=True))
            for cs, v in zip(css, scores[i % len(scores)]):
                db.session.add(StudentScore(student_id=s.id, class_subject_id=cs.id, assessment_type_id=at.id, score=v))
        db.session.commit()
        return f"term_id={term.id}&assignment_id={caa.id}", tag


def _pdf_text(data):
    with fitz.open(stream=data, filetype='pdf') as d:
        return len(d), '\n'.join(p.get_text() for p in d)


def test_pdf_has_header_tiles_stats_key_and_ranked_rows(app):
    q, tag = _seed(app)
    c = _admin(app)
    r = c.get(f'/subjects/broadsheet/export?{q}&format=pdf')
    assert r.status_code == 200 and r.data[:4] == b'%PDF'
    pages, txt = _pdf_text(r.data)
    assert pages == 1
    for s in ('Broadsheet', 'CLASS AVERAGE', 'TOP STUDENT', 'Subject average', 'Pass rate',
              'MTH', 'CIV', 'Mathematics', 'Civic Education', "Principal", 'Page 1 of 1'):
        assert s in txt, s
    # 92.5 average first (90, 95), then 65, 62.5, 35 — and no trailing zeros
    assert txt.index(f'{tag}SurA') < txt.index(f'{tag}SurC')
    assert '92.5' in txt and '62.5' in txt and '62.50' not in txt


def test_options_switch_blocks_off_and_change_order(app):
    q, tag = _seed(app)
    c = _admin(app)
    off = '&'.join(f'{k}=0' for k in ('b_kpis', 'b_stats', 'b_key', 'b_sign', 'c_pf'))
    _, txt = _pdf_text(c.get(f'/subjects/broadsheet/export?{q}&format=pdf&{off}&sort=name&c_sid=1&style=bw').data)
    for s in ('CLASS AVERAGE', 'Subject average', 'Principal', 'Subjects:'):
        assert s not in txt, s
    assert f'{tag}-0' in txt                                   # student ID column
    names = [f'{tag}Sur{x}' for x in 'ABCD']
    assert [txt.index(n) for n in names] == sorted(txt.index(n) for n in names)   # A–Z
    # Portrait A3 is a portrait A3 page.
    with fitz.open(stream=c.get(f'/subjects/broadsheet/export?{q}&format=pdf&paper=A3&orient=portrait').data,
                   filetype='pdf') as d:
        w, h = d[0].rect.width, d[0].rect.height
        assert h > w and round(w) == 842


def test_preview_pages_and_big_classes_repeat_headings(app):
    q, _tag = _seed(app, n=60)
    c = _admin(app)
    r = c.get(f'/subjects/broadsheet/export?{q}&format=image&preview=1&page=2')
    assert r.data[:4] == b'\x89PNG' and int(r.headers['X-Total-Pages']) >= 2
    assert 'Content-Disposition' not in r.headers and r.headers.get('Cache-Control') == 'no-store'
    _, txt = _pdf_text(c.get(f'/subjects/broadsheet/export?{q}&format=pdf').data)
    assert txt.count('POS') >= 2 and 'Page 2 of' in txt          # headings repeat on every page
    z = c.get(f'/subjects/broadsheet/export?{q}&format=image')
    assert z.mimetype == 'application/zip'                      # several pages → a zip of PNGs


def test_word_and_excel_follow_the_options(app):
    q, tag = _seed(app)
    c = _admin(app)
    doc = Document(io.BytesIO(c.get(f'/subjects/broadsheet/export?{q}&format=word').data))
    cells = [cell.text for t in doc.tables for row in t.rows for cell in row.cells]
    assert 'Subject average' in cells and f'{tag}SurA' in ' '.join(cells) and 'MTH' in cells
    wb = load_workbook(io.BytesIO(c.get(f'/subjects/broadsheet/export?{q}&format=excel&c_sid=1').data))
    ws = wb.active
    vals = [v for row in ws.iter_rows(values_only=True) for v in row if v is not None]
    assert 'Pass rate' in vals and f'{tag}-3' in vals and 92.5 in vals
    head = next(row for row in ws.iter_rows(values_only=True) if row and 'Student' in row)
    assert head[:3] == ('Pos', 'Student', 'ID')


def test_dialog_options_are_sent_to_the_page(app):
    q, _tag = _seed(app)
    c = _admin(app)
    j = c.get(f'/subjects/broadsheet?{q}', headers={'X-Requested-With': 'fetch'}).get_json()
    d = j.get('data', j)
    keys = {o['key'] for o in d['export_options']}
    assert {'c_pos', 'b_kpis', 'b_stats', 'b_fail', 'b_top', 'b_sign'} <= keys
