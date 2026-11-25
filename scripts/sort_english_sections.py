"""Re-file English bank questions into your syllabus's sections (Vowels,
Consonants, Rhymes, Word stress, Emphatic stress, Basic grammar, Antonyms,
Synonyms, Sentence interpretation…) from each question's wording, and reading
passages into Cloze / Summary / Comprehension from the passage and its questions.

    .venv/bin/python scripts/sort_english_sections.py            # report only
    .venv/bin/python scripts/sort_english_sections.py --apply    # save
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app  # noqa: E402


def main():
    apply = '--apply' in sys.argv
    app = create_app()
    with app.app_context():
        from models import Subject
        from utils.myschool import norm_subject
        from utils.english_sections import sort_bank, active_sections, sort_passages, grammar_audit
        subj = next((s for s in Subject.query.all() if norm_subject(s.name) == 'english language'), None)
        if not subj:
            print('No English Language subject found.'); return
        print('Sections in your current English blueprint: ' + ', '.join(sorted(active_sections(subj.name))))
        moves, samples, stuck = sort_bank(subj, apply=apply)
        print('\n' + ('APPLIED' if apply else 'DRY RUN - nothing changed. Re-run with --apply to save.'))
        print('%d questions would move' % sum(moves.values()) if not apply else '%d questions moved' % sum(moves.values()))
        for k, n in moves.most_common():
            print('\n%5d  %s' % (n, k))
            for line in samples.get(k, []):
                print('       ' + line)
        pmoves, psamples = sort_passages(subj, apply=apply)
        print('\nReading passages: %d %s' % (sum(pmoves.values()), 'moved' if apply else 'would move'))
        for k, n in pmoves.most_common():
            print('\n%5d passage(s)  %s' % (n, k))
            for line in psamples.get(k, []):
                print('       ' + line)
        words, default, gsamples = grammar_audit(subj)
        print('\nBasic grammar: %d say "complete the sentence / fill the gap"; '
              '%d are there only by default (no clear instruction).' % (words, default))
        for line in gsamples:
            print('       ' + line)
        if stuck:
            print('\nLeft where they are - wording does not say which section (re-tag or edit by hand):')
            for k, n in stuck.most_common():
                print('  %5d  in %s' % (n, k))


if __name__ == '__main__':
    main()
