"""File-upload hardening tests (upload security audit).

- ext_ok: case-insensitive whitelist keyed off the FINAL extension only.
- open_image: decodes real images with a decompression-bomb cap; rejects non-images.
- CBT question image: SVG and spoofed non-images are refused; real images are
  re-encoded to a random .png (closes the stored-XSS / polyglot vector).
- generator-teachers import rejects a non-.csv upload.
"""
import io
import os

from werkzeug.datastructures import FileStorage

from tests.conftest import auth_csrf
from utils.uploads import ext_ok, open_image, IMAGE_EXTS, SCAN_EXTS, MAX_IMAGE_PIXELS


def _png_bytes(size=(4, 4)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', size, (200, 30, 30)).save(buf, 'PNG')
    buf.seek(0)
    return buf.getvalue()


def _fs(data, filename):
    return FileStorage(stream=io.BytesIO(data), filename=filename)


# --- ext_ok ----------------------------------------------------------------

def test_ext_ok_final_extension_only_and_case_insensitive():
    assert ext_ok('photo.PNG', IMAGE_EXTS)
    assert not ext_ok('x.svg', IMAGE_EXTS)                 # svg never allowed
    assert not ext_ok('evil.php.svg', IMAGE_EXTS)          # double ext judged by .svg
    assert not ext_ok('evil.png.php', IMAGE_EXTS)          # final ext is .php
    assert ext_ok('scan.PDF', SCAN_EXTS) and not ext_ok('scan.pdf', IMAGE_EXTS)
    assert not ext_ok('', IMAGE_EXTS) and not ext_ok(None, IMAGE_EXTS)


# --- open_image ------------------------------------------------------------

def test_open_image_decodes_real_image_and_sets_bomb_cap():
    from PIL import Image
    im = open_image(_fs(_png_bytes(), 'x.png'))
    assert im.size == (4, 4)
    assert Image.MAX_IMAGE_PIXELS == MAX_IMAGE_PIXELS       # cap applied


def test_open_image_rejects_non_image():
    import pytest
    with pytest.raises(Exception):
        open_image(_fs(b'this is not an image', 'x.png'))


# --- CBT question image (the stored-XSS fix) --------------------------------

def test_cbt_question_image_refuses_svg_and_nonimage(app):
    from routes.cbt import _save_question_image
    with app.test_request_context():           # _save_question_image calls url_for
        # SVG with a script payload — must be refused outright (nothing saved).
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        assert _save_question_image(_fs(svg, 'evil.svg')) is None
        # Spoofed: image extension but not an image -> Pillow decode fails -> refused.
        assert _save_question_image(_fs(b'nope', 'fake.png')) is None
        # Even an SVG renamed .png is refused (content, not just extension).
        assert _save_question_image(_fs(svg, 'evil.png')) is None


def test_cbt_question_image_reencodes_real_image_to_png(app):
    from PIL import Image
    from routes.cbt import _save_question_image
    with app.test_request_context():           # _save_question_image calls url_for
        url = _save_question_image(_fs(_png_bytes(), 'diagram.jpeg'))
        assert url and url.endswith('.png')                # always stored as .png
        fs_path = os.path.join(app.root_path, 'static', 'uploads', 'cbt',
                               os.path.basename(url))
        try:
            assert os.path.exists(fs_path)
            with Image.open(fs_path) as im:                 # stored bytes are a real image
                im.verify()
        finally:
            if os.path.exists(fs_path):
                os.remove(fs_path)


# --- generator-teachers import ---------------------------------------------

def test_teachers_import_rejects_non_csv(auth_client):
    r = auth_client.post('/generator/teachers/import',
                         data={'file': (io.BytesIO(b'x,y,z'), 'teachers.txt'),
                               '_csrf_token': auth_csrf(auth_client)},
                         content_type='multipart/form-data', follow_redirects=False)
    assert r.status_code in (302, 303)                     # bounced, no crash (not 500)
