"""Novel section repair + the guards that stop questions being misfiled into it."""
import uuid

from models import db, Subject, MockJAMBQuestion


def _q(subj_id, text, section, topic, year='2025'):
    return MockJAMBQuestion(mock_exam_id=None, subject_id=subj_id, section=section, topic=topic, exam_year=year,
                            question_text=text, option_a='a', option_b='b', option_c='c', option_d='d',
                            correct_option='A', marks=1)


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
        subj = Subject.query.filter_by(name='English Language').first()
        if subj is None:
            subj = Subject(name='English Language', is_active=True); db.session.add(subj); db.session.flush()
        tag = uuid.uuid4().hex[:6]
        real = _q(subj.id, f'In the novel, who is the headmaster\'s deputy? {tag}', 'novel', 'What the questions test')
        lexis = _q(subj.id, f'Choose the option opposite in meaning to the word in italics: The man is generous {tag}',
                   'novel', 'Lexis and Structure')
        stray = _q(subj.id, f'Who narrates the story? {tag}', None, 'The Lekki Headmaster')
        db.session.add_all([real, lexis, stray]); db.session.commit()
        ids = real.id, lexis.id, stray.id

        stats, _s = repair(subj, apply=False, use_myschool=False, log=lambda *a: None)
        assert db.session.get(MockJAMBQuestion, ids[0]).topic == 'What the questions test'      # dry run
        assert stats['moved out of Novel'] >= 1 and stats['kept, titled'] >= 1

        repair(subj, apply=True, use_myschool=False, log=lambda *a: None)
        r, l, st = (db.session.get(MockJAMBQuestion, i) for i in ids)
        assert r.section == 'novel' and 'Lekki Headmaster' in r.topic          # 2025 novel
        assert l.section != 'novel'
        assert st.section == 'novel'


def test_retag_leaves_novel_titles_alone(app):
    from utils.mock_bank_retag import _target_ids
    with app.app_context():
        subj = Subject.query.filter_by(name='English Language').first() or Subject(name='English Language', is_active=True)
        db.session.add(subj); db.session.flush()
        q = _q(subj.id, 'In the novel, what does the narrator fear? ' + uuid.uuid4().hex[:5], 'novel',
               'The Lekki Headmaster — Kabir Alabi Garba')
        db.session.add(q); db.session.commit()
        assert q.id not in _target_ids(subj, 'all')
