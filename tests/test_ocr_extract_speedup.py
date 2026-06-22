"""extract_text must still read a large photographed-size image after the
downscale/thumbnail-OSD/LSTM speedups."""
import io
import glob
import time
import pytest

pytest.importorskip("pytesseract")
from PIL import Image, ImageDraw, ImageFont
from utils import waec_ocr


def _font(size):
    for path in (glob.glob('/usr/share/fonts/**/DejaVuSans.ttf', recursive=True) or
                 glob.glob('/usr/share/fonts/**/*.ttf', recursive=True)):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _sheet_image(width=3400, height=2600):
    """A large (phone-photo-sized) synthetic score sheet with real-sized text."""
    img = Image.new('RGB', (width, height), 'white')
    d = ImageDraw.Draw(img)
    font = _font(110)
    y = 150
    for line in ['ADE TOLA 85', 'BELLO MUSA 72', 'CHIDI OKE 64']:
        d.text((160, y), line, fill='black', font=font)
        y += 320
    buf = io.BytesIO(); img.save(buf, format='PNG'); return buf.getvalue()


def test_large_image_is_read_and_downscaled():
    if not waec_ocr.tesseract_available():
        pytest.skip("tesseract not installed")
    img_bytes = _sheet_image()
    t0 = time.time()
    text = waec_ocr.extract_text(img_bytes)
    elapsed = time.time() - t0
    up = text.upper()
    # The names survive OCR despite the aggressive downscale.
    assert 'ADE' in up and 'BELLO' in up and 'CHIDI' in up
    # Sanity bound: a single large image shouldn't approach the 25s timeout.
    assert elapsed < 20
