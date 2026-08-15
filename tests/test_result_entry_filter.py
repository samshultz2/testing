"""The WAEC/JAMB add-result dropdowns must hide students who already have that
year's result entered, so results are never entered twice. Covers the shared
routes.results.students_needing_result filter.
"""
from datetime import date

from models import db, Student, JAMBResult, WAECResult
from routes.results import students_needing_result


def _student(sid, surname):
    s = Student(student_id=sid, first_name='T', surname=surname,
                gender='Male', is_active=True)
    db.session.add(s); db.session.flush()
    return s


def test_jamb_filter_hides_students_with_this_years_result(app):
    year = date.today().year
    with app.app_context():
        done = _student('JF-DONE', 'Done')
        todo = _student('JF-TODO', 'Todo')
        db.session.add(JAMBResult(student_id=done.id, exam_year=year, total_score=250))
        # A prior-year result must NOT hide them from this year's entry.
        db.session.add(JAMBResult(student_id=todo.id, exam_year=year - 1, total_score=200))
        db.session.commit()
        cohort = [done, todo]

        remaining = students_needing_result(cohort, JAMBResult, year)
        ids = {s.id for s in remaining}
        assert todo.id in ids            # no result this year → still offered
        assert done.id not in ids        # already has this year's result → hidden

        # Cleanup
        JAMBResult.query.filter(JAMBResult.student_id.in_([done.id, todo.id])).delete(
            synchronize_session=False)
        for s in (done, todo):
            db.session.delete(s)
        db.session.commit()


def test_waec_filter_hides_students_with_this_years_result(app):
    year = date.today().year
    with app.app_context():
        done = _student('WF-DONE', 'Done')
        todo = _student('WF-TODO', 'Todo')
        # WAEC has one row per subject; any row for the year counts as "entered".
        db.session.add(WAECResult(student_id=done.id, exam_year=year,
                                  subject='Mathematics', grade='A1'))
        db.session.commit()
        cohort = [done, todo]

        remaining = students_needing_result(cohort, WAECResult, year)
        ids = {s.id for s in remaining}
        assert todo.id in ids
        assert done.id not in ids

        WAECResult.query.filter(WAECResult.student_id.in_([done.id, todo.id])).delete(
            synchronize_session=False)
        for s in (done, todo):
            db.session.delete(s)
        db.session.commit()
