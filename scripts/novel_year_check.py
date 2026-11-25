"""Where are a year's questions, and which look like novel questions?

    .venv/bin/python scripts/novel_year_check.py 2026

Counts every question for that exam year (bank and mock papers, every subject,
stand-alone or passage-bound) by subject and section, and lists those that look
like novel questions (book named, a known character, or 'novel') but are not in
the bank's Novel section.
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app  # noqa: E402


def main():
    year = (sys.argv[1] if len(sys.argv) > 1 else '2026').strip()
    app = create_app()
    with app.app_context():
        from models import MockJAMBQuestion, Subject
        from utils.myschool import book_from_characters, looks_like_novel_question
        from utils.novel_repair import _title_in_text
        names = {s.id: s.name for s in Subject.query.all()}
        rows = MockJAMBQuestion.query.filter(MockJAMBQuestion.exam_year.like(year + '%')).all()
        print('%d questions with exam year %s\n' % (len(rows), year))
        where = Counter()
        for q in rows:
            where[(names.get(q.subject_id, q.subject_id), 'bank' if q.mock_exam_id is None else 'mock #%s' % q.mock_exam_id,
                   'passage' if q.passage_id else 'stand-alone', q.section or '(no section)')] += 1
        print('subject | bank/mock | kind | section : count')
        for (sub, bm, kind, sec), n in sorted(where.items(), key=lambda x: -x[1]):
            print('  %-20s %-10s %-11s %-26s %5d' % (sub, bm, kind, sec, n))
        odd = [q for q in rows if (q.section or '') != 'novel' or q.mock_exam_id is not None or q.passage_id
               if _title_in_text(q.question_text) or book_from_characters(q.question_text)
               or looks_like_novel_question(q.question_text)]
        print('\nLook like novel questions but are NOT stand-alone bank Novel questions: %d' % len(odd))
        for q in odd[:40]:
            print('  #%s %s | %s | %s | %s' % (q.id, names.get(q.subject_id), 'bank' if q.mock_exam_id is None else 'mock',
                                            q.section, (q.question_text or '')[:80].replace('\n', ' ')))
        nov = Counter((q.topic or '(none)') for q in rows if (q.section or '') == 'novel' and q.mock_exam_id is None)
        print('\nIn the bank Novel section for %s:' % year)
        for t, n in nov.most_common():
            print('  %5d  %s' % (n, t))


if __name__ == '__main__':
    main()
