"""
Models package initialization
"""
from .models import (
    db, local_now, init_db,
    Student, ParentContact,
    AcademicSession, Term, SchoolClass, ClassArm, ClassArmAssignment, StudentEnrollment,
    Week, Holiday, Attendance,
    WAECResult, JAMBResult,
    SchoolSettings, GradeScale,
    Subject, ClassSubject, AssessmentType, SubjectAssessmentOverride,
    StudentScore, TermResult, TermSummary,
    TimetableSlot, ClassTimetable,
    PromotionRule, PromotionRecord,
    User, Teacher, TeacherClassAssignment, TeacherSubjectAssignment,
    GenTeacher, GenTeacherSubject, GenTeacherAvailability, GenSubject, GenSubjectConfig,
    GenClassSubjectConfig, GenClassStreamSubject, GenStream, GenStreamSubject, GenRoom,
    GenClassConfig, GenClassArmStream,
    GenTeacherAssignment, GenTimetableRule, GenTimetableResult, GenSettings,
    GenSubjectClashRule, GenCombinedClassRule
)
from .models_contributions import ContributionSettings, ContributionPayment, ContributionExpense

__all__ = [
    'db', 'local_now', 'init_db',
    'Student', 'ParentContact',
    'AcademicSession', 'Term', 'SchoolClass', 'ClassArm', 'ClassArmAssignment', 'StudentEnrollment',
    'Week', 'Holiday', 'Attendance',
    'WAECResult', 'JAMBResult',
    'SchoolSettings', 'GradeScale',
    'Subject', 'ClassSubject', 'AssessmentType', 'SubjectAssessmentOverride',
    'StudentScore', 'TermResult', 'TermSummary',
    'TimetableSlot', 'ClassTimetable',
    'PromotionRule', 'PromotionRecord',
    'User', 'Teacher', 'TeacherClassAssignment', 'TeacherSubjectAssignment',
    'GenTeacher', 'GenTeacherSubject', 'GenTeacherAvailability', 'GenSubject', 'GenSubjectConfig',
    'GenClassSubjectConfig', 'GenClassStreamSubject', 'GenStream', 'GenStreamSubject', 'GenRoom',
    'GenClassConfig', 'GenClassArmStream',
    'GenTeacherAssignment', 'GenTimetableRule', 'GenTimetableResult', 'GenSettings',
    'GenSubjectClashRule', 'GenCombinedClassRule',
    'ContributionSettings', 'ContributionPayment', 'ContributionExpense'
]

# Analytics models
from models.analytics_models import (
    InternalExam, InternalExamResult, StudentPerformanceSnapshot,
    SubjectPerformanceMetrics, WAECJAMBCorrelation, UniversityCutoff,
    StudentRiskAssessment, AcademicPrediction, AnalyticsCache
)

# Mock JAMB Models
from models.mock_jamb import MockJAMBExam, MockJAMBResult, MockJAMBAnalytics
