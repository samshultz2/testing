"""The total→components breakdown: integer components within their maxes that
sum exactly to the student's subject total."""
from utils.score_breakdown import distribute_total


def test_sums_exactly_and_respects_maxes():
    maxes = [5, 5, 5, 5, 30, 10, 40]      # CA1 CA2 CA3 HA CBT MID EXAM (with MID)
    for total in range(0, sum(maxes) + 1):
        out = distribute_total(total, maxes)
        assert len(out) == len(maxes)
        assert sum(out) == total
        assert all(0 <= v <= m for v, m in zip(out, maxes))


def test_example_82_spreads_not_exam_only():
    maxes = [5, 5, 5, 5, 30, 10, 40]
    out = distribute_total(82, maxes)
    assert sum(out) == 82
    # A proportional split fills the CAs too, not just the exam.
    assert out[0] > 0 and out[4] > 0 and out[-1] > 0


def test_without_mid_theory_50():
    maxes = [5, 5, 5, 5, 30, 50]          # no MID; theory worth 50
    out = distribute_total(73, maxes)
    assert sum(out) == 73
    assert all(0 <= v <= m for v, m in zip(out, maxes))


def test_full_and_zero_and_overflow():
    maxes = [5, 5, 5, 5, 30, 10, 40]
    assert distribute_total(100, maxes) == maxes          # exactly full
    assert distribute_total(0, maxes) == [0] * len(maxes)  # empty
    assert sum(distribute_total(250, maxes)) == 100        # capped at ceiling
    assert distribute_total(None, maxes) == [0] * len(maxes)


def test_empty_components():
    assert distribute_total(50, []) == []
