"""
Comprehensive Analytics Service
Provides all statistical calculations, metrics, and ML predictions
"""
import math
from utils.helpers import get_active_term
from collections import defaultdict
from typing import Dict, List, Tuple
from sqlalchemy import func
from models.models import (
    db, Student, WAECResult, JAMBResult, StudentEnrollment, ClassArmAssignment,
    Attendance
)


class AcademicAnalytics:
    """Core analytics engine for academic performance analysis"""
    
    # Grade constants
    WAEC_GRADES = ['A1', 'B2', 'B3', 'C4', 'C5', 'C6', 'D7', 'E8', 'F9']
    GRADE_POINTS = {'A1': 1, 'B2': 2, 'B3': 3, 'C4': 4, 'C5': 5, 'C6': 6, 'D7': 7, 'E8': 8, 'F9': 9}
    # Averages use a "higher is better" scale (A1 = 9 … F9 = 1) so a bigger
    # average grade-point means stronger performance. GRADE_POINTS (A1 = 1) stays
    # the WAEC ordinal used for ranking/prediction where lower = better.
    GRADE_AVERAGE_POINTS = {'A1': 9, 'B2': 8, 'B3': 7, 'C4': 6, 'C5': 5, 'C6': 4, 'D7': 3, 'E8': 2, 'F9': 1}
    PASS_GRADES = ['A1', 'B2', 'B3', 'C4', 'C5', 'C6']
    DISTINCTION_GRADES = ['A1', 'B2', 'B3']
    
    # ========================================================================
    # STUDENT-LEVEL ANALYTICS
    # ========================================================================
    
    @staticmethod
    def get_student_waec_summary(student_id: int, exam_year: int = None) -> Dict:
        """Get comprehensive WAEC summary for a student"""
        query = WAECResult.query.filter_by(student_id=student_id)
        if exam_year:
            query = query.filter_by(exam_year=exam_year)
        
        results = query.all()
        if not results:
            return None
        
        # Group by year
        by_year = defaultdict(list)
        for r in results:
            by_year[r.exam_year].append(r)
        
        summaries = {}
        for year, year_results in by_year.items():
            grades = [r.grade for r in year_results]
            # Average on the "higher is better" scale (A1 = 9 … F9 = 1).
            points = [AcademicAnalytics.GRADE_AVERAGE_POINTS.get(g, 0) for g in grades]

            summaries[year] = {
                'total_subjects': len(year_results),
                'results': [{'subject': r.subject, 'grade': r.grade} for r in year_results],
                'a1_count': grades.count('A1'),
                'distinction_count': sum(1 for g in grades if g in AcademicAnalytics.DISTINCTION_GRADES),
                'credit_count': sum(1 for g in grades if g in AcademicAnalytics.PASS_GRADES),
                'pass_count': sum(1 for g in grades if g not in ['E8', 'F9']),
                'fail_count': sum(1 for g in grades if g in ['E8', 'F9']),
                'total_points': sum(points),
                'average_points': round(sum(points) / len(points), 2) if points else 0,
                'grade_distribution': {g: grades.count(g) for g in AcademicAnalytics.WAEC_GRADES if grades.count(g) > 0},
                'best_subjects': [r.subject for r in sorted(year_results, key=lambda x: AcademicAnalytics.GRADE_POINTS.get(x.grade, 9))[:3]],
                'weak_subjects': [r.subject for r in sorted(year_results, key=lambda x: AcademicAnalytics.GRADE_POINTS.get(x.grade, 9), reverse=True)[:3] if AcademicAnalytics.GRADE_POINTS.get(r.grade, 9) >= 7]
            }
        
        return summaries
    
    @staticmethod
    def get_student_jamb_summary(student_id: int) -> Dict:
        """Get comprehensive JAMB summary for a student"""
        results = JAMBResult.query.filter_by(student_id=student_id).order_by(JAMBResult.exam_year.desc()).all()
        if not results:
            return None
        
        summaries = []
        for r in results:
            subjects = []
            if r.subject1 and r.subject1_score:
                subjects.append({'subject': r.subject1, 'score': r.subject1_score})
            if r.subject2 and r.subject2_score:
                subjects.append({'subject': r.subject2, 'score': r.subject2_score})
            if r.subject3 and r.subject3_score:
                subjects.append({'subject': r.subject3, 'score': r.subject3_score})
            if r.subject4 and r.subject4_score:
                subjects.append({'subject': r.subject4, 'score': r.subject4_score})
            
            subjects.sort(key=lambda x: x['score'], reverse=True)
            
            summaries.append({
                'exam_year': r.exam_year,
                'total_score': r.total_score,
                'subjects': subjects,
                'average_per_subject': round(r.total_score / 4, 1),
                'performance_level': AcademicAnalytics._jamb_performance_level(r.total_score),
                'best_subject': subjects[0] if subjects else None,
                'weakest_subject': subjects[-1] if subjects else None
            })
        
        return summaries
    
    @staticmethod
    def _jamb_performance_level(score: int) -> str:
        """Classify JAMB score into performance level"""
        if score >= 300: return 'EXCELLENT'
        elif score >= 250: return 'VERY_GOOD'
        elif score >= 200: return 'GOOD'
        elif score >= 180: return 'AVERAGE'
        elif score >= 150: return 'BELOW_AVERAGE'
        else: return 'POOR'
    
    @staticmethod
    def calculate_student_risk_score(student_id: int) -> Dict:
        """Calculate comprehensive risk assessment for a student"""
        student = db.session.get(Student, student_id)
        if not student:
            return None
        
        risk_factors = []
        risk_scores = {'academic': 0, 'attendance': 0, 'trend': 0}
        
        # Academic risk from WAEC
        waec_results = student.waec_results.all()
        if waec_results:
            latest_year = max(r.exam_year for r in waec_results)
            latest_results = [r for r in waec_results if r.exam_year == latest_year]
            
            fail_count = sum(1 for r in latest_results if r.grade in ['E8', 'F9'])
            credit_count = sum(1 for r in latest_results if r.grade in AcademicAnalytics.PASS_GRADES)
            
            if fail_count >= 3:
                risk_scores['academic'] += 40
                risk_factors.append(f"Multiple failures ({fail_count} subjects with E8/F9)")
            
            if credit_count < 5:
                risk_scores['academic'] += 30
                risk_factors.append(f"Insufficient credits ({credit_count} subjects with C6 or better)")
            
            # Check core subjects
            core_subjects = ['ENGLISH LANGUAGE', 'MATHEMATICS']
            for subj in core_subjects:
                core_result = next((r for r in latest_results if subj in r.subject.upper()), None)
                if core_result and core_result.grade in ['D7', 'E8', 'F9']:
                    risk_scores['academic'] += 20
                    risk_factors.append(f"Poor performance in {subj}")
        
        # Attendance risk
        active_term = get_active_term()
        if active_term:
            enrollment = StudentEnrollment.query.join(ClassArmAssignment).filter(
                StudentEnrollment.student_id == student_id,
                ClassArmAssignment.term_id == active_term.id
            ).first()
            
            if enrollment:
                attendance_records = Attendance.query.filter_by(
                    enrollment_id=enrollment.id
                ).all()
                
                if attendance_records:
                    # Calculate based on morning and afternoon presence
                    total_sessions = len(attendance_records) * 2  # 2 sessions per day
                    present_sessions = sum(
                        (1 if a.morning_present else 0) + (1 if a.afternoon_present else 0)
                        for a in attendance_records
                    )
                    attendance_rate = (present_sessions / total_sessions * 100) if total_sessions > 0 else 100
                    
                    if attendance_rate < 70:
                        risk_scores['attendance'] += 40
                        risk_factors.append(f"Low attendance rate ({attendance_rate:.1f}%)")
                    elif attendance_rate < 85:
                        risk_scores['attendance'] += 20
                        risk_factors.append(f"Below average attendance ({attendance_rate:.1f}%)")
        
        # Calculate overall risk
        overall_score = (risk_scores['academic'] * 0.5 + 
                        risk_scores['attendance'] * 0.3 + 
                        risk_scores['trend'] * 0.2)
        
        if overall_score >= 60:
            risk_level = 'RED'
        elif overall_score >= 30:
            risk_level = 'AMBER'
        else:
            risk_level = 'GREEN'
        
        return {
            'student_id': student_id,
            'student_name': student.full_name,
            'overall_risk_score': round(overall_score, 1),
            'risk_level': risk_level,
            'component_scores': risk_scores,
            'risk_factors': risk_factors,
            'recommendations': AcademicAnalytics._generate_recommendations(risk_factors)
        }
    
    @staticmethod
    def _generate_recommendations(risk_factors: List[str]) -> List[str]:
        """Generate actionable recommendations based on risk factors"""
        recommendations = []
        
        for factor in risk_factors:
            if 'failures' in factor.lower():
                recommendations.append("Arrange remedial classes for failed subjects")
                recommendations.append("Consider peer tutoring or study groups")
            if 'credits' in factor.lower():
                recommendations.append("Focus on converting D7s to credit passes")
            if 'ENGLISH' in factor or 'MATHEMATICS' in factor:
                recommendations.append("Prioritize intensive coaching in core subjects")
            if 'attendance' in factor.lower():
                recommendations.append("Schedule parent-teacher meeting to address attendance")
                recommendations.append("Investigate underlying causes of absenteeism")
        
        if not recommendations:
            recommendations.append("Maintain current performance level")
            recommendations.append("Consider advanced enrichment activities")
        
        return list(set(recommendations))  # Remove duplicates
    
    # ========================================================================
    # SCHOOL/COHORT-LEVEL ANALYTICS
    # ========================================================================
    
    @staticmethod
    def _by_branch(query, model, branch_id):
        """Restrict a WAEC/JAMB result query to one branch (None = all branches)."""
        if branch_id is not None:
            sub = db.session.query(Student.id).filter(Student.branch_id == branch_id)
            return query.filter(model.student_id.in_(sub))
        return query

    @staticmethod
    def get_waec_subject_analysis(subject, exam_year, branch_id=None, student_ids=None):
        """Full analysis of one WAEC subject in a year: grade distribution
        (A1…F9 counts + %), credit/distinction/pass/fail rates, average grade
        points (A1 = 9 … F9 = 1) and the candidate list per grade. Branch/arm
        scoped. Returns None when there are no results."""
        q = WAECResult.query.filter_by(exam_year=exam_year, subject=subject)
        q = AcademicAnalytics._by_branch(q, WAECResult, branch_id)
        if student_ids is not None:
            q = q.filter(WAECResult.student_id.in_(student_ids or [-1]))
        results = q.all()
        if not results:
            return None

        total = len(results)
        counts = {g: sum(1 for r in results if r.grade == g) for g in AcademicAnalytics.WAEC_GRADES}
        dist = [{'grade': g, 'count': counts[g],
                 'pct': round(counts[g] / total * 100, 1) if total else 0}
                for g in AcademicAnalytics.WAEC_GRADES]
        credit = sum(counts[g] for g in AcademicAnalytics.PASS_GRADES)
        distinction = sum(counts[g] for g in AcademicAnalytics.DISTINCTION_GRADES)
        fail = counts['E8'] + counts['F9']
        avg_points = round(
            sum(AcademicAnalytics.GRADE_AVERAGE_POINTS.get(r.grade, 0) for r in results) / total, 2)

        # Candidates grouped by grade (best → worst), with names.
        sids = list({r.student_id for r in results})
        students = {s.id: s for s in Student.query.filter(Student.id.in_(sids or [-1])).all()}
        by_grade = {g: [] for g in AcademicAnalytics.WAEC_GRADES}
        for r in results:
            st = students.get(r.student_id)
            if st:
                by_grade[r.grade].append({
                    'student_id': st.id, 'name': f'{st.surname} {st.first_name}',
                    'admission_no': st.student_id})
        for g in by_grade:
            by_grade[g].sort(key=lambda x: x['name'])

        return {
            'subject': subject, 'exam_year': exam_year, 'total': total,
            'distribution': dist, 'counts': counts,
            'credit_count': credit, 'credit_rate': round(credit / total * 100, 1) if total else 0,
            'distinction_count': distinction,
            'distinction_rate': round(distinction / total * 100, 1) if total else 0,
            'pass_count': credit, 'pass_rate': round(credit / total * 100, 1) if total else 0,
            'fail_count': fail, 'fail_rate': round(fail / total * 100, 1) if total else 0,
            'a1_count': counts['A1'],
            'average_points': avg_points, 'max_points': 9,
            'by_grade': by_grade,
        }

    # Score bands (out of 100) for per-subject JAMB / Mock-JAMB / Mock-WAEC score
    # distributions — highest band first.
    SCORE_BANDS = [(70, 100, 'Excellent (70–100)'), (50, 69, 'Good (50–69)'),
                   (40, 49, 'Fair (40–49)'), (25, 39, 'Weak (25–39)'),
                   (0, 24, 'Poor (0–24)')]

    @staticmethod
    def score_distribution(scores):
        """Band a list of 0–100 scores into SCORE_BANDS with counts + percentages."""
        n = len(scores) or 1
        out = []
        for lo, hi, label in AcademicAnalytics.SCORE_BANDS:
            c = sum(1 for s in scores if lo <= s <= hi)
            out.append({'label': label, 'lo': lo, 'hi': hi, 'count': c,
                        'pct': round(c / n * 100, 1)})
        return out

    @staticmethod
    def _score_subject_payload(subject, pairs):
        """Shared per-subject score analysis from (student_id, score) pairs."""
        if not pairs:
            return None
        scores = [s for _, s in pairs]
        total = len(scores)
        above_50 = sum(1 for s in scores if s >= 50)
        above_70 = sum(1 for s in scores if s >= 70)
        sids = list({sid for sid, _ in pairs})
        students = {s.id: s for s in Student.query.filter(Student.id.in_(sids or [-1])).all()}
        candidates = sorted(
            [{'student_id': sid, 'score': sc,
              'name': (f'{students[sid].surname} {students[sid].first_name}'
                       if sid in students else '—'),
              'admission_no': (students[sid].student_id if sid in students else '')}
             for sid, sc in pairs],
            key=lambda x: x['score'], reverse=True)
        return {
            'subject': subject, 'total': total,
            'avg_score': round(sum(scores) / total, 1),
            'max_score': max(scores), 'min_score': min(scores),
            'above_50': above_50, 'above_50_pct': round(above_50 / total * 100, 1),
            'above_70': above_70, 'above_70_pct': round(above_70 / total * 100, 1),
            'distribution': AcademicAnalytics.score_distribution(scores),
            'candidates': candidates,
        }

    @staticmethod
    def get_jamb_subject_analysis(subject, exam_year, branch_id=None, student_ids=None):
        """Per-subject JAMB score analysis for a year — score-band distribution,
        average, ≥50/≥70 rates and the ranked candidate list. Branch/arm scoped."""
        q = AcademicAnalytics._by_branch(
            JAMBResult.query.filter_by(exam_year=exam_year), JAMBResult, branch_id)
        if student_ids is not None:
            q = q.filter(JAMBResult.student_id.in_(student_ids or [-1]))
        pairs = []
        for r in q.all():
            for i in (1, 2, 3, 4):
                if getattr(r, f'subject{i}') == subject and getattr(r, f'subject{i}_score') is not None:
                    pairs.append((r.student_id, getattr(r, f'subject{i}_score')))
        payload = AcademicAnalytics._score_subject_payload(subject, pairs)
        if payload is not None:
            payload['exam_year'] = exam_year
        return payload

    @staticmethod
    def get_waec_school_statistics(exam_year: int, branch_id=None) -> Dict:
        """Get comprehensive school-wide WAEC statistics"""
        results = AcademicAnalytics._by_branch(
            WAECResult.query.filter_by(exam_year=exam_year), WAECResult, branch_id).all()
        if not results:
            return None
        
        # Basic counts
        total_results = len(results)
        unique_students = len(set(r.student_id for r in results))
        
        # Grade distribution
        grade_counts = {g: sum(1 for r in results if r.grade == g) for g in AcademicAnalytics.WAEC_GRADES}
        
        # Pass rates
        pass_count = sum(1 for r in results if r.grade in AcademicAnalytics.PASS_GRADES)
        distinction_count = sum(1 for r in results if r.grade in AcademicAnalytics.DISTINCTION_GRADES)
        
        # Subject-level analysis
        subject_stats = defaultdict(lambda: {'total': 0, 'grades': defaultdict(int)})
        for r in results:
            subject_stats[r.subject]['total'] += 1
            subject_stats[r.subject]['grades'][r.grade] += 1
        
        subject_analysis = []
        for subject, stats in subject_stats.items():
            total = stats['total']
            a1_count = stats['grades'].get('A1', 0)
            pass_count_subj = sum(stats['grades'].get(g, 0) for g in AcademicAnalytics.PASS_GRADES)
            # Two fail measures are reported side by side:
            #   fail (F9)          — the strict WAEC fail (D7 and E8 are Pass grades)
            #   below-credit       — anything short of a credit (D7 + E8 + F9)
            fail_count_subj = stats['grades'].get('F9', 0)
            below_credit_subj = sum(stats['grades'].get(g, 0) for g in ['D7', 'E8', 'F9'])

            subject_analysis.append({
                'subject': subject,
                'total_entries': total,
                'a1_count': a1_count,
                'a1_rate': round(a1_count / total * 100, 1) if total > 0 else 0,
                'pass_count': pass_count_subj,
                'pass_rate': round(pass_count_subj / total * 100, 1) if total > 0 else 0,
                'fail_count': fail_count_subj,
                'fail_rate': round(fail_count_subj / total * 100, 1) if total > 0 else 0,
                'below_credit_count': below_credit_subj,
                'below_credit_rate': round(below_credit_subj / total * 100, 1) if total > 0 else 0,
                'grade_distribution': dict(stats['grades'])
            })

        # Sort subjects by various metrics
        subjects_by_a1_rate = sorted(subject_analysis, key=lambda x: x['a1_rate'], reverse=True)
        subjects_by_pass_rate = sorted(subject_analysis, key=lambda x: x['pass_rate'], reverse=True)
        # rank "most failed" by the broader below-credit rate, then by strict F9
        subjects_by_fail_rate = sorted(
            subject_analysis, key=lambda x: (x['below_credit_rate'], x['fail_rate']), reverse=True)
        
        # Student rankings
        student_aggregates = defaultdict(lambda: {'a1_count': 0, 'credit_count': 0, 'total_points': 0, 'subjects': 0})
        for r in results:
            student_aggregates[r.student_id]['a1_count'] += 1 if r.grade == 'A1' else 0
            student_aggregates[r.student_id]['credit_count'] += 1 if r.grade in AcademicAnalytics.PASS_GRADES else 0
            student_aggregates[r.student_id]['total_points'] += AcademicAnalytics.GRADE_POINTS.get(r.grade, 9)
            student_aggregates[r.student_id]['subjects'] += 1
        
        # Top performers by A1 count
        top_by_a1 = sorted(
            [(sid, data) for sid, data in student_aggregates.items()],
            key=lambda x: x[1]['a1_count'],
            reverse=True
        )[:20]
        
        return {
            'exam_year': exam_year,
            'total_results': total_results,
            'unique_students': unique_students,
            'grade_distribution': grade_counts,
            'overall_pass_rate': round(pass_count / total_results * 100, 1) if total_results > 0 else 0,
            'overall_distinction_rate': round(distinction_count / total_results * 100, 1) if total_results > 0 else 0,
            'subject_analysis': subject_analysis,
            'top_subjects_by_a1': subjects_by_a1_rate[:5],
            'bottom_subjects_by_pass': subjects_by_pass_rate[-5:],
            # only subjects short of a credit in at least one entry — never pad
            # the list with 0%-fail subjects
            'most_failed_subjects': [s for s in subjects_by_fail_rate if s['below_credit_count'] > 0][:5],
            'top_performers': [{'student_id': s[0], **s[1]} for s in top_by_a1]
        }

    @staticmethod
    def get_waec_multiyear_trends(branch_id=None, limit_years=8):
        """Per-year WAEC cohort trend: how the 5-credits-incl-core rate, the
        credit rate and the F9 (fail) rate move across years. One point per year
        that has results, oldest→newest, capped to the most recent ``limit_years``.
        Branch-scoped when a branch is given."""
        from collections import defaultdict
        q = WAECResult.query.with_entities(
            WAECResult.exam_year, WAECResult.student_id, WAECResult.subject, WAECResult.grade)
        if branch_id is not None:
            q = q.join(Student, WAECResult.student_id == Student.id).filter(
                Student.branch_id == branch_id)
        rows = q.all()
        if not rows:
            return {'years': [], 'points': []}
        credit = lambda g: g in AcademicAnalytics.PASS_GRADES
        per_year = defaultdict(lambda: defaultdict(dict))     # year -> student -> {subject: grade}
        for yr, sid, subj, g in rows:
            per_year[yr][sid][subj] = g

        points = []
        for yr in sorted(per_year):
            students = per_year[yr]
            n = len(students)
            with_core = total_credits = entries = credit_entries = f9 = 0
            for gmap in students.values():
                credited = {s.lower() for s, g in gmap.items() if credit(g)}
                has_core = (any('english' in s for s in credited)
                            and any('math' in s for s in credited))
                creds = len(credited)
                if creds >= 5 and has_core:
                    with_core += 1
                total_credits += creds
                for g in gmap.values():
                    entries += 1
                    credit_entries += 1 if credit(g) else 0
                    f9 += 1 if g == 'F9' else 0
            points.append({
                'year': yr, 'students': n,
                'with_5_incl_core': with_core,
                'with_5_incl_core_pct': round(with_core / n * 100, 1) if n else 0,
                'credit_rate': round(credit_entries / entries * 100, 1) if entries else 0,
                'f9_rate': round(f9 / entries * 100, 1) if entries else 0,
                'avg_credits': round(total_credits / n, 1) if n else 0,
            })
        points = points[-limit_years:]
        return {'years': [p['year'] for p in points], 'points': points}

    @staticmethod
    def get_jamb_multiyear_trends(branch_id=None, limit_years=8):
        """Per-year JAMB trend: average total score and the ≥200 rate across
        years. One point per year with candidates, oldest→newest, capped to the
        most recent ``limit_years``. Branch-scoped when a branch is given."""
        from collections import defaultdict
        q = JAMBResult.query.with_entities(JAMBResult.exam_year, JAMBResult.total_score)
        if branch_id is not None:
            q = q.join(Student, JAMBResult.student_id == Student.id).filter(
                Student.branch_id == branch_id)
        per = defaultdict(list)
        for yr, sc in q.all():
            if sc is not None:
                per[yr].append(sc)
        if not per:
            return {'years': [], 'points': []}
        points = []
        for yr in sorted(per):
            scores = per[yr]
            n = len(scores)
            above = sum(1 for s in scores if s >= 200)
            points.append({
                'year': yr, 'candidates': n,
                'avg_score': round(sum(scores) / n, 1) if n else 0,
                'above_200': above,
                'above_200_pct': round(above / n * 100, 1) if n else 0,
                'max_score': max(scores) if scores else 0,
            })
        points = points[-limit_years:]
        return {'years': [p['year'] for p in points], 'points': points}

    @staticmethod
    def get_waec_subject_trends(branch_id=None, limit_years=8):
        """Per-subject WAEC credit-rate (C6+) across years, plus the biggest
        improvers/decliners (latest year vs the year before). Lets a school see
        which subjects are gaining or losing ground, not just the cohort totals."""
        from collections import defaultdict
        q = WAECResult.query.with_entities(
            WAECResult.exam_year, WAECResult.subject, WAECResult.grade)
        if branch_id is not None:
            q = q.join(Student, WAECResult.student_id == Student.id).filter(
                Student.branch_id == branch_id)
        rows = q.all()
        if not rows:
            return {'years': [], 'subjects': [], 'series': {}, 'movers': []}
        credit = lambda g: g in AcademicAnalytics.PASS_GRADES
        # year -> subject -> [offered, credited]
        agg = defaultdict(lambda: defaultdict(lambda: [0, 0]))
        subj_present = set()
        for yr, subj, g in rows:
            subj_present.add(subj)
            cell = agg[yr][subj]
            cell[0] += 1
            cell[1] += 1 if credit(g) else 0
        years = sorted(agg)[-limit_years:]
        subjects = AcademicAnalytics._ordered_waec_subjects(subj_present)
        series = {}
        for subj in subjects:
            series[subj] = [round(agg[y][subj][1] / agg[y][subj][0] * 100, 1)
                            if agg[y][subj][0] else None for y in years]
        movers = []
        if len(years) >= 2:
            latest, prev = years[-1], years[-2]
            for subj in subjects:
                a, b = agg[latest][subj], agg[prev][subj]
                if a[0] and b[0]:
                    lr = round(a[1] / a[0] * 100, 1)
                    pr = round(b[1] / b[0] * 100, 1)
                    movers.append({'subject': subj, 'latest': lr, 'prev': pr,
                                   'delta': round(lr - pr, 1)})
            movers.sort(key=lambda m: m['delta'], reverse=True)
        return {'years': years, 'subjects': subjects, 'series': series, 'movers': movers}

    @staticmethod
    def _ordered_waec_subjects(present):
        """WAEC subjects in canonical order (core first), extras appended A–Z."""
        try:
            from utils.helpers import WAEC_SUBJECTS
            order = {name: i for i, name in enumerate(WAEC_SUBJECTS)}
        except Exception:
            order = {}
        return sorted(present, key=lambda s: (order.get(s, len(order)), s))

    @staticmethod
    def get_waec_broadsheet(exam_year, branch_id=None):
        """The full grade matrix for a WAEC exam year — one row per student, one
        column per subject (grade only; WAEC reports no scores) — plus the
        per-subject and whole-cohort summaries, mirroring the mock-WAEC
        broadsheet. Scoped to a branch when given. Returns ``None`` when there
        are no results for the year."""
        from models import Student, WAECResult
        q = WAECResult.query.filter_by(exam_year=exam_year).join(Student)
        if branch_id is not None:
            q = q.filter(Student.branch_id == branch_id)
        results = q.all()
        if not results:
            return None

        grade_order = AcademicAnalytics.WAEC_GRADES
        pts = AcademicAnalytics.GRADE_POINTS               # A1=1 … F9=9 (lower = better)
        pt_to_grade = {v: k for k, v in pts.items()}
        credit = lambda g: g in AcademicAnalytics.PASS_GRADES

        cells, students, present = {}, {}, set()
        for r in results:
            present.add(r.subject)
            cells.setdefault(r.student_id, {})[r.subject] = r.grade
            students[r.student_id] = r.student
        subjects = AcademicAnalytics._ordered_waec_subjects(present)

        rows = []
        for sid, student in students.items():
            gmap = cells[sid]
            grades = list(gmap.values())
            credits = sum(1 for g in grades if credit(g))
            credited = {s.lower() for s, g in gmap.items() if credit(g)}
            has_core = any('english' in s for s in credited) and any('math' in s for s in credited)
            avg_pt = sum(pts.get(g, 9) for g in grades) / len(grades) if grades else None
            rows.append({
                # plain dict (not the ORM object) so the whole broadsheet is
                # JSON-serialisable and can be memoised in AnalyticsCache
                'student': {'id': student.id, 'full_name': student.full_name,
                            'surname': student.surname or '', 'first_name': student.first_name or '',
                            'stream': student.stream or ''},
                'cells': gmap,                                 # {subject: grade}
                'credits': credits,
                'distinctions': sum(1 for g in grades if g in AcademicAnalytics.DISTINCTION_GRADES),
                'has_5_incl_core': credits >= 5 and has_core,
                'has_5_credits': credits >= 5,
                'avg_grade': pt_to_grade.get(round(avg_pt), '—') if avg_pt is not None else '—',
                'subject_count': len(grades),
            })
        rows.sort(key=lambda x: (x['student']['surname'].lower(),
                                 x['student']['first_name'].lower()))

        subject_summary = {}
        for subj in subjects:
            sgrades = [cells[sid][subj] for sid in cells if subj in cells[sid]]
            offered = len(sgrades)
            passed = sum(1 for g in sgrades if credit(g))
            avg_pt = sum(pts.get(g, 9) for g in sgrades) / offered if offered else None
            dist = {g: 0 for g in grade_order}
            for g in sgrades:
                if g in dist:
                    dist[g] += 1
            subject_summary[subj] = {
                'offered': offered,
                'passed': passed,
                'failed': offered - passed,                    # short of a credit (D7–F9)
                'f9': dist['F9'],
                'avg_grade': pt_to_grade.get(round(avg_pt), '—') if avg_pt is not None else '—',
                'pass_rate': round(passed / offered * 100, 1) if offered else 0,
                'distribution': dist,
            }

        total_entries = len(results)
        overall_dist = {g: 0 for g in grade_order}
        for r in results:
            if r.grade in overall_dist:
                overall_dist[r.grade] += 1
        overall_pct = {g: (round(overall_dist[g] / total_entries * 100, 1) if total_entries else 0)
                       for g in grade_order}

        n = len(rows)
        with_core = sum(1 for r in rows if r['has_5_incl_core'])
        school = {
            'students': n,
            'subject_entries': total_entries,
            'with_5_credits': sum(1 for r in rows if r['has_5_credits']),
            'with_5_incl_core': with_core,
            'with_5_incl_core_pct': round(with_core / n * 100, 1) if n else 0,
            'avg_credits': round(sum(r['credits'] for r in rows) / n, 1) if n else 0,
        }

        return {
            'exam_year': exam_year,
            'subjects': subjects,
            'rows': rows,
            'subject_summary': subject_summary,
            'grade_order': grade_order,
            'grade_distribution': overall_dist,
            'grade_distribution_pct': overall_pct,
            'school': school,
        }

    @staticmethod
    def get_jamb_school_statistics(exam_year: int, branch_id=None) -> Dict:
        """Get comprehensive school-wide JAMB statistics"""
        results = AcademicAnalytics._by_branch(
            JAMBResult.query.filter_by(exam_year=exam_year), JAMBResult, branch_id).all()
        if not results:
            return None
        
        scores = [r.total_score for r in results]
        
        # Score distribution
        distribution = {
            '0-100': sum(1 for s in scores if s <= 100),
            '101-150': sum(1 for s in scores if 101 <= s <= 150),
            '151-200': sum(1 for s in scores if 151 <= s <= 200),
            '201-250': sum(1 for s in scores if 201 <= s <= 250),
            '251-300': sum(1 for s in scores if 251 <= s <= 300),
            '301-350': sum(1 for s in scores if 301 <= s <= 350),
            '351-400': sum(1 for s in scores if 351 <= s <= 400)
        }
        
        # Subject analysis
        subject_scores = defaultdict(list)
        for r in results:
            if r.subject1 and r.subject1_score:
                subject_scores[r.subject1].append(r.subject1_score)
            if r.subject2 and r.subject2_score:
                subject_scores[r.subject2].append(r.subject2_score)
            if r.subject3 and r.subject3_score:
                subject_scores[r.subject3].append(r.subject3_score)
            if r.subject4 and r.subject4_score:
                subject_scores[r.subject4].append(r.subject4_score)
        
        subject_analysis = []
        for subject, subj_scores in subject_scores.items():
            if subj_scores:
                subject_analysis.append({
                    'subject': subject,
                    'count': len(subj_scores),
                    'mean_score': round(sum(subj_scores) / len(subj_scores), 1),
                    'max_score': max(subj_scores),
                    'min_score': min(subj_scores),
                    'above_50': sum(1 for s in subj_scores if s >= 50),
                    'above_70': sum(1 for s in subj_scores if s >= 70)
                })
        
        subject_analysis.sort(key=lambda x: x['mean_score'], reverse=True)
        
        # Rankings
        ranked_students = sorted(results, key=lambda x: x.total_score, reverse=True)
        
        return {
            'exam_year': exam_year,
            'total_students': len(results),
            'mean_score': round(sum(scores) / len(scores), 1),
            'median_score': sorted(scores)[len(scores) // 2],
            'max_score': max(scores),
            'min_score': min(scores),
            'std_deviation': round(AcademicAnalytics._std_dev(scores), 1),
            'distribution': distribution,
            'above_200': sum(1 for s in scores if s >= 200),
            'above_250': sum(1 for s in scores if s >= 250),
            'above_300': sum(1 for s in scores if s >= 300),
            'subject_analysis': subject_analysis,
            'top_10': [{
                'student_id': r.student_id,
                'student_name': r.student.full_name,
                'score': r.total_score
            } for r in ranked_students[:10]]
        }
    
    @staticmethod
    def _std_dev(values: List[float]) -> float:
        """Calculate standard deviation"""
        if len(values) < 2:
            return 0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return math.sqrt(variance)
    
    # ========================================================================
    # WAEC-JAMB CORRELATION ANALYSIS
    # ========================================================================
    
    @staticmethod
    def calculate_waec_jamb_correlation(exam_year: int, branch_id=None) -> Dict:
        """Calculate correlation between WAEC and JAMB performance"""
        # Get students with both WAEC and JAMB results for the year
        q = db.session.query(Student).join(
            WAECResult, Student.id == WAECResult.student_id
        ).join(
            JAMBResult, Student.id == JAMBResult.student_id
        ).filter(
            WAECResult.exam_year == exam_year,
            JAMBResult.exam_year == exam_year
        )
        if branch_id is not None:
            q = q.filter(Student.branch_id == branch_id)
        students_with_both = q.distinct().all()
        
        if len(students_with_both) < 5:
            return {'error': 'Insufficient data for correlation analysis', 'sample_size': len(students_with_both)}
        
        waec_points = []
        jamb_scores = []
        
        for student in students_with_both:
            waec = student.waec_results.filter_by(exam_year=exam_year).all()
            jamb = student.jamb_results.filter_by(exam_year=exam_year).first()
            
            if waec and jamb:
                total_points = sum(AcademicAnalytics.GRADE_POINTS.get(r.grade, 9) for r in waec)
                avg_points = total_points / len(waec)
                waec_points.append(avg_points)
                jamb_scores.append(jamb.total_score)
        
        if len(waec_points) < 5:
            return {'error': 'Insufficient paired data', 'sample_size': len(waec_points)}
        
        # Calculate Pearson correlation
        correlation = AcademicAnalytics._pearson_correlation(waec_points, jamb_scores)
        
        # Interpretation
        if correlation <= -0.7:
            interpretation = "Strong negative correlation - lower WAEC points (better grades) correlate with higher JAMB scores"
        elif correlation <= -0.4:
            interpretation = "Moderate negative correlation - WAEC performance moderately predicts JAMB success"
        elif correlation <= -0.2:
            interpretation = "Weak negative correlation"
        elif correlation < 0.2:
            interpretation = "No significant correlation"
        else:
            interpretation = "Unexpected positive correlation - requires investigation"
        
        return {
            'exam_year': exam_year,
            'sample_size': len(waec_points),
            'correlation_coefficient': round(correlation, 3),
            'interpretation': interpretation,
            'mean_waec_points': round(sum(waec_points) / len(waec_points), 2),
            'mean_jamb_score': round(sum(jamb_scores) / len(jamb_scores), 1),
            'predictive_power': 'HIGH' if abs(correlation) >= 0.5 else 'MODERATE' if abs(correlation) >= 0.3 else 'LOW'
        }
    
    @staticmethod
    def _pearson_correlation(x: List[float], y: List[float]) -> float:
        """Calculate Pearson correlation coefficient"""
        n = len(x)
        if n < 2:
            return 0
        
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        
        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        
        sum_sq_x = sum((xi - mean_x) ** 2 for xi in x)
        sum_sq_y = sum((yi - mean_y) ** 2 for yi in y)
        
        denominator = math.sqrt(sum_sq_x * sum_sq_y)
        
        if denominator == 0:
            return 0
        
        return numerator / denominator
    
    # ========================================================================
    # YEAR-OVER-YEAR ANALYSIS
    # ========================================================================
    
    @staticmethod
    def get_year_over_year_comparison(branch_id=None) -> Dict:
        """Compare performance metrics across years"""
        years = db.session.query(WAECResult.exam_year).distinct().order_by(WAECResult.exam_year.desc()).all()
        years = [y[0] for y in years][:5]  # Last 5 years

        waec_trends = []
        jamb_trends = []

        for year in years:
            # WAEC metrics
            waec_results = AcademicAnalytics._by_branch(
                WAECResult.query.filter_by(exam_year=year), WAECResult, branch_id).all()
            if waec_results:
                total = len(waec_results)
                pass_count = sum(1 for r in waec_results if r.grade in AcademicAnalytics.PASS_GRADES)
                a1_count = sum(1 for r in waec_results if r.grade == 'A1')
                
                waec_trends.append({
                    'year': year,
                    'total_entries': total,
                    'pass_rate': round(pass_count / total * 100, 1),
                    'a1_rate': round(a1_count / total * 100, 1),
                    'unique_students': len(set(r.student_id for r in waec_results))
                })
            
            # JAMB metrics
            jamb_results = AcademicAnalytics._by_branch(
                JAMBResult.query.filter_by(exam_year=year), JAMBResult, branch_id).all()
            if jamb_results:
                scores = [r.total_score for r in jamb_results]
                jamb_trends.append({
                    'year': year,
                    'total_students': len(jamb_results),
                    'mean_score': round(sum(scores) / len(scores), 1),
                    'above_200_rate': round(sum(1 for s in scores if s >= 200) / len(scores) * 100, 1),
                    'above_250_rate': round(sum(1 for s in scores if s >= 250) / len(scores) * 100, 1)
                })
        
        return {
            'waec_trends': waec_trends,
            'jamb_trends': jamb_trends,
            'years_analyzed': years
        }
    
    # ========================================================================
    # FILTERING AND QUERYING
    # ========================================================================
    
    @staticmethod
    def filter_students(
        min_a1_count: int = None,
        max_a1_count: int = None,
        min_credits: int = None,
        exam_year: int = None,
        grade_in_subject: Tuple[str, str] = None,  # (subject, grade)
        risk_level: str = None,
        class_id: int = None,
        sort_by: str = 'name',
        sort_order: str = 'asc',
        limit: int = 100
    ) -> List[Dict]:
        """Advanced filtering for students based on multiple criteria"""
        
        # Start with base query
        query = Student.query.filter_by(is_active=True)
        
        # Build subqueries for WAEC criteria
        if any([min_a1_count, max_a1_count, min_credits, exam_year, grade_in_subject]):
            waec_subquery = db.session.query(
                WAECResult.student_id,
                func.sum(db.case((WAECResult.grade == 'A1', 1), else_=0)).label('a1_count'),
                func.sum(db.case((WAECResult.grade.in_(AcademicAnalytics.PASS_GRADES), 1), else_=0)).label('credit_count')
            )
            
            if exam_year:
                waec_subquery = waec_subquery.filter(WAECResult.exam_year == exam_year)
            
            waec_subquery = waec_subquery.group_by(WAECResult.student_id).subquery()
            
            query = query.join(waec_subquery, Student.id == waec_subquery.c.student_id)
            
            if min_a1_count:
                query = query.filter(waec_subquery.c.a1_count >= min_a1_count)
            if max_a1_count:
                query = query.filter(waec_subquery.c.a1_count <= max_a1_count)
            if min_credits:
                query = query.filter(waec_subquery.c.credit_count >= min_credits)
        
        # Subject-specific grade filter
        if grade_in_subject:
            subject, grade = grade_in_subject
            query = query.join(WAECResult).filter(
                WAECResult.subject == subject,
                WAECResult.grade == grade
            )
        
        # Class filter
        if class_id:
            active_term = get_active_term()
            if active_term:
                query = query.join(StudentEnrollment).join(ClassArmAssignment).filter(
                    ClassArmAssignment.term_id == active_term.id,
                    ClassArmAssignment.class_id == class_id
                )
        
        # Execute and format results
        students = query.distinct().limit(limit).all()
        
        results = []
        for student in students:
            waec_summary = AcademicAnalytics.get_student_waec_summary(student.id, exam_year)
            
            results.append({
                'id': student.id,
                'student_id': student.student_id,
                'name': student.full_name,
                'waec_summary': waec_summary
            })
        
        # Sort
        if sort_by == 'a1_count' and results:
            results.sort(
                key=lambda x: sum(y.get('a1_count', 0) for y in (x.get('waec_summary') or {}).values()),
                reverse=(sort_order == 'desc')
            )
        elif sort_by == 'name':
            results.sort(key=lambda x: x['name'], reverse=(sort_order == 'desc'))
        
        return results
    
    # ========================================================================
    # PREDICTIONS (Simple rule-based for interpretability)
    # ========================================================================
    
    @staticmethod
    def predict_jamb_score(student_id: int) -> Dict:
        """Predict JAMB score based on WAEC performance"""
        student = db.session.get(Student, student_id)
        if not student:
            return None
        
        waec_results = student.waec_results.order_by(WAECResult.exam_year.desc()).all()
        if not waec_results:
            return {'error': 'No WAEC results available for prediction'}
        
        # Get latest year results
        latest_year = max(r.exam_year for r in waec_results)
        latest_results = [r for r in waec_results if r.exam_year == latest_year]
        
        # Calculate average grade points
        total_points = sum(AcademicAnalytics.GRADE_POINTS.get(r.grade, 9) for r in latest_results)
        avg_points = total_points / len(latest_results)
        
        # Simple linear prediction model (based on typical correlations)
        # Lower WAEC points = better grades = higher JAMB prediction
        base_score = 400 - (avg_points - 1) * 30  # Rough linear mapping
        
        # Adjust for number of A1s
        a1_count = sum(1 for r in latest_results if r.grade == 'A1')
        a1_bonus = a1_count * 5
        
        # Adjust for core subjects
        core_bonus = 0
        for r in latest_results:
            if 'ENGLISH' in r.subject.upper() or 'MATHEMATICS' in r.subject.upper():
                if r.grade in ['A1', 'B2', 'B3']:
                    core_bonus += 10
        
        predicted_score = min(400, max(100, base_score + a1_bonus + core_bonus))
        
        # Confidence based on data quality
        confidence = min(0.9, 0.5 + (len(latest_results) / 20) + (0.1 if a1_count >= 3 else 0))
        
        # Score range
        margin = int(30 * (1 - confidence))
        score_range = (max(100, int(predicted_score - margin)), min(400, int(predicted_score + margin)))
        
        return {
            'student_id': student_id,
            'student_name': student.full_name,
            'predicted_score': int(predicted_score),
            'score_range': score_range,
            'confidence': round(confidence, 2),
            'performance_level': AcademicAnalytics._jamb_performance_level(int(predicted_score)),
            'explanation': f"Based on {len(latest_results)} WAEC subjects with average grade points of {avg_points:.1f}. "
                          f"Student has {a1_count} A1 grade(s).",
            'factors': {
                'waec_avg_points': round(avg_points, 2),
                'a1_count': a1_count,
                'subjects_analyzed': len(latest_results),
                'core_subjects_bonus': core_bonus
            }
        }
    
    @staticmethod
    def get_subject_recommendations(student_id: int) -> Dict:
        """Generate subject-specific recommendations"""
        waec_summary = AcademicAnalytics.get_student_waec_summary(student_id)
        if not waec_summary:
            return None
        
        # Get latest year
        latest_year = max(waec_summary.keys())
        summary = waec_summary[latest_year]
        
        recommendations = {
            'strengths': [],
            'needs_improvement': [],
            'career_suggestions': []
        }
        
        # Analyze each subject
        for result in summary['results']:
            grade = result['grade']
            subject = result['subject']
            
            if grade in ['A1', 'B2', 'B3']:
                recommendations['strengths'].append({
                    'subject': subject,
                    'grade': grade,
                    'message': f"Excellent performance in {subject}. Consider related career paths."
                })
            elif grade in ['D7', 'E8', 'F9']:
                recommendations['needs_improvement'].append({
                    'subject': subject,
                    'grade': grade,
                    'message': f"Needs significant improvement in {subject}. Recommend tutoring or extra classes."
                })
        
        # Career suggestions based on strong subjects
        strong_subjects = [r['subject'] for r in recommendations['strengths']]
        
        science_subjects = ['PHYSICS', 'CHEMISTRY', 'BIOLOGY', 'MATHEMATICS', 'FURTHER MATHEMATICS']
        arts_subjects = ['LITERATURE', 'GOVERNMENT', 'HISTORY', 'CRS', 'ECONOMICS']
        commercial_subjects = ['ACCOUNTING', 'COMMERCE', 'ECONOMICS', 'BUSINESS STUDIES']
        
        science_count = sum(1 for s in strong_subjects if any(sci in s.upper() for sci in science_subjects))
        arts_count = sum(1 for s in strong_subjects if any(art in s.upper() for art in arts_subjects))
        commercial_count = sum(1 for s in strong_subjects if any(com in s.upper() for com in commercial_subjects))
        
        if science_count >= 2:
            recommendations['career_suggestions'].append("Strong aptitude for Science-based careers: Medicine, Engineering, Technology")
        if arts_count >= 2:
            recommendations['career_suggestions'].append("Strong aptitude for Arts/Humanities: Law, Mass Communication, Education")
        if commercial_count >= 2:
            recommendations['career_suggestions'].append("Strong aptitude for Business/Commerce: Accounting, Banking, Business Administration")
        
        return recommendations
