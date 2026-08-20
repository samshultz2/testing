"""The subject-combination explorer supports several AND-combined conditions,
each testing all-subject or combined-subject totals/averages, optionally on one
assessment component (e.g. Exam only) — used to pick students who qualify for a
stream (e.g. all-subject avg >= 50 AND exam avg >= 67 across Phy+Chem+Bio).
"""
from routes.subjects.reports import _combine_multi, _cond_value


def _row(name, total, average, subjects, components):
    return {'student': name, 'total': total, 'average': average,
            'subjects': subjects, 'components': components,
            'class_name': 'SSS2', 'arm_name': 'A'}


# Subjects: 1=Physics 2=Chemistry 3=Biology; assessment type 9 = Exam.
ROWS = [
    _row('Qualifies', 300, 60,
         {'1': 70, '2': 80, '3': 60},
         {'1': {'9': 68}, '2': {'9': 70}, '3': {'9': 66}}),        # exam avg 68
    _row('LowOverall', 120, 24,
         {'1': 40, '2': 45, '3': 35},
         {'1': {'9': 30}, '2': {'9': 32}, '3': {'9': 28}}),        # fails avg>=50
    _row('LowExam', 300, 60,
         {'1': 70, '2': 80, '3': 60},
         {'1': {'9': 40}, '2': {'9': 41}, '3': {'9': 39}}),        # exam avg 40 → fails >=67
]


def test_cond_value_all_vs_combo_component():
    r = ROWS[0]
    assert _cond_value(r, ['1', '2', '3'], 'all_average', '') == 60
    assert _cond_value(r, ['1', '2', '3'], 'combo_total', '') == 210
    # Exam-only combined average across the three subjects.
    assert _cond_value(r, ['1', '2', '3'], 'combo_average', '9') == round((68 + 70 + 66) / 3, 2)


def test_and_conditions_pick_qualifiers():
    conds = [
        {'basis': 'all_average', 'component': '', 'op': 'gte', 'value': 50},
        {'basis': 'combo_average', 'component': '9', 'op': 'gte', 'value': 67},
    ]
    rows, active, labels = _combine_multi(ROWS, ['1', '2', '3'], conds,
                                          at_names={'9': 'Exam'})
    names = {r['student'] for r in rows}
    assert active is True
    assert names == {'Qualifies'}                 # only the row meeting BOTH
    assert len(labels) == 2 and 'Exam' in labels[1]


def test_no_conditions_returns_all():
    rows, active, labels = _combine_multi(ROWS, ['1', '2', '3'], [])
    assert active is False and len(rows) == len(ROWS) and labels == []


def test_missing_subject_counts_as_zero():
    # A student missing Biology: combined average divides by 3 (missing = 0).
    r = _row('MissingBio', 150, 50, {'1': 80, '2': 70}, {'1': {'9': 60}, '2': {'9': 60}})
    # combo exam avg = (60+60+0)/3 = 40
    assert _cond_value(r, ['1', '2', '3'], 'combo_average', '9') == 40
