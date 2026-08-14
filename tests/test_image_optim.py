"""encode_to_target compresses large uploads under the byte budget while keeping
them valid images (and preserves transparency as PNG)."""
from io import BytesIO

from PIL import Image

from utils.uploads import encode_to_target


def _noise(w, h, mode='RGB'):
    # Random-ish content so the encoder can't trivially compress it away.
    import os
    return Image.frombytes(mode, (w, h), os.urandom(w * h * len(mode)))


def test_large_photo_fits_budget_and_decodes():
    im = _noise(2600, 2000)               # a big, hard-to-compress photo
    data, mime = encode_to_target(im, target_bytes=600 * 1024)
    assert mime == 'image/jpeg'
    assert len(data) <= 600 * 1024, len(data)
    out = Image.open(BytesIO(data)); out.load()
    assert max(out.size) <= 1600          # downscaled to the store dimension


def test_small_image_is_untouched_in_size():
    im = _noise(300, 200)
    data, _ = encode_to_target(im)
    assert len(data) <= 600 * 1024
    out = Image.open(BytesIO(data)); out.load()
    assert out.size == (300, 200)         # small image not upscaled/altered in dims


def test_transparency_preserved_as_png():
    im = Image.new('RGBA', (500, 500), (0, 0, 0, 0))
    data, mime = encode_to_target(im)
    assert mime == 'image/png'
    out = Image.open(BytesIO(data)); out.load()
    assert out.mode in ('RGBA', 'LA', 'P')
