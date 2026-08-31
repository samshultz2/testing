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
        'manage': 'Add / Edit / Import',
        'bulk': 'Bulk Actions',
        'delete': 'Delete / Trash / Restore',
        'idcards': 'ID Cards & Export',
        'welfare': 'Discipline & Sick Bay',
    },
    'attendance': {
        'mark': 'Mark Attendance',
        'reports': 'Summaries & Analytics',
        'interventions': 'Interventions',
        'notify': 'Notify Parents',
    },
    'academics': {
        'structure': 'Sessions, Terms & Classes',
        'enrollment': 'Enrolments',
        'holidays': 'Holidays',
    },
    'cbt': {
        'exams': 'Exams & Questions',
        'bank': 'Question Bank',
        'syllabus': 'Syllabus & Topics',
        'monitor': 'Live Monitoring',
        'results': 'Results & Analysis',
        'settings': 'CBT Settings',
    },
    'promotion': {
        'promote': 'Run Promotion',
        'graduates': 'Graduate Records',
        'documents': 'Graduate Documents',
        'alumni': 'Alumni Directory',
    },
    'library': {
        'catalogue': 'Catalogue',
        'circulation': 'Issue / Return',
        'borrowers': 'Borrowers',
        'reservations': 'Reservations & Lists',
        'reports': 'Reports',
        'settings': 'Library Settings',
        # Self-scope: view only the holder's OWN borrowed books, no library access.
        'self_loans': 'My library loans — view own (self)',
    },
    'reports': {
        'dashboards': 'Dashboards',
        'exports': 'Exports & Imports',
    },
    'events': {
        'view': 'View Calendar',
        'manage': 'Manage Events',
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
        'school': 'School Configuration',
        'grading': 'Grading & Assessments',
        'slots': 'Timetable Slots',
        'users': 'User Accounts',
        'branches': 'Branches',
        'backup': 'Backup & Restore',
        'audit': 'Audit Log',
    },
    'finance': {
        'payments': 'Payments & Discounts',
        'structure': 'Fee Structure',
        'expenses': 'Expenses',
        'defaulters': 'Defaulters',
        'reports': 'Reports & Overview',
    },
    'hr': {
        'staff': 'Staff & Departments',
        'leave': 'Leave',
        'payroll': 'Payroll',
        'attendance': 'Staff Attendance',
        'settings': 'HR Settings',
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
        'waec': 'WAEC Results',
        'jamb': 'JAMB Results',
        'analytics': 'Analytics & Reports',
        'cutoffs': 'Cut-offs',
        'imports': 'Bulk Import',
    },
    'communication': {
        'announcements': 'Announcements',
        'templates': 'Message Templates',
        'messages': 'Messages & Compose',
        'settings': 'SMS Settings',
    },
    'results': {
        'subjects': 'Subjects & Class Subjects',
        'scores': 'Score Entry',
        'reportcards': 'Report Cards & Broadsheets',
        'analytics': 'Analytics & Scorecards',
        'cards': 'Generate Result Cards',
    },
    'timetable': {
        'view': 'View & Print Timetables',
        'manage': 'Edit Timetables',
        'generate': 'Generate Timetable',
    },
    'sales': {
        'pos': 'Point of Sale',
        'catalogue': 'Products & Catalogue',
        'inventory': 'Stock Control & Counts',
        'purchasing': 'Suppliers & Purchasing',
        'reports': 'Reports & Analytics',
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
                          'library.self_loans', 'sales.self_sales'}

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
RESTRICTED_GRANTS = {'results.cards': 'central'}

# Which endpoints belong to each sub-section. Entries are bare endpoint names
# (prefixed with the module's default blueprint below) OR fully-qualified
# 'blueprint.endpoint' strings for modules whose endpoints span two blueprints.
_SUBSECTION_ENDPOINTS = {
    'students': {
        'roster': {'students_list', 'api_students', 'view_student',
                   'api_student_view', 'student_photo', 'api_search_students'},
        'manage': {'add_student', 'edit_student', 'import_students',
                   'import_photos', 'apply_stream_waec'},
        'bulk': {'bulk_set_stream', 'bulk_set_gender', 'bulk_set_house',
                 'bulk_set_boarding', 'bulk_add_subject', 'bulk_message_students'},
        'delete': {'delete_student', 'bulk_delete_students', 'students_trash',
                   'restore_student', 'purge_student', 'bulk_restore_students',
                   'bulk_purge_students'},
        'idcards': {'student_id_card', 'bulk_id_cards', 'export_students_data'},
        'welfare': {'welfare.add_discipline', 'welfare.delete_discipline',
                    'welfare.add_clinic', 'welfare.delete_clinic'},
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
        'structure': {'sessions_list', 'add_session', 'edit_session',
                      'activate_session', 'terms_list', 'add_term', 'edit_term',
                      'activate_term', 'view_term', 'copy_term_setup', 'term_setup',
                      'setup_term_classes', 'add_next_week', 'generate_weeks',
                      'delete_week', 'classes_list', 'add_class', 'arms_list',
                      'add_arm', 'set_uses_arms', 'assignments_list', 'add_assignment',
                      'view_assignment', 'api_get_assignments', 'api_get_terms',
                      'api_get_weeks'},
        'enrollment': {'enroll_student', 'remove_enrollment'},
        'holidays': {'add_holiday', 'delete_holiday'},
    },
    'results': {
        'subjects': {'subjects_list', 'add_subject', 'edit_subject', 'delete_subject',
                     'class_subjects_list', 'assign_class_subjects', 'edit_class_subject',
                     'delete_class_subject', 'copy_class_subjects', 'bulk_add_subjects',
                     'api_class_subjects', 'workflow'},
        'scores': {'scores_entry', 'save_scores', 'scoresheet_paste', 'scoresheet_save',
                   'scoresheet_scan', 'bulk_entry', 'blank_score_sheet', 'import_scores',
                   'score_import_template', 'api_student_scores', 'comments', 'affective',
                   'compute_summaries'},
        'reportcards': {'student_report_card', 'report_card_pdf',
                        'print_all_report_cards', 'report_cards_pdf_batch'},
        'analytics': {'broadsheet', 'export_broadsheet', 'analytics_dashboard',
                      'analytics_report', 'subject_report', 'teacher_report',
                      'subject_scorecard_view', 'teacher_scorecard_view',
                      'institution_analytics', 'institution_report', 'institution_email',
                      'institution_auto_email'},
    },
    'cbt': {
        'exams': {'dashboard', 'add_exam', 'edit_exam', 'delete_exam', 'exam_detail',
                  'toggle_publish', 'add_question', 'delete_question',
                  'import_questions_file', 'import_from_bank', 'fill_from_jamb_bank',
                  'lab_setup', 'passwords'},
        'bank': {'bank', 'bank_add', 'bank_delete', 'bank_import', 'bank_template'},
        'syllabus': {'syllabus', 'syllabus_add', 'syllabus_edit', 'syllabus_delete',
                     'syllabus_seed', 'syllabus_seed_all', 'subject_topics',
                     'subject_topics_export', 'api_subject_topics'},
        'monitor': {'monitor', 'monitor_data', 'force_submit'},
        'results': {'results', 'results_export', 'results_export_all', 'attempt_review',
                    'item_analysis', 'item_analysis_export'},
        'settings': {'settings'},
    },
    'timetable': {
        'view': {'index', 'my_timetable', 'print_timetable', 'api_get_entries',
                 'designer_load', 'designer_saved'},
        'manage': {'designer', 'designer_save', 'designer_delete', 'edit_timetable',
                   'save_timetable', 'copy_timetable', 'backups', 'create_backup',
                   'delete_backup', 'restore_backup_route'},
    },
    'promotion': {
        # NB: graduates_list / graduate_profile / graduate_compare are deliberately
        # left out — they have a dedicated graduate-viewer bypass in
        # enforce_module_access and must not be double-gated here.
        'promote': {'index', 'process_promotion', 'execute_promotion',
                    'enroll_promoted', 'promotion_history', 'rules_list', 'add_rule',
                    'delete_rule', 'mark_graduate', 'unmark_graduate',
                    'change_graduate_status'},
        'graduates': {'graduate_sss3', 'graduate_sss3_preview', 'save_alumni_profile',
                      'set_alumni_password'},
        'documents': {'graduate_document', 'bulk_documents', 'revoke_document',
                      'doc_templates', 'doc_template_preview', 'set_doc_template',
                      'set_doc_branding', 'document_verifications', 'fulfill_request',
                      'decline_request'},
        'alumni': {'alumni_directory', 'alumni_analytics', 'alumni_export',
                   'alumni_bulk_email'},
    },
    'library': {
        'catalogue': {'books', 'add_book', 'edit_book', 'delete_book', 'add_copies',
                      'import_books', 'isbn_lookup', 'barcode_lookup', 'book_search',
                      'export'},
        'circulation': {'loans', 'issue', 'return_loan', 'renew_loan', 'mark_loan',
                        'remind_overdue'},
        'borrowers': {'borrowers', 'borrower_history', 'student_search', 'staff_search'},
        'reservations': {'reservations', 'reserve', 'reservation_cancel',
                         'reservation_fulfill', 'reading_lists', 'reading_list_add',
                         'reading_list_remove'},
        'reports': {'reports', 'reports_export'},
        'settings': {'settings'},
    },
    'reports': {
        'dashboards': {'index', 'summary_report', 'api_attendance_trend',
                       'api_enrollment_by_class', 'api_gender_distribution',
                       'api_jamb_score_distribution', 'api_religion_distribution',
                       'api_waec_grade_distribution'},
        'exports': {'export_students', 'export_class_students', 'export_template',
                    'import_students'},
    },
    'events': {
        'view': {'calendar', 'agenda'},
        'manage': {'add_event', 'edit_event', 'delete_event', 'import_calendar',
                   'import_save'},
    },
    'contributions': {
        'record': {'dashboard', 'quick_entry', 'add_payment', 'delete_payment',
                   'payments_list', 'student_detail', 'api_student_info'},
        'expenses': {'expenses_list', 'add_expense', 'delete_expense'},
        'reports': {'report', 'daily_summary', 'defaulters', 'export_defaulters',
                    'export_excel', 'import_excel', 'session_history', 'view_session'},
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
        'school': {'index', 'school_settings', 'academic_settings', 'upload_school_logo',
                   'remove_school_logo', 'ocr_settings', 'payments_settings'},
        'grading': {'grades_list', 'save_grades', 'assessments_list', 'save_assessments',
                    'traits_list', 'save_traits', 'term_assessments',
                    'term_assessment_edit', 'term_assessment_save', 'term_assessment_copy'},
        'slots': {'timetable_slots', 'save_timetable_slots', 'generate_timetable_slots'},
        'users': {'users_list', 'add_user', 'edit_user', 'delete_user'},
        'branches': {'branches', 'add_branch', 'edit_branch'},
        'backup': {'backup_page', 'create_backup', 'restore_backup', 'download_backup',
                   'download_backup_file', 'export_json'},
        'audit': {'audit_log'},
    },
    'finance': {
        'payments': {'collections', 'collections_export', 'payments_list',
                     'record_payment', 'search_students', 'receipt', 'edit_payment',
                     'delete_payment', 'statement', 'add_discount', 'edit_discount',
                     'delete_discount'},
        'structure': {'items_list', 'add_item', 'edit_item', 'delete_item',
                      'structure', 'save_structure', 'copy_structure', 'clear_structure'},
        'expenses': {'expenses_list', 'add_expense', 'edit_expense', 'delete_expense',
                     'add_expense_category', 'delete_expense_category'},
        'defaulters': {'defaulters'},
        'reports': {'dashboard', 'reports', 'export_report'},
    },
    'hr': {
        'staff': {'dashboard', 'staff_list', 'add_staff', 'staff_detail', 'edit_staff',
                  'adjust_salary', 'delete_staff', 'export_staff', 'departments',
                  'add_department', 'edit_department', 'delete_department'},
        'leave': {'leave_list', 'add_leave', 'leave_status', 'delete_leave'},
        'payroll': {'payroll_list', 'create_payroll', 'payroll_detail', 'edit_payslip',
                    'finalize_payroll', 'mark_paid', 'delete_payroll', 'print_payslip',
                    'sync_deductions'},
        'attendance': {'attendance', 'save_attendance'},
        'settings': {'settings', 'save_hr_settings'},
    },
    'external_exams': {
        'waec': {'waec_list', 'add_waec', 'scan_waec', 'view_waec_student', 'edit_waec',
                 'delete_waec', 'delete_waec_single', 'export_waec', 'waec_analytics',
                 'waec_student_analysis', 'api_waec_grade_distribution',
                 'api_waec_subject_stats'},
        'jamb': {'jamb_list', 'add_jamb', 'scan_jamb', 'scan_batch', 'view_jamb_student',
                 'edit_jamb', 'delete_jamb', 'export_jamb', 'api_jamb_score_distribution',
                 'predictions_dashboard', 'student_predictions', 'api_student_predictions',
                 'api_predict_jamb', 'api_student_risk'},
        'analytics': {'analytics_hub', 'analytics_export', 'readiness', 'api_yoy_trends',
                      'api_waec_jamb_correlation', 'api_top_performers', 'subject_enrolment',
                      'subject_enrolment_detail', 'student_report'},
        'cutoffs': {'cutoffs_list', 'cutoffs_save', 'cutoffs_delete', 'cutoffs_reference'},
        'imports': {'import_results', 'import_template', 'import_results_run'},
    },
    'communication': {
        'announcements': {'announcements', 'add_announcement', 'edit_announcement',
                          'delete_announcement'},
        'templates': {'templates_list', 'add_template', 'edit_template', 'delete_template'},
        'messages': {'compose', 'compose_preview', 'students_search', 'cancel_schedule',
                     'process_scheduled', 'messages_list', 'message_detail', 'mark_sent',
                     'mark_all_sent', 'export_recipients', 'delete_message', 'send_gateway'},
        'settings': {'settings', 'save_settings', 'test_sms'},
    },
    'sales': {
        'pos': {'new_sale', 'api_students', 'check_promo', 'receipt'},
        'catalogue': {'products', 'add_product', 'edit_product', 'product_isbn_lookup',
                      'generate_barcodes', 'product_labels'},
        'inventory': {'restock', 'adjust_stock', 'movements', 'batches', 'audits',
                      'new_audit', 'audit_detail', 'save_audit', 'complete_audit',
                      'cancel_audit', 'audit_export', 'assets', 'add_asset', 'edit_asset',
                      'convert_to_asset', 'dispose_asset', 'assets_export'},
        'purchasing': {'suppliers', 'add_supplier', 'edit_supplier', 'supplier_detail',
                       'pay_supplier', 'purchases', 'new_purchase', 'purchase_detail',
                       'approve_purchase', 'cancel_purchase', 'receive_purchase'},
        'reports': {'history', 'history_export', 'analytics', 'reports', 'reports_export',
                    'promos', 'add_promo', 'toggle_promo'},
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
