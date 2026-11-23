"""Needs-images queue: every bank question whose wording points at a picture it
doesn't have is listed (not only ones flagged on import), held out of exams,
and stays cleared once an admin rules it a false alarm."""
import re
import uuid

from config import Config
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _csrf(c):
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get('/students').get_data(as_text=True)).group(1)


def _q(subject_id, text, **kw):
    from models import MockJAMBQuestion
    return MockJAMBQuestion(mock_exam_id=None, subject_id=subject_id, question_text=text,
                            option_a='a', option_b='b', option_c='c', option_d='d',
                            correct_option='A', marks=1, **kw)


def test_mentions_figure_words_and_false_alarms():
    from utils.mock_figures import mentions_figure as m
    for t in ('Use the diagram above', 'In Fig. 2, find x', 'From the graph shown, find the slope',
              'The circuit shown below', 'Study the map below', 'the figure shown is a rhombus',
              'Name the part labelled X'):
        assert m(t), t
    for t in ('Identify the figure of speech', 'Correct to 3 significant figures', 'Graphite is',
              'Read paragraph 2', 'What is 2 + 2?', None, ''):
        assert not m(t), t
    assert m('Choose one', 'see the diagram')                 # options count too


def test_queue_lists_unflagged_figure_questions_and_sync_round_trip(app):
    from models import db, Subject, MockJAMBQuestion, MockJAMBPassage
    from utils import mock_figures
    with app.app_context():
        s = Subject(name='Fig ' + uuid.uuid4().hex[:6], is_active=True)
        db.session.add(s); db.session.flush()
        worded = _q(s.id, 'In the diagram above, find angle PQR.')
        plain = _q(s.id, 'Solve 2x + 3 = 11.')
        has_img = _q(s.id, 'Use the graph below.', image_url='/static/img/logo-mark.svg')
        gone = _q(s.id, 'Name the parts.', image_url='/static/uploads/mock_jamb/gone-%s.png' % uuid.uuid4().hex)
        p = MockJAMBPassage(subject_id=s.id, body='Study the figure below.', image_url='/static/favicon.ico')
        db.session.add(p); db.session.flush()
        via_passage = _q(s.id, 'What does the passage show?', passage_id=p.id)
        flagged = _q(s.id, 'Name this organ.', needs_image=True, source='myschool')
        db.session.add_all([worded, plain, has_img, gone, via_passage, flagged]); db.session.commit()
        ids = dict(worded=worded.id, plain=plain.id, has_img=has_img.id, passage=via_passage.id,
                   flagged=flagged.id, gone=gone.id, subject=s.id)
        mock_figures.sync(force=True)
        get = lambda k: db.session.get(MockJAMBQuestion, ids[k])
        db.session.expire_all()
        assert get('worded').needs_image is True
        assert not get('plain').needs_image and not get('has_img').needs_image
        assert not get('passage').needs_image                       # passage carries the picture
        assert get('flagged').needs_image is True
        assert get('gone').needs_image is True                      # its file is missing
        assert mock_figures.reason(get('gone')) == 'Picture file is missing'
        assert mock_figures.reason(get('worded')).startswith('Mentions')
        assert mock_figures.reason(get('flagged')) == 'Flagged on import'

    c = _admin(app)
    html = c.get('/mock-jamb/bank/needs-images?subject_id=%d' % ids['subject']).get_data(as_text=True)
    assert 'find angle PQR' in html and 'Name this organ' in html
    assert 'Solve 2x + 3 = 11' not in html and 'What does the passage show' not in html
    assert 'Questions needing images' in html

    # "No image needed" sticks: the wording still matches, but it never re-enters the queue.
    r = c.post('/mock-jamb/bank/question/%d/set-image' % ids['worded'],
               data={'_csrf_token': _csrf(c), 'dismiss': '1'}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        mock_figures.sync(force=True)
        q = db.session.get(MockJAMBQuestion, ids['worded'])
        assert q.needs_image is False and q.image_not_needed is True
    html = c.get('/mock-jamb/bank/needs-images?subject_id=%d' % ids['subject']).get_data(as_text=True)
    assert 'find angle PQR' not in html


def test_bulk_dismiss_marks_not_needed(app):
    from models import db, Subject, MockJAMBQuestion
    with app.app_context():
        s = Subject(name='FigB ' + uuid.uuid4().hex[:6], is_active=True)
        db.session.add(s); db.session.flush()
        a, b = _q(s.id, 'Sketch the graph of y = x.'), _q(s.id, 'Fig. 3 shows a lever.')
        db.session.add_all([a, b]); db.session.commit()
        ids = [a.id, b.id]
    c = _admin(app)
    c.get('/mock-jamb/bank/needs-images')                          # sync flags them
    c.post('/mock-jamb/bank/needs-images/bulk',
           data={'_csrf_token': _csrf(c), 'action': 'dismiss', 'question_ids': ','.join(map(str, ids))})
    with app.app_context():
        from utils import mock_figures
        mock_figures.sync(force=True)
        for qid in ids:
            q = db.session.get(MockJAMBQuestion, qid)
            assert q.needs_image is False and q.image_not_needed is True


def test_fix_degrees():
    from utils.mock_figures import fix_degrees
    assert fix_degrees('185 o') == '185°' and fix_degrees('22.5o') == '22.5°'
    assert fix_degrees('zero') == 'zero' and fix_degrees('2 or 3') == '2 or 3' and fix_degrees(None) is None


def test_import_copies_outside_pictures_and_repair(app, monkeypatch):
    """A pasted link to another site's picture is saved on this server; one that
    can't be downloaded sends the question to the needs-images list. The repair
    button does the same for links already in the bank, and fixes '185 o'."""
    from models import db, Subject, MockJAMBQuestion
    from utils import mock_figures
    monkeypatch.setattr(mock_figures, 'save_copy',
                        lambda url: None if 'bad' in url else '/static/img/logo-mark.svg')
    with app.app_context():
        s = Subject(name='FigImp ' + uuid.uuid4().hex[:6], is_active=True)
        db.session.add(s); db.session.commit()
        sid = s.id
    c = _admin(app)
    rows = ('Q good? | 185 o | 200 o | b | c | A | | | | 2020 | https://myschool.ng/storage/good.png\n'
            'Q bad? | a | b | c | d | A | | | | 2020 | https://myschool.ng/storage/bad.png')
    c.post('/mock-jamb/bank/import', data={'_csrf_token': _csrf(c), 'subject_id': sid, 'rows': rows})
    with app.app_context():
        good = MockJAMBQuestion.query.filter_by(subject_id=sid, question_text='Q good?').one()
        bad = MockJAMBQuestion.query.filter_by(subject_id=sid, question_text='Q bad?').one()
        assert good.image_url == '/static/img/logo-mark.svg' and good.option_a == '185°'
        assert bad.image_url is None and bad.needs_image is True
        old = MockJAMBQuestion(mock_exam_id=None, subject_id=sid, question_text='Old link',
                               option_a='90 o', option_b='b', option_c='c', option_d='d', correct_option='A',
                               marks=1, image_url='https://myschool.ng/storage/old.png')
        db.session.add(old); db.session.commit()
        oid = old.id
    r = c.post('/mock-jamb/bank/images/repair', data={'_csrf_token': _csrf(c)}, follow_redirects=True)
    assert 'saved' in r.get_data(as_text=True)
    with app.app_context():
        o = db.session.get(MockJAMBQuestion, oid)
        assert o.image_url == '/static/img/logo-mark.svg' and o.option_a == '90°'


def test_myschool_source_links(app):
    """Questions from myschool link back to their page; pasted ones keep the
    link from the 12th column; anything else gets a myschool.ng search."""
    from models import db, Subject, MockJAMBQuestion
    from utils.mock_figures import source_link
    with app.app_context():
        s = Subject(name='Mathematics' if not Subject.query.filter_by(name='Mathematics').first()
                    else 'Maths ' + uuid.uuid4().hex[:4], is_active=True)
        db.session.add(s); db.session.flush()
        harvested = _q(s.id, 'In the diagram, find x.', source='myschool', source_ref='4321',
                       exam_body='JAMB', exam_year='2015')
        pasted = _q(s.id, 'In the figure, AB is parallel to CD then x + y + z is', source='paste')
        db.session.add_all([harvested, pasted]); db.session.commit()
        url, exact = source_link(harvested)
        assert exact and '/classroom/' in url and url.split('?')[0].endswith('/4321')
        assert 'exam_type=jamb' in url and 'exam_year=2015' in url
        url, exact = source_link(pasted)
        assert not exact and url.startswith('https://www.google.com/search?q=') and 'myschool.ng' in url
        sid = s.id
    c = _admin(app)
    row = ('Q with link? | a | b | c | d | A | | | | 2016 | | '
           'https://myschool.ng/classroom/mathematics/98765?exam_type=jamb&exam_year=2016')
    c.post('/mock-jamb/bank/import', data={'_csrf_token': _csrf(c), 'subject_id': sid, 'rows': row})
    with app.app_context():
        q = MockJAMBQuestion.query.filter_by(subject_id=sid, question_text='Q with link?').one()
        assert q.source == 'myschool' and q.source_ref == '98765'
        assert source_link(q)[0].split('?')[0].endswith('/98765')
    html = c.get('/mock-jamb/bank/needs-images?subject_id=%d' % sid).get_data(as_text=True)
    assert 'Open on myschool.ng' in html and 'Find on myschool.ng' in html
