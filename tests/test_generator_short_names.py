"""The generator exports/printouts use the user's own subject short name (from
/generator/subjects) rather than a built-in abbreviation."""
from routes.generator.exports import _short


class _Subj:
    def __init__(self, name, short_name=None):
        self.name = name; self.short_name = short_name


FALLBACK = {'Mathematics': 'Maths'}


def test_prefers_user_short_name():
    assert _short(_Subj('Mathematics', 'MTH'), FALLBACK, 5) == 'MTH'      # user's own wins
    assert _short(_Subj('Mathematics', '  '), FALLBACK, 5) == 'Maths'     # blank -> fallback map
    assert _short(_Subj('Mathematics', None), FALLBACK, 5) == 'Maths'
    assert _short(_Subj('Astronomy', None), FALLBACK, 4) == 'Astr'        # else truncate
    assert _short(None, FALLBACK, 5) == ''
