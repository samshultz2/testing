"""Sort out the English question bank's Novel section (see utils/novel_repair.py).

    .venv/bin/python scripts/fix_novel_section.py            # report only, changes nothing
    .venv/bin/python scripts/fix_novel_section.py --apply    # make the changes
    add --no-web to skip re-reading myschool.ng (wording check only)
    add --from-year 2016 to search other sections only from that year (default 2010)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app  # noqa: E402


def main():
    apply = '--apply' in sys.argv
    web = '--no-web' not in sys.argv
    fy = 2010
    if '--from-year' in sys.argv:
        fy = int(sys.argv[sys.argv.index('--from-year') + 1])
    app = create_app()
    with app.app_context():
        from models import Subject
        from utils.myschool import norm_subject
        from utils.novel_repair import repair
        subj = next((s for s in Subject.query.all() if norm_subject(s.name) == 'english language'), None)
        if not subj:
            print('No English Language subject found.'); return
        stats, samples = repair(subj, apply=apply, use_myschool=web, from_year=fy)
        print('\n' + ('APPLIED' if apply else 'DRY RUN - nothing changed. Re-run with --apply to save.'))
        print('Checked via myschool page: %d, by wording: %d' % (stats.pop('checked_myschool', 0), stats.pop('checked_wording', 0)))
        for kind, n in stats.most_common():
            print('\n%5d  %s' % (n, kind))
            for line in samples.get(kind, []):
                print('       ' + line)


if __name__ == '__main__':
    main()
