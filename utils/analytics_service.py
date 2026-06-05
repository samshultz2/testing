"""
Comprehensive Analytics Service
Provides all statistical calculations, metrics, and ML predictions
"""
import json
import math
from datetime import datetime, date, timedelta
from collections import defaultdict
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy import func, and_, or_, desc, asc
from models.models import (
    db, Student, WAECResult, JAMBResult, Term, AcademicSession,
    StudentEnrollment, ClassArmAssignment, SchoolClass, ClassArm,
    Subject, Attendance
)


class AcademicAnalytics:
    """Core analytics engine for academic performance analysis"""
    
    # Grade constants
    WAEC_GRADES = ['A1', 'B2', 'B3', 'C4', 'C5', 'C6', 'D7', 'E8', 'F9']
    GRADE_POINTS = {'A1': 1, 'B2': 2, 'B3': 3, 'C4': 4, 'C5': 5, 'C6': 6, 'D7': 7, 'E8': 8, 'F9': 9}
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
            points = [AcademicAnalytics.GRADE_POINTS.get(g, 9) for g in grades]
            
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
        student = Student.query.get(student_id)
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
        active_term = Term.query.filter_by(is_active=True).first()
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
    def get_waec_school_statistics(exam_year: int) -> Dict:
        """Get comprehensive school-wide WAEC statistics"""
        results = WAECResult.query.filter_by(exam_year=exam_year).all()
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
            fail_count_subj = sum(stats['grades'].get(g, 0) for g in ['E8', 'F9'])
            
            subject_analysis.append({
                'subject': subject,
                'total_entries': total,
                'a1_count': a1_count,
                'a1_rate': round(a1_count / total * 100, 1) if total > 0 else 0,
                'pass_count': pass_count_subj,
                'pass_rate': round(pass_count_subj / total * 100, 1) if total > 0 else 0,
                'fail_count': fail_count_subj,
                'fail_rate': round(fail_count_subj / total * 100, 1) if total > 0 else 0,
                'grade_distribution': dict(stats['grades'])
            })
        
        # Sort subjects by various metrics
        subjects_by_a1_rate = sorted(subject_analysis, key=lambda x: x['a1_rate'], reverse=True)
        subjects_by_pass_rate = sorted(subject_analysis, key=lambda x: x['pass_rate'], reverse=True)
        subjects_by_fail_rate = sorted(subject_analysis, key=lambda x: x['fail_rate'], reverse=True)
        
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
            'most_failed_subjects': subjects_by_fail_rate[:5],
            'top_performers': [{'student_id': s[0], **s[1]} for s in top_by_a1]
        }
    
    @staticmethod
    def get_jamb_school_statistics(exam_year: int) -> Dict:
        """Get comprehensive school-wide JAMB statistics"""
        results = JAMBResult.query.filter_by(exam_year=exam_year).all()
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
    def calculate_waec_jamb_correlation(exam_year: int) -> Dict:
        """Calculate correlation between WAEC and JAMB performance"""
        # Get students with both WAEC and JAMB results for the year
        students_with_both = db.session.query(Student).join(
            WAECResult, Student.id == WAECResult.student_id
        ).join(
            JAMBResult, Student.id == JAMBResult.student_id
        ).filter(
            WAECResult.exam_year == exam_year,
            JAMBResult.exam_year == exam_year
        ).distinct().all()
        
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
    def get_year_over_year_comparison() -> Dict:
        """Compare performance metrics across years"""
        years = db.session.query(WAECResult.exam_year).distinct().order_by(WAECResult.exam_year.desc()).all()
        years = [y[0] for y in years][:5]  # Last 5 years
        
        waec_trends = []
        jamb_trends = []
        
        for year in years:
            # WAEC metrics
            waec_results = WAECResult.query.filter_by(exam_year=year).all()
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
            jamb_results = JAMBResult.query.filter_by(exam_year=year).all()
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
            active_term = Term.query.filter_by(is_active=True).first()
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
        student = Student.query.get(student_id)
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
