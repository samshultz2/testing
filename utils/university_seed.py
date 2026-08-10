"""Starter reference data for university aspirations — a representative set of
Nigerian universities and popular courses with representative competitive JAMB
cut-offs and the nationally-standard JAMB/WAEC subject requirements.

Idempotent: seeding again only fills gaps (matched by name), so it is safe to
re-run and safe to call when the tables are empty. Admins can add/edit everything
from Settings → Admissions data, so these values are a sensible starting point,
not gospel.
"""

# name, abbreviation, state, ownership, cutoff_bump
# A broad, representative spread of Nigerian universities — federal, state and
# private, across every geopolitical zone. The bump is a rough measure of how
# competitive the school runs above a course's national base cut-off; correct
# any of it on Settings → Admissions data.
_UNIVERSITIES = [
    # Federal — traditional / first & second generation
    ('University of Lagos', 'UNILAG', 'Lagos', 'Federal', 20),
    ('University of Ibadan', 'UI', 'Oyo', 'Federal', 20),
    ('University of Benin', 'UNIBEN', 'Edo', 'Federal', 15),
    ('University of Nigeria, Nsukka', 'UNN', 'Enugu', 'Federal', 15),
    ('Obafemi Awolowo University', 'OAU', 'Osun', 'Federal', 15),
    ('Ahmadu Bello University', 'ABU', 'Kaduna', 'Federal', 10),
    ('University of Ilorin', 'UNILORIN', 'Kwara', 'Federal', 10),
    ('University of Port Harcourt', 'UNIPORT', 'Rivers', 'Federal', 5),
    ('Nnamdi Azikiwe University', 'UNIZIK', 'Anambra', 'Federal', 5),
    ('Bayero University, Kano', 'BUK', 'Kano', 'Federal', 5),
    ('University of Abuja', 'UNIABUJA', 'FCT', 'Federal', 5),
    ('University of Calabar', 'UNICAL', 'Cross River', 'Federal', 5),
    ('University of Jos', 'UNIJOS', 'Plateau', 'Federal', 5),
    ('University of Maiduguri', 'UNIMAID', 'Borno', 'Federal', 0),
    ('University of Uyo', 'UNIUYO', 'Akwa Ibom', 'Federal', 5),
    ('Usmanu Danfodiyo University, Sokoto', 'UDUSOK', 'Sokoto', 'Federal', 0),
    ('University of Agriculture, Makurdi', 'FUAM', 'Benue', 'Federal', 0),
    ('Michael Okpara University of Agriculture', 'MOUAU', 'Abia', 'Federal', 0),
    ('University of Agriculture, Abeokuta', 'FUNAAB', 'Ogun', 'Federal', 5),
    # Federal universities of technology
    ('Federal University of Technology, Akure', 'FUTA', 'Ondo', 'Federal', 10),
    ('Federal University of Technology, Minna', 'FUTMINNA', 'Niger', 'Federal', 5),
    ('Federal University of Technology, Owerri', 'FUTO', 'Imo', 'Federal', 5),
    # Newer federal universities
    ('Federal University, Oye-Ekiti', 'FUOYE', 'Ekiti', 'Federal', 0),
    ('Federal University, Lokoja', 'FULOKOJA', 'Kogi', 'Federal', 0),
    ('Federal University, Dutse', 'FUD', 'Jigawa', 'Federal', 0),
    ('Federal University, Lafia', 'FULAFIA', 'Nasarawa', 'Federal', 0),
    ('Federal University, Ndufu-Alike Ikwo', 'FUNAI', 'Ebonyi', 'Federal', 0),
    ('Federal University, Otuoke', 'FUOTUOKE', 'Bayelsa', 'Federal', 0),
    ('Federal University, Wukari', 'FUWUKARI', 'Taraba', 'Federal', 0),
    ('Federal University, Gashua', 'FUGASHUA', 'Yobe', 'Federal', 0),
    ('Federal University, Kashere', 'FUKASHERE', 'Gombe', 'Federal', 0),
    ('Federal University, Dutsin-Ma', 'FUDMA', 'Katsina', 'Federal', 0),
    ('Nigerian Defence Academy', 'NDA', 'Kaduna', 'Federal', 10),
    ('National Open University of Nigeria', 'NOUN', 'FCT', 'Federal', 0),
    ('Nigeria Maritime University', 'NMU', 'Delta', 'Federal', 0),
    # State universities
    ('Lagos State University', 'LASU', 'Lagos', 'State', 5),
    ('Ekiti State University', 'EKSU', 'Ekiti', 'State', 0),
    ('Ambrose Alli University', 'AAU', 'Edo', 'State', 0),
    ('Rivers State University', 'RSU', 'Rivers', 'State', 0),
    ('Delta State University, Abraka', 'DELSU', 'Delta', 'State', 0),
    ('Enugu State University of Science and Technology', 'ESUT', 'Enugu', 'State', 0),
    ('Olabisi Onabanjo University', 'OOU', 'Ogun', 'State', 0),
    ('Ladoke Akintola University of Technology', 'LAUTECH', 'Oyo', 'State', 5),
    ('Kwara State University', 'KWASU', 'Kwara', 'State', 0),
    ('Osun State University', 'UNIOSUN', 'Osun', 'State', 0),
    ('Kaduna State University', 'KASU', 'Kaduna', 'State', 0),
    ('Imo State University', 'IMSU', 'Imo', 'State', 0),
    ('Abia State University', 'ABSU', 'Abia', 'State', 0),
    ('Benue State University', 'BSU', 'Benue', 'State', 0),
    ('Lagos State University of Science and Technology', 'LASUSTECH', 'Lagos', 'State', 0),
    ('Tai Solarin University of Education', 'TASUED', 'Ogun', 'State', 0),
    ('Chukwuemeka Odumegwu Ojukwu University', 'COOU', 'Anambra', 'State', 0),
    ('Ignatius Ajuru University of Education', 'IAUE', 'Rivers', 'State', 0),
    # Private
    ('Covenant University', 'CU', 'Ogun', 'Private', 10),
    ('Babcock University', 'BU', 'Ogun', 'Private', 5),
    ('Bowen University', 'BOWEN', 'Osun', 'Private', 0),
    ('Redeemer’s University', 'RUN', 'Osun', 'Private', 0),
    ('Landmark University', 'LMU', 'Kwara', 'Private', 5),
    ('Afe Babalola University', 'ABUAD', 'Ekiti', 'Private', 5),
    ('Pan-Atlantic University', 'PAU', 'Lagos', 'Private', 5),
    ('American University of Nigeria', 'AUN', 'Adamawa', 'Private', 5),
    ('Bells University of Technology', 'BELLS', 'Ogun', 'Private', 0),
    ('Bingham University', 'BHU', 'Nasarawa', 'Private', 0),
    ('Baze University', 'BAZE', 'FCT', 'Private', 0),
    ('Nile University of Nigeria', 'NILE', 'FCT', 'Private', 0),
    ('Lead City University', 'LCU', 'Oyo', 'Private', 0),
    ('Elizade University', 'EU', 'Ondo', 'Private', 0),
    ('Augustine University', 'AUI', 'Lagos', 'Private', 0),
    ('Mountain Top University', 'MTU', 'Ogun', 'Private', 0),
]

_ENG = 'English Language'
_MTH = 'Mathematics'
_BIO = 'Biology'
_CHM = 'Chemistry'
_PHY = 'Physics'
_ECO = 'Economics'
_GOV = 'Government'
_LIT = 'Literature in English'
_CRS = 'Christian Religious Studies'
_GEO = 'Geography'
_COM = 'Commerce'
_FMT = 'Further Mathematics'
_AGR = 'Agricultural Science'

# Common requirement groupings.
_SCI4 = [_ENG, _BIO, _CHM, _PHY]                       # JAMB science (bio-leaning)
_SCI_WAEC = [_ENG, _MTH, _BIO, _CHM, _PHY]             # WAEC science
_ENGR_JAMB = [_ENG, _MTH, _PHY, _CHM]                  # JAMB engineering/phys-sci
_ENGR_WAEC = [_ENG, _MTH, _PHY, _CHM, _FMT]            # WAEC engineering
_MED = [_ENG, _BIO, _CHM, _PHY]                        # medical/health JAMB
_MGMT_JAMB = [_ENG, _MTH, _ECO, _COM]
_MGMT_WAEC = [_ENG, _MTH, _ECO, _COM, 'Financial Accounting']
_SOC_JAMB = [_ENG, _ECO, _GOV, _MTH]
_SOC_WAEC = [_ENG, _MTH, _ECO, _GOV, _COM]
_ARTS_JAMB = [_ENG, _LIT, _GOV, _CRS]
_ARTS_WAEC = [_ENG, _MTH, _LIT, _GOV, _CRS]

# name, department, base_cutoff, jamb_subjects, waec_subjects
_COURSES = [
    # ---- Medical & health sciences ----
    ('Medicine and Surgery', 'Medical Sciences', 280, _MED, _SCI_WAEC),
    ('Dentistry', 'Medical Sciences', 260, _MED, _SCI_WAEC),
    ('Nursing Science', 'Medical Sciences', 250, _MED, _SCI_WAEC),
    ('Pharmacy', 'Pharmaceutical Sciences', 260, _MED, _SCI_WAEC),
    ('Medical Laboratory Science', 'Medical Sciences', 240, _MED, _SCI_WAEC),
    ('Physiotherapy', 'Medical Sciences', 245, _MED, _SCI_WAEC),
    ('Radiography', 'Medical Sciences', 240, _MED, _SCI_WAEC),
    ('Optometry', 'Medical Sciences', 235, _MED, _SCI_WAEC),
    ('Human Anatomy', 'Basic Medical Sciences', 220, _MED, _SCI_WAEC),
    ('Human Physiology', 'Basic Medical Sciences', 220, _MED, _SCI_WAEC),
    ('Public Health', 'Medical Sciences', 210, _MED, _SCI_WAEC),
    ('Veterinary Medicine', 'Veterinary Sciences', 230, _MED, _SCI_WAEC),
    ('Dietetics and Nutrition', 'Medical Sciences', 210, _MED, _SCI_WAEC),

    # ---- Engineering & technology ----
    ('Mechanical Engineering', 'Engineering', 250, _ENGR_JAMB, _ENGR_WAEC),
    ('Mechatronics Engineering', 'Engineering', 250, _ENGR_JAMB, _ENGR_WAEC),
    ('Electrical/Electronic Engineering', 'Engineering', 250, _ENGR_JAMB, _ENGR_WAEC),
    ('Civil Engineering', 'Engineering', 240, _ENGR_JAMB, _ENGR_WAEC),
    ('Chemical Engineering', 'Engineering', 250, _ENGR_JAMB, _ENGR_WAEC),
    ('Computer Engineering', 'Engineering', 250, _ENGR_JAMB, _ENGR_WAEC),
    ('Petroleum Engineering', 'Engineering', 255, _ENGR_JAMB, _ENGR_WAEC),
    ('Aeronautical Engineering', 'Engineering', 250, _ENGR_JAMB, _ENGR_WAEC),
    ('Aerospace Engineering', 'Engineering', 250, _ENGR_JAMB, _ENGR_WAEC),
    ('Agricultural Engineering', 'Engineering', 220, _ENGR_JAMB, _ENGR_WAEC),
    ('Biomedical Engineering', 'Engineering', 250, _ENGR_JAMB, _ENGR_WAEC),
    ('Marine Engineering', 'Engineering', 235, _ENGR_JAMB, _ENGR_WAEC),
    ('Metallurgical and Materials Engineering', 'Engineering', 235, _ENGR_JAMB, _ENGR_WAEC),
    ('Mining Engineering', 'Engineering', 230, _ENGR_JAMB, _ENGR_WAEC),
    ('Production Engineering', 'Engineering', 235, _ENGR_JAMB, _ENGR_WAEC),
    ('Industrial and Production Engineering', 'Engineering', 235, _ENGR_JAMB, _ENGR_WAEC),
    ('Systems Engineering', 'Engineering', 245, _ENGR_JAMB, _ENGR_WAEC),
    ('Structural Engineering', 'Engineering', 240, _ENGR_JAMB, _ENGR_WAEC),
    ('Materials and Metallurgical Engineering', 'Engineering', 235, _ENGR_JAMB, _ENGR_WAEC),
    ('Food Science and Technology', 'Technology', 220, _SCI4, _SCI_WAEC),

    # ---- Physical / computing sciences ----
    ('Computer Science', 'Physical Sciences', 240, _ENGR_JAMB, [_ENG, _MTH, _PHY, _CHM, _BIO]),
    ('Software Engineering', 'Computing', 245, _ENGR_JAMB, [_ENG, _MTH, _PHY, _CHM, _BIO]),
    ('Cyber Security', 'Computing', 240, _ENGR_JAMB, [_ENG, _MTH, _PHY, _CHM, _BIO]),
    ('Information Technology', 'Computing', 230, _ENGR_JAMB, [_ENG, _MTH, _PHY, _CHM, _BIO]),
    ('Data Science', 'Computing', 240, _ENGR_JAMB, [_ENG, _MTH, _PHY, _CHM, _ECO]),
    ('Physics', 'Physical Sciences', 200, _ENGR_JAMB, _SCI_WAEC),
    ('Mathematics', 'Physical Sciences', 200, [_ENG, _MTH, _PHY, _CHM], [_ENG, _MTH, _PHY, _CHM, _FMT]),
    ('Statistics', 'Physical Sciences', 200, [_ENG, _MTH, _PHY, _ECO], [_ENG, _MTH, _PHY, _ECO, _FMT]),
    ('Chemistry', 'Physical Sciences', 200, [_ENG, _CHM, _MTH, _PHY], _SCI_WAEC),
    ('Industrial Chemistry', 'Physical Sciences', 200, [_ENG, _CHM, _MTH, _PHY], _SCI_WAEC),
    ('Geology', 'Physical Sciences', 200, [_ENG, _CHM, _MTH, _PHY], _SCI_WAEC),

    # ---- Biological sciences ----
    ('Biology', 'Biological Sciences', 200, _SCI4, _SCI_WAEC),
    ('Microbiology', 'Biological Sciences', 210, _SCI4, _SCI_WAEC),
    ('Biochemistry', 'Biological Sciences', 220, _SCI4, _SCI_WAEC),
    ('Biotechnology', 'Biological Sciences', 215, _SCI4, _SCI_WAEC),
    ('Botany', 'Biological Sciences', 190, _SCI4, _SCI_WAEC),
    ('Zoology', 'Biological Sciences', 190, _SCI4, _SCI_WAEC),
    ('Genetics', 'Biological Sciences', 210, _SCI4, _SCI_WAEC),

    # ---- Environmental & agriculture ----
    ('Architecture', 'Environmental Sciences', 240, _ENGR_JAMB, [_ENG, _MTH, _PHY, _CHM, 'Fine Art']),
    ('Estate Management', 'Environmental Sciences', 200, [_ENG, _MTH, _ECO, _GEO], [_ENG, _MTH, _ECO, _GEO, _PHY]),
    ('Quantity Surveying', 'Environmental Sciences', 210, _ENGR_JAMB, _ENGR_WAEC),
    ('Surveying and Geoinformatics', 'Environmental Sciences', 200, _ENGR_JAMB, _SCI_WAEC),
    ('Urban and Regional Planning', 'Environmental Sciences', 200, [_ENG, _GEO, _ECO, _MTH], [_ENG, _MTH, _GEO, _ECO, _PHY]),
    ('Building Technology', 'Environmental Sciences', 200, _ENGR_JAMB, _ENGR_WAEC),
    ('Agricultural Science', 'Agriculture', 190, [_ENG, _BIO, _CHM, _GEO], [_ENG, _MTH, _BIO, _CHM, _AGR]),
    ('Agricultural Economics', 'Agriculture', 190, [_ENG, _BIO, _CHM, _ECO], [_ENG, _MTH, _BIO, _CHM, _AGR]),
    ('Animal Science', 'Agriculture', 190, _SCI4, [_ENG, _MTH, _BIO, _CHM, _AGR]),
    ('Fisheries and Aquaculture', 'Agriculture', 185, _SCI4, [_ENG, _MTH, _BIO, _CHM, _AGR]),
    ('Forestry and Wildlife', 'Agriculture', 185, _SCI4, [_ENG, _MTH, _BIO, _CHM, _AGR]),

    # ---- Management & social sciences ----
    ('Accounting', 'Management Sciences', 230, _MGMT_JAMB, _MGMT_WAEC),
    ('Banking and Finance', 'Management Sciences', 220, _MGMT_JAMB, _MGMT_WAEC),
    ('Business Administration', 'Management Sciences', 210, _MGMT_JAMB, [_ENG, _MTH, _ECO, _COM, _GOV]),
    ('Marketing', 'Management Sciences', 200, _MGMT_JAMB, [_ENG, _MTH, _ECO, _COM, _GOV]),
    ('Actuarial Science', 'Management Sciences', 220, [_ENG, _MTH, _ECO, _PHY], [_ENG, _MTH, _ECO, _PHY, _FMT]),
    ('Insurance', 'Management Sciences', 195, _MGMT_JAMB, _MGMT_WAEC),
    ('Public Administration', 'Management Sciences', 195, _SOC_JAMB, _SOC_WAEC),
    ('Economics', 'Social Sciences', 230, [_ENG, _MTH, _ECO, _GOV], [_ENG, _MTH, _ECO, _GOV, _COM]),
    ('Political Science', 'Social Sciences', 210, [_ENG, _GOV, _ECO, _LIT], [_ENG, _MTH, _GOV, _ECO, _LIT]),
    ('Sociology', 'Social Sciences', 200, _SOC_JAMB, _SOC_WAEC),
    ('Psychology', 'Social Sciences', 210, [_ENG, _BIO, _ECO, _GOV], [_ENG, _MTH, _BIO, _ECO, _GOV]),
    ('International Relations', 'Social Sciences', 215, [_ENG, _GOV, _ECO, _LIT], [_ENG, _MTH, _GOV, _ECO, _LIT]),
    ('Geography', 'Social Sciences', 190, [_ENG, _GEO, _ECO, _MTH], [_ENG, _MTH, _GEO, _ECO, _PHY]),
    ('Criminology and Security Studies', 'Social Sciences', 200, _SOC_JAMB, _SOC_WAEC),
    ('Social Work', 'Social Sciences', 190, _SOC_JAMB, _SOC_WAEC),

    # ---- Law ----
    ('Law', 'Law', 250, _ARTS_JAMB, [_ENG, _MTH, _LIT, _GOV, _ECO]),

    # ---- Communication & media ----
    ('Mass Communication', 'Communication', 230, [_ENG, _LIT, _GOV, _ECO], [_ENG, _MTH, _LIT, _GOV, _ECO]),
    ('Journalism', 'Communication', 210, [_ENG, _LIT, _GOV, _ECO], [_ENG, _MTH, _LIT, _GOV, _ECO]),
    ('Film and Multimedia', 'Communication', 195, [_ENG, _LIT, _GOV, 'Fine Art'], [_ENG, _MTH, _LIT, _GOV, 'Fine Art']),

    # ---- Arts & humanities ----
    ('English Language', 'Arts', 200, _ARTS_JAMB, _ARTS_WAEC),
    ('History and International Studies', 'Arts', 185, [_ENG, _GOV, _LIT, _CRS], _ARTS_WAEC),
    ('Philosophy', 'Arts', 185, [_ENG, _GOV, _LIT, _CRS], _ARTS_WAEC),
    ('Theatre Arts', 'Arts', 185, [_ENG, _LIT, _GOV, _CRS], _ARTS_WAEC),
    ('Linguistics', 'Arts', 185, [_ENG, _LIT, _GOV, _CRS], _ARTS_WAEC),
    ('Religious Studies', 'Arts', 180, [_ENG, _CRS, _GOV, _LIT], _ARTS_WAEC),
    ('French', 'Arts', 185, [_ENG, 'French', _LIT, _GOV], [_ENG, _MTH, 'French', _LIT, _GOV]),
    ('Fine and Applied Arts', 'Arts', 185, [_ENG, 'Fine Art', _LIT, _GOV], [_ENG, _MTH, 'Fine Art', _LIT, _GOV]),
    ('Music', 'Arts', 180, [_ENG, 'Music', _LIT, _GOV], [_ENG, _MTH, 'Music', _LIT, _GOV]),

    # ---- Education ----
    ('Education and Biology', 'Education', 180, _SCI4, _SCI_WAEC),
    ('Education and English Language', 'Education', 180, _ARTS_JAMB, _ARTS_WAEC),
    ('Education and Mathematics', 'Education', 180, [_ENG, _MTH, _PHY, _CHM], [_ENG, _MTH, _PHY, _CHM, _FMT]),
    ('Guidance and Counselling', 'Education', 180, _SOC_JAMB, _SOC_WAEC),
    ('Human Kinetics and Health Education', 'Education', 180, _SCI4, _SCI_WAEC),
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
