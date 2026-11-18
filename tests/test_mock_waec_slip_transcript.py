"""Mock WAEC result slip: the Transcript theme (fourth), which shows each
subject's result in the previous mock next to this one."""
from tests.test_mock_waec_slip_modern import _setup, _text
from tests.test_mock_waec_broadsheet_extras import _admin


def test_transcript_shows_previous_mock_per_subject(app):
    (m1, m2), sid = _setup(app)
    c = _admin(app)
    pages, t = _text(c, f'/mock-waec/exam/{m2}/student/{sid}/slip.pdf?theme=transcript')
    assert pages == 1
    for frag in ('STATEMENTOFRESULT', 'SecondCompetence', 'Okonkwo', 'FIRST', 'SECOND', 'CHANGE',
                 'C5·55', 'E8·40',                   # English / Maths in the first mock
                 '+11', '+18', 'missed', 'Absent', 'GRADING',
                 'Subjectssat', '3of4', '5creditsincl.Eng&MathsNo', 'MissingcoreNone', 'STAMP', 'Issued'):
        assert frag in t, frag


def test_transcript_without_a_previous_mock_drops_the_progress_parts(app):
    (m1, m2), sid = _setup(app)
    _, t = _text(_admin(app), f'/mock-waec/exam/{m1}/student/{sid}/slip.pdf?theme=transcript')
    assert 'FirstCompetence' in t and 'CHANGE' not in t and 'credits' not in t.split('STUDENT')[0]


def test_every_transcript_block_can_be_switched_off(app):
    (m1, m2), sid = _setup(app)
    off = ('t_label', 't_exam', 't_date', 't_progress', 't_class', 't_stream', 't_gender', 't_first',
           't_change', 'remark', 't_core', 'grades', 't_subjects', 't_credits', 't_distinctions',
           't_average', 't_five', 't_missing', 't_stamp', 't_footer', 'printed_on')
    q = '&'.join(f'{k}=0' for k in off)
    _, t = _text(_admin(app), f'/mock-waec/exam/{m2}/student/{sid}/slip.pdf?theme=transcript&{q}&signers=none')
    for frag in ('STATEMENTOFRESULT', 'SecondCompetence', 'Written', 'CLASS', 'FIRST', 'CHANGE', 'REMARK',
                 'GRADING', 'Subjectssat', 'Average', 'Missingcore', 'STAMP', 'notanofficial', 'Issued',
                 'Principal'):
        assert frag not in t, frag
    assert 'Okonkwo' in t and 'Physics' in t and t.count('CORE') == 1


def test_transcript_listed_on_the_export_screen(app):
    (m1, m2), sid = _setup(app)
    html = _admin(app).get(f'/mock-waec/exam/{m2}/student/{sid}/slip').get_data(as_text=True)
    assert 'data-v="transcript"' in html and 'data-param="t_first"' in html
    pages, t = _text(_admin(app), f'/mock-waec/exam/{m2}/slips.pdf?theme=transcript&bw=1')
    assert pages >= 1
