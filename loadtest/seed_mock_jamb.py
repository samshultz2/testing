#!/usr/bin/env python3
"""Seed a runnable Mock-JAMB online sitting load test on STAGING (never prod):
N students (portal password, enrolled in a LOADTEST class eligible for the mock,
registered for 4 JAMB subjects) + a shared question BANK (mock_exam_id NULL) with
English passages and four subjects, + one published mock for today.

    N=1000 BANK=600 python loadtest/seed_mock_jamb.py

Writes loadtest/students.csv and prints EXAM_ID. Then run:
    EXAM_ID=<id> locust -f loadtest/locustfile_mock_jamb.py --host https://<staging>
"""
import csv
import os
import sys
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app                                                     # noqa: E402
from models import (db, AcademicSession, Term, SchoolClass, ClassArm,     # noqa: E402
                    ClassArmAssignment, StudentEnrollment, Student, Subject,
                    MockJAMBExam, MockJAMBQuestion, MockJAMBPassage)

N = int(os.environ.get('N', '1000'))
BANK = int(os.environ.get('BANK', '600'))        # bank questions per calc subject
PORTAL_PW = os.environ.get('PORTAL_PASSWORD', 'pass123')
SUBJECTS = 'English Language,Mathematics,Physics,Chemistry'
CLASS_NAME = 'LOADTEST'


def goc(model, defaults=None, **kw):
    o = model.query.filter_by(**kw).first()
    if o:
        return o
    o = model(**kw, **(defaults or {})); db.session.add(o); db.session.flush()
    return o


def _seed_bank():
    """Create the shared bank (mock_exam_id NULL) once, if it isn't there yet."""
    eng = goc(Subject, name='English Language', defaults={'is_active': True})
    calc = [goc(Subject, name=n, defaults={'is_active': True})
            for n in ('Mathematics', 'Physics', 'Chemistry')]
    if MockJAMBQuestion.query.filter_by(subject_id=eng.id, mock_exam_id=None).count() >= 200:
        return                                     # already seeded
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
        for i in range(BANK):
            db.session.add(MockJAMBQuestion(
                mock_exam_id=None, subject_id=s.id,
                section=['number', 'algebra', 'geometry', 'calculus', 'statistics'][i % 5],
                question_text=f'{s.name} Q{i}', option_a='a', option_b='b', option_c='c',
                option_d='d', correct_option='A', order=i))
    db.session.commit()


def main():
    with app.app_context():
        sess = goc(AcademicSession, name='LOADTEST 24/25')
        AcademicSession.query.update({AcademicSession.is_active: False})
        sess.is_active = True
        term = goc(Term, session_id=sess.id, term_number=1, defaults={'name': 'First Term'})
        Term.query.update({Term.is_active: False}); term.is_active = True
        sc = goc(SchoolClass, name=CLASS_NAME, defaults={'level': 12})
        arm = goc(ClassArm, name='LT', defaults={'is_active': True})
        caa = goc(ClassArmAssignment, class_id=sc.id, arm_id=arm.id, term_id=term.id)

        _seed_bank()

        rows = []
        for i in range(1, N + 1):
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
                                eligible_levels=CLASS_NAME)   # this class may sit it
            db.session.add(exam); db.session.flush()
        else:
            exam.exam_date = date.today(); exam.is_published = True
            exam.eligible_levels = CLASS_NAME
        db.session.commit()
        exam_id = exam.id

    out = os.path.join(os.path.dirname(__file__), 'students.csv')
    with open(out, 'w', newline='') as fh:
        w = csv.writer(fh); w.writerow(['student_id', 'password']); w.writerows(rows)

    print(f'Seeded {N} students + bank ({BANK}/calc subject).')
    print(f'  EXAM_ID={exam_id}')
    print(f'  credentials -> {out}')
    print(f'\nRun:  EXAM_ID={exam_id} locust -f loadtest/locustfile_mock_jamb.py '
          f'--host https://<staging-url>')


if __name__ == '__main__':
    main()
