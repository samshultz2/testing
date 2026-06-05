"""Admission advisor logic, using lightweight fake student objects."""
from collections import namedtuple

from utils.admission import assess_admission

Waec = namedtuple('Waec', ['exam_year', 'subject', 'grade'])
Jamb = namedtuple('Jamb', ['total_score'])


class _Q:
    def __init__(self, items):
        self._items = items

    def all(self):
        return list(self._items)


class FakeStudent:
    def __init__(self, waec, jamb):
        self.waec_results = _Q(waec)
        self.jamb_results = _Q(jamb)


def science_credits(year=2024):
    subs = ['English Language', 'Mathematics', 'Biology', 'Chemistry', 'Physics', 'Economics']
    return [Waec(year, s, 'B2') for s in subs]


def test_meets_ssc_baseline():
    student = FakeStudent(science_credits(), [Jamb(240)])
    a = assess_admission(student)
    assert a['meets_ssc'] is True
    assert a['has_english'] and a['has_maths']
    assert a['jamb_best'] == 240


def test_engineering_eligible_with_good_jamb():
    student = FakeStudent(science_credits(), [Jamb(220)])
    a = assess_admission(student)
    eng = next(c for c in a['categories'] if c['name'].startswith('Engineering'))
    assert eng['eligible'] is True


def test_medicine_needs_250():
    student = FakeStudent(science_credits(), [Jamb(247)])
    a = assess_admission(student)
    med = next(c for c in a['categories'] if c['name'].startswith('Medicine'))
    assert med['eligible'] is False
    assert med['jamb_ok'] is False


def test_missing_maths_blocks_baseline():
    subs = ['English Language', 'Biology', 'Chemistry', 'Physics', 'Economics']
    student = FakeStudent([Waec(2024, s, 'B2') for s in subs], [Jamb(260)])
    a = assess_admission(student)
    assert a['has_maths'] is False
    assert a['meets_ssc'] is False
    assert a['eligible_count'] == 0


def test_no_jamb_score():
    student = FakeStudent(science_credits(), [])
    a = assess_admission(student)
    assert a['jamb_best'] == 0
    assert a['jamb_band'] == 'No JAMB score yet'
