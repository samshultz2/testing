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
    TimetableSlot, ClassTimetable, TimetableBackup, DesignerTimetable,
    PromotionRule, PromotionRecord,
    User, UserSession, PermissionGroup, Teacher, TeacherClassAssignment, TeacherSubjectAssignment,
    AuditLog,
    GenTeacher, GenTeacherSubject, GenTeacherAvailability, GenSubject, GenSubjectConfig,
    GenClassSubjectConfig, GenClassStreamSubject, GenStream, GenStreamSubject, GenRoom,
    GenClassConfig, GenClassArmStream,
    GenTeacherAssignment, GenTimetableRule, GenTimetableResult, GenSettings,
    GenSubjectClashRule, GenCombinedClassRule, ActiveTimetableBatch
)
from .models_contributions import ContributionSettings, ContributionPayment, ContributionExpense
from .models_finance import (FeeItem, FeeStructure, FeePayment, FeeDiscount,
                             ExpenseCategory, Expense, FinanceTransaction, AdditionalCharge, InstallmentPlan)
from .models_comms import MessageTemplate, Message, MessageRecipient, Announcement, Notification, RecipientGroup, AnnouncementAck, CommAttachment
from .models_chat import Conversation, ConversationMember, ChatMessage
from .models_hr import (Department, StaffMember, StaffEvent, LeaveRecord, PayrollRun, Payslip,
                        SalaryHistory, StaffAttendance, PayrollDeductionType,
                        PayslipDeduction, StaffDocument, TrainingRecord, PerformanceReview)
from .models_admissions import Applicant
from .models_recruitment import JobVacancy, JobApplication, Interview
from .models_attendance_intervention import AttendanceIntervention, InterventionNote
from .models_library import Book, BookLoan, BookReservation, ReadingListItem
from .models_events import SchoolEvent
from .models_website import (SiteSettings, SitePage, SiteMedia,
                             SiteViewDaily, SiteReferrerDaily, SiteVisitorDaily,
                             HolidayAssignment, NewsPost)
from .models_cbt import (CBTExam, CBTQuestion, CBTAttempt, CBTAnswer, CBTViolation,
                         QuestionBank, CBTLoginEvent, CBTDeviceSession)
from .models_scratchcard import ScratchCard, ResultCheckLog
from .models_branch import Branch
from .models_sales import (Product, Sale, SaleItem, StockMovement, Supplier,
                           PurchaseOrder, PurchaseOrderItem, SupplierPayment, PromoCode,
                           StockAudit, StockAuditItem, FixedAsset, StockBatch)
from .models_welfare import DisciplineRecord, ClinicVisit

__all__ = [
    'db', 'local_now', 'init_db',
    'Branch', 'Product', 'Sale', 'SaleItem', 'StockMovement',
    'Supplier', 'PurchaseOrder', 'PurchaseOrderItem', 'SupplierPayment', 'PromoCode',
    'StockAudit', 'StockAuditItem', 'FixedAsset', 'StockBatch',
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
    'User', 'UserSession', 'PermissionGroup', 'Teacher', 'AuditLog', 'TeacherClassAssignment', 'TeacherSubjectAssignment',
    'GenTeacher', 'GenTeacherSubject', 'GenTeacherAvailability', 'GenSubject', 'GenSubjectConfig',
    'GenClassSubjectConfig', 'GenClassStreamSubject', 'GenStream', 'GenStreamSubject', 'GenRoom',
    'GenClassConfig', 'GenClassArmStream',
    'GenTeacherAssignment', 'GenTimetableRule', 'GenTimetableResult', 'GenSettings',
    'GenSubjectClashRule', 'GenCombinedClassRule', 'ActiveTimetableBatch',
    'ContributionSettings', 'ContributionPayment', 'ContributionExpense',
    'FeeItem', 'FeeStructure', 'FeePayment', 'FeeDiscount',
    'ExpenseCategory', 'Expense', 'FinanceTransaction', 'AdditionalCharge', 'InstallmentPlan',
    'MessageTemplate', 'Message', 'MessageRecipient', 'Announcement', 'Notification', 'RecipientGroup', 'AnnouncementAck', 'CommAttachment',
    'Conversation', 'ConversationMember', 'ChatMessage',
    'Department', 'StaffMember', 'StaffEvent', 'LeaveRecord', 'PayrollRun', 'Payslip',
    'SalaryHistory', 'StaffAttendance', 'PayrollDeductionType', 'PayslipDeduction',
    'StaffDocument', 'TrainingRecord', 'PerformanceReview',
    'Applicant',
    'JobVacancy', 'JobApplication', 'Interview',
    'AttendanceIntervention', 'InterventionNote',
    'Book', 'BookLoan', 'BookReservation', 'ReadingListItem',
    'SchoolEvent',
    'SiteSettings', 'SitePage', 'SiteMedia', 'HolidayAssignment', 'NewsPost',
    'SiteViewDaily', 'SiteReferrerDaily', 'SiteVisitorDaily',
    'CBTExam', 'CBTQuestion', 'CBTAttempt', 'CBTAnswer', 'CBTViolation', 'QuestionBank'
]

# Analytics models
from models.analytics_models import (
    WAECJAMBCorrelation, UniversityCutoff,
    StudentRiskAssessment, AcademicPrediction, AnalyticsCache, WaecGradeModel
)

# Mock JAMB Models
from models.mock_jamb import MockJAMBExam, MockJAMBResult, MockJAMBAnalytics
from models.mock_waec import MockWAECExam, MockWAECResult, MockWAECAnalytics
