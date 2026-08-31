"""Stage 3: role preset definitions."""
from utils.role_presets import ROLE_PRESETS, presets_for_form
from utils.access_control import MODULES


def test_presets_cover_the_hierarchy():
    expected = {'director_of_studies', 'exams_standards', 'it_department',
                'principal', 'headmaster', 'hod_arts', 'hod_sciences',
                'headteacher', 'teacher', 'bursar'}
    assert expected <= set(ROLE_PRESETS)


def test_presets_are_well_formed():
    for key, p in ROLE_PRESETS.items():
        assert p['scope'] in ('central', 'branch')
        assert p['role'] in ('admin', 'staff', 'teacher', 'readonly')
        for m in p['modules']:
            assert m in MODULES, f'{key} references unknown module {m}'


def test_central_vs_branch_presets():
    assert ROLE_PRESETS['director_of_studies']['scope'] == 'central'
    assert ROLE_PRESETS['exams_standards']['scope'] == 'central'
    assert ROLE_PRESETS['bursar']['scope'] == 'branch'
    assert 'finance' in ROLE_PRESETS['bursar']['modules']


def test_presets_for_form_shape():
    form = presets_for_form()
    assert 'bursar' in form
    assert set(form['bursar']) >= {'role', 'scope', 'modules', 'label'}
