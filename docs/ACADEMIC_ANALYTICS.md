# Academic Analytics System - Technical Documentation

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PRESENTATION LAYER                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │ WAEC Dashboard│  │JAMB Dashboard│  │Student Profile│              │
│  │  - Charts    │  │  - Charts    │  │  - Analytics │               │
│  │  - Filters   │  │  - Filters   │  │  - Predictions│              │
│  │  - Tables    │  │  - Rankings  │  │  - Risk Score│               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         API / ROUTES LAYER                           │
│  /results/waec              - WAEC Dashboard & CRUD                  │
│  /results/jamb              - JAMB Dashboard & CRUD                  │
│  /results/api/*             - JSON API endpoints for charts          │
│  /results/export/*          - Excel export functionality             │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      ANALYTICS SERVICE LAYER                         │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                  AcademicAnalytics Class                     │    │
│  │  - get_student_waec_summary()      - Student-level analysis  │    │
│  │  - get_student_jamb_summary()      - JAMB analysis           │    │
│  │  - calculate_student_risk_score()  - Risk assessment         │    │
│  │  - get_waec_school_statistics()    - School-wide stats       │    │
│  │  - get_jamb_school_statistics()    - JAMB school stats       │    │
│  │  - calculate_waec_jamb_correlation()- Correlation analysis   │    │
│  │  - get_year_over_year_comparison() - YoY trends              │    │
│  │  - predict_jamb_score()            - ML prediction           │    │
│  │  - get_subject_recommendations()   - Career guidance         │    │
│  │  - filter_students()               - Advanced filtering      │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         DATA LAYER                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │   Student    │  │  WAECResult  │  │  JAMBResult  │               │
│  │   - id       │  │  - student_id│  │  - student_id│               │
│  │   - name     │  │  - exam_year │  │  - exam_year │               │
│  │   - etc      │  │  - subject   │  │  - total_score│              │
│  │              │  │  - grade     │  │  - subjects  │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
│                                                                      │
│  Extended Models (analytics_models.py):                              │
│  - InternalExam, InternalExamResult    - Internal assessments        │
│  - StudentPerformanceSnapshot          - Periodic snapshots          │
│  - SubjectPerformanceMetrics           - Subject-level metrics       │
│  - WAECJAMBCorrelation                 - Correlation tracking        │
│  - StudentRiskAssessment               - Risk assessment records     │
│  - AcademicPrediction                  - ML prediction records       │
│  - UniversityCutoff                    - Historical cutoffs          │
│  - AnalyticsCache                      - Computation caching         │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Features Implemented

### 1. WAEC Dashboard (`/results/waec`)
- **Grade Distribution Chart**: Bar chart showing A1-F9 distribution
- **Subject Pass Rates**: Horizontal bar chart of top subjects by pass rate
- **Year-over-Year Trends**: Line chart tracking pass rate and A1 rate over years
- **Top Performers**: Ranked list of students by A1 count
- **Subject Analysis**: Grid showing pass rates with visual progress bars
- **Advanced Filtering**:
  - By exam year
  - By subject
  - By grade
  - Minimum A1 count
  - Minimum credit count
- **Sorting**: By name, A1 count, credits, average points
- **Export**: Excel download with full formatting

### 2. JAMB Dashboard (`/results/jamb`)
- **Score Distribution**: Bar chart showing score ranges (0-100, 101-150, etc.)
- **Subject Performance**: Bar chart of average scores by subject
- **Statistical Summary**: Mean, median, std deviation, score thresholds
- **WAEC-JAMB Correlation**: Pearson correlation with interpretation
- **Top 10 Rankings**: Visual ranking with medal indicators
- **Year-over-Year Trends**: Multi-axis chart (avg score + percentage above thresholds)
- **Filtering**: By year, score range
- **Performance Badges**: EXCELLENT, VERY_GOOD, GOOD, AVERAGE, BELOW_AVERAGE, POOR

### 3. Student Profile View
- **Summary Stats**: A1s, credits, total subjects, average points
- **Risk Assessment Badge**: GREEN/AMBER/RED with score
- **JAMB Prediction**: Predicted score with confidence interval
- **Grade Distribution Chart**: Doughnut chart
- **Strengths & Weaknesses**: Subject-specific analysis
- **Career Recommendations**: Based on subject performance patterns
- **Risk Factors & Recommendations**: Actionable improvement suggestions

### 4. Analytics Engine Features

#### Student-Level Metrics
- Total grade points and average
- Credit count (A1-C6)
- Distinction count (A1-B3)
- Pass/fail breakdown
- Best and weakest subjects
- Historical performance across years

#### School-Level Metrics
- Overall pass rate (A1-C6 percentage)
- Distinction rate (A1-B3 percentage)
- Subject-by-subject analysis
- Grade distribution per subject
- A1 concentration by subject
- Failure rate by subject
- Top performers ranking

#### Risk Assessment Algorithm
```python
Risk Score = (Academic Risk × 0.5) + (Attendance Risk × 0.3) + (Trend Risk × 0.2)

Academic Risk Factors:
- Multiple failures (E8/F9): +40 points
- Insufficient credits (<5): +30 points
- Poor core subject performance: +20 points each

Risk Levels:
- GREEN: Score < 30 (Low risk)
- AMBER: Score 30-59 (Moderate risk)
- RED: Score >= 60 (High risk)
```

#### JAMB Prediction Model
```python
Base Score = 400 - (avg_grade_points - 1) × 30
Adjustments:
  + A1 count × 5 (bonus for excellence)
  + Core subject bonus (10 each for A1-B3 in English/Math)

Confidence = 0.5 + (subjects/20) + 0.1 (if A1s >= 3)
Score Range = predicted ± (30 × (1 - confidence))
```

### 5. API Endpoints
| Endpoint | Description |
|----------|-------------|
| `/api/waec/grade-distribution/<year>` | Grade counts for charts |
| `/api/waec/subject-stats/<year>` | Subject performance data |
| `/api/jamb/score-distribution/<year>` | Score range distribution |
| `/api/yoy-trends` | Year-over-year comparison data |
| `/api/student-risk/<id>` | Individual risk assessment |
| `/api/predict-jamb/<id>` | JAMB prediction for student |
| `/api/waec-jamb-correlation/<year>` | Correlation analysis |
| `/api/top-performers/<year>` | Top students list |

## Metric Definitions

### WAEC Grades
| Grade | Points | Classification |
|-------|--------|----------------|
| A1 | 1 | Excellent |
| B2 | 2 | Very Good |
| B3 | 3 | Good |
| C4 | 4 | Credit |
| C5 | 5 | Credit |
| C6 | 6 | Credit |
| D7 | 7 | Pass |
| E8 | 8 | Pass |
| F9 | 9 | Fail |

### Pass Rate Calculation
```
Pass Rate = (Count of A1-C6 grades / Total grades) × 100
```

### WAEC-JAMB Correlation
Pearson correlation coefficient between average WAEC grade points and JAMB scores:
- Strong negative correlation (< -0.5): WAEC reliably predicts JAMB
- Moderate correlation (-0.3 to -0.5): Moderate predictive power
- Weak/no correlation (> -0.3): Limited predictive value

## Visualization Specifications

### Chart.js Configurations

**Grade Distribution (Bar)**
- Colors: Gradient from green (A1) to red (F9)
- Y-axis: Count, starts at 0
- Decision Support: Identify grade concentration patterns

**Subject Pass Rates (Horizontal Bar)**
- Color coding: Green (≥70%), Yellow (50-69%), Red (<50%)
- Decision Support: Identify subjects needing intervention

**YoY Trends (Line)**
- Multiple datasets: Pass rate, A1 rate
- Tension: 0.3 for smooth curves
- Fill: true for area visualization
- Decision Support: Track improvement/decline over years

**Score Distribution (Bar)**
- Gradient colors by score range
- Decision Support: Identify score clustering and outliers

## Database Schema Extensions

### New Tables (analytics_models.py)

```sql
-- Internal Exams
CREATE TABLE internal_exams (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100),
    exam_type VARCHAR(30),  -- CA1, CA2, MID_TERM, FINAL, MOCK
    term_id INTEGER REFERENCES terms(id),
    max_score INTEGER DEFAULT 100,
    weight FLOAT DEFAULT 1.0,
    exam_date DATE
);

-- Internal Exam Results
CREATE TABLE internal_exam_results (
    id INTEGER PRIMARY KEY,
    exam_id INTEGER REFERENCES internal_exams(id),
    student_id INTEGER REFERENCES students(id),
    subject_id INTEGER REFERENCES subjects(id),
    score FLOAT,
    grade VARCHAR(2),
    UNIQUE(exam_id, student_id, subject_id)
);

-- Performance Snapshots
CREATE TABLE student_performance_snapshots (
    id INTEGER PRIMARY KEY,
    student_id INTEGER REFERENCES students(id),
    term_id INTEGER REFERENCES terms(id),
    average_score FLOAT,
    a1_count INTEGER,
    credit_count INTEGER,
    attendance_rate FLOAT,
    risk_level VARCHAR(10),
    class_rank INTEGER,
    UNIQUE(student_id, term_id)
);

-- Risk Assessments
CREATE TABLE student_risk_assessments (
    id INTEGER PRIMARY KEY,
    student_id INTEGER REFERENCES students(id),
    assessment_date DATE,
    overall_risk_score FLOAT,
    risk_level VARCHAR(10),
    risk_factors TEXT,  -- JSON
    recommendations TEXT  -- JSON
);

-- Academic Predictions
CREATE TABLE academic_predictions (
    id INTEGER PRIMARY KEY,
    student_id INTEGER REFERENCES students(id),
    prediction_type VARCHAR(50),  -- JAMB_SCORE, WAEC_GRADE, ADMISSION
    predicted_value VARCHAR(100),
    confidence_score FLOAT,
    explanation TEXT,
    actual_value VARCHAR(100)  -- For validation
);
```

## Role-Based Dashboard Views

### Student View
- Personal performance trends
- Subject strengths/weaknesses
- Predicted outcomes
- Improvement recommendations

### Teacher View
- Class-level subject analytics
- At-risk student lists
- Grade distribution by class
- Comparative analysis

### Administrator View
- School-wide statistics
- Year-over-year trends
- Subject effectiveness metrics
- WAEC/JAMB success rates
- Export and reporting tools

## Future Enhancements

1. **Internal Exam Integration**: Link CA, mock exams to predictions
2. **Attendance Correlation**: Factor attendance into risk scores
3. **University Admission Predictor**: Match scores to historical cutoffs
4. **Parent Dashboard**: Simplified view with key metrics
5. **SMS/Email Alerts**: Automated risk notifications
6. **Batch Import**: Excel upload for bulk results
7. **Advanced ML Models**: Neural network for score prediction
8. **Cohort Analysis**: Track class performance across years
