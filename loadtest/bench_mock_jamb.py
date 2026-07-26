#!/usr/bin/env python3
"""In-process benchmark of the Mock-JAMB sitting hot paths — the parts we hardened
for a mass concurrent start: the per-candidate paper DRAW, the paper CACHE reuse,
and GRADING. Runs on a throwaway SQLite DB so it needs no VPS.

    N=500 BANK=500 python loadtest/bench_mock_jamb.py

What it measures (server-side data cost per student — NOT network/template):
  * cold draw      — first render: draws the paper from the bank + caches it
  * cached rebuild — a reload/resume: rebuilt from the attempt's cached paper
  * no-cache draw  — what EVERY reload would cost WITHOUT the cache (baseline)
  * grade          — scoring the attempt over its served set

Caveat: SQLite serialises writes, so it UNDER-represents Postgres write
concurrency. Treat the DRAW/READ numbers as representative and the WRITE numbers
as pessimistic; run loadtest/locustfile_mock_jamb.py against the real VPS for the
true end-to-end ceiling.
"""
import os
import sys
import time
import tempfile
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

N = int(os.environ.get('N', '500'))            # simulated students
BANK = int(os.environ.get('BANK', '500'))      # bank questions per calc subject
OPTS = ['A', 'B', 'C', 'D']


def _pct(vals, p):
    if not vals:
        return 0.0
    s = sorted(vals)
    return s[min(len(s) - 1, int(len(s) * p))]


def main():
    from config import Config
    from app import create_app

    tmp = tempfile.mkdtemp()

    class Bench(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(tmp, 'bench.db')
        BACKUP_RETENTION = 0

    app = create_app(Bench)
    with app.app_context():
        from models import (db, Subject, Branch, AcademicSession, Student,
                            MockJAMBExam, MockJAMBQuestion, MockJAMBPassage,
                            MockJAMBAttempt, MockJAMBAnswer)
        from utils.mock_jamb_sitting import (candidate_subject_ids, subject_items,
                                             grade_attempt)

        bid = Branch.get_default().id

        # ---- seed the bank -------------------------------------------------
        print(f'Seeding: {N} students, English bank + 3 calc subjects @ {BANK} each ...')
        t0 = time.perf_counter()
        eng = Subject(name='English Language', is_active=True); db.session.add(eng)
        calc = []
        for nm in ('Mathematics', 'Physics', 'Chemistry'):
            s = Subject(name=nm, is_active=True); db.session.add(s); calc.append(s)
        db.session.flush()

        # English: comprehension (2 passages x5), cloze (1 x10), novel (20),
        # + standalone lexis/oral sections, padded so the pool is realistically big.
        for p in range(2):
            pas = MockJAMBPassage(mock_exam_id=None, subject_id=eng.id,
                                  section='comprehension', kind='comprehension',
                                  title=f'Comp {p}', body='x' * 800, order=p)
            db.session.add(pas); db.session.flush()
            for i in range(5):
                db.session.add(MockJAMBQuestion(
                    mock_exam_id=None, subject_id=eng.id, section='comprehension',
                    passage_id=pas.id, question_text=f'c{p}{i}', option_a='a',
                    option_b='b', option_c='c', option_d='d', correct_option='A', order=i))
        clz = MockJAMBPassage(mock_exam_id=None, subject_id=eng.id, section='cloze',
                              kind='cloze', title='Cloze', body='x' * 800, order=0)
        db.session.add(clz); db.session.flush()
        for i in range(10):
            db.session.add(MockJAMBQuestion(
                mock_exam_id=None, subject_id=eng.id, section='cloze', passage_id=clz.id,
                question_text=f'z{i}', option_a='a', option_b='b', option_c='c',
                option_d='d', correct_option='A', order=i))
        eng_sections = ['novel', 'sentence_interpretation', 'synonyms', 'antonyms',
                        'lexis_structure', 'oral']
        for sec in eng_sections:
            for i in range(60):          # padded pool per section
                db.session.add(MockJAMBQuestion(
                    mock_exam_id=None, subject_id=eng.id, section=sec,
                    topic=('The Life Changer' if sec == 'novel' else None),
                    exam_year=('2024' if sec == 'novel' else None),
                    question_text=f'{sec}{i}', option_a='a', option_b='b',
                    option_c='c', option_d='d', correct_option='A', order=i))
        for s in calc:
            for i in range(BANK):
                db.session.add(MockJAMBQuestion(
                    mock_exam_id=None, subject_id=s.id,
                    section=['number', 'algebra', 'geometry', 'calculus', 'statistics'][i % 5],
                    question_text=f'{s.name}{i}', option_a='a', option_b='b',
                    option_c='c', option_d='d', correct_option='A', order=i))
        db.session.commit()

        sess = AcademicSession(name='BENCH'); db.session.add(sess); db.session.flush()
        exam = MockJAMBExam(name='Bench Mock', exam_number=1, session_id=sess.id,
                            exam_date=date.today(), branch_id=bid, is_published=True,
                            duration_minutes=120)
        db.session.add(exam); db.session.flush()

        subs = 'English Language,Mathematics,Physics,Chemistry'
        students = []
        for i in range(N):
            st = Student(student_id=f'LB{i:05d}', first_name='L', surname=f'{i}',
                         gender='Male', is_active=True, branch_id=bid, jamb_subjects=subs)
            db.session.add(st); students.append(st)
        db.session.commit()
        exam_id = exam.id
        sids = [s.id for s in students]
        print(f'  seeded in {time.perf_counter() - t0:.1f}s '
              f'({MockJAMBQuestion.query.count()} bank questions)\n')

        # confirm the pool index is actually chosen (SQLite plan)
        try:
            plan = db.session.execute(db.text(
                "EXPLAIN QUERY PLAN SELECT id FROM mock_jamb_questions "
                "WHERE subject_id=1 AND mock_exam_id IS NULL")).fetchall()
            print('Pool query plan:', ' | '.join(r[-1] for r in plan))
        except Exception as e:
            print('plan check skipped:', e)
        print()

        exam = db.session.get(MockJAMBExam, exam_id)

        # ---- Phase A: mass start (cold draw + cache, per student) ----------
        cold = []
        att_ids = []
        t0 = time.perf_counter()
        for sid in sids:
            att = MockJAMBAttempt(mock_exam_id=exam_id, student_id=sid,
                                  duration_minutes=120)
            db.session.add(att); db.session.flush()
            ts = time.perf_counter()
            for subj_id in candidate_subject_ids(exam, db.session.get(Student, sid)):
                subject_items(exam, subj_id, att)      # cold draw + cache the paper
            db.session.commit()                        # persist the paper (as portal_sit does)
            cold.append((time.perf_counter() - ts) * 1000)
            att_ids.append(att.id)
        wall_start = time.perf_counter() - t0

        # ---- Phase B: reload/resume (cached rebuild) -----------------------
        cached = []
        for aid in att_ids:
            att = db.session.get(MockJAMBAttempt, aid)
            student = db.session.get(Student, att.student_id)
            ts = time.perf_counter()
            for subj_id in candidate_subject_ids(exam, student):
                subject_items(exam, subj_id, att)      # rebuilt from cache (PK lookups)
            cached.append((time.perf_counter() - ts) * 1000)

        # ---- Phase C: no-cache baseline (what every reload would cost) -----
        nocache = []
        for aid in att_ids[:min(len(att_ids), 200)]:
            att = db.session.get(MockJAMBAttempt, aid)
            student = db.session.get(Student, att.student_id)
            saved = att.paper
            att.paper = None                           # force a fresh draw
            ts = time.perf_counter()
            from utils.mock_jamb_sitting import _draw_subject_items
            for subj_id in candidate_subject_ids(exam, student):
                _draw_subject_items(exam, subj_id, att)
            nocache.append((time.perf_counter() - ts) * 1000)
            att.paper = saved                          # restore (don't persist the None)
        db.session.rollback()

        # ---- Phase D: grade ------------------------------------------------
        graded = []
        for aid in att_ids[:min(len(att_ids), 200)]:
            att = db.session.get(MockJAMBAttempt, aid)
            # answer ~70% of the served questions
            served = []
            for subj_id in candidate_subject_ids(exam, db.session.get(Student, att.student_id)):
                _it, s = subject_items(exam, subj_id, att)
                served.extend(s)
            import random
            for qid in random.sample(served, int(len(served) * 0.7)):
                db.session.add(MockJAMBAnswer(attempt_id=att.id, question_id=qid,
                                              selected_option='A', is_correct=True))
            db.session.commit()
            ts = time.perf_counter()
            grade_attempt(att)
            graded.append((time.perf_counter() - ts) * 1000)

        # ---- Phase E: end-to-end HTTP page render (incl. Jinja template) ---
        # Hit the real portal_sit route so the ~180-question page render is timed,
        # not just the data layer. Log in by stamping the portal session directly.
        from routes.cbt import PORTAL_KEY
        http_first, http_reload = [], []
        # fresh students with no attempt yet: portal_sit creates the attempt +
        # draws + renders on first GET (the true first-open cost), cached on reload.
        fresh = []
        for i in range(60):
            st = Student(student_id=f'HB{i:04d}', first_name='H', surname=f'{i}',
                         gender='Male', is_active=True, branch_id=bid, jamb_subjects=subs)
            db.session.add(st); fresh.append(st)
        db.session.commit()
        client = app.test_client()
        for student in fresh:
            with client.session_transaction() as ss:
                ss[PORTAL_KEY] = student.id            # guard resolves by primary key
            url = f'/exam/mock-jamb/{exam_id}'
            ts = time.perf_counter(); r1 = client.get(url); dt1 = (time.perf_counter()-ts)*1000
            ts = time.perf_counter(); r2 = client.get(url); dt2 = (time.perf_counter()-ts)*1000
            if r1.status_code == 200:
                http_first.append(dt1)
            if r2.status_code == 200:
                http_reload.append(dt2)

        # ---- report --------------------------------------------------------
        def row(name, vals):
            print(f'  {name:<22} mean {sum(vals)/len(vals):6.1f} ms   '
                  f'p50 {_pct(vals,.5):6.1f}   p95 {_pct(vals,.95):6.1f}   '
                  f'max {max(vals):6.1f}')

        print('=' * 74)
        print(f'MOCK-JAMB SITTING BENCHMARK  (N={N} students, 4 subjects each, SQLite)')
        print('=' * 74)
        print('Per-student server-side cost (draw/cache/grade of the whole 4-subject paper):')
        row('cold draw + cache', cold)
        row('cached rebuild', cached)
        row('no-cache (baseline)', nocache)
        row('grade', graded)
        if http_first:
            print('Full HTTP page render (real route + Jinja template, ~180 questions):')
            row('  first open (draw)', http_first)
        if http_reload:
            row('  reload (cached)', http_reload)
        print('-' * 74)
        speedup = (sum(nocache)/len(nocache)) / (sum(cached)/len(cached))
        print(f'  cache speedup on reload/resume:  {speedup:.1f}x cheaper than re-drawing')
        print(f'  mass-start wall time (serial, 1 conn): {wall_start:.1f}s for {N} students'
              f'  -> {N/wall_start:.0f} cold starts/sec/connection')
        print(f'  with W concurrent workers/conns, multiply by ~W (Postgres, not SQLite).')
        print('=' * 74)


if __name__ == '__main__':
    main()
