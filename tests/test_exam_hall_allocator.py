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
    # Same seed -> identical layout (so a re-run / the PDF reproduces the sheet).
    a = allocate_halls(groups, halls, seed=7)
    b = allocate_halls(groups, halls, seed=7)
    assert [[s['id'] for s in h['students']] for h in a['halls']] == \
           [[s['id'] for s in h['students']] for h in b['halls']]
    # Different seeds -> counts unchanged (capacity-driven) but a fresh mix.
    c = allocate_halls(groups, halls, seed=99)
    assert [h['count'] for h in a['halls']] == [h['count'] for h in c['halls']]


# ---- Seat layout within a hall -------------------------------------------------
from utils.exam_hall_allocator import seat_hall


def _seat_students(spec):
    """spec: {'SSS1 Rose': 10, ...} -> flat student list stamped with group key."""
    out = []
    for key, n in spec.items():
        for i in range(n):
            out.append({'id': f'{key}-{i}', 'name': f'{key} {i}', 'gender': 'Male',
                        '_group_key': key})
    return out


def _conflicts(res):
    return res['conflicts']


def test_seat_grid_shape_and_numbering():
    res = seat_hall(_seat_students({'A': 7, 'B': 6}), cols=5)
    assert res['cols'] == 5 and res['nrows'] == 3 and res['count'] == 13
    seats = [c['seat'] for row in res['rows'] for c in row if c]
    assert seats == list(range(1, 14))          # numbered 1..N, no gaps


def test_seating_avoids_same_group_neighbours():
    # Two equal groups on a wide-enough grid can be laid out with zero conflicts.
    res = seat_hall(_seat_students({'SSS1 Rose': 15, 'SSS1 Lily': 15}), cols=6)
    assert _conflicts(res) == 0


def test_seating_single_group_is_handled():
    res = seat_hall(_seat_students({'Solo': 12}), cols=4)
    # One group only — adjacency is unavoidable, but it must still seat everyone.
    assert res['count'] == 12
    seats = [c for row in res['rows'] for c in row if c]
    assert len(seats) == 12


def test_seating_beats_naive_block_layout():
    students = _seat_students({'A': 12, 'B': 12, 'C': 12})
    res = seat_hall(students, cols=6, optimize=True)
    # A naive "all A, then all B, then all C" block layout has many same-group
    # neighbours; the allocator should do far better.
    assert _conflicts(res) <= 4


def _cls_students(spec):
    """spec: {('SSS2','Rose'): 8, ('SSS1',''): 4} -> students carrying class_name/arm."""
    out = []
    for (cls, arm), n in spec.items():
        for i in range(n):
            out.append({'id': f'{cls}{arm}-{i}', 'name': f'{cls} {arm} {i}', 'gender': 'Male',
                        'class_name': cls, 'arm': arm})
    return out


def test_seating_separates_by_class_not_arm():
    # Same class, two different arms — they must still be kept apart (same papers).
    students = _cls_students({('SSS2', 'Rose'): 10, ('SSS2', 'Lily'): 10, ('SSS1', 'A'): 20})
    res = seat_hall(students, cols=6)
    # With 20 SSS1 to interleave 20 SSS2 across a 6-wide grid, no two SSS2 need
    # ever be adjacent — conflicts (same CLASS neighbours) should be zero.
    assert res['conflicts'] == 0


def test_sss1_sits_between_sss2():
    # The user's example: 2 SSS2 + 1 SSS1 in a single row -> SSS1 in the middle.
    students = _cls_students({('SSS2', 'A'): 2, ('SSS1', 'A'): 1})
    res = seat_hall(students, cols=3)
    row = [c['student']['class_name'] for c in res['rows'][0] if c]
    assert row == ['SSS2', 'SSS1', 'SSS2']
    assert res['conflicts'] == 0


def test_two_balanced_classes_alternate_without_solver():
    # The core promise: two balanced classes -> perfect alternation (SSS2 between
    # SSS1 and vice versa), guaranteed by the deterministic layout alone.
    students = _cls_students({('SSS1', 'A'): 30, ('SSS2', 'A'): 30})
    res = seat_hall(students, cols=6, optimize=False)   # deterministic, no CP-SAT
    assert res['conflicts'] == 0
