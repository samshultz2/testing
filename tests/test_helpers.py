"""Pure-logic helper tests (no DB)."""
from utils.helpers import STREAM_WAEC_SUBJECTS, WAEC_DEFAULT_SUBJECTS
from utils.waec_ocr import vision_available


def test_stream_waec_defaults_have_core_subjects():
    for stream, subjects in STREAM_WAEC_SUBJECTS.items():
        assert 'Mathematics' in subjects
        assert 'English Language' in subjects
        assert 'Civic Education' in subjects
        assert 'Livestock Farming' in subjects


def test_science_includes_sciences():
    sci = STREAM_WAEC_SUBJECTS['Science']
    assert {'Physics', 'Chemistry', 'Biology'} <= set(sci)


def test_waec_default_subjects():
    assert WAEC_DEFAULT_SUBJECTS == ['Mathematics', 'English Language', 'Livestock Farming', 'Civic Education']


def test_vision_off_without_config():
    # No ANTHROPIC_API_KEY / flag in the test env.
    assert vision_available() is False
