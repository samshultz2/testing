"""Whole-class Mock WAEC result slips open with a contents page: every student,
their page number, and a link from each name to their slip."""
import uuid
from datetime import date

import pytest

from models import db, AcademicSession
from models.mock_waec import MockWAECExam, MockWAECResult, waec_grade_from_score
from tests.test_mock_waec_broadsheet_extras import _admin, _student


def _exam_with(app, names):
    with app.app_context():
        s = AcademicSession(name=f'TOC-{uuid.uuid4().hex[:6]}'); db.session.add(s); db.session.flush()
        ex = MockWAECExam(name='M1', exam_number=1, session_id=s.id, exam_date=date(2026, 3, 2))
        db.session.add(ex); db.session.commit()
        eid = ex.id
    tag = uuid.uuid4().hex[:4].upper()
    for first, sur in names:
        sid = _student(app, 'TC' + tag + first[:3].upper(), first, sur + tag)
        with app.app_context():
            for subj, sc in {'English Language': 66, 'Mathematics': 58}.items():
                db.session.add(MockWAECResult(student_id=sid, mock_exam_id=eid, subject=subj, score=sc,
                                              grade=waec_grade_from_score(sc)))
            db.session.commit()
    return eid, tag


@pytest.mark.parametrize('theme', ['classic', 'modern', 'profile', 'transcript'])
def test_contents_page_lists_and_links_every_student(app, theme):
    import fitz
    eid, tag = _exam_with(app, [('Ada', 'Bello'), ('Chidi', 'Okafor'), ('Zainab', 'Yusuf')])
    c = _admin(app)
    r = c.get(f'/mock-waec/exam/{eid}/slips.pdf?theme={theme}')
    assert r.status_code == 200
    with fitz.open(stream=r.get_data(), filetype='pdf') as d:
        assert len(d) == 1 + 3                               # contents + one page each
        first = d[0].get_text()
        assert 'Contents' in first
        for sur in ('Bello', 'Okafor', 'Yusuf'):
            assert sur + tag in first
        # Rows are A–Z by surname; each links to the page that holds that slip.
        targets = sorted(l['page'] for l in d[0].get_links() if l.get('kind') == fitz.LINK_GOTO)
        assert targets == [1, 2, 3]
        for link in d[0].get_links():
            name_on_row = d[0].get_textbox(link['from'])
            surname = next(s for s in ('Bello', 'Okafor', 'Yusuf') if s in name_on_row)
            assert surname + tag in d[link['page']].get_text().replace('\n', ' ') or \
                surname.upper() + tag in d[link['page']].get_text().upper()
        # The PDF outline lists the contents page and every student.
        outline = [t[1] for t in d.get_toc()]
        assert outline[0] == 'Contents' and len(outline) == 4


def test_contents_can_be_switched_off_and_single_slips_have_none(app):
    import fitz
    eid, tag = _exam_with(app, [('Ada', 'Bello'), ('Chidi', 'Okafor')])
    c = _admin(app)
    with fitz.open(stream=c.get(f'/mock-waec/exam/{eid}/slips.pdf?toc=0').get_data(), filetype='pdf') as d:
        assert len(d) == 2 and 'Contents' not in d[0].get_text()
    page = c.get(f'/mock-waec/exam/{eid}/slips').get_data(as_text=True)
    assert 'data-param="toc"' in page


def test_contents_spills_onto_more_pages_for_big_classes(app, monkeypatch):
    from types import SimpleNamespace
    import fitz
    import utils.mock_waec_pdf as mp
    from utils.mock_waec_pdf import result_slips_pdf, _TOC_ROWS
    # Only the contents pages are under test here, so skip drawing each slip.
    monkeypatch.setattr(mp, '_draw_competence_slip', lambda *a, **k: None)
    n = _TOC_ROWS + 5
    slips = [{'student': SimpleNamespace(id=i, full_name=f'Student {i:03d}', surname=f'S{i:03d}', first_name='A',
                                         student_id=f'X{i}', gender='Male', photo=None, middle_name=''),
              'summary': {'results': []}, 'klass': 'SSS3 Gold'} for i in range(n)]
    exam = SimpleNamespace(display_name='Mock 1', name='M1', exam_number=1, exam_date=None, session=None,
                           session_id=None, id=0, branch_id=None)
    with app.test_request_context('/'):
        buf = result_slips_pdf(slips, exam, {'name': 'Test School'}, opts={}, theme='classic')
    with fitz.open(stream=buf.getvalue(), filetype='pdf') as d:
        assert len(d) == 2 + n
        assert len(d[0].get_links()) == _TOC_ROWS and len(d[1].get_links()) == 5
        assert max(l['page'] for l in d[1].get_links()) == 2 + n - 1     # last student, last page
        assert 'Page 2 of 2' in d[1].get_text()
