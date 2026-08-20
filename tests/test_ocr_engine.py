"""OCR engine selection: the setting resolves to a fallback-ordered list of the
engines actually available, and PaddleOCR degrades gracefully when absent."""


def test_paddle_absent_is_graceful():
    from utils.paddle_ocr import paddle_available, extract_scoresheet
    # Not installed in CI — must report False and never raise.
    assert paddle_available() in (True, False)
    if not paddle_available():
        assert extract_scoresheet(b'not-an-image', ['CA1', 'EXAM']) is None


def test_engine_order_filters_to_available(app):
    with app.app_context():
        from utils import ocr_engine
        avail = ocr_engine.availability()
        assert set(avail) == {'claude', 'tesseract', 'paddle'}
        order = ocr_engine.engine_order()
        # Only available engines are offered, and never more than the three.
        assert all(avail[e] for e in order)
        assert len(order) <= 3


def test_selected_engine_default_and_set(app):
    from models import db, SchoolSettings
    from utils.ocr_engine import selected_engine
    with app.app_context():
        assert selected_engine() == 'auto'          # default when unset
        SchoolSettings.set('ocr_engine', 'paddle', 'string')
        assert selected_engine() == 'paddle'
        SchoolSettings.query.filter_by(key='ocr_engine').delete()
        db.session.commit()


def test_status_rows_shape(app):
    with app.app_context():
        from utils.ocr_engine import status_rows
        rows = status_rows()
        assert [r['id'] for r in rows] == ['claude', 'tesseract', 'paddle']
        assert all('available' in r and 'label' in r for r in rows)
