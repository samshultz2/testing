"""Pure allocation algorithm for Study Groups (utils/study_groups.allocate_groups)
-- no Flask/DB involved, so every invariant is checked directly."""
from math import ceil

from utils.study_groups import allocate_groups


def _all_members(groups):
    out = []
    for g in groups:
        out.extend(g['members'])
    return out


def test_group_count_is_ceil_total_over_size():
    students = [(i, 100 - i) for i in range(23)]
    groups = allocate_groups(students, 5)
    assert len(groups) == ceil(23 / 5) == 5


def test_every_student_placed_exactly_once():
    students = [(i, float(i)) for i in range(37)]
    groups = allocate_groups(students, 6)
    members = _all_members(groups)
    assert sorted(members) == sorted(sid for sid, _ in students)
    assert len(members) == len(set(members))


def test_group_sizes_differ_by_at_most_one():
    students = [(i, float(i)) for i in range(22)]  # 22/5 -> 5 groups, sizes 5,5,4,4,4
    groups = allocate_groups(students, 5)
    sizes = [len(g['members']) for g in groups]
    assert max(sizes) - min(sizes) <= 1
    assert sum(sizes) == 22


def test_leaders_are_the_top_n_performers_by_average():
    # Averages 0..29, strictly increasing with id -- top 6 are ids 24..29.
    students = [(i, float(i)) for i in range(30)]
    groups = allocate_groups(students, 5)   # 30/5 -> 6 groups
    assert len(groups) == 6
    leaders = {g['leader_id'] for g in groups}
    assert leaders == {24, 25, 26, 27, 28, 29}
    # Each leader is the first (and highest-ranked) member of their own group.
    for g in groups:
        assert g['members'][0] == g['leader_id']


def test_new_students_with_no_prior_average_are_never_leaders_when_enough_ranked_exist():
    ranked = [(i, float(100 - i)) for i in range(10)]     # ids 0..9, decreasing basis
    unranked = [(100 + i, None) for i in range(10)]        # 10 brand-new students
    groups = allocate_groups(ranked + unranked, 5)          # 20 students / 5 -> 4 groups
    assert len(groups) == 4
    for g in groups:
        assert g['leader_id'] in {sid for sid, avg in ranked}


def test_all_random_when_nobody_has_prior_data():
    students = [(i, None) for i in range(12)]
    groups = allocate_groups(students, 4)
    assert len(groups) == 3
    # Every group still ends up with SOME leader (promoted from its own
    # random members), even with zero ranked students.
    assert all(g['leader_id'] is not None for g in groups)
    assert sorted(_all_members(groups)) == list(range(12))


def test_fewer_ranked_students_than_groups_still_fills_every_leader_slot():
    ranked = [(0, 90.0), (1, 80.0)]            # only 2 ranked students
    unranked = [(10 + i, None) for i in range(10)]
    groups = allocate_groups(ranked + unranked, 4)   # 12 students / 4 -> 3 groups
    assert len(groups) == 3
    assert all(g['leader_id'] is not None for g in groups)
    # The two genuinely-ranked students must each lead a group.
    leaders = {g['leader_id'] for g in groups}
    assert {0, 1} <= leaders


def test_group_size_larger_than_class_gives_one_group():
    students = [(i, float(i)) for i in range(5)]
    groups = allocate_groups(students, 50)
    assert len(groups) == 1
    assert sorted(groups[0]['members']) == [0, 1, 2, 3, 4]
    assert groups[0]['leader_id'] == 4   # highest average


def test_empty_input_returns_no_groups():
    assert allocate_groups([], 5) == []


def test_zero_or_negative_group_size_returns_no_groups():
    assert allocate_groups([(1, 50.0)], 0) == []
    assert allocate_groups([(1, 50.0)], -3) == []


def test_exact_multiple_gives_perfectly_even_groups():
    students = [(i, float(i)) for i in range(20)]
    groups = allocate_groups(students, 5)
    assert len(groups) == 4
    assert all(len(g['members']) == 5 for g in groups)
