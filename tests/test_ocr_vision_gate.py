"""The Claude-vision OCR path stays off (and free) unless explicitly enabled."""
from utils import waec_ocr


def test_vision_disabled_by_default(app, monkeypatch):
    # Flag off -> never available, even if a key were present.
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-test')
    monkeypatch.setattr('config.Config.OCR_VISION_FALLBACK', False)
    assert waec_ocr.vision_available() is False
    # And extract is a safe no-op (callers fall back to Tesseract).
    assert waec_ocr.vision_extract(b'\x89PNG...', 'waec') is None


def test_vision_needs_a_key_even_when_enabled(app, monkeypatch):
    monkeypatch.setattr('config.Config.OCR_VISION_FALLBACK', True)
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    assert waec_ocr.vision_available() is False


def test_default_vision_model_is_the_cheap_one():
    from config import Config
    assert Config.OCR_VISION_MODEL == 'claude-haiku-4-5'
