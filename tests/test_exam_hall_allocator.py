"""The exam hall allocator spreads each class+arm across as many halls as
possible, fills halls in proportion to capacity, and balances gender."""
import pytest
from utils.exam_hall_allocator import allocate_halls


def _group(key, n, fem_ratio=0.5):
    studs = []
    for i in range(n):
        g = 'Female' if i < int(n * fem_ratio) else 'Male'
        studs.append({'id': f'{key}-{i}', 'name': f'{key} Student {i}',
                      'gender': g, 'student_id': f'{key}{i:03d}'})
    return {'key': key, 'students': studs}


def test_capacity_respected_and_everyone_placed():
    groups = [_group('SSS1 Rose', 40), _group('SSS1 Lily', 40), _group('SSS2 Iris', 30)]
    halls = [{'name': 'Main Hall', 'capacity': 120, 'is_main': True},
             {'name': 'Hall B', 'capacity': 40},
             {'name': 'Hall C', 'capacity': 40}]
    res = allocate_halls(groups, halls)
    assert res['total_students'] == 110
    placed = sum(h['count'] for h in res['halls'])
    assert placed == 110
    for h in res['halls']:
        assert h['count'] <= h['capacity']


def test_main_hall_gets_proportionally_more():
    groups = [_group('SSS3 A', 60), _group('SSS3 B', 60)]
    halls = [{'name': 'Main', 'capacity': 90, 'is_main': True},
             {'name': 'B', 'capacity': 30},
             {'name': 'C', 'capacity': 30}]
    res = allocate_halls(groups, halls)
    counts = {h['name']: h['count'] for h in res['halls']}
    # Main (3x capacity) should hold clearly more than each small hall.
    assert counts['Main'] > counts['B']
    assert counts['Main'] > counts['C']
    # Roughly proportional: ~half in Main (90/150 of 120 = 72).
    assert 66 <= counts['Main'] <= 78


def test_each_group_spread_across_all_halls():
    groups = [_group('SSS1 Rose', 30), _group('SSS1 Lily', 30)]
    halls = [{'name': 'H1', 'capacity': 40}, {'name': 'H2', 'capacity': 40},
             {'name': 'H3', 'capacity': 40}]
    res = allocate_halls(groups, halls)
    for g in res['groups']:
        # Every group appears in all 3 halls, thinly (no hall hoards a group).
        assert g['halls_used'] == 3
        assert g['max_in_hall'] <= 11        # ~10 per hall for 30 across 3


def test_gender_balanced_per_hall():
    groups = [_group('SSS1 Rose', 60, fem_ratio=0.5)]
    halls = [{'name': 'H1', 'capacity': 30}, {'name': 'H2', 'capacity': 30}]
    res = allocate_halls(groups, halls, balance_gender=True)
    for h in res['halls']:
        # 50/50 overall → each hall should be close to balanced.
        assert abs(h['gender']['Female'] - h['gender']['Male']) <= 2


def test_insufficient_capacity_raises():
    groups = [_group('A', 100)]
    halls = [{'name': 'Small', 'capacity': 40}]
    with pytest.raises(ValueError):
        allocate_halls(groups, halls)


def test_no_students_raises():
    with pytest.raises(ValueError):
        allocate_halls([], [{'name': 'H', 'capacity': 10}])


def test_deterministic():
    groups = [_group('A', 33), _group('B', 27), _group('C', 41)]
    halls = [{'name': 'M', 'capacity': 80, 'is_main': True},
             {'name': 'B', 'capacity': 30}, {'name': 'C', 'capacity': 30}]
    a = allocate_halls(groups, halls)
    b = allocate_halls(groups, halls)
    assert [h['count'] for h in a['halls']] == [h['count'] for h in b['halls']]
