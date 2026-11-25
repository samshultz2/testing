"""AI retag can be limited to one, several or all exam years."""
import uuid

from models import db, Subject, MockJAMBQuestion


def _subject():
    s = Subject(name='Retag Years ' + uuid.uuid4().hex[:6], is_active=False)
    db.session.add(s); db.session.flush()
    return s


def _q(subj_id, year):
    return MockJAMBQuestion(mock_exam_id=None, subject_id=subj_id, exam_year=year, topic=None,
                            question_text='Q ' + year, option_a='a', option_b='b', option_c='c',
                            option_d='d', correct_option='A', marks=1)


def test_year_values():
    from utils.mock_bank_retag import year_values
    assert year_values(None) == [] and year_values('') == [] and year_values(['', ' ']) == []
    assert year_values('2025') == ['2025']
    assert year_values(['2026', ' 2024', '2026']) == ['2024', '2026']


def test_target_ids_accept_several_years(app):
    from utils.mock_bank_batch_retag import target_ids
    from utils.mock_bank_retag import _target_ids
    with app.app_context():
        subj = _subject()
        rows = {y: _q(subj.id, y) for y in ('2023', '2024', '2025')}
        db.session.add_all(rows.values()); db.session.commit()
        ids = {y: r.id for y, r in rows.items()}
        try:
            got = set(target_ids(subj, year=['2023', '2025'], force=True))
            assert got == {ids['2023'], ids['2025']}
            assert set(target_ids(subj, year='2024', force=True)) == {ids['2024']}
            assert set(target_ids(subj, year=None, force=True)) == set(ids.values())
            assert set(_target_ids(subj, 'all', year=['2024', '2025'])) == {ids['2024'], ids['2025']}
        finally:
            for r in rows.values():
                db.session.delete(r)
            db.session.delete(subj); db.session.commit()


def test_years_label():
    from routes.mock_jamb import _years_label
    assert _years_label(None) == '' and _years_label(['2025']) == '2025'
    assert _years_label(['2024', '2025']) == '2024 & 2025'
    assert _years_label(['2021', '2022', '2026']) == '2021–2026 (3 years)'
