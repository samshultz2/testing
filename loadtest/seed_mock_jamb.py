#!/usr/bin/env python3
"""Seed a runnable Mock-JAMB online sitting load test (STAGING / a throwaway
tenant only — never a live school): N students (portal password, enrolled in a
LOADTEST class eligible for the mock, registered for 4 JAMB subjects) + a shared
question BANK (mock_exam_id NULL) with English passages and four subjects, + one
published mock for today.

Standalone (seeds the app's default DB):
    N=1000 BANK=600 python loadtest/seed_mock_jamb.py

Reusable: ``seed_current_app(N, BANK)`` seeds whatever app context is active — the
ephemeral-tenant tooling (loadtest/tenant_ctl.py) calls it inside a tenant DB.
"""
import csv
import os
import sys
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

PORTAL_PW = os.environ.get('PORTAL_PASSWORD', 'pass123')
SUBJECTS = 'English Language,Mathematics,Physics,Chemistry'
CLASS_NAME = 'LOADTEST'
CSV_PATH = os.path.join(os.path.dirname(__file__), 'students.csv')


def _goc(model, defaults=None, **kw):
    from models import db
    o = model.query.filter_by(**kw).first()
    if o:
        return o
    o = model(**kw, **(defaults or {})); db.session.add(o); db.session.flush()
    return o


def _seed_bank(bank):
    """Create the shared bank (mock_exam_id NULL) once, if it isn't there yet."""
    from models import db, Subject, MockJAMBQuestion, MockJAMBPassage
    eng = _goc(Subject, name='English Language', defaults={'is_active': True})
    calc = [_goc(Subject, name=n, defaults={'is_active': True})
            for n in ('Mathematics', 'Physics', 'Chemistry')]
    if MockJAMBQuestion.query.filter_by(subject_id=eng.id, mock_exam_id=None).count() >= 200:
        return
    for p in range(2):                             # comprehension: 2 passages x5
        pas = MockJAMBPassage(mock_exam_id=None, subject_id=eng.id,
                              section='comprehension', kind='comprehension',
                              title=f'Comp {p}', body='Passage text. ' * 60, order=p)
        db.session.add(pas); db.session.flush()
        for i in range(5):
            db.session.add(MockJAMBQuestion(
                mock_exam_id=None, subject_id=eng.id, section='comprehension',
                passage_id=pas.id, question_text=f'Comp {p} Q{i}?', option_a='a',
                option_b='b', option_c='c', option_d='d', correct_option='A', order=i))
    clz = MockJAMBPassage(mock_exam_id=None, subject_id=eng.id, section='cloze',
                          kind='cloze', title='Cloze', body='Cloze text. ' * 60, order=0)
    db.session.add(clz); db.session.flush()
    for i in range(10):
        db.session.add(MockJAMBQuestion(
            mock_exam_id=None, subject_id=eng.id, section='cloze', passage_id=clz.id,
            question_text=f'Cloze blank {i}', option_a='a', option_b='b', option_c='c',
            option_d='d', correct_option='A', order=i))
    for sec in ('novel', 'sentence_interpretation', 'synonyms', 'antonyms',
                'lexis_structure', 'oral'):
        for i in range(80):
            db.session.add(MockJAMBQuestion(
                mock_exam_id=None, subject_id=eng.id, section=sec,
                topic=('The Life Changer' if sec == 'novel' else None),
                exam_year=('2024' if sec == 'novel' else None),
                question_text=f'{sec} Q{i}', option_a='a', option_b='b', option_c='c',
                option_d='d', correct_option='A', order=i))
    for s in calc:
        for i in range(bank):
            db.session.add(MockJAMBQuestion(
                mock_exam_id=None, subject_id=s.id,
                section=['number', 'algebra', 'geometry', 'calculus', 'statistics'][i % 5],
                question_text=f'{s.name} Q{i}', option_a='a', option_b='b', option_c='c',
                option_d='d', correct_option='A', order=i))
    db.session.commit()


def seed_current_app(n_students, bank):
    """Seed the bank + students + a published mock into the ACTIVE app context.
    Returns ``(exam_id, rows)`` where rows is ``[(student_id, password), ...]``."""
    from models import (db, AcademicSession, Term, SchoolClass, ClassArm,
                        ClassArmAssignment, StudentEnrollment, Student, MockJAMBExam)
    sess = _goc(AcademicSession, name='LOADTEST 24/25')
    AcademicSession.query.update({AcademicSession.is_active: False}); sess.is_active = True
    term = _goc(Term, session_id=sess.id, term_number=1, defaults={'name': 'First Term'})
    Term.query.update({Term.is_active: False}); term.is_active = True
    sc = _goc(SchoolClass, name=CLASS_NAME, defaults={'level': 12})
    arm = _goc(ClassArm, name='LT', defaults={'is_active': True})
    caa = _goc(ClassArmAssignment, class_id=sc.id, arm_id=arm.id, term_id=term.id)

    _seed_bank(bank)

    rows = []
    for i in range(1, n_students + 1):
        sid = f'MJLT{i:05d}'
        s = Student.query.filter_by(student_id=sid).first()
        if not s:
            s = Student(student_id=sid, first_name=f'Load{i}', surname='Test',
                        gender='Male', is_active=True, branch_id=None)
            db.session.add(s); db.session.flush()
        s.set_portal_password(PORTAL_PW)
        s.jamb_subjects = SUBJECTS
        if not StudentEnrollment.query.filter_by(
                student_id=s.id, class_arm_assignment_id=caa.id).first():
            db.session.add(StudentEnrollment(student_id=s.id,
                                             class_arm_assignment_id=caa.id, is_active=True))
        rows.append((sid, PORTAL_PW))
    db.session.commit()

    exam = MockJAMBExam.query.filter_by(name='Load Test Mock JAMB').first()
    if not exam:
        exam = MockJAMBExam(name='Load Test Mock JAMB', exam_number=1,
                            session_id=sess.id, exam_date=date.today(),
                            is_published=True, duration_minutes=120,
                            eligible_levels=CLASS_NAME)
        db.session.add(exam); db.session.flush()
    else:
        exam.exam_date = date.today(); exam.is_published = True
        exam.eligible_levels = CLASS_NAME
    db.session.commit()
    return exam.id, rows


def write_csv(rows, path=CSV_PATH):
    with open(path, 'w', newline='') as fh:
        w = csv.writer(fh); w.writerow(['student_id', 'password']); w.writerows(rows)
    return path


def main():
    n = int(os.environ.get('N', '1000'))
    bank = int(os.environ.get('BANK', '600'))
    from app import app
    with app.app_context():
        exam_id, rows = seed_current_app(n, bank)
    path = write_csv(rows)
    print(f'Seeded {n} students + bank ({bank}/calc subject).')
    print(f'  EXAM_ID={exam_id}')
    print(f'  credentials -> {path}')
    print(f'\nRun:  EXAM_ID={exam_id} locust -f loadtest/locustfile_mock_jamb.py '
          f'--host https://<staging-url>')


if __name__ == '__main__':
    main()
