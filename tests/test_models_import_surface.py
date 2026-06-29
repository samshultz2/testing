"""Guard the public surface of `models.models` after splitting it into a package.
~25 modules do `from models.models import X`, so every previously-importable name must
stay importable from the package root (and the model classes must still be mappers)."""
import importlib


# A representative slice spanning every submodule + the base/helpers/schema kept in
# the package __init__. If any of these stops importing, the split dropped a re-export.
EXPECTED = [
    # base / helpers / schema (kept in __init__)
    'db', 'local_now', 'EncryptedString', '_INDEXES', '_ensure_indexes', 'init_db',
    # one or more classes from each submodule
    'Student', 'ParentContact',                                  # student
    'AcademicSession', 'Term', 'SchoolClass', 'ClassArmAssignment', 'StudentEnrollment',  # academics
    'Attendance',                                                # attendance
    'WAECResult', 'JAMBResult',                                  # external_exams
    'Subject', 'ClassSubject', 'GradeScale',                     # subjects
    'StudentScore', 'TermResult', 'TermSummary',                 # scores
    'ClassTimetable', 'TimetableBackup',                         # timetable
    'PromotionRule', 'PromotionRecord',                          # promotion
    'User', 'Teacher', 'TeacherSubjectAssignment',              # users
    'SchoolSettings', 'AuditLog', 'RateLimitHit',               # settings
    'GenTeacher', 'GenTimetableResult', 'GenSubjectClashRule',  # generator
]


def test_model_import_surface_intact():
    m = importlib.import_module('models.models')
    missing = [n for n in EXPECTED if not hasattr(m, n)]
    assert not missing, f'models.models lost these names after the split: {missing}'


def test_model_classes_are_mapped():
    m = importlib.import_module('models.models')
    for name in ('Student', 'WAECResult', 'GenTimetableResult', 'TermResult'):
        cls = getattr(m, name)
        assert issubclass(cls, m.db.Model), f'{name} is not a db.Model'
        assert hasattr(cls, '__tablename__')


def test_classes_are_same_object_via_models_package():
    # `from models import Student` and `from models.models import Student` must be
    # the identical class (no duplicate mapper registration).
    from models import Student as A
    from models.models import Student as B
    assert A is B
