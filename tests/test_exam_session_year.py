"""External exams are session-based: the stored exam_year is the academic
session's second year (2025/2026 → 2026), and the add-result pages offer
sessions defaulting to the active one. Covers the mapping + the picker helper.
"""
from models import db, AcademicSession
from utils.helpers import session_exam_year, exam_year_choices


def test_session_exam_year_is_the_second_year(app):
    with app.app_context():
        s = AcademicSession(name='2031/2032', is_active=False)
        db.session.add(s); db.session.commit()
        try:
            assert session_exam_year(s) == 2032          # WAEC/JAMB sit in the 2nd year
        finally:
            db.session.delete(s); db.session.commit()


def test_exam_year_choices_maps_session_to_its_exam_year(app):
    with app.app_context():
        s = AcademicSession(name='2031/2032', is_active=False)
        db.session.add(s); db.session.commit()
        try:
            choices = exam_year_choices()
            assert (2032, '2031/2032') in choices        # value is the year, label the session
        finally:
            db.session.delete(s); db.session.commit()
