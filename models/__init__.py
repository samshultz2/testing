"""
Models package initialization
"""
from .models import (
    db, local_now, init_db,
    Student, ParentContact,
    AcademicSession, Term, SchoolClass, ClassArm, ClassArmAssignment, StudentEnrollment,
    Week, Holiday, Attendance,
    WAECResult, JAMBResult,
    SchoolSettings, GradeScale, BehaviouralTrait,
    Subject, ClassSubject, AssessmentType, SubjectAssessmentOverride,
    StudentScore, TermResult, TermSummary,
    TimetableSlot, ClassTimetable, TimetableBackup,
    PromotionRule, PromotionRecord,
    User, PermissionGroup, Teacher, TeacherClassAssignment, TeacherSubjectAssignment,
    AuditLog,
    GenTeacher, GenTeacherSubject, GenTeacherAvailability, GenSubject, GenSubjectConfig,
    GenClassSubjectConfig, GenClassStreamSubject, GenStream, GenStreamSubject, GenRoom,
    GenClassConfig, GenClassArmStream,
    GenTeacherAssignment, GenTimetableRule, GenTimetableResult, GenSettings,
    GenSubjectClashRule, GenCombinedClassRule
)
from .models_contributions import ContributionSettings, ContributionPayment, ContributionExpense
from .models_finance import (FeeItem, FeeStructure, FeePayment, FeeDiscount,
                             ExpenseCategory, Expense)
from .models_comms import MessageTemplate, Message, MessageRecipient, Announcement, Notification
from .models_hr import (Department, StaffMember, LeaveRecord, PayrollRun, Payslip,
                        SalaryHistory, StaffAttendance, PayrollDeductionType,
                        PayslipDeduction)
from .models_admissions import Applicant
from .models_library import Book, BookLoan
from .models_events import SchoolEvent
from .models_cbt import (CBTExam, CBTQuestion, CBTAttempt, CBTAnswer, CBTViolation,
                         QuestionBank, CBTLoginEvent, CBTDeviceSession)
from .models_scratchcard import ScratchCard, ResultCheckLog
from .models_branch import Branch
from .models_sales import Product, Sale, SaleItem
from .models_welfare import DisciplineRecord, ClinicVisit

__all__ = [
    'db', 'local_now', 'init_db',
    'Branch', 'Product', 'Sale', 'SaleItem',
    'DisciplineRecord', 'ClinicVisit',
    'ScratchCard', 'ResultCheckLog', 'CBTLoginEvent', 'CBTDeviceSession',
    'Student', 'ParentContact',
    'AcademicSession', 'Term', 'SchoolClass', 'ClassArm', 'ClassArmAssignment', 'StudentEnrollment',
    'Week', 'Holiday', 'Attendance',
    'WAECResult', 'JAMBResult',
    'SchoolSettings', 'GradeScale', 'BehaviouralTrait',
    'Subject', 'ClassSubject', 'AssessmentType', 'SubjectAssessmentOverride',
    'StudentScore', 'TermResult', 'TermSummary',
    'TimetableSlot', 'ClassTimetable', 'TimetableBackup',
    'PromotionRule', 'PromotionRecord',
    'User', 'PermissionGroup', 'Teacher', 'AuditLog', 'TeacherClassAssignment', 'TeacherSubjectAssignment',
    'GenTeacher', 'GenTeacherSubject', 'GenTeacherAvailability', 'GenSubject', 'GenSubjectConfig',
    'GenClassSubjectConfig', 'GenClassStreamSubject', 'GenStream', 'GenStreamSubject', 'GenRoom',
    'GenClassConfig', 'GenClassArmStream',
    'GenTeacherAssignment', 'GenTimetableRule', 'GenTimetableResult', 'GenSettings',
    'GenSubjectClashRule', 'GenCombinedClassRule',
    'ContributionSettings', 'ContributionPayment', 'ContributionExpense',
    'FeeItem', 'FeeStructure', 'FeePayment', 'FeeDiscount',
    'ExpenseCategory', 'Expense',
    'MessageTemplate', 'Message', 'MessageRecipient', 'Announcement', 'Notification',
    'Department', 'StaffMember', 'LeaveRecord', 'PayrollRun', 'Payslip',
    'SalaryHistory', 'StaffAttendance', 'PayrollDeductionType', 'PayslipDeduction',
    'Applicant',
    'Book', 'BookLoan',
    'SchoolEvent',
    'CBTExam', 'CBTQuestion', 'CBTAttempt', 'CBTAnswer', 'CBTViolation', 'QuestionBank'
]

# Analytics models
from models.analytics_models import (
    InternalExam, InternalExamResult, StudentPerformanceSnapshot,
    SubjectPerformanceMetrics, WAECJAMBCorrelation, UniversityCutoff,
    StudentRiskAssessment, AcademicPrediction, AnalyticsCache
)

# Mock JAMB Models
from models.mock_jamb import MockJAMBExam, MockJAMBResult, MockJAMBAnalytics
from models.mock_waec import MockWAECExam, MockWAECResult, MockWAECAnalytics
