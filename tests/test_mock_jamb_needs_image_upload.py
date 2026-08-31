"""Needs-images queue: uploading a figure to a flagged bank question must work
(regression — the allowed-extension set was un-dotted, so ext_ok rejected every
file since file_ext returns the extension WITH its dot)."""
import io
import re

from config import Config
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _csrf(c):
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get('/students').get_data(as_text=True)).group(1)


def _jpg():
    from PIL import Image
    buf = io.BytesIO(); Image.new('RGB', (80, 60), (30, 120, 90)).save(buf, 'JPEG'); buf.seek(0)
    return buf


def _flagged_q(app, name):
    from models import db, Subject, MockJAMBQuestion
    with app.app_context():
        s = Subject(name=name, is_active=True); db.session.add(s); db.session.flush()
        q = MockJAMBQuestion(mock_exam_id=None, subject_id=s.id, question_text='needs a figure',
                             option_a='a', option_b='b', option_c='c', option_d='d',
                             correct_option='A', marks=1, source='ms', needs_image=True)
        db.session.add(q); db.session.commit()
        return q.id


def test_upload_jpg_clears_needs_image(app):
    qid = _flagged_q(app, 'NIUpJpg')
    c = _admin(app)
    r = c.post(f'/mock-jamb/bank/question/{qid}/set-image',
               data={'_csrf_token': _csrf(c), 'image': (_jpg(), 'diagram.jpg')},
               content_type='multipart/form-data', follow_redirects=True)
    assert 'Image added' in r.get_data(as_text=True)
    from models import db, MockJAMBQuestion
    with app.app_context():
        q = db.session.get(MockJAMBQuestion, qid)
        assert q.image_url and q.needs_image is False


def test_upload_accepts_uppercase_extension(app):
    qid = _flagged_q(app, 'NIUpUpper')
    c = _admin(app)
    r = c.post(f'/mock-jamb/bank/question/{qid}/set-image',
               data={'_csrf_token': _csrf(c), 'image': (_jpg(), 'PHOTO.JPG')},
               content_type='multipart/form-data', follow_redirects=True)
    assert 'Image added' in r.get_data(as_text=True)
    from models import db, MockJAMBQuestion
    with app.app_context():
        assert db.session.get(MockJAMBQuestion, qid).image_url


def test_upload_rejects_non_image(app):
    qid = _flagged_q(app, 'NIUpBad')
    c = _admin(app)
    bad = io.BytesIO(b'not an image');
    r = c.post(f'/mock-jamb/bank/question/{qid}/set-image',
               data={'_csrf_token': _csrf(c), 'image': (bad, 'notes.txt')},
               content_type='multipart/form-data', follow_redirects=True)
    assert 'Choose an image file' in r.get_data(as_text=True)
    from models import db, MockJAMBQuestion
    with app.app_context():
        assert db.session.get(MockJAMBQuestion, qid).needs_image is True   # still flagged


def _make_flagged(app, name, n):
    from models import db, Subject, MockJAMBQuestion
    with app.app_context():
        s = Subject(name=name, is_active=True); db.session.add(s); db.session.flush()
        ids = []
        for i in range(n):
            q = MockJAMBQuestion(mock_exam_id=None, subject_id=s.id, needs_image=True,
                                 question_text=f'q{i}', option_a='a', option_b='b',
                                 option_c='c', option_d='d', correct_option='A', marks=1, source='ms')
            db.session.add(q); db.session.flush(); ids.append(q.id)
        db.session.commit()
        return s.id, ids


def _flagged_count(app, ids):
    from models import MockJAMBQuestion
    with app.app_context():
        return MockJAMBQuestion.query.filter(
            MockJAMBQuestion.needs_image.is_(True), MockJAMBQuestion.id.in_(ids)).count()


def test_bulk_dismiss_selected(app):
    sid, ids = _make_flagged(app, 'NIBulkDismiss', 4)
    c = _admin(app)
    c.post('/mock-jamb/bank/needs-images/bulk',
           data={'_csrf_token': _csrf(c), 'action': 'dismiss',
                 'question_ids': f'{ids[0]},{ids[1]}'}, follow_redirects=True)
    assert _flagged_count(app, ids) == 2                 # only the 2 selected cleared


def test_bulk_dismiss_all_filtered(app):
    sid, ids = _make_flagged(app, 'NIBulkAll', 3)
    c = _admin(app)
    c.post('/mock-jamb/bank/needs-images/bulk',
           data={'_csrf_token': _csrf(c), 'action': 'dismiss_all', 'subject_id': sid},
           follow_redirects=True)
    assert _flagged_count(app, ids) == 0


def test_bulk_delete_selected(app):
    from models import db, MockJAMBQuestion
    sid, ids = _make_flagged(app, 'NIBulkDel', 3)
    c = _admin(app)
    c.post('/mock-jamb/bank/needs-images/bulk',
           data={'_csrf_token': _csrf(c), 'action': 'delete',
                 'question_ids': f'{ids[0]},{ids[1]}'}, follow_redirects=True)
    with app.app_context():
        assert db.session.get(MockJAMBQuestion, ids[0]) is None
        assert db.session.get(MockJAMBQuestion, ids[2]) is not None   # unselected kept
