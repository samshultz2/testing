"""JAMB, Mock JAMB and Mock WAEC exports use the branded results document
(Students List / Subject Analysis, PDF / image / Word, text size) — the same
design as the WAEC / NECO export."""
import uuid
from datetime import date
from io import BytesIO

import fitz
from docx import Document

from config import Config
from models import db, Student, AcademicSession, JAMBResult
from models.mock_jamb import MockJAMBExam, MockJAMBResult
from models.mock_waec import MockWAECExam, MockWAECResult, waec_grade_from_score
from models.models import RateLimitHit
from tests.conftest import login_token


def _client(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _students(app, names):
    with app.app_context():
        out = []
        for n in names:
            s = Student(student_id='RX' + uuid.uuid4().hex[:6].upper(), first_name=n, surname='Rxtest',
                        gender='Female', is_active=True)
            db.session.add(s); db.session.flush(); out.append(s.id)
        db.session.commit()
        return out


def _text(data):
    with fitz.open(stream=data, filetype='pdf') as d:
        return ' '.join(' '.join(p.get_text() for p in d).split())


def _clean_limits(app):
    with app.app_context():
        RateLimitHit.query.filter(RateLimitHit.rkey.like('%export%')).delete(synchronize_session=False)
        db.session.commit()


def test_jamb_branded_exports(app):
    _clean_limits(app)
    a, b = _students(app, ['Jambhigh', 'Jamblow'])
    with app.app_context():
        db.session.add_all([
            JAMBResult(student_id=a, exam_year=2061, total_score=301, subject1='Use of English', subject1_score=80,
                       subject2='Mathematics', subject2_score=75, subject3='Physics', subject3_score=76,
                       subject4='Chemistry', subject4_score=70),
            JAMBResult(student_id=b, exam_year=2061, total_score=170, subject1='Use of English', subject1_score=45,
                       subject2='Mathematics', subject2_score=35, subject3='Physics', subject3_score=40,
                       subject4='Chemistry', subject4_score=50),
            JAMBResult(student_id=b, exam_year=2060, total_score=150, subject1='Use of English', subject1_score=40,
                       subject2='Mathematics', subject2_score=30, subject3='Physics', subject3_score=40,
                       subject4='Chemistry', subject4_score=40)])
        db.session.commit()
    c = _client(app)
    html = c.get('/results/jamb?year=2061').get_data(as_text=True)
    assert 'id="rxExportModal"' in html and 'name="rxSize"' in html and 'html2canvas' not in html
    base = '/results/jamb/export?year=2061'
    txt = _text(c.get(base + '&format=pdf&type=students&cols=rank,student_id,subjects,level,cutoff').data)
    assert 'UTME 2061 — Results' in txt and 'SCORE KEY' in txt and 'Subject codes:' in txt
    assert txt.index('Rxtest Jambhigh') < txt.index('Rxtest Jamblow') or \
        txt.index('Jambhigh') < txt.index('Jamblow')
    assert '301/400' in txt.replace(' ', '') and 'Excellent' in txt
    # Score range filter
    txt = _text(c.get(base + '&format=pdf&type=students&min_score=200').data)
    assert 'Jambhigh' in txt and 'Jamblow' not in txt
    # Subject analysis with change vs last year, chart and highlights
    txt = _text(c.get(base + '&format=pdf&type=subjects').data)
    assert 'Subject Analysis' in txt and 'All subjects' in txt and 'VS 2060' in txt and 'STRONGEST SUBJECT' in txt
    img = c.get(base + '&format=image&type=subjects&size=l&cols=total,bands,spread,avg,high,low,pass,delta,chart')
    assert img.data[:4] == b'\x89PNG' and img.headers.get('X-Total-Pages') == '1'
    doc = Document(BytesIO(c.get(base + '&format=word&type=students').data))
    assert any('Jambhigh' in cell.text for t in doc.tables for row in t.rows for cell in row.cells)
    assert c.get(base).data[:2] == b'PK'                       # Excel unchanged


def test_mock_jamb_branded_exports(app):
    _clean_limits(app)
    a, = _students(app, ['Mockjambone'])
    with app.app_context():
        ss = AcademicSession.query.filter_by(is_active=True).first() or AcademicSession(name='RX 61/62', is_active=True)
        db.session.add(ss); db.session.flush()
        ex = MockJAMBExam(name='RX Mock', exam_number=7, session_id=ss.id, exam_date=date(2061, 3, 1))
        db.session.add(ex); db.session.flush()
        db.session.add(MockJAMBResult(student_id=a, mock_exam_id=ex.id, total_score=244,
                                      subject1='Use of English', subject1_score=61, subject2='Biology',
                                      subject2_score=62, subject3='Physics', subject3_score=60,
                                      subject4='Chemistry', subject4_score=61))
        db.session.commit()
        eid = ex.id
    c = _client(app)
    page = c.get(f'/mock-jamb/exam/{eid}').get_data(as_text=True)
    assert 'export_cols' in page or 'Subject scores' in page
    base = f'/mock-jamb/exam/{eid}/export?'
    txt = _text(c.get(base + 'format=pdf&type=students').data)
    assert 'Mock JAMB' in txt and 'Mockjambone' in txt and 'SCORE KEY' in txt
    txt = _text(c.get(base + 'format=pdf&type=subjects').data)
    assert 'Subject Analysis' in txt and 'Biology' in txt
    assert c.get(base + 'format=word&type=subjects').data[:2] == b'PK'
    assert c.get(base + 'format=image').data[:4] == b'\x89PNG'


def test_mock_waec_branded_exports(app):
    _clean_limits(app)
    a, b = _students(app, ['Mockwaecone', 'Mockwaectwo'])
    with app.app_context():
        ss = AcademicSession.query.filter_by(is_active=True).first() or AcademicSession(name='RX 61/62', is_active=True)
        db.session.add(ss); db.session.flush()
        ex = MockWAECExam(name='RX Mock WAEC', exam_number=8, session_id=ss.id, exam_date=date(2061, 4, 1))
        db.session.add(ex); db.session.flush()
        for sid, sc in ((a, 78), (b, 45)):
            for subj in ('English Language', 'Mathematics', 'Biology'):
                db.session.add(MockWAECResult(student_id=sid, mock_exam_id=ex.id, subject=subj, score=sc,
                                              grade=waec_grade_from_score(sc)))
        db.session.commit()
        eid = ex.id
    c = _client(app)
    page = c.get(f'/mock-waec/exam/{eid}').get_data(as_text=True)
    assert 'id="rxExportModal"' in page and 'value="g:A1"' in page
    base = f'/mock-waec/exam/{eid}/export?'
    txt = _text(c.get(base + 'format=pdf&type=students').data)
    assert 'Mock WAEC' in txt and 'A1–B3' in txt and 'Mockwaecone' in txt
    assert txt.index('Mockwaecone') < txt.index('Mockwaectwo')
    txt = _text(c.get(base + 'format=pdf&type=subjects&size=s').data)
    assert 'Subject Analysis' in txt and 'All subjects' in txt and 'CREDIT RATE' in txt
    assert c.get(base + 'format=word').data[:2] == b'PK'
    assert c.get(base + 'format=image&type=subjects').data[:4] == b'\x89PNG'
    assert c.get(f'/mock-waec/exam/{eid}/export').data[:2] == b'PK'   # Excel unchanged
