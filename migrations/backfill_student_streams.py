"""
Backfill the `students.stream` column from existing JAMB subject choices.

Mapping (per the school's rule):
    Physics in JAMB              -> Science
    Literature in English        -> Arts
    Commerce                     -> Commercial

Only students whose stream is not already set are updated, so it is safe to
re-run. Run with:  python migrations/backfill_student_streams.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models.models import db, Student
from utils.helpers import infer_stream_from_jamb


def run():
    with app.app_context():
        updated = {'Science': 0, 'Arts': 0, 'Commercial': 0}
        skipped_existing = 0
        unmatched = 0
        for student in Student.query.all():
            if student.stream:
                skipped_existing += 1
                continue
            inferred = infer_stream_from_jamb(student)
            if inferred:
                student.stream = inferred
                updated[inferred] += 1
            else:
                unmatched += 1
        db.session.commit()
        print(f"Backfill complete. Science={updated['Science']} "
              f"Arts={updated['Arts']} Commercial={updated['Commercial']} "
              f"| already-set={skipped_existing} | no-marker-subject={unmatched}")


if __name__ == '__main__':
    run()
