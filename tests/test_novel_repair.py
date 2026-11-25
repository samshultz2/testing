"""Novel section repair + the guards that stop questions being misfiled into it."""
import uuid

from models import db, Subject, MockJAMBQuestion


def _q(subj_id, text, section, topic, year='2025'):
    return MockJAMBQuestion(mock_exam_id=None, subject_id=subj_id, section=section, topic=topic, exam_year=year,
                            question_text=text, option_a='a', option_b='b', option_c='c', option_d='d',
                            correct_option='A', marks=1)


def _english():
    # its own subject ("English" = English Language to the classifier) so these
    # rows never leak into other tests' English Language bank
    subj = Subject.query.filter_by(name='English').first()
    if subj is None:
        subj = Subject(name='English', is_active=False); db.session.add(subj); db.session.flush()
    return subj


def test_classifier_never_guesses_novel():
    from utils import myschool as ms
    for text in ['Choose the option nearest in meaning to the word in italics: The style of the dress was odd',
                 'Choose the word that has the same vowel sound as setting',
                 'zzz qqq']:
        assert ms.classify('English Language', text)[0] != 'novel', text
        assert ms.classify_confident('English Language', text)[0] != 'novel', text
    assert ms.classify('English Language', 'In the novel, who is the narrator of the story?')[0] == 'novel'


def test_fallback_sections_exclude_novel(app):
    from utils.mock_bank_retag import _drawable_sections
    with app.app_context():
        s = Subject(name='English Language ' + uuid.uuid4().hex[:4], is_active=True)
        assert 'novel' not in _drawable_sections(type('S', (), {'name': 'English Language'})())


def test_repair_novel_section(app):
    from utils.novel_repair import repair
    with app.app_context():
        subj = _english()
        tag = uuid.uuid4().hex[:6]
        real = _q(subj.id, f'In the novel, who is the headmaster\'s deputy? {tag}', 'novel', 'What the questions test')
        lexis = _q(subj.id, f'Choose the option opposite in meaning to the word in italics: The man is generous {tag}',
                   'novel', 'Lexis and Structure')
        stray = _q(subj.id, f'Who narrates the story? {tag}', None, 'The Lekki Headmaster')
        bare = _q(subj.id, f'Mr Mezie is best described as {tag}', 'novel', 'Recommended Novel', year='2026')
        db.session.add_all([real, lexis, stray, bare]); db.session.commit()
        ids = real.id, lexis.id, stray.id, bare.id

        stats, _s = repair(subj, apply=False, use_myschool=False, log=lambda *a: None)
        assert db.session.get(MockJAMBQuestion, ids[0]).topic == 'What the questions test'      # dry run
        assert stats['moved out of Novel'] >= 1 and stats['kept, titled'] >= 1

        repair(subj, apply=True, use_myschool=False, log=lambda *a: None)
        r, l, st, b = (db.session.get(MockJAMBQuestion, i) for i in ids)
        assert b.section == 'novel' and 'Lekki Headmaster' in b.topic          # names a character only; 2026
        assert r.section == 'novel' and 'Lekki Headmaster' in r.topic          # 2025 novel
        assert l.section != 'novel'
        assert st.section == 'novel'
        MockJAMBQuestion.query.filter(MockJAMBQuestion.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()


def test_retag_leaves_novel_titles_alone(app):
    from utils.mock_bank_retag import _target_ids
    with app.app_context():
        subj = _english()
        q = _q(subj.id, 'In the novel, what does the narrator fear? ' + uuid.uuid4().hex[:5], 'novel',
               'The Lekki Headmaster — Kabir Alabi Garba')
        db.session.add(q); db.session.commit()
        assert q.id not in _target_ids(subj, 'all')
        db.session.delete(q); db.session.commit()


def test_finds_novel_questions_filed_elsewhere(app):
    """By the book named in the question, or by character names learned from the
    confirmed novel questions (made-up names here)."""
    from utils.novel_repair import repair
    with app.app_context():
        subj = _english()
        t = uuid.uuid4().hex[:5]
        lekki = 'The Lekki Headmaster — Kabir Alabi Garba'
        conf = [_q(subj.id, f'Why did Zorbadu leave the staff room? {t}', 'novel', lekki),
                _q(subj.id, f'Zorbadu and Quillana argued about the {t} fees', 'novel', lekki),
                _q(subj.id, f"Who is Quillana's guardian? {t}", 'novel', lekki)]
        titled = _q(subj.id, f'The following question is based on The Lekki Headmaster. Who {t}?', 'comprehension', 'What the questions test')
        by_name = _q(subj.id, f'What did Zorbadu promise the pupils? {t}', 'lexis_structure', 'Lexis and Structure', year='2026')
        plain = _q(subj.id, f'Choose the option nearest in meaning to the word in italics {t}', 'lexis_structure', 'Lexis and Structure')
        other_year = _q(subj.id, f'What did Zorbadu say? {t}', None, None, year='2012')
        rows = conf + [titled, by_name, plain, other_year]
        db.session.add_all(rows); db.session.commit()
        ids = [r.id for r in rows]
        repair(subj, apply=True, use_myschool=False, log=lambda *a: None)
        g = lambda r: db.session.get(MockJAMBQuestion, r.id)
        assert g(titled).section == 'novel' and 'Lekki' in g(titled).topic
        assert g(by_name).section == 'novel' and 'Lekki' in g(by_name).topic
        assert g(plain).section == 'lexis_structure'
        assert g(other_year).section != 'novel'            # 2012 is not a Lekki year
        MockJAMBQuestion.query.filter(MockJAMBQuestion.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()


def test_known_characters_identify_the_book():
    from utils import myschool as ms
    lekki = ms.book_from_characters
    assert 'Lekki' in lekki('What did Mr Bepo tell the staff at assembly?')
    assert 'Lekki' in lekki('Mrs Ibidun Gloss, the MD, insisted that')
    assert 'Lekki' in lekki('Who is Mr Audu?')                        # everyday name + title
    assert 'Lekki' in lekki('The headmaster of Stardom Schools is')
    assert lekki('Sola and Ade went to school') is None               # everyday name alone
    assert lekki('Gloss over the details, he said') is None
    assert 'Life Changer' in lekki("Ummi's husband wanted to study law")
    assert 'Lekki' in lekki('What subject did Mr Justus Anabel teach?')
    assert 'Lekki' in lekki("Why did Mr Guta complain about Mr Fafore?")
    assert 'Lekki' in lekki('Mrs Grace Apeh is the')
    assert 'Lekki' in lekki('Who are Nike and Kike?')                  # two of the book's names together
    assert 'Lekki' in lekki('Mr Ibe was the games master')               # everyday name + title
    assert lekki('Ade as well as Jide comes to school') is None          # myschool grammar sentence
    sec, top, _ = ms.classify('English Language', 'What did Mr Bepo tell the staff?', year=2025)
    assert sec == 'novel' and 'Lekki' in top
    assert ms.classify('English Language', 'Choose the option nearest in meaning: Mr Audu is generous')[0] != 'novel'
    assert ms.classify('Mathematics', 'Bepo bought 3 pens')[0] != 'novel'


def test_repair_finds_2025_question_by_known_character(app):
    from utils.novel_repair import repair
    with app.app_context():
        subj = _english()
        t = uuid.uuid4().hex[:5]
        q = _q(subj.id, f'Why was Mr Bepo unable to speak at the assembly? {t}', 'comprehension', 'What the questions test')
        db.session.add(q); db.session.commit()
        repair(subj, apply=True, use_myschool=False, log=lambda *a: None)
        q = db.session.get(MockJAMBQuestion, q.id)
        assert q.section == 'novel' and 'Lekki' in q.topic
        db.session.delete(q); db.session.commit()


def test_title_match_is_whole_words():
    from utils.novel_repair import _title_in_text
    assert _title_in_text('Choose the option that best complete the gap: The students had a ... On Independence Day') is None
    assert 'Lekki' in _title_in_text('The following question is based on The Lekki Headmaster . The dominant message')
    assert 'Forcados' in _title_in_text("This question is from the novel 'The Last Days at Forcados High school'. Who was")
    assert 'Dependence' in _title_in_text('In the novel In Dependence, Tayo')


def test_book_named_in_question_beats_the_page_check(app, monkeypatch):
    """#32007: myschool's page has no novel note (the book is named in the question
    itself), so the page check says 'not novel' — the question must stay in Novel."""
    from utils import novel_repair
    monkeypatch.setattr(novel_repair, '_myschool_verdict', lambda *a, **k: (False, None))
    with app.app_context():
        subj = _english()
        t = uuid.uuid4().hex[:5]
        q = _q(subj.id, f'The following question is based on The Lekki Headmaster . The dominant message {t}',
               'novel', 'The Lekki Headmaster', year='2026')
        q.source, q.source_ref = 'myschool', '99999'
        c = _q(subj.id, f'Why did Mr Guta complain? {t}', 'novel', 'What the questions test', year='2026')
        c.source, c.source_ref = 'myschool', '99998'
        db.session.add_all([q, c]); db.session.commit()
        novel_repair.repair(subj, apply=True, use_myschool=True, log=lambda *a: None, find_elsewhere=False)
        q, c = db.session.get(MockJAMBQuestion, q.id), db.session.get(MockJAMBQuestion, c.id)
        assert q.section == 'novel' and 'Lekki' in q.topic
        assert c.section == 'novel' and 'Lekki' in c.topic           # named character, 2026
        db.session.delete(q); db.session.delete(c); db.session.commit()


def test_learned_names_skip_authors_and_title_words():
    from utils.novel_repair import _names
    n = _names('Kabir Alabi Garba wrote The Lekki Headmaster. Questions about Stardom Schools and Bepo')
    assert 'Bepo' in n and 'Stardom' in n
    assert not ({'Kabir', 'Alabi', 'Garba', 'Questions', 'Schools', 'Lekki', 'Headmaster'} & n)


def test_elsewhere_character_found_even_when_page_says_no(app, monkeypatch):
    from utils import novel_repair
    monkeypatch.setattr(novel_repair, '_myschool_verdict', lambda *a, **k: (False, None))
    with app.app_context():
        subj = _english()
        t = uuid.uuid4().hex[:5]
        q = _q(subj.id, f'Why did Mr Guta complain about Mr Fafore? {t}', 'lexis_structure', 'Lexis and Structure', year='2025')
        q.source, q.source_ref = 'myschool', '99997'
        g = _q(subj.id, f'Ade as well as Jide comes to school {t}', 'lexis_structure', 'Lexis and Structure', year='2025')
        g.source, g.source_ref = 'myschool', '99996'
        db.session.add_all([q, g]); db.session.commit()
        novel_repair.repair(subj, apply=True, use_myschool=True, log=lambda *a: None, from_year=2025)
        q, g = db.session.get(MockJAMBQuestion, q.id), db.session.get(MockJAMBQuestion, g.id)
        assert q.section == 'novel' and 'Lekki' in q.topic
        assert g.section == 'lexis_structure'
        db.session.delete(q); db.session.delete(g); db.session.commit()


def test_real_lekki_questions_found_in_antonyms(app, monkeypatch):
    """Real 2025 myschool questions a school found filed under Antonyms; their
    pages carry no novel note, so only the character list identifies them."""
    from utils import novel_repair
    monkeypatch.setattr(novel_repair, '_myschool_verdict', lambda *a, **k: (False, None))
    texts = ['How much was the boarding house fee per session at Stardom before it was reduced?',
             'Why is Mr. Bepo reluctant to relocate to the United Kingdom?',
             'Where does Bepo live?',
             'Why was Mr Ayesoro transferred from his teaching role?',
             'What is the primary reason Mr Bepo organises excursions for the students at Stardom?',
             'Why was Mr Bepo moved during his visit to the Black Heritage Museum?']
    with app.app_context():
        subj = _english()
        t = uuid.uuid4().hex[:5]
        rows = []
        for i, x in enumerate(texts):
            q = _q(subj.id, f'{x} {t}', 'antonyms', 'What the questions test', year='2025')
            q.source, q.source_ref = 'myschool', str(88000 + i)
            rows.append(q)
        db.session.add_all(rows); db.session.commit()
        novel_repair.repair(subj, apply=True, use_myschool=True, log=lambda *a: None, from_year=2025)
        for q in rows:
            q = db.session.get(MockJAMBQuestion, q.id)
            assert q.section == 'novel' and 'Lekki' in q.topic, q.question_text
            db.session.delete(q)
        db.session.commit()
