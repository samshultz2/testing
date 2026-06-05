"""
Rule-based university admission / course-eligibility advisor.

Combines a student's best WAEC year (SSC credits) with their best JAMB score to
flag which broad course categories they currently qualify for. These are
general Nigerian admission guidelines — individual schools vary — so it's framed
as guidance, not a guarantee.
"""
from collections import defaultdict

PASS_GRADES = {'A1', 'B2', 'B3', 'C4', 'C5', 'C6'}

# Broad course categories with their typical SSC credit requirements and an
# indicative JAMB cut-off.
COURSE_CATEGORIES = [
    {'name': 'Medicine & Health Sciences',
     'required': ['English Language', 'Mathematics', 'Biology', 'Chemistry', 'Physics'], 'jamb': 250},
    {'name': 'Engineering & Technology',
     'required': ['English Language', 'Mathematics', 'Physics', 'Chemistry'], 'jamb': 200},
    {'name': 'Physical & Computer Sciences',
     'required': ['English Language', 'Mathematics', 'Physics'], 'jamb': 180},
    {'name': 'Agricultural & Biological Sciences',
     'required': ['English Language', 'Mathematics', 'Biology', 'Chemistry'], 'jamb': 180},
    {'name': 'Law',
     'required': ['English Language', 'Literature in English', 'Government'], 'jamb': 230},
    {'name': 'Social Sciences & Management',
     'required': ['English Language', 'Mathematics', 'Economics'], 'jamb': 200},
    {'name': 'Arts & Humanities',
     'required': ['English Language', 'Literature in English', 'Government'], 'jamb': 180},
    {'name': 'Education',
     'required': ['English Language', 'Mathematics'], 'jamb': 160},
]


def assess_admission(student):
    """Return an admission-readiness assessment for a student."""
    # Best WAEC year = the sitting with the most credit passes.
    by_year = defaultdict(dict)
    for r in student.waec_results.all():
        by_year[r.exam_year][r.subject] = r.grade

    best_credits = set()
    best_year = None
    for year, subs in by_year.items():
        credits = {s for s, g in subs.items() if g in PASS_GRADES}
        if len(credits) > len(best_credits):
            best_credits, best_year = credits, year

    jamb_scores = [r.total_score for r in student.jamb_results.all()]
    jamb_best = max(jamb_scores) if jamb_scores else 0

    has_english = 'English Language' in best_credits
    has_maths = 'Mathematics' in best_credits
    meets_ssc = len(best_credits) >= 5 and has_english and has_maths

    categories = []
    for c in COURSE_CATEGORIES:
        missing = [s for s in c['required'] if s not in best_credits]
        credit_ok = not missing
        jamb_ok = jamb_best >= c['jamb']
        categories.append({
            'name': c['name'],
            'jamb_required': c['jamb'],
            'credit_ok': credit_ok,
            'missing': missing,
            'jamb_ok': jamb_ok,
            'eligible': meets_ssc and credit_ok and jamb_ok,
        })

    categories.sort(key=lambda c: (not c['eligible'], c['jamb_required']))

    # Course-specific evaluation from the seeded requirements table.
    courses = []
    reference = 'General Requirements'
    try:
        import json
        from models import UniversityCutoff, SchoolSettings
        reference = SchoolSettings.get('admission_reference', 'General Requirements')
        rows = UniversityCutoff.query.filter_by(university_name=reference).all()
        if not rows and reference != 'General Requirements':
            reference = 'General Requirements'
            rows = UniversityCutoff.query.filter_by(university_name=reference).all()
        for cu in rows:
            required = json.loads(cu.required_subjects or '[]')
            missing = [s for s in required if s not in best_credits]
            min_credits = cu.min_credits or 5
            credit_ok = (not missing) and len(best_credits) >= min_credits
            jamb_ok = jamb_best >= (cu.jamb_cutoff or 0)
            courses.append({
                'course': cu.course_name,
                'faculty': cu.faculty,
                'jamb_required': cu.jamb_cutoff or 0,
                'required': required,
                'missing': missing,
                'credit_ok': credit_ok,
                'jamb_ok': jamb_ok,
                'eligible': meets_ssc and credit_ok and jamb_ok,
            })
        courses.sort(key=lambda c: (not c['eligible'], c['jamb_required'], c['course']))
    except Exception:
        courses = []

    eligible_courses = [c for c in courses if c['eligible']]

    if jamb_best >= 250:
        band = 'Highly competitive'
    elif jamb_best >= 200:
        band = 'Competitive (meets most cut-offs)'
    elif jamb_best >= 180:
        band = 'Eligible for many courses'
    elif jamb_best > 0:
        band = 'Below common cut-offs'
    else:
        band = 'No JAMB score yet'

    return {
        'best_year': best_year,
        'credit_count': len(best_credits),
        'has_english': has_english,
        'has_maths': has_maths,
        'meets_ssc': meets_ssc,
        'jamb_best': jamb_best,
        'jamb_band': band,
        'categories': categories,
        'eligible_count': sum(1 for c in categories if c['eligible']),
        'courses': courses,
        'eligible_courses': eligible_courses,
        'eligible_course_count': len(eligible_courses),
        'reference': reference,
    }
