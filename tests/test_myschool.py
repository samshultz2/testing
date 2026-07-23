"""myschool.ng scraper core: parsing (stem/options/answer/table/figure flags),
classification, the paste importer's image column, and the in-app harvest
(dedup by source_ref) — all offline via a synthetic fixture / monkeypatch."""
from config import Config
from tests.conftest import login_token


def _fixture(stem, correct='b', with_table=False):
    table = ('<table><tr><th>City</th><th>Pop</th></tr>'
             '<tr><td>Lagos</td><td>20</td></tr></table>') if with_table else ''
    return f"""
    <div class="card">
      <div class="qwrap"><h1>{stem}</h1>{table}</div>
      <div class="opts">
        <div><span class="uppercase">a</span><p>Lagos</p></div>
        <div><span class="uppercase">b</span><p>Abuja</p></div>
        <div><span class="uppercase">c</span><p>Kano</p></div>
        <div><span class="uppercase">d</span><p>Ibadan</p></div>
      </div>
      <div class="ans">Correct Option <span class="uppercase">{correct}</span></div>
    </div>"""


def test_parse_detail_basic():
    from utils import myschool as ms
    p = ms.parse_detail(_fixture("Which city is the capital of Nigeria?"))
    assert p and p['correct'] == 'B'
    assert p['options'] == ['Lagos', 'Abuja', 'Kano', 'Ibadan']
    assert not p['figure_dependent'] and not p['has_table']


def test_parse_detail_table_folded_into_stem():
    from utils import myschool as ms
    p = ms.parse_detail(_fixture("Study the population figures.", with_table=True))
    assert p['has_table'] and 'table' in p['flags']
    assert 'Lagos | 20' in p['stem']            # table serialized into the stem
    assert not p['figure_dependent']            # tables are kept, not skipped


def test_parse_detail_figure_dependent_flagged():
    from utils import myschool as ms
    p = ms.parse_detail(_fixture("In the diagram above, find the marked angle."))
    assert p['figure_dependent'] and p['needs_review'] and 'figure' in p['flags']


def test_parse_detail_captures_figure_image():
    from utils import myschool as ms
    # a stem figure delivered via a lazy-load attr + a site-relative URL
    html = """
    <div class="card">
      <div class="qwrap"><h1>Use the circuit shown to find the current.</h1>
        <img data-original="/storage/questions/circuit123.png"></div>
      <div class="opts">
        <div><span class="uppercase">a</span><p>1A</p></div>
        <div><span class="uppercase">b</span><p>2A</p></div>
        <div><span class="uppercase">c</span><p>3A</p></div>
        <div><span class="uppercase">d</span><p>4A</p></div>
      </div>
      <div class="ans">Correct Option <span class="uppercase">c</span></div>
    </div>"""
    p = ms.parse_detail(html)
    assert p['image_url'] == 'https://myschool.ng/storage/questions/circuit123.png'
    assert 'image' in p['flags']
    assert not p['figure_dependent']            # we have the figure → answerable


def test_parse_detail_ignores_avatar_images():
    from utils import myschool as ms
    html = """
    <div class="card">
      <div class="qwrap"><h1>Plain text question with no figure.</h1>
        <img src="https://myschool.ng/storage/members/avatar123.jpg"></div>
      <div class="opts">
        <div><span class="uppercase">a</span><p>x</p></div>
        <div><span class="uppercase">b</span><p>y</p></div>
        <div><span class="uppercase">c</span><p>z</p></div>
        <div><span class="uppercase">d</span><p>w</p></div>
      </div>
      <div class="ans">Correct Option <span class="uppercase">a</span></div>
    </div>"""
    p = ms.parse_detail(html)
    assert p['image_url'] is None               # avatars are not question figures


def test_on_jamb_flags_school_only_subjects():
    from utils import myschool as ms
    for s in ('Commerce', 'Mathematics', 'Physics', 'Literature in English',
              'Further Mathematics', 'Accounting'):
        assert ms.on_jamb(s), s
    for s in ('Civic Education', 'Digital Technologies', 'Phonetics',
              'Project Work', 'Livestock Farming'):
        assert not ms.on_jamb(s), s


def test_classify_maps_to_taxonomy():
    from utils import myschool as ms
    sec, top, sub = ms.classify('commerce', 'A cheque drawn on a bank is an instrument of banking')
    assert top == 'Aids to Trade'               # banking keyword → Aids to Trade
    sec2, top2, _ = ms.classify('mathematics', 'Solve the quadratic equation for its roots')
    assert top2 == 'Algebra'


# ---- paste importer: optional image-URL (11th) column ----------------------
def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _csrf(c):
    import re
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', c.get('/students').get_data(as_text=True))
    return m.group(1) if m else None


def test_paste_import_accepts_image_url(app):
    from models import db, Subject, MockJAMBQuestion
    with app.app_context():
        s = Subject(name='PasteImgSubj', is_active=True); db.session.add(s); db.session.commit()
        sid = s.id
    c = _admin(app)
    row = 'What is shown? | a | b | c | d | A | | | | 2020 | https://example.com/fig.png'
    c.post('/mock-jamb/bank/import', data={'_csrf_token': _csrf(c), 'subject_id': sid, 'rows': row},
           follow_redirects=True)
    with app.app_context():
        q = MockJAMBQuestion.query.filter_by(subject_id=sid, mock_exam_id=None).first()
        assert q and q.image_url == 'https://example.com/fig.png' and q.exam_year == '2020'


# ---- in-app harvest: saves + dedupes by source_ref -------------------------
def test_harvest_saves_and_dedupes(app, monkeypatch):
    from models import db, Subject, MockJAMBQuestion
    from utils import myschool as ms
    from utils import myschool_harvest as mh

    monkeypatch.setattr(ms, 'list_question_ids', lambda *a, **k: ['101', '102'])
    monkeypatch.setattr(ms, 'fetch', lambda url, sess, **k: _fixture('A commerce question about banking'))

    with app.app_context():
        s = Subject(name='HarvestSubjCommerce', is_active=True); db.session.add(s); db.session.commit()
        sid = s.id
        mh.start_harvest([{'id': sid, 'name': 'Commerce'}], exam='jamb', year_min=2019, year_max=2019)
        for _ in range(4):
            st = mh.harvest_step(max_questions=6)
            if st['status'] == 'done':
                break
        assert st['added'] == 2
        rows = MockJAMBQuestion.query.filter_by(subject_id=sid, source='myschool').all()
        assert len(rows) == 2 and {r.source_ref for r in rows} == {'101', '102'}

        # re-run → everything is a duplicate, nothing added twice
        mh.start_harvest([{'id': sid, 'name': 'Commerce'}], exam='jamb', year_min=2019, year_max=2019)
        for _ in range(4):
            st2 = mh.harvest_step(max_questions=6)
            if st2['status'] == 'done':
                break
        assert st2['added'] == 0 and st2['duplicates'] == 2
        assert MockJAMBQuestion.query.filter_by(subject_id=sid, source='myschool').count() == 2


def test_harvest_reports_empty_subjects(app, monkeypatch):
    """A subject myschool has no questions for is reported in empty_subjects so
    the user learns why nothing was saved (e.g. not offered under that exam)."""
    from models import db, Subject
    from utils import myschool as ms
    from utils import myschool_harvest as mh

    monkeypatch.setattr(ms, 'list_question_ids', lambda *a, **k: [])   # nothing found
    with app.app_context():
        s = Subject(name='Civic Education', is_active=True); db.session.add(s); db.session.commit()
        mh.start_harvest([{'id': s.id, 'name': 'Civic Education'}], exam='jamb',
                         year_min=2018, year_max=2019)
        for _ in range(6):
            st = mh.harvest_step(max_questions=6)
            if st['status'] == 'done':
                break
        assert st['status'] == 'done' and st['added'] == 0
        assert st['empty_subjects'] == ['Civic Education']
