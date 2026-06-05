"""
Backfill each student's `jamb_subjects` profile field from the subjects they
actually sat for JAMB (taken from their most recent JAMBResult).

Only students whose `jamb_subjects` is not already set are updated, so it is
safe to re-run and it never overwrites a manual entry.

Run with:  python migrations/backfill_jamb_subjects.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models.models import db, Student, JAMBResult


def run():
    with app.app_context():
        updated = 0
        skipped_existing = 0
        no_jamb = 0
        for student in Student.query.all():
            if student.jamb_subjects:
                skipped_existing += 1
                continue
            latest = JAMBResult.query.filter_by(student_id=student.id).order_by(
                JAMBResult.exam_year.desc(), JAMBResult.id.desc()
            ).first()
            if not latest:
                no_jamb += 1
                continue
            subjects = [s for s in (latest.subject1, latest.subject2,
                                    latest.subject3, latest.subject4) if s]
            if subjects:
                student.jamb_subjects = ', '.join(subjects)
                updated += 1
            else:
                no_jamb += 1
        db.session.commit()
        print(f"JAMB-subjects backfill complete. updated={updated} "
              f"| already-set={skipped_existing} | no-jamb-subjects={no_jamb}")


if __name__ == '__main__':
    run()
