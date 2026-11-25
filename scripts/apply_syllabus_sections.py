"""Bring every subject's imported syllabus up to date with the bundled
topic -> paper-section mappings, then re-section the questions that already
have a syllabus code (no AI, no tokens).

    .venv/bin/python scripts/apply_syllabus_sections.py            # report only
    .venv/bin/python scripts/apply_syllabus_sections.py --apply    # save
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app  # noqa: E402


def main():
    apply = '--apply' in sys.argv
    app = create_app()
    with app.app_context():
        from models import Subject, MockJAMBSyllabus
        from utils.syllabus_sections import sync_mappings, resection
        ids = {s.subject_id for s in MockJAMBSyllabus.query.all()}
        for subj in Subject.query.filter(Subject.id.in_(ids)).order_by(Subject.name).all():
            n = sync_mappings(subj, commit=apply)      # a dry run rolls it back in resection()
            moves, samples = resection(subj, apply=apply)
            if not n and not moves:
                continue
            print('\n== %s: %s%d coded questions %s' % (
                subj.name, ('%d mappings added; ' % n) if n else '', sum(moves.values()),
                'moved' if apply else 'would move'))
            for k, c in moves.most_common():
                print('   %5d  %s' % (c, k))
                for line in samples.get(k, []):
                    print('          ' + line)
        print('\n' + ('APPLIED.' if apply else 'DRY RUN - nothing changed. Run with --apply to save.'))


if __name__ == '__main__':
    main()
