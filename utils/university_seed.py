"""Starter reference data for university aspirations — a representative set of
Nigerian universities and popular courses with representative competitive JAMB
cut-offs and the nationally-standard JAMB/WAEC subject requirements.

Idempotent: seeding again only fills gaps (matched by name), so it is safe to
re-run and safe to call when the tables are empty. Admins can add/edit everything
from Settings → Admissions data, so these values are a sensible starting point,
not gospel.
"""

# name, abbreviation, state, ownership, cutoff_bump
_UNIVERSITIES = [
    ('University of Lagos', 'UNILAG', 'Lagos', 'Federal', 20),
    ('University of Ibadan', 'UI', 'Oyo', 'Federal', 20),
    ('University of Benin', 'UNIBEN', 'Edo', 'Federal', 15),
    ('University of Nigeria, Nsukka', 'UNN', 'Enugu', 'Federal', 15),
    ('Obafemi Awolowo University', 'OAU', 'Osun', 'Federal', 15),
    ('Ahmadu Bello University', 'ABU', 'Kaduna', 'Federal', 10),
    ('University of Ilorin', 'UNILORIN', 'Kwara', 'Federal', 10),
    ('Federal University of Technology, Akure', 'FUTA', 'Ondo', 'Federal', 10),
    ('Covenant University', 'CU', 'Ogun', 'Private', 10),
    ('University of Port Harcourt', 'UNIPORT', 'Rivers', 'Federal', 5),
    ('Nnamdi Azikiwe University', 'UNIZIK', 'Anambra', 'Federal', 5),
    ('Bayero University, Kano', 'BUK', 'Kano', 'Federal', 5),
    ('Lagos State University', 'LASU', 'Lagos', 'State', 5),
    ('Babcock University', 'BU', 'Ogun', 'Private', 5),
    ('University of Abuja', 'UNIABUJA', 'FCT', 'Federal', 0),
    ('Ekiti State University', 'EKSU', 'Ekiti', 'State', 0),
]

_ENG = 'English Language'
_MTH = 'Mathematics'
# name, department, base_cutoff, jamb_subjects, waec_subjects
_COURSES = [
    ('Medicine and Surgery', 'Medical Sciences', 280,
     [_ENG, 'Biology', 'Chemistry', 'Physics'], [_ENG, _MTH, 'Biology', 'Chemistry', 'Physics']),
    ('Nursing Science', 'Medical Sciences', 250,
     [_ENG, 'Biology', 'Chemistry', 'Physics'], [_ENG, _MTH, 'Biology', 'Chemistry', 'Physics']),
    ('Pharmacy', 'Pharmaceutical Sciences', 260,
     [_ENG, 'Biology', 'Chemistry', 'Physics'], [_ENG, _MTH, 'Biology', 'Chemistry', 'Physics']),
    ('Medical Laboratory Science', 'Medical Sciences', 240,
     [_ENG, 'Biology', 'Chemistry', 'Physics'], [_ENG, _MTH, 'Biology', 'Chemistry', 'Physics']),
    ('Law', 'Law', 250,
     [_ENG, 'Literature in English', 'Government', 'Christian Religious Studies'],
     [_ENG, _MTH, 'Literature in English', 'Government', 'Economics']),
    ('Computer Science', 'Physical Sciences', 240,
     [_ENG, _MTH, 'Physics', 'Chemistry'], [_ENG, _MTH, 'Physics', 'Chemistry', 'Biology']),
    ('Mechanical Engineering', 'Engineering', 250,
     [_ENG, _MTH, 'Physics', 'Chemistry'], [_ENG, _MTH, 'Physics', 'Chemistry', 'Further Mathematics']),
    ('Electrical/Electronic Engineering', 'Engineering', 250,
     [_ENG, _MTH, 'Physics', 'Chemistry'], [_ENG, _MTH, 'Physics', 'Chemistry', 'Further Mathematics']),
    ('Civil Engineering', 'Engineering', 240,
     [_ENG, _MTH, 'Physics', 'Chemistry'], [_ENG, _MTH, 'Physics', 'Chemistry', 'Further Mathematics']),
    ('Architecture', 'Environmental Sciences', 240,
     [_ENG, _MTH, 'Physics', 'Chemistry'], [_ENG, _MTH, 'Physics', 'Chemistry', 'Fine Art']),
    ('Accounting', 'Management Sciences', 230,
     [_ENG, _MTH, 'Economics', 'Commerce'], [_ENG, _MTH, 'Economics', 'Commerce', 'Financial Accounting']),
    ('Business Administration', 'Management Sciences', 210,
     [_ENG, _MTH, 'Economics', 'Commerce'], [_ENG, _MTH, 'Economics', 'Commerce', 'Government']),
    ('Economics', 'Social Sciences', 230,
     [_ENG, _MTH, 'Economics', 'Government'], [_ENG, _MTH, 'Economics', 'Government', 'Commerce']),
    ('Mass Communication', 'Communication', 230,
     [_ENG, 'Literature in English', 'Government', 'Economics'],
     [_ENG, _MTH, 'Literature in English', 'Government', 'Economics']),
    ('Political Science', 'Social Sciences', 210,
     [_ENG, 'Government', 'Economics', 'Literature in English'],
     [_ENG, _MTH, 'Government', 'Economics', 'Literature in English']),
    ('Microbiology', 'Biological Sciences', 210,
     [_ENG, 'Biology', 'Chemistry', 'Physics'], [_ENG, _MTH, 'Biology', 'Chemistry', 'Physics']),
    ('Biochemistry', 'Biological Sciences', 220,
     [_ENG, 'Biology', 'Chemistry', 'Physics'], [_ENG, _MTH, 'Biology', 'Chemistry', 'Physics']),
    ('Agricultural Science', 'Agriculture', 190,
     [_ENG, 'Biology', 'Chemistry', 'Geography'], [_ENG, _MTH, 'Biology', 'Chemistry', 'Agricultural Science']),
    ('Estate Management', 'Environmental Sciences', 200,
     [_ENG, _MTH, 'Economics', 'Geography'], [_ENG, _MTH, 'Economics', 'Geography', 'Physics']),
    ('English Language', 'Arts', 200,
     [_ENG, 'Literature in English', 'Government', 'Christian Religious Studies'],
     [_ENG, _MTH, 'Literature in English', 'Government', 'Christian Religious Studies']),
]

# Representative per-university, per-department competitive cut-offs. A university
# doesn't use one flat number for every course — competitive departments (e.g.
# Engineering, Medicine, Law) sit well above the school's general line — so these
# pin the real departmental target for the popular combos. Anything not listed
# falls back to course base + the university's bump. Illustrative starting
# values; correct them on Settings → Admissions data.
_MATRIX = {
    'UNILAG': {'Medicine and Surgery': 300, 'Pharmacy': 285, 'Nursing Science': 275, 'Law': 280,
               'Computer Science': 265, 'Mechanical Engineering': 260, 'Electrical/Electronic Engineering': 262,
               'Civil Engineering': 255, 'Accounting': 255, 'Economics': 250, 'Mass Communication': 250,
               'Architecture': 255, 'Business Administration': 245},
    'UI': {'Medicine and Surgery': 298, 'Pharmacy': 282, 'Nursing Science': 270, 'Law': 278,
           'Computer Science': 255, 'Mechanical Engineering': 250, 'Electrical/Electronic Engineering': 252,
           'Civil Engineering': 248, 'Accounting': 248, 'Economics': 245, 'Mass Communication': 245,
           'Architecture': 248},
    'UNIBEN': {'Medicine and Surgery': 290, 'Pharmacy': 275, 'Nursing Science': 265, 'Law': 262,
               'Computer Science': 250, 'Mechanical Engineering': 252, 'Electrical/Electronic Engineering': 252,
               'Civil Engineering': 248, 'Accounting': 245, 'Economics': 240, 'Architecture': 245},
    'UNN': {'Medicine and Surgery': 290, 'Pharmacy': 272, 'Nursing Science': 262, 'Law': 258,
            'Computer Science': 248, 'Mechanical Engineering': 245, 'Electrical/Electronic Engineering': 246,
            'Civil Engineering': 242, 'Accounting': 242, 'Architecture': 244},
    'OAU': {'Medicine and Surgery': 292, 'Pharmacy': 278, 'Nursing Science': 266, 'Law': 265,
            'Computer Science': 252, 'Mechanical Engineering': 250, 'Electrical/Electronic Engineering': 252,
            'Civil Engineering': 246, 'Accounting': 246, 'Architecture': 248},
    'ABU': {'Medicine and Surgery': 275, 'Pharmacy': 255, 'Nursing Science': 245, 'Law': 245,
            'Computer Science': 235, 'Mechanical Engineering': 235, 'Civil Engineering': 232, 'Accounting': 230},
    'UNILORIN': {'Medicine and Surgery': 270, 'Pharmacy': 255, 'Nursing Science': 248, 'Law': 248,
                 'Computer Science': 238, 'Mechanical Engineering': 235, 'Accounting': 235},
    'FUTA': {'Computer Science': 250, 'Mechanical Engineering': 248, 'Electrical/Electronic Engineering': 250,
             'Civil Engineering': 245, 'Architecture': 245, 'Microbiology': 220, 'Biochemistry': 228},
    'UNIPORT': {'Medicine and Surgery': 270, 'Pharmacy': 255, 'Nursing Science': 248, 'Law': 248,
                'Computer Science': 235, 'Accounting': 232},
    'UNIZIK': {'Medicine and Surgery': 270, 'Pharmacy': 252, 'Nursing Science': 245, 'Law': 245,
               'Computer Science': 235, 'Accounting': 230},
    'LASU': {'Medicine and Surgery': 260, 'Nursing Science': 240, 'Law': 245, 'Computer Science': 230,
             'Accounting': 228, 'Mass Communication': 235},
    'CU': {'Computer Science': 250, 'Mechanical Engineering': 245, 'Electrical/Electronic Engineering': 245,
           'Accounting': 240, 'Mass Communication': 240, 'Business Administration': 235},
}
_OVERRIDES = [(abbr, cname, cutoff)
              for abbr, courses in _MATRIX.items()
              for cname, cutoff in courses.items()]


def seed_university_data():
    """Fill any missing universities/courses/overrides. Returns a small summary."""
    from models import db, University, Course, UniversityCourse
    added = {'universities': 0, 'courses': 0, 'overrides': 0}

    by_abbr = {}
    for name, abbr, state, ownership, bump in _UNIVERSITIES:
        u = University.query.filter_by(name=name).first()
        if not u:
            u = University(name=name, abbreviation=abbr, state=state,
                           ownership=ownership, cutoff_bump=bump, is_active=True)
            db.session.add(u); added['universities'] += 1
        by_abbr[abbr] = u
    db.session.flush()

    by_course = {}
    for name, dept, base, jamb, waec in _COURSES:
        c = Course.query.filter_by(name=name).first()
        if not c:
            c = Course(name=name, department=dept, base_cutoff=base,
                       jamb_subjects=', '.join(jamb), waec_subjects=', '.join(waec),
                       is_active=True)
            db.session.add(c); added['courses'] += 1
        by_course[name] = c
    db.session.flush()

    for abbr, cname, cutoff in _OVERRIDES:
        u, c = by_abbr.get(abbr), by_course.get(cname)
        if not (u and c):
            continue
        if not UniversityCourse.query.filter_by(university_id=u.id, course_id=c.id).first():
            db.session.add(UniversityCourse(university_id=u.id, course_id=c.id,
                                            jamb_cutoff=cutoff, is_active=True))
            added['overrides'] += 1
    db.session.commit()
    return added
