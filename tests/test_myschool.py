"""myschool.ng scraper core: parsing (stem/options/answer/table/figure flags),
classification, the paste importer's image column, and the in-app harvest
(dedup by source_ref) — all offline via a synthetic fixture / monkeypatch."""
from config import Config
from tests.conftest import login_token


def _fixture(stem, correct='b', with_table=False, instruction=None):
    table = ('<table><tr><th>City</th><th>Pop</th></tr>'
             '<tr><td>Lagos</td><td>20</td></tr></table>') if with_table else ''
    # myschool renders the shared novel-note / reading passage in a prevent-copy div
    instr = (f'<div class="mb-2 bg-white rounded-2xl p-3 prevent-copy">{instruction}</div>'
             if instruction else '')
    return f"""
    <div class="card">
      {instr}
      <div class="qwrap"><h1>{stem}</h1>{table}</div>
      <div class="opts">
        <div class="prevent-copy"><span class="uppercase">a</span><p>Lagos</p></div>
        <div class="prevent-copy"><span class="uppercase">b</span><p>Abuja</p></div>
        <div class="prevent-copy"><span class="uppercase">c</span><p>Kano</p></div>
        <div class="prevent-copy"><span class="uppercase">d</span><p>Ibadan</p></div>
      </div>
      <div class="ans">Correct Option <span class="uppercase">{correct}</span></div>
    </div>"""


_PASSAGE = ("The victory of the small Greek democracy of Athens over the mighty "
            "Persian Empire is one of the most inspiring events in history. It "
            "showed how a free people could rise against tyranny and prevail "
            "against overwhelming odds, and it shaped the culture that followed.")


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


def test_parse_detail_extracts_nested_table_from_stem():
    """A table nested in the stem is pulled out (its cells don't leak in as
    run-on text) and kept as a structured [table: …] marker."""
    from utils import myschool as ms
    html = """
    <div class="card">
      <div class="qwrap"><h1><table><tr><th>Price</th><th>Qty</th></tr>
        <tr><td>8</td><td>10</td></tr></table> If we move from 8 to 6, find elasticity</h1></div>
      <div class="opts">
        <div><span class="uppercase">a</span><p>1</p></div>
        <div><span class="uppercase">b</span><p>2</p></div>
        <div><span class="uppercase">c</span><p>3</p></div>
        <div><span class="uppercase">d</span><p>4</p></div>
      </div>
      <div class="ans">Correct Option <span class="uppercase">b</span></div>
    </div>"""
    p = ms.parse_detail(html)
    assert p['has_table']
    before = p['stem'].split('[table:')[0]
    assert 'If we move from 8 to 6' in before
    assert '8 10' not in before and 'Price Qty' not in before      # not duplicated
    assert '[table: Price | Qty ; 8 | 10]' in p['stem']


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


def _data_uri_png(w=120, h=90):
    """A real (non-trivial) inline PNG data URI, above the placeholder threshold."""
    from io import BytesIO
    import base64
    from PIL import Image
    im = Image.new('RGB', (w, h), (30, 160, 90))
    for x in range(0, w, 2):
        for y in range(0, h, 2):
            im.putpixel((x, y), ((x * 7) % 256, (y * 9) % 256, (x + y) % 256))
    buf = BytesIO(); im.save(buf, 'PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


def _img_fixture(stem, img_tag, correct='c'):
    return f"""
    <div class="card">
      <div class="qwrap"><h1>{stem}</h1>{img_tag}</div>
      <div class="opts">
        <div class="prevent-copy"><span class="uppercase">a</span><p>1A</p></div>
        <div class="prevent-copy"><span class="uppercase">b</span><p>2A</p></div>
        <div class="prevent-copy"><span class="uppercase">c</span><p>3A</p></div>
        <div class="prevent-copy"><span class="uppercase">d</span><p>4A</p></div>
      </div>
      <div class="ans">Correct Option <span class="uppercase">{correct}</span></div>
    </div>"""


def test_parse_detail_captures_nuxt_img_and_prefers_real_url():
    """myschool serves figures as a NuxtImg. When it inlines a base64 placeholder in
    ``src`` and the real figure in ``srcset``, the real hosted URL wins."""
    from utils import myschool as ms
    img = ('<img data-nuxt-img src="data:image/png;base64,AAAA" '
           'srcset="https://myschool.ng/storage/classroom/fig9.jpeg 1x, '
           'https://myschool.ng/storage/classroom/fig9.jpeg 2x">')
    p = ms.parse_detail(_img_fixture('Find the resistance of the circuit shown.', img))
    assert p['image_url'] == 'https://myschool.ng/storage/classroom/fig9.jpeg'
    assert 'image' in p['flags'] and not p['figure_dependent']


def test_parse_detail_captures_inline_base64_figure():
    """Some diagrams are embedded straight into the page as a base64 data URI —
    they are real figures, so the question is answerable (not needs_image)."""
    from utils import myschool as ms
    uri = _data_uri_png()
    p = ms.parse_detail(_img_fixture('The value of T in the figure above is', f'<img src="{uri}">'))
    assert p['image_url'] == uri and 'image' in p['flags']
    assert not p['figure_dependent']
    # a tiny inline blur/placeholder is NOT treated as a figure
    q = ms.parse_detail(_img_fixture('In the diagram above, find the angle.',
                                     '<img src="data:image/png;base64,AAAABBBB">'))
    assert q['image_url'] is None and q['figure_dependent']   # still needs a real image


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


def test_english_novel_tagged_by_year():
    from utils import myschool as ms
    q = "Which character in the recommended novel is the protagonist?"
    sec, top, _ = ms.classify('english language', q, year=2019)
    assert sec == 'novel' and 'Forcados' in top          # 2016-2020 novel
    sec, top, _ = ms.classify('english language', q, year=2023)
    assert sec == 'novel' and 'Life Changer' in top      # 2021-2024 novel
    sec, top, _ = ms.classify('english language', q, year=2025)
    assert sec == 'novel' and 'Lekki Headmaster' in top  # 2025 has its own text
    # unknown year keeps the generic label (assign manually)
    sec, top, _ = ms.classify('english language', q, year=1990)
    assert sec == 'novel' and top == 'Recommended Novel'
    # a non-novel English question is unaffected by the year
    sec, top, _ = ms.classify('english language', "Choose the nearest in meaning to 'candid'", year=2023)
    assert sec != 'novel'


def test_english_novel_title_overrides_year_map():
    """The name scraped off the listing page wins over the hardcoded year map, so
    a year whose set text changed (or a fresh year) is tagged correctly."""
    from utils import myschool as ms
    q = "Which character in the recommended novel is the protagonist?"
    sec, top, _ = ms.classify('english language', q, year=2024,
                              novel_title='The Lekki Headmaster')
    assert sec == 'novel' and top == 'The Lekki Headmaster'   # override, not 'Life Changer'
    # a blank/absent scrape falls back to the year map
    sec, top, _ = ms.classify('english language', q, year=2023, novel_title=None)
    assert sec == 'novel' and 'Life Changer' in top


def test_scrape_novel_title_reads_listing_badge(monkeypatch):
    """The recommended novel is read from the listing-page badge
    ``div.bg-primary_accent strong`` (myschool labels each year's set text there)."""
    from utils import myschool as ms
    listing = """
    <div class="row">
      <div class="mb-2 inline-block bg-primary_accent rounded-2xl p-3 prevent-copy">
        <strong>The Lekki Headmaster</strong>
      </div>
      <a href="/classroom/english-language/501?exam_type=jamb">Q</a>
    </div>"""
    monkeypatch.setattr(ms, 'fetch', lambda url, sess, **k: listing)
    assert ms.scrape_novel_title('English Language', 'jamb', 2025, session=object()) \
        == 'The Lekki Headmaster'
    # non-English subjects never carry a novel badge → None (and no fetch needed)
    assert ms.scrape_novel_title('Mathematics', 'jamb', 2025, session=object()) is None
    # a listing without the badge (older years) → None
    monkeypatch.setattr(ms, 'fetch', lambda url, sess, **k: '<div>no badge here</div>')
    assert ms.scrape_novel_title('English Language', 'jamb', 2018, session=object()) is None


def test_parse_detail_reads_novel_note():
    """A Novel question is flagged from myschool's instruction note, and the book
    title is extracted from it — the authoritative per-question signal."""
    from utils import myschool as ms
    note = 'This question is based on Khadijat Abubakar Jalli\'s novel , "The Life Changer"'
    p = ms.parse_detail(_fixture("Who was Omar's immediate sister?", instruction=note))
    assert p['is_novel'] and p['novel_title'] == 'The Life Changer'
    assert 'novel' in p['flags'] and not p['passage_text']


def test_parse_detail_captures_passage_and_kind():
    from utils import myschool as ms
    # comprehension: the passage is captured, lead-in stripped, kind=comprehension
    lead = 'Read the passage carefully and answer the questions that follow: '
    p = ms.parse_detail(_fixture("What is the main idea of the passage?",
                                 instruction=lead + _PASSAGE))
    assert 'passage' in p['flags']
    assert p['passage_text'].startswith('The victory of the small Greek')  # lead-in gone
    assert ms.passage_kind(p['passage_text'], p['stem']) == 'comprehension'
    # cloze: a blank in the stem makes it a cloze passage
    q = ms.parse_detail(_fixture("Athens had ________ the Greek states.",
                                 instruction=lead + _PASSAGE))
    assert ms.passage_kind(q['passage_text'], q['stem']) == 'cloze'


def test_on_jamb_flags_school_only_subjects():
    from utils import myschool as ms
    for s in ('Commerce', 'Mathematics', 'Physics', 'Literature in English',
              'Accounting', 'Christian Religious Studies', 'Islamic Studies', 'Fine Art'):
        assert ms.on_jamb(s), s
    # not offered under JAMB on myschool (WAEC-only, or not there at all)
    for s in ('Civic Education', 'Digital Technologies', 'Phonetics', 'Project Work',
              'Livestock Farming', 'Further Mathematics', 'Insurance', 'Marketing'):
        assert not ms.on_jamb(s), s


def test_subject_slugs_match_myschool():
    from utils import myschool as ms
    assert ms.subject_slug('Christian Religious Studies') == 'christian-religious-knowledge-crk'
    assert ms.subject_slug('Islamic Studies') == 'islamic-religious-knowledge-irk'
    assert ms.subject_slug('Accounting') == 'accounts-principles-of-accounts'
    assert ms.subject_slug('Fine Art') == 'fine-arts'


def test_literature_sections_including_novels():
    """JAMB Literature is a blueprint subject with genre sections; its novel/prose
    questions land in the Prose section (drama→drama, poetry→poetry)."""
    from utils import myschool as ms
    from utils.jamb_blueprint import JAMB_BLUEPRINT, norm_subject, sections_for
    assert norm_subject('Literature in English') in JAMB_BLUEPRINT
    assert {s['section'] for s in sections_for('Literature in English')} == \
        {'appreciation', 'prose', 'drama', 'poetry'}
    sec, _t, _s = ms.classify('literature in english',
                              'Which narrative technique does the novelist use in the prose novel')
    assert sec == 'prose'                                   # the novels
    sec, _t, _s = ms.classify('literature in english',
                              'Identify the tragic hero and the comedy in the drama play')
    assert sec == 'drama'
    sec, _t, _s = ms.classify('literature in english',
                              'The rhyme scheme and meter of the poem build imagery')
    assert sec == 'poetry'


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


def test_harvest_flags_figure_questions_and_holds_them_out(app, monkeypatch):
    """A figure-dependent question is saved with needs_image=True, kept out of the
    exam pool, and re-enters once an image is set (or the flag is dismissed)."""
    from models import db, Subject, MockJAMBQuestion
    from utils import myschool as ms
    from utils import myschool_harvest as mh
    from utils.mock_jamb_sitting import _subject_pool

    figure_html = _fixture("In the diagram above, find the marked angle.")
    monkeypatch.setattr(ms, 'list_question_ids', lambda *a, **k: ['201'])
    monkeypatch.setattr(ms, 'fetch', lambda url, sess, **k: figure_html)

    with app.app_context():
        s = Subject(name='HarvestFigSubj', is_active=True); db.session.add(s); db.session.commit()
        sid = s.id
        mh.start_harvest([{'id': sid, 'name': 'Physics'}], exam='jamb', year_min=2019, year_max=2019)
        for _ in range(3):
            st = mh.harvest_step(max_questions=6)
            if st['status'] == 'done':
                break
        assert st['added'] == 1 and st['needs_image'] == 1
        q = MockJAMBQuestion.query.filter_by(subject_id=sid, source='myschool').first()
        assert q.needs_image is True

        # held out of the draw pool
        class _Exam:  # minimal stand-in; a bank-source exam owns no questions
            id = -999
        _passages, qrows = _subject_pool(_Exam(), sid)
        assert q.id not in {x.id for x in qrows}

        # dismissing the flag returns it to the pool
        from config import Config
        from tests.conftest import login_token
        c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    import re
    tok = re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                    c.get('/students').get_data(as_text=True)).group(1)
    c.post(f'/mock-jamb/bank/question/{q.id}/set-image',
           data={'_csrf_token': tok, 'dismiss': '1'}, follow_redirects=True)
    with app.app_context():
        q2 = db.session.get(MockJAMBQuestion, q.id)
        assert q2.needs_image is False


def test_harvest_tags_english_novel_from_listing_badge(app, monkeypatch):
    """A harvested English novel question is tagged with the novel scraped off the
    listing page (``scrape_novel_title``), not the stale hardcoded year map."""
    from models import db, Subject, MockJAMBQuestion
    from utils import myschool as ms
    from utils import myschool_harvest as mh

    novel_q = _fixture("Which character in the recommended novel is the protagonist?")
    # English harvest reads ids + per-question set-text off the listing badge
    monkeypatch.setattr(ms, 'list_ids_and_texts', lambda *a, **k: (['301'], {'301': 'The Lekki Headmaster'}))
    monkeypatch.setattr(ms, 'fetch', lambda url, sess, **k: novel_q)

    with app.app_context():
        s = Subject(name='HarvestEnglishNovel', is_active=True); db.session.add(s); db.session.commit()
        sid = s.id
        # name it 'English Language' so classify builds the English index
        mh.start_harvest([{'id': sid, 'name': 'English Language'}], exam='jamb',
                         year_min=2025, year_max=2025)
        for _ in range(3):
            st = mh.harvest_step(max_questions=6)
            if st['status'] == 'done':
                break
        q = MockJAMBQuestion.query.filter_by(subject_id=sid, source='myschool').first()
        assert q is not None and q.section == 'novel'
        assert q.topic == 'The Lekki Headmaster'      # from the badge, not the year map


def test_harvest_groups_comprehension_under_one_passage(app, monkeypatch):
    """Two comprehension questions quoting the same passage are grouped under a
    single shared MockJAMBPassage (deduped by body), section='comprehension'."""
    from models import db, Subject, MockJAMBQuestion, MockJAMBPassage
    from utils import myschool as ms
    from utils import myschool_harvest as mh

    lead = 'Read the passage carefully and answer the questions that follow: '
    pages = {
        '401': _fixture('What is the main idea of the passage?', instruction=lead + _PASSAGE),
        '402': _fixture('What does the writer admire most?', correct='c', instruction=lead + _PASSAGE),
    }
    monkeypatch.setattr(ms, 'list_ids_and_texts', lambda *a, **k: (['401', '402'], {}))
    monkeypatch.setattr(ms, 'fetch', lambda url, sess, **k: pages[url.split('/')[-1].split('?')[0]])

    with app.app_context():
        s = Subject(name='HarvestEnglishPassage', is_active=True); db.session.add(s); db.session.commit()
        sid = s.id
        mh.start_harvest([{'id': sid, 'name': 'English Language'}], exam='jamb',
                         year_min=2023, year_max=2023)
        for _ in range(4):
            st = mh.harvest_step(max_questions=6)
            if st['status'] == 'done':
                break
        qs = MockJAMBQuestion.query.filter_by(subject_id=sid, source='myschool').all()
        assert len(qs) == 2 and all(q.section == 'comprehension' for q in qs)
        pids = {q.passage_id for q in qs}
        assert len(pids) == 1 and None not in pids            # one shared passage
        passage = db.session.get(MockJAMBPassage, pids.pop())
        assert passage.kind == 'comprehension'
        assert passage.body.startswith('The victory of the small Greek')


def test_harvest_tags_novel_from_question_note(app, monkeypatch):
    """A harvested Novel question is detected from myschool's own note and tagged
    with the book title, regardless of the keyword classifier."""
    from models import db, Subject, MockJAMBQuestion
    from utils import myschool as ms
    from utils import myschool_harvest as mh

    note = 'This question is based on the recommended novel , "The Lekki Headmaster"'
    # no listing badge — the novel title comes from myschool's own in-question note
    monkeypatch.setattr(ms, 'list_ids_and_texts', lambda *a, **k: (['501'], {}))
    monkeypatch.setattr(ms, 'fetch', lambda url, sess, **k:
                        _fixture("Who is the headmaster's confidant?", instruction=note))

    with app.app_context():
        s = Subject(name='HarvestEnglishNote', is_active=True); db.session.add(s); db.session.commit()
        sid = s.id
        mh.start_harvest([{'id': sid, 'name': 'English Language'}], exam='jamb',
                         year_min=2025, year_max=2025)
        for _ in range(3):
            st = mh.harvest_step(max_questions=6)
            if st['status'] == 'done':
                break
        q = MockJAMBQuestion.query.filter_by(subject_id=sid, source='myschool').first()
        assert q.section == 'novel' and q.topic == 'The Lekki Headmaster'


def _listing(slug, exam, ids, badge=None):
    """A synthetic myschool listing page: the set-text badge plus the per-question
    detail links the id-scraper matches on."""
    b = f'<div class="bg-primary_accent"><strong>{badge}</strong></div>' if badge else ''
    links = ''.join(
        f'<a href="/classroom/{slug}/{i}?exam_type={exam}&exam_year=2022">Q{i}</a>' for i in ids)
    return f'<div class="list">{b}{links}</div>'


def test_list_ids_and_texts_tags_per_page_badge(monkeypatch):
    """``list_ids_and_texts`` returns the ids AND a {qid: set-text} map read from
    each page's badge — Literature's text varies page to page, so the badge is
    applied per question, not once for the whole year."""
    from utils import myschool as ms
    slug, exam = 'literature-in-english', 'jamb'
    pages = {
        1: _listing(slug, exam, ['801', '802'], badge='Kossoh Town Boy'),
        2: _listing(slug, exam, ['803'], badge='Faceless'),
        3: None,   # end of pagination
    }
    import re as _re
    monkeypatch.setattr(ms, 'fetch', lambda url, sess, **k:
                        pages.get(int(_re.search(r'page=(\d+)', url).group(1))))
    ids, texts = ms.list_ids_and_texts(slug, exam, 2022, None, max_pages=10, delay=0)
    assert ids == ['801', '802', '803']
    assert texts == {'801': 'Kossoh Town Boy', '802': 'Kossoh Town Boy',
                     '803': 'Faceless'}


def test_harvest_tags_literature_prose_with_set_text(app, monkeypatch):
    """A harvested Literature prose question is tagged (topic) with the set text
    named in the listing badge, mirroring how English novel questions carry the
    book title."""
    from models import db, Subject, MockJAMBQuestion
    from utils import myschool as ms
    from utils import myschool_harvest as mh

    prose_q = _fixture('In the novel, what motivates the protagonist to leave home?')
    monkeypatch.setattr(ms, 'list_ids_and_texts', lambda *a, **k: (['901'], {'901': 'Kossoh Town Boy'}))
    monkeypatch.setattr(ms, 'fetch', lambda url, sess, **k: prose_q)

    with app.app_context():
        s = Subject(name='HarvestLitProse', is_active=True); db.session.add(s); db.session.commit()
        sid = s.id
        mh.start_harvest([{'id': sid, 'name': 'Literature in English'}], exam='jamb',
                         year_min=2022, year_max=2022)
        for _ in range(3):
            st = mh.harvest_step(max_questions=6)
            if st['status'] == 'done':
                break
        q = MockJAMBQuestion.query.filter_by(subject_id=sid, source='myschool').first()
        assert q is not None
        assert q.section in ('prose', 'drama', 'poetry')
        assert q.topic == 'Kossoh Town Boy'


def test_harvest_literature_novel_note_maps_to_prose(app, monkeypatch):
    """Literature has no 'novel' section (that's English) — a Literature question
    myschool flags as a recommended-novel question must be remapped to 'prose' and
    tagged with the text, not dropped to section=None (unservable)."""
    from models import db, Subject, MockJAMBQuestion
    from utils import myschool as ms
    from utils import myschool_harvest as mh

    note = 'This question is based on the recommended text , "Kossoh Town Boy"'
    monkeypatch.setattr(ms, 'list_ids_and_texts', lambda *a, **k: (['601'], {}))
    monkeypatch.setattr(ms, 'fetch', lambda url, sess, **k:
                        _fixture('Who narrates the story?', instruction=note))

    with app.app_context():
        s = Subject(name='HarvestLitNovelNote', is_active=True); db.session.add(s); db.session.commit()
        sid = s.id
        mh.start_harvest([{'id': sid, 'name': 'Literature in English'}], exam='jamb',
                         year_min=2022, year_max=2022)
        for _ in range(3):
            st = mh.harvest_step(max_questions=6)
            if st['status'] == 'done':
                break
        q = MockJAMBQuestion.query.filter_by(subject_id=sid, source='myschool').first()
        assert q is not None
        assert q.section == 'prose'                 # remapped from 'novel'
        assert q.topic == 'Kossoh Town Boy'


def test_harvest_caps_overlong_topic(app, monkeypatch):
    """A very long novel/set-text title is trimmed to the topic column's limit so
    the INSERT never overflows VARCHAR(100) and pauses the whole harvest."""
    from models import db, Subject, MockJAMBQuestion
    from utils import myschool as ms
    from utils import myschool_harvest as mh

    long_title = 'A ' + 'Very ' * 40 + 'Long Novel Title'   # > 100 chars
    note = f'This question is based on the recommended novel , "{long_title}"'
    monkeypatch.setattr(ms, 'list_ids_and_texts', lambda *a, **k: (['811'], {}))
    monkeypatch.setattr(ms, 'fetch', lambda url, sess, **k:
                        _fixture('Who is the protagonist?', instruction=note))

    with app.app_context():
        s = Subject(name='HarvestCapTopic', is_active=True); db.session.add(s); db.session.commit()
        sid = s.id
        mh.start_harvest([{'id': sid, 'name': 'English Language'}], exam='jamb',
                         year_min=2025, year_max=2025)
        for _ in range(3):
            st = mh.harvest_step(max_questions=6)
            if st['status'] == 'done':
                break
        assert st['status'] == 'done' and not st['last_error']    # no truncation crash
        q = MockJAMBQuestion.query.filter_by(subject_id=sid, source='myschool').first()
        assert q is not None and len(q.topic) <= 100


def test_harvest_rehosts_inline_base64_figure(app, monkeypatch):
    """A figure delivered as an inline base64 data URI is decoded, re-hosted
    locally, and the question is kept in the pool (not flagged needs_image)."""
    from models import db, Subject, MockJAMBQuestion
    from utils import myschool as ms
    from utils import myschool_harvest as mh

    html = _img_fixture('In the diagram above, find the marked angle.', f'<img src="{_data_uri_png()}">')
    monkeypatch.setattr(ms, 'list_question_ids', lambda *a, **k: ['701'])
    monkeypatch.setattr(ms, 'fetch', lambda url, sess, **k: html)

    with app.app_context():
        s = Subject(name='HarvestInlineFig', is_active=True); db.session.add(s); db.session.commit()
        sid = s.id
        mh.start_harvest([{'id': sid, 'name': 'Physics'}], exam='jamb', year_min=2019, year_max=2019)
        for _ in range(3):
            st = mh.harvest_step(max_questions=6)
            if st['status'] == 'done':
                break
        assert st['images'] == 1 and st['needs_image'] == 0
        q = MockJAMBQuestion.query.filter_by(subject_id=sid, source='myschool').first()
        assert q.needs_image is False
        assert q.image_url and q.image_url.endswith('.png') and 'uploads/mock_jamb/' in q.image_url


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
