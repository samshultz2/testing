"""Mock WAEC result slip: the Profile theme (third, beside Classic and Modern)."""
from tests.test_mock_waec_slip_modern import _setup, _text
from tests.test_mock_waec_broadsheet_extras import _admin


def test_profile_theme_draws_the_profile_card(app):
    (m1, m2), sid = _setup(app)
    c = _admin(app)
    pages, t = _text(c, f'/mock-waec/exam/{m2}/student/{sid}/slip.pdf?theme=profile')
    assert pages == 1
    for frag in ('RESULTSLIP', 'SECONDCOMPETENCE', 'Okonkwo', 'AVERAGE', 'Subjectssat', 'Credits',
                 'Distinctions', 'AveragevsFirst', '5creditsincl.English&Maths:No', 'Missingcore:None',
                 'ABS', 'Absent', 'GRADING', 'STAMP', 'Issued'):
        assert frag in t, frag
    # No photo uploaded: the initials stand in for it.
    assert 'OA' in t


def test_every_profile_block_can_be_switched_off(app):
    (m1, m2), sid = _setup(app)
    c = _admin(app)
    off = ('p_pill', 'p_session', 'p_photo', 'p_exam', 'p_class', 'p_stream', 'p_gender', 'p_ring',
           'p_subjects', 'p_credits', 'p_distinctions', 'p_avgtile', 'p_five', 'p_missing', 'p_core',
           'remark', 'grades', 'p_stamp', 'p_footer', 'printed_on')
    q = '&'.join(f'{k}=0' for k in off)
    _, t = _text(c, f'/mock-waec/exam/{m2}/student/{sid}/slip.pdf?theme=profile&{q}&signers=none')
    for frag in ('RESULTSLIP', 'session', 'SECONDCOMPETENCE', 'Class', 'AVERAGE', 'Subjectssat', 'Credits',
                 'Distinctions', '5credits', 'Missingcore', 'REMARK', 'GRADING', 'STAMP',
                 'notanofficial', 'Issued', 'Principal', 'OA'):
        assert frag not in t, frag
    assert 'Okonkwo' in t and 'Physics' in t
    assert t.count('CORE') == 1                      # only the SCORE header is left


def test_profile_whole_class_black_and_white(app):
    (m1, m2), sid = _setup(app, ('Oluwadamilare Chukwuemeka', 'Adebayo-Okonkwo-Ibrahim'))
    pages, t = _text(_admin(app), f'/mock-waec/exam/{m2}/slips.pdf?theme=profile&bw=1')
    assert pages >= 1 and 'Adebayo-Okonkwo-Ibrahim' in t


def test_export_screen_lists_profile(app):
    (m1, m2), sid = _setup(app)
    html = _admin(app).get(f'/mock-waec/exam/{m2}/student/{sid}/slip').get_data(as_text=True)
    assert 'data-v="profile"' in html and 'data-theme="profile"' in html and 'data-param="p_ring"' in html
