#!/usr/bin/env python3
"""
Seed a runnable CBT load test: N students enrolled in a class, with known portal
passwords, plus one published exam (today) with M questions and an access
password. Writes loadtest/students.csv and prints the EXAM_ID / ACCESS_PASSWORD.

    python loadtest/seed_loadtest.py            # 200 students, 40 questions
    N=800 M=50 python loadtest/seed_loadtest.py

Run this against your STAGING database (never production).
"""
import csv
import os
import sys
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app                                                    # noqa: E402
from models import (db, AcademicSession, Term, SchoolClass, ClassArm,    # noqa: E402
                    ClassArmAssignment, StudentEnrollment, Student,
                    CBTExam, CBTQuestion)

N = int(os.environ.get('N', '200'))
M = int(os.environ.get('M', '40'))
PORTAL_PW = os.environ.get('PORTAL_PASSWORD', 'pass123')
ACCESS_PW = os.environ.get('ACCESS_PASSWORD', 'exam123')
OPTS = ['A', 'B', 'C', 'D']


def get_or_create(model, defaults=None, **kw):
    obj = model.query.filter_by(**kw).first()
    if obj:
        return obj
    obj = model(**kw, **(defaults or {}))
    db.session.add(obj)
    db.session.flush()
    return obj


def main():
    with app.app_context():
        sess = get_or_create(AcademicSession, name='LOADTEST 24/25')
        AcademicSession.query.update({AcademicSession.is_active: False})
        sess.is_active = True
        term = get_or_create(Term, session_id=sess.id, term_number=1,
                             defaults={'name': 'First Term'})
        Term.query.update({Term.is_active: False})
        term.is_active = True
        sc = get_or_create(SchoolClass, name='LOADTEST', defaults={'level': 9})
        arm = get_or_create(ClassArm, name='LT', defaults={'is_active': True})
        caa = get_or_create(ClassArmAssignment, class_id=sc.id, arm_id=arm.id, term_id=term.id)

        # Students + enrolment + portal password
        rows = []
        for i in range(1, N + 1):
            sid = f'STULT{i:05d}'
            s = Student.query.filter_by(student_id=sid).first()
            if not s:
                s = Student(student_id=sid, first_name=f'Load{i}', surname='Test',
                            gender='Male', is_active=True, branch_id=None)
                db.session.add(s); db.session.flush()
            s.set_portal_password(PORTAL_PW)
            if not StudentEnrollment.query.filter_by(
                    student_id=s.id, class_arm_assignment_id=caa.id).first():
                db.session.add(StudentEnrollment(student_id=s.id,
                                                 class_arm_assignment_id=caa.id, is_active=True))
            rows.append((sid, PORTAL_PW))
        db.session.commit()

        # One published exam for today + M questions
        exam = CBTExam.query.filter_by(title='Load Test Exam', class_id=sc.id).first()
        if not exam:
            exam = CBTExam(title='Load Test Exam', class_id=sc.id, term_id=term.id,
                           exam_date=date.today(), duration_minutes=60,
                           access_password=ACCESS_PW, is_published=True,
                           strict_mode=False, shuffle=True)
            db.session.add(exam); db.session.flush()
        else:
            exam.exam_date = date.today(); exam.is_published = True
            exam.access_password = ACCESS_PW; exam.strict_mode = False
        if exam.questions.count() < M:
            for n in range(exam.questions.count() + 1, M + 1):
                db.session.add(CBTQuestion(
                    exam_id=exam.id, question_text=f'Question {n}: pick an option.',
                    option_a='Alpha', option_b='Bravo', option_c='Charlie', option_d='Delta',
                    correct_option=OPTS[n % 4], marks=1, order=n))
        db.session.commit()
        exam_id = exam.id

    out = os.path.join(os.path.dirname(__file__), 'students.csv')
    with open(out, 'w', newline='') as fh:
        w = csv.writer(fh); w.writerow(['student_id', 'password']); w.writerows(rows)

    print(f'Seeded {N} students, {M} questions.')
    print(f'  EXAM_ID={exam_id}')
    print(f'  ACCESS_PASSWORD={ACCESS_PW}')
    print(f'  credentials -> {out}')
    print(f'\nRun:  EXAM_ID={exam_id} ACCESS_PASSWORD={ACCESS_PW} \\')
    print(f'      locust -f loadtest/locustfile.py --host https://your-demo-url')


if __name__ == '__main__':
    main()
