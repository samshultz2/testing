"""JAMB raw-correct -> score-over-100 conversion."""
from utils.jamb_config import convert_correct_to_100, question_count_for


def test_english_is_60_questions():
    assert question_count_for('English Language') == 60


def test_other_subjects_are_40_questions():
    assert question_count_for('Mathematics') == 40
    assert question_count_for('Physics') == 40


def test_maths_30_of_40_is_75():
    assert convert_correct_to_100('Mathematics', 30) == 75


def test_english_48_of_60_is_80():
    assert convert_correct_to_100('English Language', 48) == 80


def test_blank_returns_none():
    assert convert_correct_to_100('Mathematics', None) is None
    assert convert_correct_to_100('Mathematics', '') is None


def test_caps_at_question_count():
    assert convert_correct_to_100('Mathematics', 50) == 100
