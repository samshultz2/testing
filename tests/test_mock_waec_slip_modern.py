"""Mock WAEC result slip: the Modern theme beside the Classic one, with every
block switchable."""
import uuid
from datetime import date

from models import db, AcademicSession
from models.mock_waec import MockWAECExam, MockWAECResult, waec_grade_from_score
from tests.test_mock_waec_broadsheet_extras import _admin, _student


def _setup(app, name=('Ada', 'Okonkwo')):
    with app.app_context():
        s = AcademicSession(name=f'SM-{uuid.uuid4().hex[:6]}'); db.session.add(s); db.session.flush()
        m1 = MockWAECExam(name='M1', exam_number=1, session_id=s.id, exam_date=date(2026, 1, 10))
        m2 = MockWAECExam(name='M2', exam_number=2, session_id=s.id, exam_date=date(2026, 5, 2))
        db.session.add_all([m1, m2]); db.session.commit()
        ids = (m1.id, m2.id)
    sid = _student(app, 'SM' + uuid.uuid4().hex[:5].upper(), name[0], name[1])
    with app.app_context():
        for subj, sc in {'English Language': 55, 'Mathematics': 40, 'Physics': 60}.items():
            db.session.add(MockWAECResult(student_id=sid, mock_exam_id=ids[0], subject=subj, score=sc,
                                          grade=waec_grade_from_score(sc)))
        for subj, sc in {'English Language': 66, 'Mathematics': 58, 'Physics': 47}.items():
            db.session.add(MockWAECResult(student_id=sid, mock_exam_id=ids[1], subject=subj, score=sc,
                                          grade=waec_grade_from_score(sc)))
        db.session.add(MockWAECResult(student_id=sid, mock_exam_id=ids[1], subject='Biology',
                                      score=None, grade=None, is_absent=True))
        db.session.commit()
    return ids, sid


def _text(c, url):
    import fitz
    r = c.get(url)
    assert r.status_code == 200 and r.mimetype == 'application/pdf'
    with fitz.open(stream=r.get_data(), filetype='pdf') as d:
        # Letter-spaced labels come out as "R E S U L T"; compare without spaces.
        return len(d), ''.join(''.join(p.get_text().split()) for p in d)


def test_modern_theme_draws_the_new_slip(app):
    (m1, m2), sid = _setup(app)
    c = _admin(app)
    pages, t = _text(c, f'/mock-waec/exam/{m2}/student/{sid}/slip.pdf?theme=modern')
    assert pages == 1
    for frag in ('RESULTSLIP', 'SecondCompetence', 'Okonkwo', 'SUBJECTS', 'CREDITS', 'AVERAGE',
                 'sinceFirstCompetence', 'ABS', 'Absent', 'GRADING', 'STAMP', 'Issued'):
        assert frag in t, frag
    assert t.count('CORE') == 3                      # the SCORE header + English and Maths tags
    # Classic is still the default and untouched.
    _, classic = _text(c, f'/mock-waec/exam/{m2}/student/{sid}/slip.pdf')
    assert 'COMPETENCERESULT' in classic and 'RESULTSLIP' not in classic


def test_every_block_can_be_switched_off(app):
    (m1, m2), sid = _setup(app)
    c = _admin(app)
    off = ('m_label', 'm_exam', 'm_session', 'm_date', 'm_class', 'm_gender', 'm_subjects', 'm_credits',
           'm_average', 'm_core', 'remark', 'grades', 'm_stamp', 'm_footer', 'printed_on')
    q = '&'.join(f'{k}=0' for k in off)
    _, t = _text(c, f'/mock-waec/exam/{m2}/student/{sid}/slip.pdf?theme=modern&{q}&signers=none')
    for frag in ('RESULTSLIP', 'SecondCompetence', 'Session', 'Examdate', 'GENDER', 'papermissed', 'A1–C6', 'CREDITS',
                 'AVERAGE', 'REMARK', 'GRADING', 'STAMP', 'notanofficial', 'Issued', 'Principal'):
        assert frag not in t, frag
    assert t.count('CORE') == 1                      # only the SCORE header is left
    assert 'Okonkwo' in t and 'Physics' in t          # the name and the results always stay


def test_whole_class_and_long_names(app):
    (m1, m2), sid = _setup(app, ('Oluwadamilare Chukwuemeka', 'Adebayo-Okonkwo-Ibrahim'))
    c = _admin(app)
    pages, t = _text(c, f'/mock-waec/exam/{m2}/slips.pdf?theme=modern&bw=1')
    assert pages >= 1 and 'Adebayo-Okonkwo-Ibrahim' in t


def test_export_screen_offers_both_themes(app):
    (m1, m2), sid = _setup(app)
    html = _admin(app).get(f'/mock-waec/exam/{m2}/student/{sid}/slip').get_data(as_text=True)
    assert 'id="themeSel"' in html and 'data-theme="modern"' in html and 'data-theme="classic"' in html
    assert 'data-param="m_stamp"' in html
