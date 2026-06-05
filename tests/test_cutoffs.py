"""Course admission requirements are seeded into a fresh database."""
import json


def test_cutoffs_seeded(app):
    with app.app_context():
        from models import UniversityCutoff
        rows = UniversityCutoff.query.filter_by(university_name='General Requirements').all()
        assert len(rows) >= 30
        med = next(r for r in rows if r.course_name == 'Medicine & Surgery')
        assert med.jamb_cutoff == 250
        subjects = json.loads(med.required_subjects)
        assert 'Biology' in subjects and 'Chemistry' in subjects and 'Physics' in subjects


def test_seed_is_idempotent(app):
    with app.app_context():
        from models import db, UniversityCutoff
        from utils.cutoff_seed import seed_cutoffs
        before = UniversityCutoff.query.filter_by(university_name='General Requirements').count()
        added = seed_cutoffs(db, UniversityCutoff)
        after = UniversityCutoff.query.filter_by(university_name='General Requirements').count()
        assert added == 0
        assert before == after
