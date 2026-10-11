"""
Access Control Utilities for PosyHub
Provides decorators and helper functions for role-based access control
"""
from functools import wraps
from utils.helpers import get_active_term
from flask import session, redirect, url_for, flash, request, abort
from models import db, User, ClassArmAssignment, StudentEnrollment


def get_current_user():
    """Get the current logged-in user object"""
    user_id = session.get('user_id')
    if user_id:
        return db.session.get(User, user_id)
    return None


# =============================================================================
# FINE-GRAINED MODULE PERMISSIONS
# =============================================================================

# All grantable modules: key -> human label (order = display order).
MODULES = {
    'students': 'Students',
    'admissions': 'Admissions',
    'academics': 'Academics (sessions/classes)',
    'events': 'Calendar & Events',
    'attendance': 'Attendance',
    'results': 'Subjects & Scores',
    'external_exams': 'WAEC / JAMB / Analytics',
    'cbt': 'CBT / Online Tests',
    'timetable': 'Timetable',
    'promotion': 'Promotion',
    'finance': 'Finance & Fees',
    'communication': 'Parent Communication',
    'hr': 'Staff / HR',
    'library': 'Library',
    'reports': 'Reports',
    'sales': 'Sales & Inventory',
    'contributions': 'Contributions & Levies',
    'website': 'Website Builder',
    'settings': 'School Settings',
}

# Which module a blueprint belongs to (blueprints not listed are never gated).
BLUEPRINT_MODULE = {
    'main': 'students', 'admissions': 'admissions', 'academics': 'academics',
    'events': 'events', 'attendance': 'attendance', 'subjects': 'results',
    'results': 'external_exams', 'mock_jamb': 'external_exams', 'cbt': 'cbt',
    'timetable': 'timetable', 'generator': 'timetable', 'promotion': 'promotion',
    'finance': 'finance', 'comms': 'communication', 'hr': 'hr',
    'library': 'library', 'reports': 'reports', 'scratchcards': 'results',
    'sales': 'sales', 'welfare': 'students',
    # Previously ungated staff surfaces — now permission-checked like the rest.
    'contributions': 'contributions', 'mock_waec': 'external_exams',
    'settings': 'settings', 'website_admin': 'website',
}

# Endpoints always reachable by any logged-in user (the shell + own account).
_ALWAYS_ALLOWED_ENDPOINTS = {
    'main.dashboard', 'main.global_search', 'main.set_view_branch', 'main.set_theme',
    'main.dashboard_customize', 'auth.logout', 'auth.change_password',
    # Per-user self-service: the header bell and this device's web-push
    # subscription belong to the signed-in user, not to any module.
    'main.api_notifications', 'main.api_notification_read', 'main.api_notifications_read_all',
    'main.api_push_public_key', 'main.api_push_subscribe', 'main.api_push_unsubscribe',
    # Self-service staff attendance: any staff member may check themselves in,
    # even without HR-module access (they only touch their own record).
    'hr.checkin', 'hr.checkin_self',
    # Self clock-in: reachable without HR-module access, but the view itself
    # requires the 'hr.self_attendance' capability at edit level and only ever
    # writes the caller's own attendance row. Its read-side (own attendance,
    # payslips, deductions) lives on the /account self-service page.
    'hr.clock',
    # Self document download: requires 'hr.self_documents' and only serves a
    # file that belongs to the caller's own staff record (checked in-view).
    'hr.my_document',
    # Acknowledging an announcement: shown to every logged-in user on the main
    # dashboard regardless of Communication-module access; only ever inserts
    # one row scoped to the caller's own id (unique-constrained, idempotent).
    'comms.ack_announcement',
}

# Default module set when a non-admin user has no explicit allowed_modules.
ROLE_DEFAULT_MODULES = {
    'teacher': {'students', 'attendance', 'results', 'external_exams', 'cbt',
                'timetable', 'events'},
    'readonly': {'students', 'results', 'external_exams', 'reports', 'events'},
    'staff': set(),
}


# Optional sub-sections within a module: {module: {sub_key: label}}. A user may
# be granted access to specific sub-sections instead of the whole module.
MODULE_SUBSECTIONS = {
    'students': {
        'roster': 'Browse & View Students',
        'create': 'Add / Import Students',
        'edit': 'Edit Students',
        'bulk': 'Bulk Actions',
        'delete': 'Delete Students',
        'trash': 'View Deleted Students',
        'restore': 'Restore Deleted Students',
        'purge': 'Delete Forever',
        'idcards': 'ID Cards & Export',
        'welfare': 'Discipline & Sick Bay',
    },
    'admissions': {
        'view': 'View Admissions',
        'create': 'Create Admission Details',
        'edit': 'Edit / Update Admission Details',
        'convert': 'Admit & Convert to Student',
        'download': 'Download Admission Form',
        'delete': 'Delete Admission Details',
    },
    'attendance': {
        'mark': 'Mark Attendance',
        'reports': 'Summaries & Analytics',
        'interventions': 'Interventions',
        'notify': 'Notify Parents',
    },
    'academics': {
        'structure_view': 'Sessions, Terms & Classes (View)',
        'structure_create': 'Add Sessions / Terms / Classes / Arms',
        'structure_edit': 'Edit Sessions / Terms / Classes / Arms',
        'structure_delete': 'Delete Classes / Arms / Weeks',
        'structure_bulk': 'Bulk Setup Tools',
        'enrollment_create': 'Enrol Students',
        'enrollment_edit': 'Reassign Students',
        'enrollment_delete': 'Remove Enrolments',
        'holidays_create': 'Add Holidays',
        'holidays_delete': 'Delete Holidays',
    },
    'cbt': {
        'exams_view': 'View Exams & Questions',
        'exams_create': 'Create Exams',
        'exams_edit': 'Edit Exams',
        'exams_delete': 'Delete Exams',
        'exams_publish': 'Publish / Unpublish Exams',
        'exams_questions_edit': 'Add / Remove Exam Questions',
        'exams_questions_bulk': 'Bulk-Import Exam Questions',
        'bank_view': 'View Question Bank',
        'bank_create': 'Add Bank Questions',
        'bank_delete': 'Delete Bank Questions',
        'bank_import': 'Bulk-Import Bank Questions',
        'syllabus_view': 'View Syllabus & Topics',
        'syllabus_create': 'Add Syllabus Topics',
        'syllabus_edit': 'Edit Syllabus Topics',
        'syllabus_delete': 'Delete Syllabus Topics',
        'syllabus_seed': 'Bulk-Seed Starter Syllabus',
        'monitor_view': 'Live Exam Monitoring',
        'monitor_force_submit': 'Force-Submit an Attempt',
        'results_view': 'View Results & Item Analysis',
        'results_export': 'Export Results & Item Analysis',
    },
    'promotion': {
        'promote_view': 'View Promotion & History',
        'promote_rules': 'Configure Promotion Rules',
        'promote_execute': 'Run Promotion',
        'promote_graduate_status': 'Graduate Status & Flags',
        'graduates_sss3': 'Graduate Current SSS3 (bulk)',
        'graduates_alumni_edit': 'Edit Alumni Profile (admin)',
        'documents_generate': 'Generate / Reprint Documents',
        'documents_bulk_generate': 'Bulk-Generate Documents',
        'documents_templates': 'Document Designs & Branding',
        'documents_verifications': 'Verification Activity (view)',
        'documents_requests': 'Fulfil Document Requests',
        'alumni_view': 'Alumni Directory & Analytics',
        'alumni_export': 'Export Alumni Data',
        'alumni_bulk_email': 'Bulk Email Alumni',
    },
    'library': {
        'catalogue_view': 'Browse Catalogue',
        'catalogue_create': 'Add Books / Add Copies',
        'catalogue_edit': 'Edit Books',
        'catalogue_delete': 'Delete Books',
        'catalogue_import': 'Bulk-Import Catalogue (CSV)',
        'catalogue_export': 'Export Catalogue',
        'circulation_view': 'View Loans',
        'circulation_issue': 'Issue Books',
        'circulation_return': 'Return / Renew / Mark Lost or Damaged',
        'circulation_remind': 'Send Overdue Reminders',
        'borrowers_view': 'Borrowers Directory & History',
        'reservations_view': 'View Reservations',
        'reservations_create': 'Place Reservations',
        'reservations_cancel': 'Cancel Reservations',
        'reservations_fulfill': 'Fulfil Reservations (Issue Held Book)',
        'reading_lists_view': 'View Class Reading Lists',
        'reading_lists_manage': 'Add / Remove Reading-List Items',
        'reports_view': 'View Reports',
        'reports_export': 'Export Reports',
        'settings': 'Library Settings',
        # Self-scope: view only the holder's OWN borrowed books, no library access.
        'self_loans': 'My library loans — view own (self)',
    },
    'reports': {
        'dashboards': 'Dashboards',
        'export': 'Export Students Data',
        'import': 'Bulk-Import Students',
    },
    'events': {
        'view': 'View Calendar',
        'create': 'Add Events',
        'edit': 'Edit Events',
        'delete': 'Delete Events',
        'import': 'Import Calendar',
    },
    'contributions': {
        'record': 'Record Payments',
        'expenses': 'Expenses',
        'reports': 'Reports',
        'settings': 'Settings',
    },
    'website': {
        'pages': 'Pages & Content',
        'media': 'Media Library',
        'news': 'News / Blog',
        'admissions': 'Admissions Applications',
        'analytics': 'Site Analytics',
    },
    'settings': {
        'school_info': 'School Info / Logo',
        'academic_config': 'Academic Config',
        'grades_view': 'View Grade Scale',
        'grades_edit': 'Edit Grade Scale',
        'traits_view': 'View Behavioural Traits',
        'traits_edit': 'Edit Behavioural Traits',
        'assessments_view': 'View Assessment Types',
        'assessments_edit': 'Edit Assessment Types',
        'term_overrides_view': 'View Per-Term Assessment Overrides',
        'term_overrides_edit': 'Edit Per-Term Assessment Overrides',
        'slots_view': 'View Timetable Period/Break Slots',
        'slots_edit': 'Edit Timetable Period/Break Slots',
        'slots_generate': 'Auto-Generate Timetable Period/Break Slots',
        # Sensitive actions granted explicitly (see CAPABILITY_SUBSECTIONS) —
        # hold a live third-party secret (OCR vision API key / payment
        # gateway key), so never implied by school_info_edit.
        'ocr_manage': 'Manage OCR / Vision Settings',
        'payments_manage': 'Manage Payment Gateway Settings',
        # NB: user accounts, branches, backup/restore and the audit log are
        # deliberately left out entirely — every one of those routes stays
        # hard @central_admin_required and is not independently grantable,
        # same treatment as HR's device-token reset / Promotion's
        # set_alumni_password / CBT's settings-passwords.
    },
    'finance': {
        'payments_view': 'View Payments',
        'payments_export': 'Export Payment Collections',
        'payments_create': 'Record Payments',
        'payments_edit': 'Edit Payments',
        'payments_delete': 'Delete Payments',
        'discounts_create': 'Grant Discounts / Waivers',
        'discounts_edit': 'Edit Discounts / Waivers',
        'discounts_delete': 'Delete Discounts / Waivers',
        'structure_view': 'View Fee Structure',
        'structure_create': 'Create Fee Items',
        'structure_edit': 'Edit Fee Structure',
        'structure_delete': 'Delete Fee Items / Structure',
        'structure_bulk': 'Copy Fee Structure Between Terms',
        'expenses_view': 'View Expenses',
        'expenses_create': 'Record Expenses',
        'expenses_edit': 'Edit Expenses',
        'expenses_delete': 'Delete Expenses',
        'defaulters_view': 'View Defaulters',
        'defaulters_notify': 'Notify / Message Defaulters',
        'reports_view': 'View Finance Reports',
        'reports_export': 'Export Finance Reports',
        'overview_view': 'View Finance Overview (Ledger)',
        'overview_export': 'Export Finance Overview',
        'overview_sync': 'Sync Finance Ledger',
        'accounting_view': 'View Accounting Statements',
        'accounting_export': 'Export Accounting Statements',
        'billing_tools_view': 'View Billing Tools',
        'billing_tools_create': 'Bulk Charges / Penalties',
        'billing_tools_delete': 'Remove Additional Charges',
        'installments_view': 'View Installment Plans',
        'installments_edit': 'Edit Installment Plans',
        'installments_delete': 'Delete Installment Plans',
    },
    'hr': {
        'staff_view': 'View Staff Directory',
        'staff_create': 'Add Staff',
        'staff_edit': 'Edit Staff / Notes / Documents / Training',
        'staff_delete': 'Delete Staff',
        'staff_export': 'Export Staff Directory',
        'staff_lifecycle': 'Salary Adjustments / Promote / Transfer / Confirm',
        'staff_import': 'Bulk Import Staff (CSV)',
        'staff_notify': 'Draft Staff Notifications (Comms)',
        'reviews_edit': 'Performance Reviews',
        'deductions_assign': 'Assign Per-Staff Deduction Overrides',
        'departments_view': 'View Departments',
        'departments_create': 'Create Departments',
        'departments_edit': 'Edit Departments',
        'departments_delete': 'Delete Departments',
        'leave_view': 'View Leave',
        'leave_create': 'Request / Record Leave',
        'leave_approve': 'Approve / Reject Leave',
        'leave_delete': 'Delete Leave Records',
        'payroll_view': 'View Payroll',
        'payroll_create': 'Create Payroll Runs',
        'payroll_edit': 'Edit Payslips / Sync Deductions',
        'payroll_finalize': 'Finalize / Mark Payroll Paid',
        'payroll_delete': 'Delete Payroll Runs',
        'attendance_view': 'View Staff Attendance',
        'attendance_mark': 'Mark / Save Staff Attendance',
        'attendance_qr': 'Display Self-Checkin QR',
        'settings_view': 'View HR Settings',
        'settings_edit': 'Edit HR Settings',
        'deduction_types_edit': 'Manage Deduction Types',
        'reports_view': 'View HR Reports',
        'reports_export': 'Export HR Reports',
        'recruitment_view': 'View Recruitment / Vacancies',
        'recruitment_create': 'Post Vacancies / Record Applications',
        'recruitment_edit': 'Edit Vacancies / Applications / Interviews',
        'recruitment_delete': 'Delete Vacancies / Applications',
        'recruitment_hire': 'Hire Applicant (Convert to Staff)',
        'loans_view': 'View Staff Loans',
        'loans_settings': 'Staff Loan Program Settings',
        'loans_create': 'Create Staff Loans',
        'loans_manage': 'Manage Loan Repayments / Guarantors / Cancellation',
        # Self-scope grants: the holder sees ONLY their own record, never other
        # staff's. Granting these does not unlock the HR module (they're
        # capabilities). View = read own; Edit on 'self_attendance' also lets
        # them clock themselves in.
        'self_attendance': 'My attendance — view own / clock in (self)',
        'self_payroll': 'My payslips — view own (self)',
        'self_deductions': 'My deductions — view own (self)',
        'self_leave': 'My leave — view own & balances (self)',
        'self_loans': 'My staff loans — view own balance (self)',
        'self_documents': 'My documents — view/download own (self)',
    },
    'external_exams': {
        'waec_view': 'View WAEC Results',
        'waec_create': 'Add / Scan / Paste WAEC Results',
        'waec_edit': 'Edit WAEC Results',
        'waec_delete': 'Delete WAEC Results',
        'waec_export': 'Export WAEC Results',
        'jamb_view': 'View JAMB Results',
        'jamb_create': 'Add / Scan / Paste JAMB Results',
        'jamb_edit': 'Edit JAMB Results',
        'jamb_delete': 'Delete JAMB Results',
        'jamb_export': 'Export JAMB Results',
        'predictions_view': 'WAEC → JAMB Predictions',
        'predictions_config': 'Prediction Model Settings',
        'analytics_view': 'View Analytics & Reports',
        'analytics_export': 'Export Analytics & Reports',
        'analytics_recompute': 'Recompute Analytics (Bulk)',
        'grade_distribution_create': 'Import / Edit Grade Distribution',
        'grade_distribution_delete': 'Delete Grade Distribution Imports',
        'cutoffs_view': 'View Admission Cut-offs',
        'cutoffs_write': 'Add / Edit Admission Cut-offs',
        'cutoffs_delete': 'Delete Admission Cut-offs',
        'imports': 'Bulk Import',
        'cert_generate': 'Generate WAEC Certificates',
        'cert_templates': 'Manage Certificate Templates',
        'cert_templates_delete': 'Delete Certificate Templates',
        'cert_presets': 'Manage Certificate Presets',
        'cert_bulk': 'Bulk Certificate Generation',
        'mock_waec_exam_view': 'View Mock WAEC Exams',
        'mock_waec_exam_create': 'Create Mock WAEC Exams',
        'mock_waec_exam_edit': 'Edit Mock WAEC Exams',
        'mock_waec_exam_delete': 'Delete Mock WAEC Exams',
        'mock_waec_results_view': 'View Mock WAEC Results',
        'mock_waec_results_export': 'Export Mock WAEC Results',
        'mock_waec_results_create': 'Enter Mock WAEC Results',
        'mock_waec_results_edit': 'Edit Mock WAEC Results',
        'mock_waec_results_delete': 'Delete Mock WAEC Results',
        'mock_jamb_exam_view': 'View Mock JAMB Exams',
        'mock_jamb_exam_create': 'Create Mock JAMB Exams',
        'mock_jamb_exam_edit': 'Edit Mock JAMB Exams',
        'mock_jamb_exam_delete': 'Delete Mock JAMB Exams',
        'mock_jamb_results_create': 'Enter Mock JAMB Results',
        'mock_jamb_results_edit': 'Edit Mock JAMB Results',
        'mock_jamb_results_delete': 'Delete Mock JAMB Results',
        'mock_jamb_results_export': 'Export Mock JAMB Results',
        'mock_jamb_build_view': 'View Mock JAMB Questions',
        'mock_jamb_build_edit': 'Build Mock JAMB Questions',
        'mock_jamb_build_delete': 'Delete Mock JAMB Questions',
        'mock_jamb_analytics_view': 'View Mock JAMB Analytics',
        'mock_jamb_analytics_export': 'Export Mock JAMB Analytics',
        'mock_jamb_bank_view': 'View Mock JAMB Question Bank',
        'mock_jamb_bank_edit': 'Edit Mock JAMB Question Bank',
        'mock_jamb_bank_delete': 'Delete Mock JAMB Question Bank',
        'mock_jamb_bank_syllabus_view': 'View Mock JAMB Bank Syllabus',
        'mock_jamb_bank_syllabus_edit': 'Edit Mock JAMB Bank Syllabus',
        'mock_jamb_bank_syllabus_delete': 'Delete Mock JAMB Bank Syllabus',
        'mock_jamb_bank_retag': 'Retag Mock JAMB Bank Questions',
        'mock_jamb_bank_scrape': 'Run Mock JAMB Bank Scraper',
        'mock_jamb_bank_images_view': 'View Mock JAMB Bank Image Queue',
        'mock_jamb_bank_images_edit': 'Manage Mock JAMB Bank Image Queue',
        'mock_jamb_bank_analytics_view': 'View Mock JAMB Bank Analytics',
    },
    'communication': {
        'announcements_view': 'View Announcements',
        'announcements_create': 'Post Announcements',
        'announcements_edit': 'Edit Announcements',
        'announcements_delete': 'Delete Announcements',
        'templates_view': 'View Message Templates',
        'templates_create': 'Create Message Templates',
        'templates_edit': 'Edit Message Templates',
        'templates_delete': 'Delete Message Templates',
        'contacts_view': 'View Parent Contacts',
        'messages_view': 'View Messages & Campaigns',
        'messages_create': 'Compose Messages',
        'messages_edit': 'Edit / Manage Sent Messages',
        'messages_export': 'Export Message Recipients',
        'messages_delete': 'Delete Messages',
        'reports_view': 'View Communication Reports',
        'reports_export': 'Export Communication Reports',
        'inbox_view': 'View Staff Inbox',
        'inbox_send': 'Send Staff Inbox Messages',
        'settings_view': 'View SMS Settings',
        'settings_edit': 'Edit SMS Settings',
    },
    'results': {
        'subjects_view': 'View Subjects & Class Subjects',
        'subjects_create': 'Create Subjects',
        'subjects_edit': 'Edit Subjects / Class Subjects',
        'subjects_delete': 'Delete Subjects / Class Subjects',
        'subjects_assign': 'Assign Subjects to Classes / Copy Between Terms',
        'scores_view': 'View Scores',
        'scores_enter': 'Enter Scores / Affective / Comments',
        'scores_bulk_import': 'Bulk Score Import (Sheet Scan / Paste / Upload)',
        'scores_tools': 'Blank Score Sheet / Recompute Summaries',
        'broadsheet_view': 'View Broadsheet / Explorer / Combination',
        'broadsheet_export': 'Export Broadsheet / Explorer / Combination',
        'reportcard_view': 'View / Print a Student Report Card',
        'reportcard_batch': 'Batch-Print Report Cards',
        'analytics_view': 'View Analytics & Scorecards',
        'analytics_export': 'Export Analytics & Scorecards',
        'cards': 'Generate Result Cards',
    },
    'timetable': {
        'class_view': 'View & Print Class Timetables',
        'class_edit': 'Edit Class Timetables (manual grid)',
        'designer_view': 'View Saved Designer Timetables',
        'designer_edit': 'Create / Edit Designer Timetables',
        'backups_view': 'View Timetable Backups',
        'backups_create': 'Create Timetable Backups',
        'backups_restore': 'Restore Timetable Backups',
        'backups_delete': 'Delete Timetable Backups',
        'generator_structure': 'Generator: Rooms / Streams / Classes Setup',
        'generator_subjects': 'Generator: Subjects & Subject Rules',
        'generator_teachers': 'Generator: Teacher Roster',
        'generator_teachers_bulk': 'Generator: Bulk Teacher Operations / Import',
        'generator_rules': 'Generator: Scheduling Rules & Settings',
        'generator_assignments': 'Generator: Teacher Assignments',
        'generator_assignments_bulk': 'Generator: Bulk-Delete Teacher Assignments',
        'generator_results_view': 'Generator: View Generated Results',
        'generator_results_manage': 'Generator: Edit / Apply Generated Results',
        'generator_results_delete': 'Generator: Delete Generated Results',
        'generator_reports': 'Generator: Reports',
        'generator_exports': 'Generator: Exports (PDF / Image)',
        # Sensitive action granted explicitly (see CAPABILITY_SUBSECTIONS) —
        # dual-gated with 'generator_generate' below (also requires an
        # ordinary edit grant on that key, same pattern as Sales'
        # purchasing_approve + approve_po).
        'generate': 'Generate Timetable',
        'generator_generate': 'Generator: Run / Open the Generate Page',
    },
    'sales': {
        'pos_view': 'View Receipts',
        'pos_sell': 'Ring Up Sales',
        'catalogue_view': 'View Products & Catalogue',
        'catalogue_create': 'Add Products',
        'catalogue_edit': 'Edit Products',
        'catalogue_labels': 'Generate Barcodes / Print Labels',
        'stock_view': 'View Stock Movements & Batches',
        'stock_adjust': 'Restock / Adjust Stock',
        'counts_view': 'View Stock Counts',
        'counts_create': 'Start / Save Stock Counts',
        'counts_cancel': 'Cancel Stock Counts',
        'counts_export': 'Export Stock Counts',
        # Dual-gated: also requires the 'signoff_count' capability (see
        # CAPABILITY_SUBSECTIONS) — this key alone is not enough to complete
        # a count, same pattern as results.reportcard_batch + the 'cards'
        # capability.
        'counts_signoff': 'Sign Off Stock Counts',
        'assets_view': 'View Fixed Assets',
        'assets_create': 'Add Assets / Units',
        'assets_edit': 'Edit / Transfer / Assign Assets',
        'assets_dispose': 'Dispose / Retire Assets',
        'assets_delete': 'Permanently Delete Assets',
        'assets_bulk': 'Bulk Transfer / Assign / Dispose / Delete Assets',
        'assets_loans': 'Checkout / Return Asset Loans',
        'assets_maintenance': 'Log / Edit / Delete Maintenance Records',
        'assets_audit': 'Fixed-Asset Physical Audits',
        'assets_snapshot': 'Asset Snapshots & Analytics',
        'assets_export': 'Export Asset Register',
        'purchasing_view': 'View Suppliers & Purchase Orders',
        'purchasing_create': 'Add Suppliers / Create Purchase Orders',
        'purchasing_edit': 'Edit Suppliers',
        'purchasing_pay': 'Record Supplier Payments',
        'purchasing_cancel': 'Cancel Purchase Orders',
        'purchasing_receive': 'Receive Goods (GRN)',
        # Dual-gated: also requires the 'approve_po' capability (see
        # CAPABILITY_SUBSECTIONS) — this key alone is not enough to approve a PO.
        'purchasing_approve': 'Approve Purchase Orders',
        'reports_view': 'View History / Analytics / Reports',
        'reports_export': 'Export History / Reports',
        'promos_view': 'View Promo Codes',
        'promos_manage': 'Add / Toggle Promo Codes',
        # Sensitive actions granted explicitly (see CAPABILITY_SUBSECTIONS).
        'approve_po': 'Approve purchase orders',
        'signoff_count': 'Sign off stock counts',
        # Self-scope: a cashier views only the sales THEY recorded, no Sales access.
        'self_sales': 'My sales — view own takings (self)',
    },
}

# Some sub-sections are standalone CAPABILITIES (an explicit action grant), not
# slices of a module: granting one must NOT unlock the whole module, and the
# capability is required explicitly (broad module access does not imply it).
CAPABILITY_SUBSECTIONS = {'results.cards', 'timetable.generate',
                          'sales.approve_po', 'sales.signoff_count',
                          'hr.self_attendance', 'hr.self_payroll', 'hr.self_deductions',
                          'hr.self_leave', 'hr.self_loans', 'hr.self_documents',
                          'library.self_loans', 'sales.self_sales',
                          'settings.ocr_manage', 'settings.payments_manage'}

# Self-scope capabilities: an explicit grant that lets a user act on their OWN
# record only (never other people's) — the finest permission tier. They ride on
# the normal view/edit machinery (view = read own, edit = act on own) but the
# route implementation is what enforces the "own record" boundary. Registered
# here so the UI can label them distinctly and so callers can reason about them.
SELF_SCOPE_SUBSECTIONS = {'hr.self_attendance', 'hr.self_payroll', 'hr.self_deductions',
                          'hr.self_leave', 'hr.self_loans', 'hr.self_documents',
                          'library.self_loans', 'sales.self_sales'}


def self_scope_level(key):
    """The current user's level ('view'|'edit') for a self-scope capability, or
    None. Admins and full-module holders pass too (they may act on their own
    record like anyone else); the route still limits data to the caller."""
    module, _, sub = key.partition('.')
    return subsection_level(module, sub)

# Capabilities only certain managers may grant. key -> who may set it.
# 'central' => only a central admin may grant/revoke this capability.
RESTRICTED_GRANTS = {'results.cards': 'central',
                     'settings.ocr_manage': 'central', 'settings.payments_manage': 'central'}

# Which endpoints belong to each sub-section. Entries are bare endpoint names
# (prefixed with the module's default blueprint below) OR fully-qualified
# 'blueprint.endpoint' strings for modules whose endpoints span two blueprints.
_SUBSECTION_ENDPOINTS = {
    'students': {
        'roster': {'students_list', 'api_students', 'view_student',
                   'api_student_view', 'student_photo', 'api_search_students'},
        'create': {'add_student', 'import_students', 'import_photos'},
        'edit': {'edit_student', 'apply_stream_waec', 'update_import_students'},
        'bulk': {'bulk_set_stream', 'bulk_set_gender', 'bulk_set_house',
                 'bulk_set_boarding', 'bulk_add_subject', 'bulk_message_students'},
        'delete': {'delete_student', 'bulk_delete_students'},
        'trash': {'students_trash'},
        'restore': {'restore_student', 'bulk_restore_students'},
        'purge': {'purge_student', 'bulk_purge_students'},
        'idcards': {'student_id_card', 'bulk_id_cards', 'export_students_data'},
        'welfare': {'welfare.add_discipline', 'welfare.delete_discipline',
                    'welfare.add_clinic', 'welfare.delete_clinic'},
    },
    'admissions': {
        'view': {'dashboard', 'applicants', 'applicant_detail', 'applicant_photo', 'export'},
        'create': {'add_applicant'},
        'edit': {'edit_applicant', 'set_status'},
        'convert': {'convert'},
        'download': {'blank_application_form', 'export_applicant'},
        'delete': {'delete_applicant'},
    },
    'attendance': {
        'mark': {'index', 'mark_attendance_page', 'save_attendance',
                 'mark_all_present_route', 'api_mark', 'api_roster',
                 'api_check_attendance', 'api_context', 'api_copy_previous',
                 'copy_previous_attendance', 'week_grid', 'week_save', 'api_week',
                 'api_week_mark', 'api_week_totals', 'api_school_days',
                 'attendance_app', 'attendance_react_redirect', 'api_student_search'},
        'reports': {'analytics_export', 'api_analytics', 'daily_summary',
                    'api_daily_summary', 'weekly_summary', 'termly_summary',
                    'api_report_daily', 'api_report_weekly', 'api_report_termly',
                    'api_report_alerts', 'export_weekly', 'export_termly',
                    'export_alerts', 'attendance_alerts', 'print_register',
                    'api_student_profile'},
        'interventions': {'api_interventions', 'api_intervention_open',
                          'api_intervention_note', 'api_intervention_status'},
        'notify': {'api_notify_absentees', 'api_notify_low'},
    },
    'academics': {
        'structure_view': {'sessions_list', 'terms_list', 'view_term', 'classes_list',
                           'arms_list', 'assignments_list', 'view_assignment', 'term_setup',
                           'api_get_terms', 'api_get_assignments', 'api_get_weeks'},
        'structure_create': {'add_session', 'add_term', 'add_class', 'add_arm',
                             'add_assignment', 'add_next_week'},
        'structure_edit': {'edit_session', 'edit_term', 'activate_session', 'activate_term',
                           'set_uses_arms', 'edit_class', 'edit_arm', 'edit_assignment_teacher'},
        'structure_delete': {'delete_class', 'delete_arm', 'delete_week'},
        'structure_bulk': {'setup_term_classes', 'copy_term_setup', 'generate_weeks'},
        'enrollment_create': {'enroll_student'},
        'enrollment_edit': {'reassign_students'},
        'enrollment_delete': {'remove_enrollment'},
        'holidays_create': {'add_holiday'},
        'holidays_delete': {'delete_holiday'},
    },
    'results': {
        'subjects_view': {'subjects_list', 'class_subjects_list', 'api_class_subjects', 'workflow'},
        'subjects_create': {'add_subject', 'bulk_add_subjects'},
        'subjects_edit': {'edit_subject', 'edit_class_subject', 'bulk_teacher_class_subjects'},
        'subjects_delete': {'delete_subject', 'delete_class_subject'},
        'subjects_assign': {'assign_class_subjects', 'copy_class_subjects'},
        'scores_view': {'scores_entry', 'api_student_subject_scores', 'api_student_scores'},
        'scores_enter': {'save_scores', 'save_student_scores', 'bulk_entry', 'affective', 'comments'},
        'scores_bulk_import': {'import_scores', 'score_import_template', 'scoresheet_scan',
                               'scoresheet_paste', 'scoresheet_save', 'broadsheet_import',
                               'broadsheet_save', 'subject_sheet_import', 'subject_sheet_save'},
        'scores_tools': {'blank_score_sheet', 'compute_summaries'},
        'broadsheet_view': {'broadsheet', 'broadsheet_explore', 'broadsheet_combine'},
        'broadsheet_export': {'export_broadsheet', 'export_explore', 'combine_export'},
        'reportcard_view': {'student_report_card', 'report_card_pdf'},
        'reportcard_batch': {'print_all_report_cards', 'report_cards_pdf_batch'},
        'analytics_view': {'analytics_dashboard', 'institution_analytics',
                           'teacher_scorecard_view', 'subject_scorecard_view'},
        'analytics_export': {'analytics_report', 'institution_report', 'teacher_report',
                             'subject_report'},
    },
    'cbt': {
        'exams_view': {'dashboard', 'exam_detail', 'lab_setup'},
        'exams_create': {'add_exam'},
        'exams_edit': {'edit_exam'},
        'exams_delete': {'delete_exam'},
        'exams_publish': {'toggle_publish'},
        'exams_questions_edit': {'add_question', 'delete_question'},
        'exams_questions_bulk': {'import_questions_file', 'import_from_bank', 'fill_from_jamb_bank'},
        'bank_view': {'bank', 'bank_template'},
        'bank_create': {'bank_add'},
        'bank_delete': {'bank_delete'},
        'bank_import': {'bank_import'},
        'syllabus_view': {'syllabus', 'api_subject_topics', 'subject_topics', 'subject_topics_export'},
        'syllabus_create': {'syllabus_add'},
        'syllabus_edit': {'syllabus_edit'},
        'syllabus_delete': {'syllabus_delete'},
        'syllabus_seed': {'syllabus_seed', 'syllabus_seed_all'},
        'monitor_view': {'monitor', 'monitor_data'},
        'monitor_force_submit': {'force_submit'},
        'results_view': {'results', 'item_analysis', 'attempt_review'},
        'results_export': {'results_export', 'results_export_all', 'item_analysis_export'},
    },
    'timetable': {
        # Bare names below default to the 'timetable' blueprint
        # (routes/timetable.py); the generator blueprint's endpoints are
        # fully-qualified 'generator.<name>' since it shares this module_key
        # (BLUEPRINT_MODULE['generator'] = 'timetable') but is a different
        # blueprint — same escape hatch used by students' 'welfare.*' entries.
        'class_view': {'index', 'my_timetable', 'print_timetable', 'api_get_entries'},
        'class_edit': {'edit_timetable', 'save_timetable', 'copy_timetable'},
        'designer_view': {'designer_load', 'designer_saved'},
        'designer_edit': {'designer', 'designer_save', 'designer_delete'},
        'backups_view': {'backups'},
        'backups_create': {'create_backup'},
        'backups_restore': {'restore_backup_route'},
        'backups_delete': {'delete_backup'},
        'generator_structure': {
            'generator.index', 'generator.setup_guide', 'generator.setup_jss',
            'generator.copy_subject_config', 'generator.level_dashboard',
            'generator.api_teacher_subjects', 'generator.api_class_arms',
            'generator.api_stream_subjects', 'generator.api_swap_slots',
            'generator.rooms_list', 'generator.add_room', 'generator.delete_room',
            'generator.streams_list', 'generator.add_stream', 'generator.edit_stream',
            'generator.update_stream', 'generator.update_stream_subjects',
            'generator.delete_stream', 'generator.classes_config',
            'generator.add_class_config', 'generator.edit_class_config',
            'generator.update_class_config', 'generator.update_arm_streams',
            'generator.delete_class_config',
        },
        'generator_subjects': {
            'generator.subjects_config', 'generator.add_gen_subject',
            'generator.sync_gen_subjects', 'generator.delete_gen_subject',
            'generator.edit_gen_subject', 'generator.save_subjects_config',
            'generator.class_subjects_list', 'generator.class_subjects_config',
            'generator.save_class_subjects_config', 'generator.class_stream_subjects',
            'generator.save_class_stream_subjects', 'generator.subject_rules',
            'generator.save_subject_rules',
        },
        'generator_teachers': {
            'generator.teachers_list', 'generator.add_teacher', 'generator.edit_teacher',
            'generator.update_teacher', 'generator.update_teacher_subjects',
            'generator.update_teacher_availability', 'generator.delete_teacher',
        },
        'generator_teachers_bulk': {
            'generator.bulk_increase_teacher_periods', 'generator.bulk_delete_teachers',
            'generator.bulk_sync_teacher_periods', 'generator.import_teachers',
        },
        'generator_rules': {
            'generator.rules_config', 'generator.save_rules',
            'generator.set_day_separation_class_override', 'generator.generator_settings',
            'generator.save_generator_settings', 'generator.clash_rules_list',
            'generator.add_clash_rule', 'generator.toggle_clash_rule',
            'generator.delete_clash_rule', 'generator.add_combined_rule',
            'generator.toggle_combined_rule', 'generator.delete_combined_rule',
            'generator.add_coschedule_rule', 'generator.toggle_coschedule_rule',
            'generator.delete_coschedule_rule', 'generator.add_day_separation_rule',
            'generator.toggle_day_separation_rule', 'generator.delete_day_separation_rule',
            'generator.add_period_placement_rule', 'generator.toggle_period_placement_rule',
            'generator.delete_period_placement_rule',
        },
        'generator_assignments': {
            'generator.teacher_assignments', 'generator.add_teacher_assignment',
            'generator.delete_teacher_assignment',
        },
        'generator_assignments_bulk': {'generator.bulk_delete_teacher_assignments'},
        # Dual-gated with the 'generate' capability (@timetable_generate_required
        # stays on run_generation/run_ortools_generation unchanged).
        'generator_generate': {
            'generator.generate_page', 'generator.run_generation',
            'generator.run_ortools_generation',
        },
        'generator_results_view': {'generator.results_list', 'generator.view_results'},
        # Dual-gated with 'generate' on apply_results/set_in_use (unchanged).
        'generator_results_manage': {
            'generator.edit_timetable', 'generator.save_timetable_edit',
            'generator.apply_results', 'generator.set_in_use',
        },
        'generator_results_delete': {'generator.delete_results', 'generator.bulk_delete_results'},
        'generator_reports': {
            'generator.reports_index', 'generator.period_count_report',
            'generator.teacher_assignment_summary_report', 'generator.teacher_workload_report',
            'generator.clash_report', 'generator.unassigned_report',
            'generator.teacher_timetable', 'generator.master_timetable',
        },
        'generator_exports': {
            'generator.print_results', 'generator.print_single_timetable',
            'generator.print_single_timetable_pdf', 'generator.export_results',
            'generator.export_results_by_day', 'generator.export_results_by_day_pdf',
            'generator.export_image', 'generator.export_image_hd', 'generator.export_image_ultra',
            'generator.export_teacher_image', 'generator.print_teacher_timetable',
            'generator.print_all_teacher_timetables_pdf', 'generator.unassigned_report_image',
            'generator.unassigned_report_pdf', 'generator.teacher_workload_report_image',
            'generator.teacher_workload_report_pdf', 'generator.period_count_report_image',
            'generator.period_count_report_pdf', 'generator.teacher_assignment_summary_image',
            'generator.teacher_assignment_summary_pdf',
        },
    },
    'promotion': {
        # NB: graduates_list / graduate_profile / graduate_compare are deliberately
        # left out — they have a dedicated graduate-viewer bypass in
        # enforce_module_access and must not be double-gated here.
        # NB: set_alumni_password is deliberately left out — it writes a portal
        # login credential and stays hard admin-only (@admin_required), like
        # HR's device-token and CBT's settings/passwords.
        'promote_view': {'index', 'process_promotion', 'promotion_history'},
        'promote_rules': {'rules_list', 'add_rule', 'delete_rule'},
        'promote_execute': {'execute_promotion', 'enroll_promoted'},
        'promote_graduate_status': {'mark_graduate', 'unmark_graduate',
                                     'change_graduate_status'},
        'graduates_sss3': {'graduate_sss3_preview', 'graduate_sss3'},
        'graduates_alumni_edit': {'save_alumni_profile'},
        'documents_generate': {'graduate_document', 'revoke_document'},
        'documents_bulk_generate': {'bulk_documents'},
        'documents_templates': {'doc_templates', 'doc_template_preview',
                                 'set_doc_template', 'set_doc_branding'},
        'documents_verifications': {'document_verifications'},
        'documents_requests': {'fulfill_request', 'decline_request'},
        'alumni_view': {'alumni_directory', 'alumni_analytics'},
        'alumni_export': {'alumni_export'},
        'alumni_bulk_email': {'alumni_bulk_email'},
    },
    'library': {
        # NB: book_search / barcode_lookup / student_search / staff_search /
        # isbn_lookup are deliberately left out — read-only lookup helpers
        # called from several buckets' own pages (Issue, Reserve, Reading
        # Lists); bucketing them singularly would block the other buckets'
        # workflows from using them. They fall back to "holds any library
        # subsection", same as the dashboard.
        'catalogue_view': {'books'},
        'catalogue_create': {'add_book', 'add_copies'},
        'catalogue_edit': {'edit_book'},
        'catalogue_delete': {'delete_book'},
        'catalogue_import': {'import_books'},
        'catalogue_export': {'export'},
        'circulation_view': {'loans'},
        'circulation_issue': {'issue'},
        'circulation_return': {'return_loan', 'renew_loan', 'mark_loan'},
        'circulation_remind': {'remind_overdue'},
        'borrowers_view': {'borrowers', 'borrower_history'},
        'reservations_view': {'reservations'},
        'reservations_create': {'reserve'},
        'reservations_cancel': {'reservation_cancel'},
        'reservations_fulfill': {'reservation_fulfill'},
        'reading_lists_view': {'reading_lists'},
        'reading_lists_manage': {'reading_list_add', 'reading_list_remove'},
        'reports_view': {'reports'},
        'reports_export': {'reports_export'},
        'settings': {'settings'},
    },
    'reports': {
        # NB: index is deliberately left out — it's a pure navigation hub with
        # no content of its own, reachable with any 'reports' grant (same
        # treatment as other modules' landing pages).
        'dashboards': {'summary_report', 'api_attendance_trend',
                       'api_enrollment_by_class', 'api_gender_distribution',
                       'api_jamb_score_distribution', 'api_religion_distribution',
                       'api_waec_grade_distribution'},
        'export': {'export_students', 'export_class_students', 'export_template'},
        'import': {'import_students'},
    },
    'events': {
        'view': {'calendar', 'agenda'},
        'create': {'add_event'},
        'edit': {'edit_event'},
        'delete': {'delete_event'},
        'import': {'import_calendar', 'import_save'},
    },
    'contributions': {
        'record': {'dashboard', 'quick_entry', 'add_payment', 'delete_payment',
                   'payments_list', 'student_detail', 'api_student_info', 'import_excel'},
        'expenses': {'expenses_list', 'add_expense', 'delete_expense'},
        'reports': {'report', 'daily_summary', 'defaulters', 'export_defaulters',
                    'export_excel', 'session_history', 'view_session'},
        'settings': {'settings', 'clear_all_data'},
    },
    'website': {
        'pages': {'index', 'new_page', 'edit_page', 'delete_page', 'save_page_meta',
                  'add_block', 'block_content', 'block_op', 'block_ai', 'publish',
                  'generate_site', 'theme'},
        'media': {'media_library', 'media_upload', 'media_delete'},
        'news': {'news', 'news_new', 'news_edit', 'news_save', 'news_delete'},
        'admissions': {'admissions_settings', 'assignments', 'assignment_upload',
                       'assignment_delete', 'assignment_toggle'},
        'analytics': {'analytics', 'analytics_export'},
    },
    'settings': {
        # NB: 'index' is deliberately left out — it's the module's pure
        # navigation/landing page, reachable with any single settings grant,
        # same treatment as every other module's dashboard (fixes a real bug:
        # it used to be bucketed under 'school', blocking e.g. a grading-only
        # holder from the Settings landing page itself).
        # school_settings/academic_settings are single GET+POST endpoints —
        # one key each, same view/edit split enforced by request method
        # (enforce_subsection_access already differentiates GET vs write).
        'school_info': {'school_settings', 'upload_school_logo', 'remove_school_logo'},
        'academic_config': {'academic_settings'},
        'grades_view': {'grades_list'},
        'grades_edit': {'save_grades'},
        'traits_view': {'traits_list'},
        'traits_edit': {'save_traits'},
        'assessments_view': {'assessments_list'},
        'assessments_edit': {'save_assessments'},
        'term_overrides_view': {'term_assessments', 'term_assessment_edit'},
        'term_overrides_edit': {'term_assessment_save', 'term_assessment_copy'},
        'slots_view': {'timetable_slots'},
        'slots_edit': {'save_timetable_slots'},
        'slots_generate': {'generate_timetable_slots'},
        # ocr_settings/payments_settings are capabilities (see
        # CAPABILITY_SUBSECTIONS) checked inline in the route, not mapped
        # here as ordinary ADMIN-level keys.
        # NB: users/branches/backup/audit are deliberately excluded entirely
        # — every endpoint in them stays hard @central_admin_required and is
        # not independently grantable (see MODULE_SUBSECTIONS note above).
    },
    'finance': {
        'payments_view': {'collections', 'payments_list', 'receipt', 'receipt_pdf', 'statement'},
        'payments_export': {'collections_export'},
        'payments_create': {'record_payment', 'payment_link', 'search_students'},
        'payments_edit': {'edit_payment'},
        'payments_delete': {'delete_payment'},
        'discounts_create': {'add_discount'},
        'discounts_edit': {'edit_discount'},
        'discounts_delete': {'delete_discount'},
        'structure_view': {'items_list', 'structure'},
        'structure_create': {'add_item'},
        'structure_edit': {'edit_item', 'save_structure'},
        'structure_delete': {'delete_item', 'clear_structure'},
        'structure_bulk': {'copy_structure'},
        'expenses_view': {'expenses_list'},
        'expenses_create': {'add_expense', 'add_expense_category'},
        'expenses_edit': {'edit_expense'},
        'expenses_delete': {'delete_expense', 'delete_expense_category'},
        'defaulters_view': {'defaulters'},
        'defaulters_notify': {'notify_overdue', 'draft_reminders'},
        'reports_view': {'dashboard', 'reports'},
        'reports_export': {'export_report'},
        'overview_view': {'overview'},
        'overview_export': {'overview_export'},
        'overview_sync': {'ledger_sync'},
        'accounting_view': {'accounting'},
        'accounting_export': {'accounting_export'},
        'billing_tools_view': {'billing_tools'},
        'billing_tools_create': {'bulk_charge', 'apply_penalties'},
        'billing_tools_delete': {'remove_charge'},
        'installments_view': {'installments'},
        'installments_edit': {'installments_save'},
        'installments_delete': {'installments_clear'},
    },
    'hr': {
        'staff_view': {'dashboard', 'staff_list', 'staff_detail', 'staff_search'},
        'staff_create': {'add_staff'},
        'staff_edit': {'edit_staff', 'add_staff_note', 'upload_document', 'delete_document',
                       'add_training', 'delete_training'},
        'staff_delete': {'delete_staff'},
        'staff_export': {'export_staff'},
        'staff_lifecycle': {'adjust_salary', 'promote_staff', 'transfer_staff', 'confirm_staff'},
        'staff_import': {'import_staff'},
        'staff_notify': {'notify_staff'},
        'reviews_edit': {'add_review', 'delete_review'},
        'deductions_assign': {'set_staff_deduction', 'deduction_amounts'},
        'departments_view': {'departments'},
        'departments_create': {'add_department'},
        'departments_edit': {'edit_department'},
        'departments_delete': {'delete_department'},
        'leave_view': {'leave_list'},
        'leave_create': {'add_leave'},
        'leave_approve': {'leave_status'},
        'leave_delete': {'delete_leave'},
        'payroll_view': {'payroll_list', 'payroll_detail', 'print_payslip'},
        'payroll_create': {'create_payroll'},
        'payroll_edit': {'edit_payslip', 'sync_deductions'},
        'payroll_finalize': {'finalize_payroll', 'mark_paid'},
        'payroll_delete': {'delete_payroll'},
        'attendance_view': {'attendance'},
        'attendance_mark': {'save_attendance'},
        'attendance_qr': {'checkin_qr'},
        'settings_view': {'settings'},
        'settings_edit': {'save_hr_settings'},
        'deduction_types_edit': {'add_deduction_type', 'toggle_deduction_type', 'delete_deduction_type'},
        'reports_view': {'reports'},
        'reports_export': {'reports_export'},
        'recruitment_view': {'recruitment', 'vacancy_detail'},
        'recruitment_create': {'vacancy_add', 'application_add'},
        'recruitment_edit': {'vacancy_edit', 'application_status', 'interview_schedule', 'interview_outcome'},
        'recruitment_delete': {'vacancy_delete', 'application_delete'},
        'recruitment_hire': {'hire_applicant'},
        'loans_view': {'loans_list', 'loan_detail'},
        'loans_settings': {'loans_settings'},
        'loans_create': {'loan_new'},
        'loans_manage': {'loan_guarantor_act', 'loan_repay', 'loan_cancel'},
    },
    'external_exams': {
        'waec_view': {'waec_list', 'waec_subject', 'view_waec_student', 'waec_analytics',
                      'waec_student_analysis', 'api_waec_grade_distribution',
                      'api_waec_subject_stats'},
        'waec_create': {'add_waec', 'scan_waec', 'paste_waec'},
        'waec_edit': {'edit_waec'},
        'waec_delete': {'delete_waec', 'delete_waec_single'},
        'waec_export': {'export_waec'},
        'jamb_view': {'jamb_list', 'jamb_subject', 'view_jamb_student',
                      'api_jamb_score_distribution'},
        'jamb_create': {'add_jamb', 'scan_jamb', 'scan_batch', 'paste_jamb'},
        'jamb_edit': {'edit_jamb'},
        'jamb_delete': {'delete_jamb'},
        'jamb_export': {'export_jamb'},
        'predictions_view': {'predictions_dashboard', 'student_predictions',
                             'api_student_predictions', 'api_predict_jamb',
                             'focus_areas', 'student_action_plan', 'api_student_risk'},
        'predictions_config': {'waec_model_config'},
        'analytics_view': {'index', 'analytics_hub', 'analytics_by_class', 'analytics_trends',
                           'at_risk_watchlist', 'aspiration_hub', 'readiness', 'readiness_funnel',
                           'subject_enrolment', 'subject_enrolment_detail', 'student_report',
                           'api_yoy_trends', 'api_at_risk', 'api_waec_jamb_correlation',
                           'api_top_performers', 'tasks', 'task_status', 'waec_broadsheet',
                           'subject_branch_breakdown', 'grade_distribution_manage'},
        'analytics_export': {'analytics_export', 'analytics_by_class_export', 'analytics_export_csv',
                             'analytics_board_pack', 'analytics_deck', 'waec_broadsheet_pdf',
                             'waec_broadsheet_export', 'waec_broadsheet_download',
                             'subject_branch_breakdown_export'},
        'analytics_recompute': {'recompute_analytics'},
        'grade_distribution_create': {'grade_distribution_import', 'grade_distribution_edit',
                                      'grade_distribution_import_save'},
        'grade_distribution_delete': {'grade_distribution_delete'},
        'cutoffs_view': {'cutoffs_list'},
        'cutoffs_write': {'cutoffs_save', 'cutoffs_reference'},
        'cutoffs_delete': {'cutoffs_delete'},
        'imports': {'import_results', 'import_template', 'import_results_run'},
        'cert_generate': {'waec_cert_generator', 'waec_cert_preview', 'waec_cert_generate'},
        'cert_templates': {'waec_cert_templates', 'waec_cert_create_template', 'waec_cert_edit_template',
                           'waec_cert_duplicate_template', 'waec_cert_template_status',
                           'waec_cert_template_default'},
        'cert_templates_delete': {'waec_cert_delete_template'},
        'cert_presets': {'waec_cert_save_preset', 'waec_cert_delete_preset'},
        'cert_bulk': {'waec_cert_bulk', 'waec_cert_bulk_generate'},
        # mock_waec is a separate blueprint from the 'results' default for this
        # module -- every entry below must be fully-qualified or it would
        # resolve against the wrong blueprint (and collide with e.g. the
        # analytics_view 'index' entry above, which is 'results.index').
        'mock_waec_exam_view': {'mock_waec.index', 'mock_waec.view_exam'},
        'mock_waec_exam_create': {'mock_waec.create_exam'},
        'mock_waec_exam_edit': {'mock_waec.edit_exam'},
        'mock_waec_exam_delete': {'mock_waec.delete_exam'},
        'mock_waec_results_view': {'mock_waec.broadsheet', 'mock_waec.broadsheet_print',
                                   'mock_waec.broadsheet_blank', 'mock_waec.analytics',
                                   'mock_waec.subject_analysis', 'mock_waec.deep',
                                   'mock_waec.trends', 'mock_waec.validation',
                                   'mock_waec.student_progress', 'mock_waec.result_slip',
                                   'mock_waec.result_slips_all'},
        'mock_waec_results_export': {'mock_waec.broadsheet_pdf_view', 'mock_waec.broadsheet_blank_pdf',
                                     'mock_waec.broadsheet_export', 'mock_waec.trends_export',
                                     'mock_waec.deep_export', 'mock_waec.validation_export',
                                     'mock_waec.result_slip_pdf', 'mock_waec.result_slips_pdf_view',
                                     'mock_waec.export_results'},
        'mock_waec_results_create': {'mock_waec.grid_entry', 'mock_waec.add_result',
                                     'mock_waec.paste_entry'},
        'mock_waec_results_edit': {'mock_waec.edit_student_results'},
        'mock_waec_results_delete': {'mock_waec.delete_result'},
        # mock_jamb is likewise a separate blueprint from 'results' -- every
        # entry below must be fully-qualified, or bare names like 'index' and
        # 'bulk_entry' would collide with existing 'results.*' entries above.
        'mock_jamb_exam_view': {'mock_jamb.index', 'mock_jamb.view_exam'},
        'mock_jamb_exam_create': {'mock_jamb.create_exam'},
        'mock_jamb_exam_edit': {'mock_jamb.edit_exam', 'mock_jamb.toggle_publish'},
        'mock_jamb_exam_delete': {'mock_jamb.delete_exam'},
        'mock_jamb_results_create': {'mock_jamb.add_result', 'mock_jamb.bulk_entry'},
        'mock_jamb_results_edit': {'mock_jamb.edit_result'},
        'mock_jamb_results_delete': {'mock_jamb.delete_result'},
        'mock_jamb_results_export': {'mock_jamb.export_results'},
        'mock_jamb_build_view': {'mock_jamb.questions'},
        'mock_jamb_build_edit': {'mock_jamb.add_passage', 'mock_jamb.edit_passage',
                                 'mock_jamb.add_mock_question', 'mock_jamb.edit_mock_question',
                                 'mock_jamb.exam_blueprint'},
        'mock_jamb_build_delete': {'mock_jamb.delete_passage', 'mock_jamb.delete_mock_question'},
        'mock_jamb_analytics_view': {'mock_jamb.analytics', 'mock_jamb.deep', 'mock_jamb.trends',
                                     'mock_jamb.validation', 'mock_jamb.student_progress',
                                     'mock_jamb.subject_analysis', 'mock_jamb.items',
                                     'mock_jamb.mastery', 'mock_jamb.student_mastery_view',
                                     'mock_jamb.api_exam_stats', 'mock_jamb.api_student_progress'},
        'mock_jamb_analytics_export': {'mock_jamb.trends_export', 'mock_jamb.deep_export',
                                       'mock_jamb.items_export', 'mock_jamb.weakness_export',
                                       'mock_jamb.validation_export'},
        'mock_jamb_bank_view': {'mock_jamb.bank'},
        'mock_jamb_bank_edit': {'mock_jamb.bank_add_passage', 'mock_jamb.bank_edit_passage',
                               'mock_jamb.bank_add_question', 'mock_jamb.bank_edit_question',
                               'mock_jamb.bank_import', 'mock_jamb.bank_assign_novel'},
        'mock_jamb_bank_delete': {'mock_jamb.bank_delete_passage', 'mock_jamb.bank_delete_question',
                                 'mock_jamb.bank_delete_bulk'},
        'mock_jamb_bank_syllabus_view': {'mock_jamb.bank_syllabus'},
        'mock_jamb_bank_syllabus_edit': {'mock_jamb.bank_syllabus_import', 'mock_jamb.bank_syllabus_retag',
                                        'mock_jamb.bank_syllabus_batch_retag',
                                        'mock_jamb.bank_syllabus_batch_status'},
        'mock_jamb_bank_syllabus_delete': {'mock_jamb.bank_syllabus_clear'},
        'mock_jamb_bank_retag': {'mock_jamb.bank_retag', 'mock_jamb.bank_ai_retag',
                                 'mock_jamb.bank_local_tag'},
        'mock_jamb_bank_scrape': {'mock_jamb.bank_scrape_start', 'mock_jamb.bank_scrape_step',
                                  'mock_jamb.bank_scrape_stop', 'mock_jamb.bank_scrape_resume',
                                  'mock_jamb.bank_scrape_status'},
        'mock_jamb_bank_images_view': {'mock_jamb.bank_needs_images'},
        'mock_jamb_bank_images_edit': {'mock_jamb.bank_set_question_image',
                                       'mock_jamb.bank_needs_images_bulk'},
        'mock_jamb_bank_analytics_view': {'mock_jamb.bank_analytics'},
    },
    'communication': {
        'announcements_view': {'announcements'},
        'announcements_create': {'add_announcement'},
        'announcements_edit': {'edit_announcement'},
        'announcements_delete': {'delete_announcement'},
        'templates_view': {'templates_list'},
        'templates_create': {'add_template', 'duplicate_template'},
        'templates_edit': {'edit_template', 'toggle_favorite'},
        'templates_delete': {'delete_template'},
        'contacts_view': {'contacts'},
        'messages_view': {'messages_list', 'message_detail'},
        'messages_create': {'compose', 'compose_preview', 'students_search',
                            'save_group', 'delete_group'},
        'messages_edit': {'cancel_schedule', 'mark_sent', 'mark_all_sent',
                          'send_gateway', 'process_scheduled'},
        'messages_export': {'export_recipients'},
        'messages_delete': {'delete_message'},
        'reports_view': {'reports'},
        'reports_export': {'reports_export'},
        'inbox_view': {'inbox', 'inbox_users', 'inbox_thread', 'inbox_unread'},
        'inbox_send': {'inbox_start', 'inbox_send'},
        'settings_view': {'settings'},
        'settings_edit': {'save_settings', 'test_sms'},
    },
    'sales': {
        # NB: dashboard (index) and unit_scan (a public, @login_required-free
        # QR-landing page) are deliberately left out — unmapped, same
        # treatment as every other module's pure landing/public page.
        'pos_view': {'receipt'},
        'pos_sell': {'new_sale', 'api_students', 'check_promo'},
        'catalogue_view': {'products', 'product_isbn_lookup'},
        'catalogue_create': {'add_product'},
        'catalogue_edit': {'edit_product'},
        'catalogue_labels': {'generate_barcodes', 'product_labels'},
        'stock_view': {'movements', 'batches'},
        'stock_adjust': {'restock', 'adjust_stock'},
        'counts_view': {'audits', 'audit_detail'},
        'counts_create': {'new_audit', 'save_audit'},
        'counts_cancel': {'cancel_audit'},
        'counts_export': {'audit_export'},
        'counts_signoff': {'complete_audit'},
        'assets_view': {'assets', 'asset_detail', 'asset_history', 'asset_loans_list',
                        'unit_history', 'asset_units'},
        'assets_create': {'add_asset', 'convert_to_asset', 'add_units'},
        'assets_edit': {'edit_asset', 'transfer_asset', 'assign_asset', 'move_asset_status',
                        'transfer_unit', 'assign_unit', 'update_unit_status'},
        'assets_dispose': {'dispose_asset', 'dispose_unit'},
        'assets_delete': {'delete_asset', 'delete_unit'},
        'assets_bulk': {'bulk_transfer_assets', 'bulk_assign_assets', 'bulk_dispose_assets',
                        'bulk_delete_assets'},
        'assets_loans': {'checkout_asset', 'checkout_unit', 'return_loan'},
        'assets_maintenance': {'asset_maintenance_list', 'add_maintenance', 'edit_maintenance',
                               'delete_maintenance'},
        'assets_audit': {'asset_audit_list', 'asset_create_audit', 'asset_audit_detail',
                         'asset_start_audit', 'asset_complete_audit', 'asset_delete_audit',
                         'asset_mark_audit_item'},
        'assets_snapshot': {'assets_snapshot', 'assets_snapshot_terms', 'assets_analytics'},
        'assets_export': {'assets_export'},
        'purchasing_view': {'suppliers', 'supplier_detail', 'purchases', 'purchase_detail'},
        'purchasing_create': {'add_supplier', 'new_purchase'},
        'purchasing_edit': {'edit_supplier'},
        'purchasing_pay': {'pay_supplier'},
        'purchasing_cancel': {'cancel_purchase'},
        'purchasing_receive': {'receive_purchase'},
        'purchasing_approve': {'approve_purchase'},
        'reports_view': {'history', 'analytics', 'reports'},
        'reports_export': {'history_export', 'reports_export'},
        'promos_view': {'promos'},
        'promos_manage': {'add_promo', 'toggle_promo'},
    },
}

# The blueprint each sub-sectioned module's endpoints live under (blueprint name
# differs from the module key for these two).
_SUBSECTION_BLUEPRINT = {'external_exams': 'results', 'communication': 'comms',
                         'students': 'main', 'results': 'subjects',
                         'website': 'website_admin'}

# Reverse map: 'finance.payments_list' -> ('finance', 'payments'). Endpoint
# entries already containing a '.' are treated as fully-qualified (used where a
# module's endpoints span more than one blueprint, e.g. students + welfare).
_ENDPOINT_SUBSECTION = {}
for _mod, _subs in _SUBSECTION_ENDPOINTS.items():
    _bp = _SUBSECTION_BLUEPRINT.get(_mod, _mod)
    for _sub, _eps in _subs.items():
        for _ep in _eps:
            _key = _ep if '.' in _ep else f'{_bp}.{_ep}'
            _ENDPOINT_SUBSECTION[_key] = (_mod, _sub)


def subsection_for_endpoint(endpoint):
    """('module','sub') for a gated endpoint, or None."""
    return _ENDPOINT_SUBSECTION.get(endpoint or '')


def effective_perms():
    """Raw effective permission entries (may include 'module.sub' keys).

    Admins => 'edit' on everything (view-only admins => 'view'); else the user's
    stored map; else the role default.

    Memoised per request: the nav and template gates call this dozens of times
    per render and the current user's permissions are constant within a request.
    Callers only read the result. Outside a request it always recomputes.
    """
    from flask import g, has_request_context
    if has_request_context() and '_effective_perms' in g.__dict__:
        return g._effective_perms
    result = _effective_perms_uncached()
    if has_request_context():
        g._effective_perms = result
    return result


def _effective_perms_uncached():
    if is_admin():
        lvl = 'view' if is_read_only() else 'edit'
        return {k: lvl for k in MODULES}
    user = get_current_user()
    if user:
        pm = user.permission_map
        if pm:
            scoped = {k: v for k, v in pm.items() if k.split('.', 1)[0] in MODULES}
            if scoped:
                if user.view_only:
                    scoped = {k: 'view' for k in scoped}
                return scoped
    role = session.get('role', 'teacher')
    default = ROLE_DEFAULT_MODULES.get(role, ROLE_DEFAULT_MODULES['teacher'])
    lvl = 'view' if role == 'readonly' else 'edit'
    return {k: lvl for k in default}


def module_level(key):
    """Broadest level the user has for a module (across module + sub keys).

    Standalone capability sub-sections (CAPABILITY_SUBSECTIONS) are ignored here
    so that granting e.g. 'results.cards' does not unlock the whole module.
    """
    perms = effective_perms()
    best = None
    for k, v in perms.items():
        if k in CAPABILITY_SUBSECTIONS:
            continue
        if k == key or k.startswith(key + '.'):
            if v == 'edit':
                return 'edit'
            best = 'view'
    return best


def has_capability(key):
    """True if the user holds an explicit capability grant (e.g. results.cards).

    Capabilities are never implied by module-level access — they must be granted
    explicitly. Admin module defaults don't include sub-section keys, so admins
    only pass via the dedicated can_generate_* helpers below.
    """
    return effective_perms().get(key) in ('view', 'edit')


def can_generate_result_cards():
    """Only a central admin, or a user explicitly granted 'results.cards'."""
    from utils.branch_scope import is_central
    if is_admin() and is_central():
        return True
    return has_capability('results.cards')


def can_manage_ocr_settings():
    """Only a central admin, or a user explicitly granted 'settings.ocr_manage'
    (holds a live, billable third-party vision-API key)."""
    from utils.branch_scope import is_central
    if is_admin() and is_central():
        return True
    return has_capability('settings.ocr_manage')


def can_manage_payment_settings():
    """Only a central admin, or a user explicitly granted
    'settings.payments_manage' (holds this school's live payment-gateway
    secret key — money moves through it)."""
    from utils.branch_scope import is_central
    if is_admin() and is_central():
        return True
    return has_capability('settings.payments_manage')


def can_generate_timetable():
    """Central admin, a branch principal/HOD (branch manager), or a user
    explicitly granted 'timetable.generate' by their branch principal/HOD."""
    from utils.branch_scope import is_central
    if is_admin() and is_central():
        return True
    if current_manage_scope() == 'branch':
        return True
    return has_capability('timetable.generate')


def can_approve_purchase():
    """Who may approve/cancel a purchase order (a financial commitment): a central
    admin, a branch manager (principal/HOD), or a user explicitly granted the
    'sales.approve_po' capability."""
    from utils.branch_scope import is_central
    if is_admin() and is_central():
        return True
    if current_manage_scope() == 'branch':
        return True
    return has_capability('sales.approve_po')


def can_sign_off_count():
    """Who may finalise a stock count (writing variances to stock + the finance
    ledger): a central admin, a branch manager, or a user explicitly granted the
    'sales.signoff_count' capability."""
    from utils.branch_scope import is_central
    if is_admin() and is_central():
        return True
    if current_manage_scope() == 'branch':
        return True
    return has_capability('sales.signoff_count')


def granter_level(key, perms):
    """The granter's own level for a permission key: an explicit key wins, else
    the whole-module grant covers its sub-sections. None => not held."""
    if key in perms:
        return perms[key]
    return perms.get(key.split('.', 1)[0])


def can_grant_key(key):
    """May the current manager delegate the permission ``key`` at all?

    Central admins may grant anything; everyone else may only delegate access
    they themselves hold. Capabilities work the same (a manager can only pass on
    a capability they hold).
    """
    from utils.branch_scope import is_central
    if is_admin() and is_central():
        return True
    return granter_level(key, effective_perms()) is not None


def clamp_to_granter(new_perms, target_user):
    """Non-central managers may only delegate access they themselves hold, at a
    level no higher than their own — you cannot hand out a bundle larger than
    yours. Keys beyond the granter's authority keep the target's EXISTING value
    (so a lower manager can neither add nor strip a superior-granted permission).
    """
    from utils.branch_scope import is_central
    if is_admin() and is_central():
        return dict(new_perms)                 # central: unfettered
    granter = effective_perms()
    existing = dict(target_user.permission_map) if target_user else {}
    out = {}
    for key, lvl in new_perms.items():
        mine = granter_level(key, granter)
        if mine is None:
            if key in existing:                # can't touch it -> preserve
                out[key] = existing[key]
            continue                           # else drop (never had it)
        out[key] = 'view' if (mine == 'view' and lvl == 'edit') else lvl
    # keep any existing out-of-authority grant the form omitted
    for key, lvl in existing.items():
        if key not in out and granter_level(key, granter) is None:
            out[key] = lvl
    return out


def restrict_grant_perms(new_perms, target_user):
    """Drop capability grants the current user isn't allowed to set, preserving
    the target's existing value so a non-privileged manager can't add/remove
    them, then clamp everything to what the granter themselves holds. Used
    wherever permissions are saved."""
    from utils.branch_scope import is_central
    central = is_admin() and is_central()
    existing = dict(target_user.permission_map) if target_user else {}
    out = dict(new_perms)
    for key, who in RESTRICTED_GRANTS.items():
        if who == 'central' and not central:
            if key in existing:
                out[key] = existing[key]
            else:
                out.pop(key, None)
    # A manager may not delegate access larger than their own.
    out = clamp_to_granter(out, target_user)
    return out


def subsection_level(module, sub):
    """Level for a specific sub-section: explicit > module grant > none."""
    perms = effective_perms()
    full = f'{module}.{sub}'
    if full in perms:
        return perms[full]
    if module in perms:
        return perms[module]
    return None   # granular user without this sub-section (or no access)


def user_module_levels():
    """{module_key: broadest level} for modules the user can access."""
    out = {}
    for m in MODULES:
        lvl = module_level(m)
        if lvl:
            out[m] = lvl
    return out


def user_modules():
    """Set of module keys the current user may access (admins => all)."""
    return set(user_module_levels().keys())


def can_access_module(key):
    return is_admin() or module_level(key) is not None


def can_write_module(key):
    """True if the current user may make changes in a module."""
    return module_level(key) == 'edit'


def page_can_write():
    """Whether the current page's module/sub-section is writable for this user.

    Used to hide create/update/delete controls on view-only pages (server-side
    enforcement still applies regardless).
    """
    ep = request.endpoint or ''
    if ep in _READONLY_WRITE_OK:
        return True
    if is_read_only():          # globally view-only account
        return False
    if is_admin():
        return True
    sub = subsection_for_endpoint(ep)
    if sub:
        return subsection_level(sub[0], sub[1]) == 'edit'
    module = BLUEPRINT_MODULE.get(ep.split('.')[0])
    if not module:
        return True             # ungated page — nothing to hide
    return module_level(module) == 'edit'


# Graduate / current-SSS3-comparison endpoints. These live under the promotion
# blueprint but must also be reachable by SSS3 form teachers, who do not normally
# hold the 'promotion' module — so the module gate defers to can_access_graduates().
_GRADUATE_ENDPOINTS = {
    'promotion.graduates_list', 'promotion.graduate_profile',
    'promotion.graduate_compare',
}


def enforce_module_access():
    """before_request gate: block non-admins from modules they lack."""
    if not session.get('logged_in') or is_admin():
        return None
    endpoint = request.endpoint
    if not endpoint or endpoint in _ALWAYS_ALLOWED_ENDPOINTS:
        return None
    if endpoint in _GRADUATE_ENDPOINTS and can_access_graduates():
        return None
    # SSS3 arm teachers reach the arm-scoped WAEC/JAMB pages without the module.
    if endpoint in _SSS3_EXAM_ENDPOINTS and has_sss3_exam_access():
        return None
    blueprint = endpoint.split('.')[0]
    module = BLUEPRINT_MODULE.get(blueprint)
    if module and module not in user_modules():
        if request.headers.get('X-Requested-With') == 'fetch' or request.is_json:
            abort(403)
        flash('You do not have access to that section.', 'error')
        return redirect(url_for('main.dashboard'))
    return None


# Unsafe methods a read-only user may still call (managing their own account).
_READONLY_WRITE_OK = {'auth.login', 'auth.logout', 'auth.change_password',
                      'main.set_theme', 'main.dashboard_customize', 'hr.checkin_self'}
_SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}


# --- Write-form endpoints ---------------------------------------------------
# An endpoint whose GET renders a *create / edit / import form* (as opposed to a
# read-only list or dashboard). A user who can only VIEW a module has no reason
# to sit on such a page — the write always fails — so the access gates redirect
# them out on arrival (GET), not merely on submit (POST). This is what makes a
# pasted URL like /students/add bounce a view-only user to their dashboard.
#
# We detect these by the view-function name (the part after the blueprint dot).
# The app names its form endpoints consistently (add_*, edit_*, create_*,
# import_*, …); pages that double as a *view* with an inline action (score
# broadsheets, comment/behaviour sheets, settings screens) are deliberately NOT
# matched here so a viewer keeps read access to them.
_WRITE_ENDPOINT_PREFIXES = (
    'add_', 'edit_', 'create_', 'new_', 'update_', 'delete_', 'remove_',
    'import_', 'record_', 'assign_',
)
_WRITE_ENDPOINT_SUFFIXES = ('_new', '_add', '_edit', '_create', '_import', '_delete')
_WRITE_ENDPOINT_EXACT = {
    'new_sale', 'compose', 'issue', 'quick_entry', 'loan_new',
    'bank_import', 'bank_edit_question', 'edit_mock_question',
}


def is_write_form_endpoint(endpoint):
    """True when ``endpoint``'s GET renders a create/edit/import form, so a
    view-only user should be redirected out rather than shown the form."""
    if not endpoint:
        return False
    name = endpoint.split('.')[-1]
    if name in _WRITE_ENDPOINT_EXACT:
        return True
    if name.startswith(_WRITE_ENDPOINT_PREFIXES):
        return True
    if name.endswith(_WRITE_ENDPOINT_SUFFIXES):
        return True
    return False


def _is_write_request(endpoint):
    """A request that requires edit-level: any unsafe HTTP method, OR a GET that
    lands on a create/edit/import form page."""
    return request.method not in _SAFE_METHODS or is_write_form_endpoint(endpoint)


def is_read_only():
    """True if the current user may browse but not change anything."""
    if is_admin():
        return False
    if session.get('role') == 'readonly':
        return True
    user = get_current_user()
    return bool(user and getattr(user, 'view_only', False))


def enforce_read_only():
    """before_request gate: block create/edit/delete for view-only users.

    Blocks both unsafe methods and GETs that land on a create/edit/import form
    page, so a view-only account is redirected out of e.g. /students/add rather
    than shown a form it can never submit."""
    if not session.get('logged_in'):
        return None
    endpoint = request.endpoint or ''
    if not _is_write_request(endpoint):
        return None
    if not is_read_only():
        return None
    if endpoint in _READONLY_WRITE_OK:
        return None
    if request.headers.get('X-Requested-With') == 'fetch' or request.is_json:
        abort(403)
    flash('Your account is view-only — you cannot make changes.', 'error')
    from utils.helpers import safe_redirect
    return safe_redirect(url_for('main.dashboard'))


def _deny_access(view_only=False):
    """Standard block response for the access gates."""
    if request.headers.get('X-Requested-With') == 'fetch' or request.is_json:
        abort(403)
    if view_only:
        flash('You have view-only access to that section.', 'error')
    else:
        flash('You do not have access to that section.', 'error')
    from utils.helpers import safe_redirect
    return safe_redirect(url_for('main.dashboard'))


def enforce_write_level():
    """before_request gate: block writes to a module the user can only view.

    "Writes" here means any unsafe method AND any GET that renders a
    create/edit/import form page — so a view-only user who pastes the URL of a
    form (e.g. /hr/staff/add) is redirected out, not just blocked on submit."""
    if not session.get('logged_in'):
        return None
    endpoint = request.endpoint or ''
    if not _is_write_request(endpoint):
        return None
    if is_admin():
        return None   # admins may write (global view-only handled by enforce_read_only)
    if endpoint in _ALWAYS_ALLOWED_ENDPOINTS or endpoint in _READONLY_WRITE_OK:
        return None
    if subsection_for_endpoint(endpoint):
        return None   # handled by the finer sub-section gate
    module = BLUEPRINT_MODULE.get(endpoint.split('.')[0])
    if not module:
        return None
    if module_level(module) != 'edit':
        return _deny_access(view_only=True)
    return None


def enforce_session_version():
    """Server-side session revocation. The login stamps the user's token_version
    into the session; here we re-check it every request. A mismatch (password
    change / admin reset / forced sign-out bumped it), a deactivated account, or
    a deleted user all end the session immediately — so a leaked cookie can be
    revoked and password changes log out other devices. Legacy password-admin
    sessions carry no user_id and are exempt (nothing to version)."""
    if not session.get('logged_in') or request.endpoint == 'static':
        return None
    uid = session.get('user_id')
    if not uid:
        return None                       # legacy admin: no per-user versioning
    user = db.session.get(User, uid)
    if user is not None and user.is_active and session.get('tv') == user.token_version:
        # Per-device revocation: if this signed-in device was signed out from the
        # "active sessions" screen, end it here. Only enforced for sessions that
        # carry a sid (older sessions predate the feature and stay valid).
        sid = session.get('sid')
        if sid:
            from utils.sessions import is_live, touch
            if not is_live(sid):
                session.clear()
                if request.headers.get('X-Requested-With') == 'fetch' or request.is_json:
                    abort(401)
                flash('You were signed out of this device.', 'warning')
                return redirect(url_for('auth.login'))
            touch(sid)
        return None
    session.clear()
    if request.headers.get('X-Requested-With') == 'fetch' or request.is_json:
        abort(401)
    flash('Your session has ended. Please sign in again.', 'warning')
    return redirect(url_for('auth.login'))


def enforce_idle_timeout():
    """Log a user out after a period of inactivity (Config.SESSION_IDLE_MINUTES)."""
    if not session.get('logged_in'):
        return None
    from config import Config
    mins = getattr(Config, 'SESSION_IDLE_MINUTES', 0)
    if not mins or request.endpoint == 'static':
        return None
    import time
    now = int(time.time())
    last = session.get('last_seen')
    session['last_seen'] = now
    if last and (now - last) > mins * 60:
        session.clear()
        if request.headers.get('X-Requested-With') == 'fetch' or request.is_json:
            abort(401)
        flash('Your session timed out due to inactivity. Please log in again.', 'warning')
        return redirect(url_for('auth.login'))
    return None


# Endpoints a user who must change their password may still reach.
_PW_CHANGE_ALLOWED = {'auth.change_password', 'auth.logout', 'static', 'main.set_theme'}


def enforce_password_change():
    """Force users flagged must_change_password onto the change-password page."""
    if not session.get('logged_in') or not session.get('must_change_password'):
        return None
    if (request.endpoint or '') in _PW_CHANGE_ALLOWED:
        return None
    if request.headers.get('X-Requested-With') == 'fetch' or request.is_json:
        abort(403)
    flash('Please set a new password to continue.', 'warning')
    return redirect(url_for('auth.change_password'))


def enforce_subsection_access():
    """before_request gate: per-sub-section access/write for granular users."""
    if not session.get('logged_in') or is_admin():
        return None
    # SSS3 arm teachers reach the whitelisted WAEC/JAMB pages via derived access,
    # so don't hold them to the external_exams sub-section grants.
    if request.endpoint in _SSS3_EXAM_ENDPOINTS and has_sss3_exam_access():
        return None
    res = subsection_for_endpoint(request.endpoint)
    if not res:
        return None
    module, sub = res
    lvl = subsection_level(module, sub)
    if lvl is None:
        return _deny_access()                              # no access to this part
    if _is_write_request(request.endpoint) and lvl != 'edit':
        return _deny_access(view_only=True)                # view-only part
    return None


def module_required(key):
    """Decorator form for a single route."""
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not session.get('logged_in'):
                return redirect(url_for('auth.login'))
            if not can_access_module(key):
                flash('You do not have access to that section.', 'error')
                return redirect(url_for('main.dashboard'))
            return f(*args, **kwargs)
        return wrapper
    return deco


def is_admin():
    """Check if current user is admin"""
    role = session.get('role')
    return role in ('super_admin', 'admin')


def is_teacher():
    """Check if current user is teacher"""
    role = session.get('role')
    return role == 'teacher'


def get_teacher_profile():
    """Get teacher profile for current user"""
    user = get_current_user()
    if user and user.is_teacher:
        return user.teacher_profile
    return None


def get_accessible_class_ids():
    """
    Get list of class_arm_assignment_ids the current user can access.

    Teachers: only their assigned classes. Admins / non-teacher staff: every
    class in the branch(es) currently in view (so a branch admin is limited to
    their own branch, a central user sees all).
    """
    active_term = get_active_term()
    if not active_term:
        return []

    teacher = get_teacher_profile()
    if teacher and not is_admin():
        accessible = set()
        # Form teacher classes
        for assignment in teacher.class_assignments.filter_by(is_active=True).all():
            accessible.add(assignment.class_arm_assignment_id)
        # Subject teaching classes
        for assignment in teacher.subject_assignments.filter_by(is_active=True).all():
            accessible.add(assignment.class_arm_assignment_id)
        return list(accessible)

    # Admin / non-teacher staff: all classes in the branch(es) in view.
    from utils.branch_scope import scope_query
    q = scope_query(ClassArmAssignment.query.filter_by(term_id=active_term.id),
                    ClassArmAssignment)
    return [a.id for a in q.all()]


def can_access_class(class_arm_assignment_id):
    """Check if current user can access a specific class (branch/section aware)."""
    if class_arm_assignment_id is None:
        return True  # No class selected yet

    asg = db.session.get(ClassArmAssignment, class_arm_assignment_id)
    if not asg:
        return False
    from utils.branch_scope import can_access_branch
    from utils.org_scope import allowed_sections
    # Branch gate applies to everyone except central users (can_access_branch
    # returns True for them) — so even a branch *admin* is held to their branch.
    if not can_access_branch(asg.branch_id):
        return False
    sections = allowed_sections()
    if sections and (not asg.school_class or asg.school_class.section not in sections):
        return False
    # Teachers are further limited to their own classes; admins/staff are not.
    teacher = get_teacher_profile()
    if teacher and not is_admin():
        return teacher.can_access_class(class_arm_assignment_id)
    return True


def can_mark_attendance(class_arm_assignment_id=None):
    """Check if current user can mark attendance for a class.

    Teachers may mark attendance only for the class they are *form teacher* of
    (not the subject classes they merely teach in).
    """
    # Branch/section gate first (applies to admins too).
    if class_arm_assignment_id is not None and not can_access_class(class_arm_assignment_id):
        return False
    if is_admin():
        return True

    teacher = get_teacher_profile()
    if teacher and teacher.can_mark_attendance:
        if class_arm_assignment_id is None:
            return True
        return teacher.is_form_teacher_of(class_arm_assignment_id)

    return False


def can_view_attendance(class_arm_assignment_id=None):
    """Check if current user can VIEW attendance for a class.

    A teacher may view attendance only for the class they are *form teacher* of
    — not subject classes they merely teach in (mirrors marking). Admins and
    other non-teacher staff keep their branch/section scope. Use on every
    attendance view route/report so a guessed class id can't reveal another
    class's register.
    """
    if class_arm_assignment_id is not None and not can_access_class(class_arm_assignment_id):
        return False
    if is_admin():
        return True
    teacher = get_teacher_profile()
    if teacher:                       # actual teachers: their form class(es) only
        if class_arm_assignment_id is None:
            return True
        return teacher.is_form_teacher_of(class_arm_assignment_id)
    return True                       # non-teacher staff: branch/section scope above


def can_enter_results(class_arm_assignment_id=None, subject_id=None):
    """Check if current user can enter results"""
    # Branch/section gate first (applies to admins too).
    if class_arm_assignment_id is not None and not can_access_class(class_arm_assignment_id):
        return False
    if is_admin():
        return True

    teacher = get_teacher_profile()
    if teacher and teacher.can_enter_results:
        if class_arm_assignment_id is None:
            return True
        if subject_id:
            # Check specific subject assignment
            return teacher.subject_assignments.filter_by(
                class_arm_assignment_id=class_arm_assignment_id,
                subject_id=subject_id,
                is_active=True
            ).first() is not None
        return teacher.can_access_class(class_arm_assignment_id)

    return False


def teacher_form_student_ids():
    """Set of student ids in the current teacher's form classes (active term).

    Returns None when the current user is not a teacher (no extra restriction).
    """
    if not is_teacher():
        return None
    teacher = get_teacher_profile()
    if not teacher:
        return set()
    form_ids = teacher.form_class_ids
    if not form_ids:
        return set()
    rows = StudentEnrollment.query.filter(
        StudentEnrollment.class_arm_assignment_id.in_(form_ids),
        StudentEnrollment.is_active == True).all()
    return {e.student_id for e in rows}


def assert_student_access(student):
    """Abort 403 unless the current user may access THIS specific student:
    branch-scoped, and a form teacher is limited to their own students. Use on
    any route that loads a student by a URL id and returns/exports their data,
    so a guessable id can't reveal another branch's (or class's) student."""
    from utils.branch_scope import require_branch_access
    require_branch_access(student.branch_id)
    tids = teacher_form_student_ids()
    if tids is not None and student.id not in tids:
        abort(403)


def assert_graduate_access(student):
    """Abort 403 unless the current user may view THIS graduate. Graduates are no
    longer form-enrolled, so the normal form-teacher student filter would wrongly
    exclude them; instead require the graduate gate (admin / SSS3 form teacher)
    plus branch scope."""
    from utils.branch_scope import require_branch_access
    if not can_access_graduates():
        abort(403)
    require_branch_access(student.branch_id)


def can_view_student_details():
    """Check if current user can view student details"""
    if is_admin():
        return True
    
    teacher = get_teacher_profile()
    if teacher:
        return teacher.can_view_student_details
    
    return False


def is_sss3_form_teacher():
    """True if the current user is a teacher who is form teacher of an SSS3 class
    (gates the SSS3-only WAEC subject filter/tools)."""
    teacher = get_teacher_profile()
    if not teacher:
        return False
    for caa_id in teacher.form_class_ids:
        caa = db.session.get(ClassArmAssignment, caa_id)
        if caa and caa.school_class and caa.school_class.name == 'SSS3':
            return True
    return False


def can_access_graduates():
    """Who may see graduates and the current-SSS3 comparison: a branch admin, a
    central admin, or a teacher who is form teacher of an SSS3 class. Graduate
    data and the cross-cohort analysis are sensitive and SSS3-specific, so plain
    teachers / other staff are excluded even though they can log in."""
    return is_admin() or is_sss3_form_teacher()


# --- External Exams: automatic, arm-scoped access for SSS3 teachers ----------
# A teacher assigned to an SSS3 arm (as form teacher OR subject teacher) gets
# automatic access to the External Exams (WAEC/JAMB) surfaces for THAT arm only,
# even without holding the external_exams module. It is derived from live
# assignments, so removing the assignment revokes the access. Branch-scoped
# throughout; per-tenant DBs give the school scoping for free.

def teacher_sss3_arm_ids():
    """Active class_arm_assignment_ids of SSS3 arms the current teacher is
    assigned to (form or subject teacher), within the caller's branch scope.
    Empty for admins/non-teachers. Looks up the teaching profile directly (not
    via get_teacher_profile) so staff-role accounts that teach still qualify."""
    user = get_current_user()
    teacher = user.teacher_profile if user else None
    if not teacher:
        return set()
    from utils.branch_scope import can_access_branch
    caa_ids = {a.class_arm_assignment_id for a in
               teacher.class_assignments.filter_by(is_active=True).all()}
    caa_ids |= {a.class_arm_assignment_id for a in
                teacher.subject_assignments.filter_by(is_active=True).all()}
    out = set()
    for cid in caa_ids:
        caa = db.session.get(ClassArmAssignment, cid)
        if (caa and caa.school_class and caa.school_class.name == 'SSS3'
                and can_access_branch(caa.branch_id)):
            out.add(cid)
    return out


def has_sss3_exam_access():
    """True when a non-admin who does NOT already hold the External Exams module
    is assigned to at least one SSS3 arm — the trigger for automatic, arm-scoped
    WAEC/JAMB access. Admins and full module-holders return False (they don't
    need the derived grant)."""
    if is_admin():
        return False
    if module_level('external_exams') is not None:
        return False
    return bool(teacher_sss3_arm_ids())


def exam_student_scope():
    """Student ids an External-Exams user may see, or None for no extra limit.

    * Admins and anyone holding the external_exams module in full -> None
      (their normal branch/school scope applies).
    * A teacher whose access is *derived* from an SSS3 arm assignment -> the set
      of active enrollees of their SSS3 arm(s) only. An empty set means a derived
      teacher whose arm currently has no enrolled students (sees nothing).
    """
    if is_admin() or module_level('external_exams') is not None:
        return None
    arm_ids = teacher_sss3_arm_ids()
    if not arm_ids:
        return None
    rows = StudentEnrollment.query.filter(
        StudentEnrollment.class_arm_assignment_id.in_(arm_ids),
        StudentEnrollment.is_active == True).all()
    return {e.student_id for e in rows}


# WAEC/JAMB + Mock endpoints a derived SSS3-arm teacher may reach. Deliberately
# excludes school-wide analytics, exports, cohort grids/broadsheets, the aggregate
# APIs and the shared question bank — those stay admin / full-module only, so no
# cross-arm data can leak. Everything here is either arm-scoped in the view or
# guarded per student.
_SSS3_EXAM_ENDPOINTS = {
    'results.index',
    'results.waec_list', 'results.add_waec', 'results.scan_waec', 'results.paste_waec',
    'results.view_waec_student', 'results.edit_waec', 'results.waec_student_analysis',
    'results.jamb_list', 'results.add_jamb', 'results.scan_jamb', 'results.paste_jamb',
    'results.scan_batch', 'results.view_jamb_student', 'results.edit_jamb',
    # Mock JAMB — dashboard, single-student entry, per-student views.
    'mock_jamb.index', 'mock_jamb.add_result', 'mock_jamb.edit_result',
    'mock_jamb.student_progress', 'mock_jamb.student_mastery_view',
    # Mock WAEC — dashboard, single-student entry, per-student views/slips.
    'mock_waec.index', 'mock_waec.add_result', 'mock_waec.edit_student_results',
    'mock_waec.student_progress', 'mock_waec.result_slip', 'mock_waec.result_slip_pdf',
}


def assert_exam_student(student_id):
    """Abort 403 unless the current user may touch THIS student's exam data. A
    no-op for admins and full-module holders; for a derived SSS3-arm teacher it
    enforces their own-arm scope. Use on every per-student WAEC/JAMB/Mock route."""
    scope = exam_student_scope()
    if scope is not None and int(student_id) not in scope:
        abort(403)


def graduates_access_required(f):
    """Gate a route to branch/central admins and SSS3 form teachers only."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if not can_access_graduates():
            if request.headers.get('X-Requested-With') == 'fetch' or request.is_json:
                abort(403)
            flash('Graduate records are restricted to admins and SSS3 form teachers.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return wrapper


def auto_select_assignment(assignments):
    """The class a form teacher should land on by default.

    When the current user is a teacher whose accessible (form) classes is
    exactly one, return that class's id so selectors pre-select it. Admins and
    multi-class users get no auto-selection (they choose). `assignments` should
    already be filtered via filter_classes_for_user(..., form_only=True).
    """
    try:
        if is_teacher() and len(assignments) == 1:
            return assignments[0].id
    except Exception:
        pass
    return None


def filter_classes_for_user(assignments, form_only=False):
    """Filter ClassArmAssignment objects to those the current user may access.

    Composes branch scope (branch users / a central user viewing one branch),
    section scope (Principal vs Headmaster) and, for actual teachers, their
    assigned classes. Admins / central users viewing all branches see everything.

    ``form_only`` limits a teacher to the class they are *form teacher* of (used
    by attendance and parent communication, where subject-teaching is not enough).
    """
    from utils.branch_scope import viewing_branch_id
    from utils.org_scope import allowed_sections
    result = list(assignments)
    bid = viewing_branch_id()
    if bid is not None:
        result = [a for a in result if getattr(a, 'branch_id', None) == bid]
    sections = allowed_sections()
    if sections:
        result = [a for a in result
                  if a.school_class and a.school_class.section in sections]
    if is_teacher():
        teacher = get_teacher_profile()
        if form_only:
            allowed = teacher.form_class_ids if teacher else set()
        else:
            allowed = set(get_accessible_class_ids())
        result = [a for a in result if a.id in allowed]
    # Lowest class to highest (Nursery -> Primary -> JSS -> SSS via
    # SchoolClass.level), then arms alphabetically within a class — the
    # display order every class+arm dropdown on the platform should use.
    result.sort(key=lambda a: (
        a.school_class.level if a.school_class and a.school_class.level is not None else 999,
        (a.arm.name if a.arm else '') or ''))
    return result


def filter_class_ids_for_user(class_ids):
    """
    Filter a list of class_arm_assignment_ids to only those accessible by current user.
    """
    if is_admin():
        return class_ids

    accessible_ids = set(get_accessible_class_ids())
    return [cid for cid in class_ids if cid in accessible_ids]


# =============================================================================
# DELEGATED USER MANAGEMENT (rank + branch hierarchy)
# =============================================================================

def current_manage_scope():
    """'central' / 'branch' / 'none' — how widely the current user may manage."""
    from utils.branch_scope import is_central
    if is_admin() and is_central():
        return 'central'
    user = get_current_user()
    if not user:
        return 'none'
    ms = user.manage_scope or 'none'
    # A branch-scoped user must never manage centrally, even if their stored
    # manage_scope says 'central' (stale data or misconfig). Otherwise they
    # could edit accounts in other branches. Clamp them to their own branch.
    if ms == 'central' and not user.is_central:
        ms = 'branch'
    return ms


def current_rank():
    """Authority level of the current user (legacy/central admin = top)."""
    user = get_current_user()
    if user:
        return user.rank or 0
    return 9999   # legacy password admin


def can_manage_users():
    """True if the user may manage at least some other accounts."""
    return current_manage_scope() in ('branch', 'central')


def can_manage(target_user):
    """May the current user edit ``target_user``'s account/permissions?

    Never themselves. Central managers manage everyone; branch managers manage
    strictly-lower-ranked users in their own branch.
    """
    if target_user is None:
        return False
    me = get_current_user()
    if me and target_user.id == me.id:
        return False                       # never manage yourself
    scope = current_manage_scope()
    if scope == 'central':
        return True
    if scope == 'branch':
        if me is None or target_user.branch_id != me.branch_id:
            return False
        return current_rank() > (target_user.rank or 0)
    return False


def manage_users_required(f):
    """Allow any user who can manage accounts (central admin, principal, HOD…)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if not can_manage_users():
            flash('You are not allowed to manage user accounts.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# =============================================================================
# DECORATORS
# =============================================================================

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'warning')
            from utils.nav import login_url
            return redirect(login_url())
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator to require admin access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        
        if not is_admin():
            flash('Admin access required.', 'error')
            return redirect(url_for('main.dashboard'))

        return f(*args, **kwargs)
    return decorated_function


def central_admin_required(f):
    """Require a CENTRAL admin (manages users, branches, system settings).

    A branch-scoped admin is full-featured within their branch but must not be
    able to manage accounts/permissions or cross-branch configuration.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        from utils.branch_scope import is_central
        if not (is_admin() and is_central()):
            flash('That area is for central administrators only.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def result_card_required(f):
    """Gate an endpoint behind the 'generate result cards' capability."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('auth.login'))
        if not can_generate_result_cards():
            if request.headers.get('X-Requested-With') == 'fetch' or request.is_json:
                abort(403)
            flash('You do not have permission to generate result cards.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return wrapper


def timetable_generate_required(f):
    """Gate an endpoint behind the 'generate timetable' capability."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('auth.login'))
        if not can_generate_timetable():
            if request.headers.get('X-Requested-With') == 'fetch' or request.is_json:
                abort(403)
            flash('You do not have permission to generate the timetable.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return wrapper


def class_access_required(f):
    """
    Decorator to check class access.
    Looks for 'assignment_id' or 'class_id' in request args or view args.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        
        # Get class ID from various sources
        class_id = (
            kwargs.get('assignment_id') or
            kwargs.get('class_id') or
            request.args.get('assignment_id', type=int) or
            request.args.get('class_id', type=int) or
            request.form.get('assignment_id', type=int) or
            request.form.get('class_id', type=int)
        )
        
        if class_id and not can_access_class(class_id):
            flash('You do not have access to this class.', 'error')
            return redirect(url_for('main.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function


def attendance_access_required(f):
    """Decorator to check attendance marking permission"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        
        class_id = (
            kwargs.get('assignment_id') or
            request.args.get('assignment_id', type=int) or
            request.form.get('assignment_id', type=int)
        )
        
        if not can_mark_attendance(class_id):
            flash('You do not have permission to mark attendance.', 'error')
            return redirect(url_for('main.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function


def results_access_required(f):
    """Decorator to check results entry permission"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        
        class_id = (
            kwargs.get('assignment_id') or
            request.args.get('assignment_id', type=int) or
            request.form.get('assignment_id', type=int)
        )
        
        subject_id = (
            kwargs.get('subject_id') or
            request.args.get('subject_id', type=int) or
            request.form.get('subject_id', type=int)
        )
        
        if not can_enter_results(class_id, subject_id):
            flash('You do not have permission to enter results for this class/subject.', 'error')
            return redirect(url_for('main.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function


# =============================================================================
# CONTEXT PROCESSOR HELPERS
# =============================================================================

def get_user_context():
    """
    Get user context for templates.
    Returns dict with user info and permissions.
    """
    user = get_current_user()
    teacher = get_teacher_profile()
    
    return {
        'current_user': user,
        'is_admin': is_admin(),
        'is_teacher': is_teacher(),
        'teacher_profile': teacher,
        'accessible_class_ids': get_accessible_class_ids(),
        'can_mark_attendance': can_mark_attendance(),
        'can_enter_results': can_enter_results(),
        'can_view_student_details': can_view_student_details(),
    }
