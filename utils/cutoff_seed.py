"""
Seed data for course admission requirements.

These are the *standard* national O'level (SSCE) credit requirements per course
plus an indicative JAMB/UTME cut-off. Actual departmental cut-offs vary by
university and year, so the advisor frames results as guidance. Stored under a
synthetic ``university_name='General Requirements'`` with ``exam_year=0``.

Subject names match the school's WAEC subject list so the advisor can compare
them against a student's credits directly.
"""
import json

ENG = 'English Language'
MATH = 'Mathematics'
PHY = 'Physics'
CHEM = 'Chemistry'
BIO = 'Biology'
ECO = 'Economics'
GOV = 'Government'
LIT = 'Literature in English'
COM = 'Commerce'
ACC = 'Accounting'
AGR = 'Agricultural Science'
GEO = 'Geography'
CRS = 'Christian Religious Studies'

# (course, faculty, jamb_cutoff, [required O'level credit subjects])
COURSES = [
    # Medical & Health Sciences
    ('Medicine & Surgery', 'Medical Sciences', 250, [ENG, MATH, BIO, CHEM, PHY]),
    ('Dentistry', 'Medical Sciences', 240, [ENG, MATH, BIO, CHEM, PHY]),
    ('Pharmacy', 'Medical Sciences', 230, [ENG, MATH, BIO, CHEM, PHY]),
    ('Nursing Science', 'Medical Sciences', 200, [ENG, MATH, BIO, CHEM, PHY]),
    ('Medical Laboratory Science', 'Medical Sciences', 200, [ENG, MATH, BIO, CHEM, PHY]),
    ('Physiotherapy', 'Medical Sciences', 210, [ENG, MATH, BIO, CHEM, PHY]),
    ('Radiography', 'Medical Sciences', 200, [ENG, MATH, BIO, CHEM, PHY]),
    ('Veterinary Medicine', 'Medical Sciences', 200, [ENG, MATH, BIO, CHEM, PHY]),

    # Engineering & Technology
    ('Mechanical Engineering', 'Engineering', 200, [ENG, MATH, PHY, CHEM]),
    ('Electrical/Electronic Engineering', 'Engineering', 200, [ENG, MATH, PHY, CHEM]),
    ('Civil Engineering', 'Engineering', 190, [ENG, MATH, PHY, CHEM]),
    ('Chemical Engineering', 'Engineering', 200, [ENG, MATH, PHY, CHEM]),
    ('Computer Engineering', 'Engineering', 200, [ENG, MATH, PHY, CHEM]),
    ('Petroleum Engineering', 'Engineering', 220, [ENG, MATH, PHY, CHEM]),

    # Physical & Computer Sciences
    ('Computer Science', 'Sciences', 200, [ENG, MATH, PHY]),
    ('Cyber Security', 'Sciences', 190, [ENG, MATH, PHY]),
    ('Physics', 'Sciences', 180, [ENG, MATH, PHY]),
    ('Chemistry', 'Sciences', 180, [ENG, MATH, CHEM, PHY]),
    ('Microbiology', 'Sciences', 190, [ENG, MATH, BIO, CHEM, PHY]),
    ('Biochemistry', 'Sciences', 190, [ENG, MATH, BIO, CHEM, PHY]),
    ('Statistics', 'Sciences', 180, [ENG, MATH, PHY]),

    # Agriculture
    ('Agriculture', 'Agriculture', 160, [ENG, MATH, AGR, CHEM]),

    # Law
    ('Law', 'Law', 230, [ENG, LIT, GOV]),

    # Social & Management Sciences
    ('Accounting', 'Management Sciences', 210, [ENG, MATH, ECO, COM]),
    ('Economics', 'Social Sciences', 210, [ENG, MATH, ECO]),
    ('Business Administration', 'Management Sciences', 190, [ENG, MATH, ECO]),
    ('Banking & Finance', 'Management Sciences', 190, [ENG, MATH, ECO]),
    ('Mass Communication', 'Social Sciences', 210, [ENG, LIT, ECO]),
    ('Political Science', 'Social Sciences', 190, [ENG, GOV, ECO]),
    ('Sociology', 'Social Sciences', 180, [ENG, GOV]),
    ('Psychology', 'Social Sciences', 200, [ENG, MATH, BIO]),
    ('Geography', 'Social Sciences', 170, [ENG, GEO, MATH]),

    # Arts & Humanities
    ('English & Literary Studies', 'Arts', 190, [ENG, LIT]),
    ('History & International Studies', 'Arts', 170, [ENG, GOV]),
    ('Religious Studies', 'Arts', 160, [ENG, CRS]),
    ('Theatre Arts', 'Arts', 170, [ENG, LIT]),

    # Education
    ('Education (Sciences)', 'Education', 160, [ENG, MATH, BIO]),
    ('Education (Arts)', 'Education', 150, [ENG, LIT]),
    ('Guidance & Counselling', 'Education', 150, [ENG, MATH]),
]


def seed_cutoffs(db, UniversityCutoff):
    """Insert the standard course requirements if none exist. Idempotent."""
    if UniversityCutoff.query.filter_by(university_name='General Requirements').count() > 0:
        return 0
    added = 0
    for course, faculty, jamb, subjects in COURSES:
        db.session.add(UniversityCutoff(
            university_name='General Requirements',
            course_name=course,
            faculty=faculty,
            exam_year=0,
            jamb_cutoff=jamb,
            required_subjects=json.dumps(subjects),
            min_credits=5,
        ))
        added += 1
    db.session.commit()
    return added
