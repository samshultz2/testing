# AI Prompt: Build a Comprehensive Student Management System (PosyHub)

## Project Overview

Build a **production-ready, full-stack web application** in Python for managing students in a Nigerian secondary school setting. The system must handle student information, WAEC/JAMB results, and a sophisticated attendance tracking system with automatic calculations.

**Tech Stack Requirements:**
- **Backend:** Python with Flask or FastAPI
- **Frontend:** Modern HTML/CSS/JavaScript with a distinctive, professional design (not generic Bootstrap)
- **Database:** SQLite with SQLAlchemy ORM (easily switchable to PostgreSQL)
- **Charts:** Chart.js or ApexCharts for data visualization
- **Export/Import:** Support for Excel files using openpyxl or pandas

---

## Authentication

- Single admin login with hardcoded password: `posyhubcomng`
- Session-based authentication
- Protected routes - all pages except login require authentication
- Clean, modern login page with school branding

---

## Core Data Models

### 1. Student Model
```
- student_id (auto-generated, unique)
- first_name (required)
- middle_name (optional)
- surname (required)
- gender (Male/Female)
- date_of_birth
- religion
- home_address
- hobbies (text field or tags)
- created_at
- updated_at
```

### 2. Parent Contact Model (One-to-Many with Student)
```
- contact_id
- student_id (foreign key)
- phone_number
- relationship (Father, Mother, Guardian, etc.)
- is_primary (boolean)
```

### 3. Academic Session Model
```
- session_id
- session_name (e.g., "2023/2024", "2024/2025")
- start_date
- end_date
- is_active (boolean)
```

### 4. Term Model
```
- term_id
- session_id (foreign key)
- term_number (1, 2, or 3)
- term_name (First Term, Second Term, Third Term)
- start_date
- end_date
- is_active (boolean)
```

### 5. Class Model
```
- class_id
- class_name (JSS1, JSS2, JSS3, SSS1, SSS2, SSS3)
- class_level (1-6)
- can_add_more_classes: YES
```

### 6. Class Arm Model
```
- arm_id
- arm_name (Rose, Lily, Iris, Daisy, Ivy, Violet, etc.)
- can_add_more_arms: YES
```

### 7. Class Arm Assignment Model (Links Class + Arm + Session + Term)
```
- assignment_id
- class_id (foreign key)
- arm_id (foreign key)
- session_id (foreign key)
- term_id (foreign key)
- form_teacher_name
- form_teacher_phone (optional)
```

### 8. Student Enrollment Model (Which student is in which class/arm/term)
```
- enrollment_id
- student_id (foreign key)
- class_arm_assignment_id (foreign key)
- enrolled_at
```

### 9. Holiday/Non-School Day Model
```
- holiday_id
- term_id (foreign key)
- date
- reason (Public Holiday, Mid-term Break, etc.)
```

### 10. Weekly Schedule Model (Defines weeks in a term)
```
- week_id
- term_id (foreign key)
- week_number (1-15)
- start_date (Monday)
- end_date (Friday)
```

### 11. Daily Attendance Model
```
- attendance_id
- enrollment_id (foreign key)
- date
- week_id (foreign key)
- morning_present (boolean, default: True)
- afternoon_present (boolean, default: True)
- marked_by
- marked_at
```

### 12. WAEC Result Model
```
- result_id
- student_id (foreign key)
- exam_year
- subject_name
- grade (A1, B2, B3, C4, C5, C6, D7, E8, F9)
```

### 13. JAMB Result Model
```
- jamb_id
- student_id (foreign key)
- exam_year
- total_score (0-400)
- subject_scores (JSON or separate table for 4 subjects)
```

---

## Attendance System Specifications

### Daily Attendance
- **Two sessions per day:** Morning and Afternoon
- **School days:** Monday to Friday only
- **Excludes:** Weekends, Public Holidays, Mid-term Breaks
- **Default behavior:** All students marked PRESENT by default
- **Marking method:** Teacher marks ABSENT students only (more efficient since absences are fewer)
- **Each class arm tracks attendance independently**

### Week Structure
- Terms have 11-15 weeks
- Each week: Monday to Friday
- **Number of times school opened per week** = (School days in week) × 2 (for both sessions)
- Example: If all 5 days are school days, times opened = 10

### Weekly Calculations (Per Class Arm)

For each student:
```
Weekly Total = Sum of (morning_present + afternoon_present) for all school days that week
```

For class totals:
```
Total Weekly Morning Attendance = Sum of all students' morning attendance for the week
Total Weekly Afternoon Attendance = Sum of all students' afternoon attendance for the week
Total Weekly Attendance = Total Morning + Total Afternoon
Times School Opened (Week) = Number of school days × 2
Weekly Percentage = (Total Weekly Attendance / (Number of Students × Times Opened)) × 100
```

### Termly Calculations (Per Class Arm)

```
Student Termly Total = Sum of all weekly totals for student
Male Termly Total = Sum of all male students' termly totals
Female Termly Total = Sum of all female students' termly totals
Total Times Opened (Term) = Sum of times opened for all weeks
Termly Average Attendance = (Male Total + Female Total) / Total Times Opened
```

All percentages to **2 decimal places**.

---

## Feature Requirements

### 1. Dashboard
- Overview statistics
- Quick links to common actions
- Current term/session display
- Attendance summary charts
- Recent activity log

### 2. Student Management
- Add/Edit/Delete students
- View student profile with all details
- Search and filter by: name, gender, religion, class, arm, date of birth
- Sort by any field
- Bulk import from Excel
- Export to Excel
- Pagination for large lists

### 3. Class & Arm Management
- Create/Edit/Delete classes (JSS1-SSS3 and custom)
- Create/Edit/Delete arms (Rose, Lily, etc.)
- Assign form teachers to class arms per term
- View class arm rosters

### 4. Academic Session Management
- Create sessions (e.g., 2024/2025)
- Create 3 terms per session
- Define term dates
- Mark active session/term
- Define weeks within terms

### 5. Holiday Management
- Add public holidays
- Add mid-term breaks
- Calendar view of school days vs non-school days
- Holidays automatically excluded from attendance

### 6. Attendance Module

**Marking Attendance:**
- Select: Session → Term → Week → Class → Arm → Date → Session (Morning/Afternoon)
- Display all enrolled students with checkboxes
- "Mark All Present" button (default)
- Toggle to mark absences
- Save with timestamp and marker name
- Prevent marking for holidays/weekends
- Visual indicators for already-marked days

**Daily View:**
- Show attendance for specific date
- Morning and afternoon columns
- Present/Absent counts

**Weekly Summary:**
- Table showing Mon-Fri with morning/afternoon for each student
- Auto-calculate weekly totals per student
- Class-level weekly statistics
- Percentage calculations

**Termly Summary:**
- Student-by-student termly totals
- Gender breakdown (male/female totals)
- Overall termly statistics
- Exportable reports

### 7. WAEC/JAMB Results Module

**Data Entry:**
- Select student
- Enter grades for 9 subjects
- WAEC grades: A1, B2, B3, C4, C5, C6, D7, E8, F9
- Enter JAMB total score (0-400)
- Edit existing results

**Statistics & Analytics:**
- Total A1s, B2s, etc. across all students
- Subject-wise grade distribution
- How many students got A1 in [Subject]
- Pass rate per subject (C6 and above)
- JAMB score distribution
- Top performers
- Comparative charts

### 8. Reports & Charts

**Chart Types:**
- Attendance trends (line chart)
- Gender distribution (pie chart)
- WAEC grade distribution (bar chart)
- JAMB score histogram
- Weekly attendance comparison
- Termly attendance trends

**Export Options:**
- Excel export for all data types
- PDF report generation (optional)
- Print-friendly views

### 9. Import/Export
- Import students from Excel template
- Export student list to Excel
- Export attendance records
- Export WAEC/JAMB results
- Provide downloadable Excel templates

---

## UI/UX Requirements

### Design Philosophy
- **Modern, clean, professional** - suitable for educational institution
- **NOT generic Bootstrap** - use custom styling or Tailwind CSS
- **Color scheme:** Professional blues/greens with accent colors
- **Typography:** Clean, readable fonts (not Arial/Inter - use something distinctive)
- **Responsive:** Works on desktop, tablet, mobile
- **Intuitive navigation:** Sidebar with clear menu structure

### Key UI Components
- Collapsible sidebar navigation
- Breadcrumb navigation
- Data tables with sorting/filtering/pagination
- Modal dialogs for forms
- Toast notifications for actions
- Loading states and spinners
- Empty states with helpful messages
- Confirmation dialogs for destructive actions

### Accessibility
- Proper form labels
- Keyboard navigation
- Color contrast compliance
- Screen reader friendly

---

## Technical Requirements

### Code Quality
- **Clean, readable code** with meaningful variable names
- **Comments** for complex logic
- **Modular structure:** Separate files for routes, models, utilities
- **DRY principle:** Reusable components and functions
- **Error handling:** Graceful error messages
- **Input validation:** Server-side and client-side

### Database
- Proper indexing for frequently queried fields
- Foreign key constraints
- Cascade deletes where appropriate
- Database migrations support

### Security
- Password hashing (even for single password)
- CSRF protection
- SQL injection prevention (use ORM)
- XSS prevention
- Session security

### File Structure
```
/student_management/
├── app.py (or main.py)
├── config.py
├── requirements.txt
├── /models/
│   ├── __init__.py
│   ├── student.py
│   ├── attendance.py
│   ├── academic.py
│   └── results.py
├── /routes/
│   ├── __init__.py
│   ├── auth.py
│   ├── students.py
│   ├── attendance.py
│   ├── academics.py
│   └── reports.py
├── /templates/
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── /students/
│   ├── /attendance/
│   ├── /academics/
│   └── /reports/
├── /static/
│   ├── /css/
│   ├── /js/
│   └── /images/
├── /utils/
│   ├── helpers.py
│   ├── excel_utils.py
│   └── calculations.py
└── /instance/
    └── database.db
```

---

## Sample Workflows

### Workflow 1: Mark Daily Attendance
1. Login → Dashboard
2. Click "Mark Attendance"
3. Select current term (auto-selected if active)
4. Select class (e.g., SSS1)
5. Select arm (e.g., Rose)
6. Select date (defaults to today)
7. Select session (Morning/Afternoon)
8. See list of students with checkboxes (all checked = present)
9. Uncheck absent students
10. Click "Save Attendance"
11. Success notification

### Workflow 2: View Weekly Summary
1. Navigate to Attendance → Weekly Summary
2. Select class arm and week
3. View table with all students
4. See daily breakdown (Mon-Fri, Morning/Afternoon)
5. See auto-calculated weekly totals
6. See class statistics at bottom
7. Option to export to Excel

### Workflow 3: Enter WAEC Results
1. Navigate to Results → WAEC
2. Search/select student
3. Enter exam year
4. Enter grade for each of 9 subjects
5. Save
6. View individual student report or aggregate statistics

---

## Validation Rules

- Phone numbers: Nigerian format (11 digits starting with 0)
- Date of birth: Must be in the past, reasonable age range
- JAMB score: 0-400
- WAEC grades: Only valid grades (A1-F9)
- Names: No numbers, reasonable length
- Attendance: Cannot mark for future dates
- Attendance: Cannot mark for holidays/weekends

---

## Error Handling

- Database connection failures
- Invalid form submissions
- Duplicate entries
- Missing required fields
- File upload errors (wrong format)
- Session expiry

---

## Deliverables

1. Complete Python application with all features
2. SQLite database with sample data
3. Excel templates for import
4. README with setup instructions
5. Requirements.txt with all dependencies
6. Clean, commented code

---

## Priority Order for Implementation

1. **Phase 1:** Authentication, Student CRUD, Basic UI
2. **Phase 2:** Academic Session/Term/Class management
3. **Phase 3:** Attendance marking and daily views
4. **Phase 4:** Weekly and termly calculations
5. **Phase 5:** WAEC/JAMB results module
6. **Phase 6:** Charts and reports
7. **Phase 7:** Import/Export functionality
8. **Phase 8:** Polish and optimization

---

## Notes

- Nigerian school context: Use appropriate terminology
- Academic year typically runs September to July
- WAEC subjects include: English, Mathematics, Physics, Chemistry, Biology, Economics, Government, Literature, etc.
- Class naming convention is standard Nigerian secondary school format
- Arm names (Rose, Lily, etc.) are common in Nigerian schools
