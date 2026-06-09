"""
Enhanced Exam Analytics Service
Comprehensive statistical analysis for WAEC, JAMB, and Mock JAMB results
Includes predictive analytics for Mock JAMB -> Real JAMB/WAEC correlation
"""
from collections import defaultdict
import math
from models import db, Student, WAECResult, JAMBResult
from models.mock_jamb import MockJAMBResult, MockJAMBExam


class ExamAnalytics:
    """Comprehensive exam analytics with predictions"""
    
    # JAMB score ranges for performance classification
    JAMB_RANGES = {
        'Excellent': (300, 400),
        'Very Good': (250, 299),
        'Good': (200, 249),
        'Average': (180, 199),
        'Below Average': (150, 179),
        'Poor': (0, 149)
    }
    
    # WAEC grade points for calculations
    WAEC_GRADE_POINTS = {
        'A1': 1, 'B2': 2, 'B3': 3, 'C4': 4, 'C5': 5, 'C6': 6,
        'D7': 7, 'E8': 8, 'F9': 9
    }
    
    # Core subjects for university admission
    CORE_SUBJECTS = ['English Language', 'Mathematics', 'Physics', 'Chemistry', 'Biology', 'Economics']
    
    @staticmethod
    def calculate_standard_deviation(values):
        """Calculate standard deviation"""
        if len(values) < 2:
            return 0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return math.sqrt(variance)
    
    @staticmethod
    def calculate_percentile(values, score):
        """Calculate percentile rank for a score"""
        if not values:
            return 0
        count_below = sum(1 for v in values if v < score)
        return round((count_below / len(values)) * 100, 1)
    
    @staticmethod
    def calculate_quartiles(values):
        """Calculate Q1, Q2 (median), Q3"""
        if not values:
            return {'Q1': 0, 'Q2': 0, 'Q3': 0}
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        
        def percentile(data, p):
            k = (len(data) - 1) * p / 100
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return data[int(k)]
            return data[f] * (c - k) + data[c] * (k - f)
        
        return {
            'Q1': round(percentile(sorted_vals, 25), 1),
            'Q2': round(percentile(sorted_vals, 50), 1),
            'Q3': round(percentile(sorted_vals, 75), 1)
        }


class JAMBAnalytics(ExamAnalytics):
    """Comprehensive JAMB results analytics"""
    
    @staticmethod
    def get_year_statistics(year):
        """Get comprehensive statistics for a JAMB year"""
        results = JAMBResult.query.filter_by(exam_year=year).all()
        
        if not results:
            return None
        
        scores = [r.total_score for r in results]
        
        # Basic stats
        stats = {
            'year': year,
            'total_students': len(results),
            'total_score': sum(scores),
            'mean_score': round(sum(scores) / len(scores), 1),
            'median_score': sorted(scores)[len(scores) // 2],
            'max_score': max(scores),
            'min_score': min(scores),
            'std_deviation': round(ExamAnalytics.calculate_standard_deviation(scores), 1),
            'score_range': max(scores) - min(scores),
        }
        
        # Quartiles
        quartiles = ExamAnalytics.calculate_quartiles(scores)
        stats.update(quartiles)
        stats['iqr'] = quartiles['Q3'] - quartiles['Q1']  # Interquartile range
        
        # Distribution by score ranges
        distribution = {
            '350-400': sum(1 for s in scores if 350 <= s <= 400),
            '300-349': sum(1 for s in scores if 300 <= s < 350),
            '250-299': sum(1 for s in scores if 250 <= s < 300),
            '200-249': sum(1 for s in scores if 200 <= s < 250),
            '180-199': sum(1 for s in scores if 180 <= s < 200),
            '150-179': sum(1 for s in scores if 150 <= s < 180),
            '0-149': sum(1 for s in scores if s < 150),
        }
        stats['distribution'] = distribution
        
        # Percentage distribution
        stats['distribution_pct'] = {
            k: round((v / len(scores)) * 100, 1) 
            for k, v in distribution.items()
        }
        
        # Above thresholds
        stats['above_300'] = sum(1 for s in scores if s >= 300)
        stats['above_250'] = sum(1 for s in scores if s >= 250)
        stats['above_200'] = sum(1 for s in scores if s >= 200)
        stats['above_180'] = sum(1 for s in scores if s >= 180)
        
        # Percentages
        stats['pct_above_300'] = round((stats['above_300'] / len(scores)) * 100, 1)
        stats['pct_above_250'] = round((stats['above_250'] / len(scores)) * 100, 1)
        stats['pct_above_200'] = round((stats['above_200'] / len(scores)) * 100, 1)
        
        # Performance levels
        stats['performance_distribution'] = {
            'Excellent': sum(1 for s in scores if s >= 300),
            'Very Good': sum(1 for s in scores if 250 <= s < 300),
            'Good': sum(1 for s in scores if 200 <= s < 250),
            'Average': sum(1 for s in scores if 180 <= s < 200),
            'Below Average': sum(1 for s in scores if s < 180),
        }
        
        # Gender analysis
        male_scores = [r.total_score for r in results if r.student.gender == 'Male']
        female_scores = [r.total_score for r in results if r.student.gender == 'Female']
        
        stats['gender_analysis'] = {
            'male': {
                'count': len(male_scores),
                'average': round(sum(male_scores) / len(male_scores), 1) if male_scores else 0,
                'max': max(male_scores) if male_scores else 0,
                'min': min(male_scores) if male_scores else 0,
            },
            'female': {
                'count': len(female_scores),
                'average': round(sum(female_scores) / len(female_scores), 1) if female_scores else 0,
                'max': max(female_scores) if female_scores else 0,
                'min': min(female_scores) if female_scores else 0,
            }
        }
        
        return stats
    
    @staticmethod
    def get_subject_performance(year):
        """Analyze subject-wise performance"""
        results = JAMBResult.query.filter_by(exam_year=year).all()
        
        subject_data = defaultdict(list)
        
        for r in results:
            if r.subject1 and r.subject1_score:
                subject_data[r.subject1].append(r.subject1_score)
            if r.subject2 and r.subject2_score:
                subject_data[r.subject2].append(r.subject2_score)
            if r.subject3 and r.subject3_score:
                subject_data[r.subject3].append(r.subject3_score)
            if r.subject4 and r.subject4_score:
                subject_data[r.subject4].append(r.subject4_score)
        
        subject_stats = []
        for subject, scores in subject_data.items():
            if scores:
                stats = {
                    'subject': subject,
                    'count': len(scores),
                    'avg_score': round(sum(scores) / len(scores), 1),
                    'max_score': max(scores),
                    'min_score': min(scores),
                    'std_deviation': round(ExamAnalytics.calculate_standard_deviation(scores), 1),
                    'above_70': sum(1 for s in scores if s >= 70),
                    'above_50': sum(1 for s in scores if s >= 50),
                    'above_70_pct': round((sum(1 for s in scores if s >= 70) / len(scores)) * 100, 1),
                    'above_50_pct': round((sum(1 for s in scores if s >= 50) / len(scores)) * 100, 1),
                    'below_40': sum(1 for s in scores if s < 40),
                }
                subject_stats.append(stats)
        
        return sorted(subject_stats, key=lambda x: x['avg_score'], reverse=True)
    
    @staticmethod
    def get_top_performers(year, limit=10):
        """Get top performing students"""
        results = JAMBResult.query.filter_by(exam_year=year).order_by(
            JAMBResult.total_score.desc()
        ).limit(limit).all()
        
        return [{
            'rank': i + 1,
            'student_id': r.student.student_id,
            'name': r.student.full_name,
            'score': r.total_score,
            'percentile': ExamAnalytics.calculate_percentile(
                [x.total_score for x in JAMBResult.query.filter_by(exam_year=year).all()],
                r.total_score
            )
        } for i, r in enumerate(results)]
    
    @staticmethod
    def get_year_comparison(years):
        """Compare statistics across multiple years"""
        comparison = []
        for year in years:
            stats = JAMBAnalytics.get_year_statistics(year)
            if stats:
                comparison.append({
                    'year': year,
                    'students': stats['total_students'],
                    'average': stats['mean_score'],
                    'median': stats['median_score'],
                    'max': stats['max_score'],
                    'min': stats['min_score'],
                    'above_250': stats['above_250'],
                    'pct_above_250': stats['pct_above_250'],
                })
        return comparison


class MockJAMBAnalytics(ExamAnalytics):
    """Mock JAMB analytics with predictive capabilities"""
    
    @staticmethod
    def get_exam_statistics(exam_id):
        """Get comprehensive statistics for a mock exam"""
        results = MockJAMBResult.query.filter_by(exam_id=exam_id).all()
        
        if not results:
            return None
        
        scores = [r.total_score for r in results]
        
        stats = {
            'exam_id': exam_id,
            'student_count': len(results),
            'statistics': {
                'average': round(sum(scores) / len(scores), 1),
                'median': sorted(scores)[len(scores) // 2],
                'max': max(scores),
                'min': min(scores),
                'std_deviation': round(ExamAnalytics.calculate_standard_deviation(scores), 1),
                'above_300': sum(1 for s in scores if s >= 300),
                'above_250': sum(1 for s in scores if s >= 250),
                'above_200': sum(1 for s in scores if s >= 200),
            },
            'distribution': {
                '300-400': sum(1 for s in scores if 300 <= s <= 400),
                '250-299': sum(1 for s in scores if 250 <= s < 300),
                '200-249': sum(1 for s in scores if 200 <= s < 250),
                '180-199': sum(1 for s in scores if 180 <= s < 200),
                '0-179': sum(1 for s in scores if s < 180),
            }
        }
        
        # Quartiles
        quartiles = ExamAnalytics.calculate_quartiles(scores)
        stats['statistics'].update(quartiles)
        
        # Subject analysis
        subject_data = defaultdict(list)
        for r in results:
            if r.subject1 and r.subject1_score:
                subject_data[r.subject1].append(r.subject1_score)
            if r.subject2 and r.subject2_score:
                subject_data[r.subject2].append(r.subject2_score)
            if r.subject3 and r.subject3_score:
                subject_data[r.subject3].append(r.subject3_score)
            if r.subject4 and r.subject4_score:
                subject_data[r.subject4].append(r.subject4_score)
        
        stats['subject_analysis'] = []
        for subject, subj_scores in subject_data.items():
            if subj_scores:
                stats['subject_analysis'].append({
                    'subject': subject,
                    'count': len(subj_scores),
                    'average': round(sum(subj_scores) / len(subj_scores), 1),
                    'max': max(subj_scores),
                    'min': min(subj_scores),
                    'above_70': sum(1 for s in subj_scores if s >= 70),
                    'above_50': sum(1 for s in subj_scores if s >= 50),
                })
        
        stats['subject_analysis'].sort(key=lambda x: x['average'], reverse=True)
        
        # Gender analysis
        male_scores = [r.total_score for r in results if r.student.gender == 'Male']
        female_scores = [r.total_score for r in results if r.student.gender == 'Female']
        
        stats['gender_analysis'] = {
            'male': {
                'count': len(male_scores),
                'average': round(sum(male_scores) / len(male_scores), 1) if male_scores else 0,
            },
            'female': {
                'count': len(female_scores),
                'average': round(sum(female_scores) / len(female_scores), 1) if female_scores else 0,
            }
        }
        
        return stats
    
    @staticmethod
    def predict_real_jamb(student_id, session_id=None):
        """
        Predict real JAMB score based on mock exam performance
        Uses weighted average with recent exams weighted more heavily
        """
        query = MockJAMBResult.query.filter_by(student_id=student_id)
        
        if session_id:
            query = query.join(MockJAMBExam).filter(MockJAMBExam.session_id == session_id)
        
        results = query.order_by(MockJAMBResult.id.desc()).all()
        
        if not results:
            return None
        
        # Weighted average - more recent exams get higher weight
        total_weight = 0
        weighted_sum = 0
        
        for i, r in enumerate(results):
            weight = len(results) - i  # Most recent gets highest weight
            weighted_sum += r.total_score * weight
            total_weight += weight
        
        predicted_score = round(weighted_sum / total_weight) if total_weight else 0
        
        # Calculate improvement trend
        scores = [r.total_score for r in reversed(results)]  # Chronological order
        improvement = 0
        if len(scores) >= 2:
            improvement = scores[-1] - scores[0]  # Latest - First
        
        # Consistency score (inverse of standard deviation)
        consistency = 100 - min(ExamAnalytics.calculate_standard_deviation(scores), 100)
        
        # Confidence level based on number of exams
        confidence = min(len(results) * 20, 100)  # Max at 5 exams
        
        return {
            'student_id': student_id,
            'mock_count': len(results),
            'mock_average': round(sum(scores) / len(scores), 1),
            'mock_highest': max(scores),
            'mock_lowest': min(scores),
            'predicted_score': predicted_score,
            'predicted_range': {
                'low': max(predicted_score - 30, 0),
                'high': min(predicted_score + 30, 400),
            },
            'improvement_trend': improvement,
            'improvement_per_exam': round(improvement / (len(results) - 1), 1) if len(results) > 1 else 0,
            'consistency_score': round(consistency, 1),
            'confidence_level': confidence,
            'recommendation': MockJAMBAnalytics._get_recommendation(predicted_score, improvement, consistency)
        }
    
    @staticmethod
    def _get_recommendation(predicted_score, improvement, consistency):
        """Generate personalized recommendation based on predictions"""
        if predicted_score >= 300 and consistency >= 70:
            return "Excellent preparation! Maintain your study routine and stay confident."
        elif predicted_score >= 250:
            if improvement > 20:
                return "Great progress! Focus on your weaker subjects to push into 300+."
            else:
                return "Good performance. Identify and work on areas where you lose points."
        elif predicted_score >= 200:
            if improvement > 0:
                return "You're improving! Increase practice intensity and focus on time management."
            else:
                return "Consider revising your study strategy. Focus on core concepts."
        else:
            return "More preparation needed. Start with fundamentals and gradually increase difficulty."
    
    @staticmethod
    def compare_mock_exams(session_id):
        """Compare performance across multiple mock exams in a session"""
        exams = MockJAMBExam.query.filter_by(session_id=session_id).order_by(
            MockJAMBExam.exam_date
        ).all()
        
        comparison = []
        for exam in exams:
            stats = MockJAMBAnalytics.get_exam_statistics(exam.id)
            if stats:
                comparison.append({
                    'exam_id': exam.id,
                    'exam_name': exam.display_name,
                    'exam_date': exam.exam_date,
                    'student_count': stats['student_count'],
                    'average': stats['statistics']['average'],
                    'median': stats['statistics']['median'],
                    'max': stats['statistics']['max'],
                    'min': stats['statistics']['min'],
                    'above_250': stats['statistics']['above_250'],
                })
        
        # Calculate trends
        if len(comparison) >= 2:
            for i in range(1, len(comparison)):
                comparison[i]['avg_change'] = round(
                    comparison[i]['average'] - comparison[i-1]['average'], 1
                )
        
        return comparison
    
    @staticmethod
    def predict_waec_performance(student_id, subject_mapping=None):
        """
        Predict WAEC performance based on Mock JAMB subject scores
        This is a rough correlation - actual WAEC depends on many factors
        """
        results = MockJAMBResult.query.filter_by(student_id=student_id).all()
        
        if not results:
            return None
        
        # Aggregate subject scores
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
        
        # Predict WAEC grades based on average JAMB subject scores
        predictions = []
        for subject, scores in subject_scores.items():
            avg_score = sum(scores) / len(scores)
            
            # Map JAMB score (0-100) to likely WAEC grade
            # This is approximate - JAMB 70+ often correlates with WAEC A1-B3
            if avg_score >= 80:
                predicted_grade = 'A1'
                confidence = 'High'
            elif avg_score >= 70:
                predicted_grade = 'B2-B3'
                confidence = 'High'
            elif avg_score >= 60:
                predicted_grade = 'B3-C4'
                confidence = 'Medium'
            elif avg_score >= 50:
                predicted_grade = 'C4-C6'
                confidence = 'Medium'
            elif avg_score >= 40:
                predicted_grade = 'C6-D7'
                confidence = 'Low'
            else:
                predicted_grade = 'D7-F9'
                confidence = 'Low'
            
            predictions.append({
                'subject': subject,
                'jamb_average': round(avg_score, 1),
                'exams_taken': len(scores),
                'predicted_waec_grade': predicted_grade,
                'confidence': confidence,
            })
        
        predictions.sort(key=lambda x: x['jamb_average'], reverse=True)
        
        return {
            'student_id': student_id,
            'total_subjects': len(predictions),
            'subject_predictions': predictions,
            'note': 'Predictions are based on Mock JAMB performance and may vary from actual WAEC results.'
        }
    
    @staticmethod
    def get_student_progress(student_id):
        """Get detailed progress report for a student"""
        results = MockJAMBResult.query.filter_by(student_id=student_id).join(
            MockJAMBExam
        ).order_by(MockJAMBExam.exam_date).all()
        
        if not results:
            return None
        
        student = db.session.get(Student, student_id)
        
        progress = {
            'student_id': student_id,
            'student_name': student.full_name if student else 'Unknown',
            'total_exams': len(results),
            'scores': [r.total_score for r in results],
            'dates': [r.exam.exam_date.strftime('%Y-%m-%d') for r in results],
            'exams': [{
                'name': r.exam.display_name,
                'date': r.exam.exam_date.strftime('%Y-%m-%d'),
                'score': r.total_score,
                'subjects': {
                    r.subject1: r.subject1_score,
                    r.subject2: r.subject2_score,
                    r.subject3: r.subject3_score,
                    r.subject4: r.subject4_score,
                }
            } for r in results]
        }
        
        scores = progress['scores']
        progress['statistics'] = {
            'average': round(sum(scores) / len(scores), 1),
            'highest': max(scores),
            'lowest': min(scores),
            'latest': scores[-1] if scores else 0,
            'first': scores[0] if scores else 0,
            'total_improvement': scores[-1] - scores[0] if len(scores) >= 2 else 0,
        }
        
        # Add prediction
        prediction = MockJAMBAnalytics.predict_real_jamb(student_id)
        if prediction:
            progress['prediction'] = prediction
        
        return progress


class WAECAnalytics(ExamAnalytics):
    """Enhanced WAEC analytics with comprehensive statistics"""
    
    @staticmethod
    def get_year_statistics(year):
        """Get comprehensive statistics for a WAEC year"""
        results = WAECResult.query.filter_by(exam_year=year).all()
        
        if not results:
            return None
        
        # Get unique students
        student_ids = set(r.student_id for r in results)
        
        # Grade distribution
        grade_counts = defaultdict(int)
        for r in results:
            grade_counts[r.grade] += 1
        
        # Subject analysis
        subject_data = defaultdict(lambda: {'grades': defaultdict(int), 'count': 0})
        for r in results:
            subject_data[r.subject]['grades'][r.grade] += 1
            subject_data[r.subject]['count'] += 1
        
        subject_analysis = []
        for subject, data in subject_data.items():
            grades = data['grades']
            total = data['count']
            a1_count = grades.get('A1', 0)
            credit_count = sum(grades.get(g, 0) for g in ['A1', 'B2', 'B3', 'C4', 'C5', 'C6'])
            
            subject_analysis.append({
                'subject': subject,
                'total': total,
                'a1_count': a1_count,
                'a1_rate': round(a1_count / total * 100, 1) if total else 0,
                'credit_count': credit_count,
                'credit_rate': round(credit_count / total * 100, 1) if total else 0,
                'fail_count': total - credit_count,
                'fail_rate': round((total - credit_count) / total * 100, 1) if total else 0,
                'grades': dict(grades),
            })
        
        subject_analysis.sort(key=lambda x: x['credit_rate'], reverse=True)
        
        # Student-level analysis
        student_stats = []
        for sid in student_ids:
            student_results = [r for r in results if r.student_id == sid]
            student = db.session.get(Student, sid)
            
            grades = [r.grade for r in student_results]
            points = [ExamAnalytics.WAEC_GRADE_POINTS.get(g, 9) for g in grades]
            
            a1_count = grades.count('A1')
            credit_count = sum(1 for g in grades if g in ['A1', 'B2', 'B3', 'C4', 'C5', 'C6'])
            
            student_stats.append({
                'student_id': sid,
                'name': student.full_name if student else 'Unknown',
                'total_subjects': len(student_results),
                'a1_count': a1_count,
                'credit_count': credit_count,
                'total_points': sum(points),
                'avg_points': round(sum(points) / len(points), 2) if points else 0,
            })
        
        # Overall statistics
        total_results = len(results)
        total_credits = sum(1 for r in results if r.grade in ['A1', 'B2', 'B3', 'C4', 'C5', 'C6'])
        total_distinctions = sum(1 for r in results if r.grade in ['A1', 'B2', 'B3'])
        
        stats = {
            'year': year,
            'total_students': len(student_ids),
            'total_results': total_results,
            'total_subjects': len(subject_data),
            'grade_distribution': dict(grade_counts),
            'overall_credit_rate': round(total_credits / total_results * 100, 1) if total_results else 0,
            'overall_distinction_rate': round(total_distinctions / total_results * 100, 1) if total_results else 0,
            'subject_analysis': subject_analysis,
            'student_stats': sorted(student_stats, key=lambda x: x['a1_count'], reverse=True),
            'top_performers': sorted(student_stats, key=lambda x: x['a1_count'], reverse=True)[:10],
            'students_with_5_credits': sum(1 for s in student_stats if s['credit_count'] >= 5),
            'students_with_5_credits_with_english_maths': 0,  # Calculate separately
        }
        
        # Calculate 5 credits including English and Maths
        english_maths_count = 0
        for sid in student_ids:
            student_results = [r for r in results if r.student_id == sid]
            subjects = {r.subject: r.grade for r in student_results}
            
            has_english = subjects.get('English Language') in ['A1', 'B2', 'B3', 'C4', 'C5', 'C6']
            has_maths = subjects.get('Mathematics') in ['A1', 'B2', 'B3', 'C4', 'C5', 'C6']
            credit_count = sum(1 for g in subjects.values() if g in ['A1', 'B2', 'B3', 'C4', 'C5', 'C6'])
            
            if has_english and has_maths and credit_count >= 5:
                english_maths_count += 1
        
        stats['students_with_5_credits_with_english_maths'] = english_maths_count
        
        return stats
    
    @staticmethod
    def get_student_waec_analysis(student_id, year=None):
        """Get detailed WAEC analysis for a student"""
        query = WAECResult.query.filter_by(student_id=student_id)
        if year:
            query = query.filter_by(exam_year=year)
        
        results = query.all()
        if not results:
            return None
        
        student = db.session.get(Student, student_id)
        
        # Group by year
        by_year = defaultdict(list)
        for r in results:
            by_year[r.exam_year].append(r)
        
        analysis = {
            'student_id': student_id,
            'student_name': student.full_name if student else 'Unknown',
            'years': {}
        }
        
        for yr, yr_results in by_year.items():
            grades = [r.grade for r in yr_results]
            points = [ExamAnalytics.WAEC_GRADE_POINTS.get(g, 9) for g in grades]
            subjects = {r.subject: r.grade for r in yr_results}
            
            a1_count = grades.count('A1')
            credit_count = sum(1 for g in grades if g in ['A1', 'B2', 'B3', 'C4', 'C5', 'C6'])
            
            # Check key requirements
            has_english = subjects.get('English Language') in ['A1', 'B2', 'B3', 'C4', 'C5', 'C6']
            has_maths = subjects.get('Mathematics') in ['A1', 'B2', 'B3', 'C4', 'C5', 'C6']
            
            analysis['years'][yr] = {
                'total_subjects': len(yr_results),
                'results': [{'subject': r.subject, 'grade': r.grade} for r in yr_results],
                'a1_count': a1_count,
                'credit_count': credit_count,
                'total_points': sum(points),
                'avg_points': round(sum(points) / len(points), 2) if points else 0,
                'has_english_credit': has_english,
                'has_maths_credit': has_maths,
                'meets_university_requirement': has_english and has_maths and credit_count >= 5,
                'grade_distribution': {g: grades.count(g) for g in ExamAnalytics.WAEC_GRADE_POINTS.keys() if grades.count(g) > 0},
                'best_subjects': [r.subject for r in sorted(yr_results, key=lambda x: ExamAnalytics.WAEC_GRADE_POINTS.get(x.grade, 9))[:3]],
                'weak_subjects': [r.subject for r in sorted(yr_results, key=lambda x: ExamAnalytics.WAEC_GRADE_POINTS.get(x.grade, 9), reverse=True) if ExamAnalytics.WAEC_GRADE_POINTS.get(r.grade, 9) >= 7][:3],
            }
        
        return analysis
    
    @staticmethod
    def compare_years(years=None):
        """Compare WAEC performance across multiple years"""
        if not years:
            years = [y[0] for y in db.session.query(WAECResult.exam_year).distinct().order_by(WAECResult.exam_year.desc()).limit(5).all()]
        
        comparison = []
        for year in sorted(years):
            stats = WAECAnalytics.get_year_statistics(year)
            if stats:
                comparison.append({
                    'year': year,
                    'total_students': stats['total_students'],
                    'credit_rate': stats['overall_credit_rate'],
                    'distinction_rate': stats['overall_distinction_rate'],
                    '5_credits': stats['students_with_5_credits'],
                    '5_credits_eng_maths': stats['students_with_5_credits_with_english_maths'],
                })
        
        return comparison


class WAECJAMBCorrelation(ExamAnalytics):
    """Analyze correlation between WAEC and JAMB/Mock JAMB performance"""
    
    # Correlation mappings based on typical performance patterns
    JAMB_TO_WAEC_MAP = {
        # JAMB subject score range -> likely WAEC grade
        (80, 100): 'A1',
        (70, 79): 'B2',
        (60, 69): 'B3',
        (50, 59): 'C4',
        (45, 49): 'C5',
        (40, 44): 'C6',
        (35, 39): 'D7',
        (25, 34): 'E8',
        (0, 24): 'F9',
    }
    
    WAEC_TO_JAMB_MAP = {
        # WAEC grade -> expected JAMB score range
        'A1': (75, 100),
        'B2': (65, 85),
        'B3': (55, 75),
        'C4': (45, 65),
        'C5': (40, 55),
        'C6': (35, 50),
        'D7': (25, 40),
        'E8': (15, 30),
        'F9': (0, 20),
    }
    
    @staticmethod
    def predict_waec_from_mock_jamb(student_id, session_id=None):
        """
        Predict WAEC grades based on Mock JAMB subject scores.
        More sophisticated than the simple method in MockJAMBAnalytics.
        """
        query = MockJAMBResult.query.filter_by(student_id=student_id)
        if session_id:
            query = query.join(MockJAMBExam).filter(MockJAMBExam.session_id == session_id)
        
        results = query.all()
        if not results:
            return None
        
        student = db.session.get(Student, student_id)
        
        # Aggregate scores by subject
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
        
        predictions = []
        for subject, scores in subject_scores.items():
            # Use weighted average (recent scores weighted more)
            weights = list(range(1, len(scores) + 1))
            weighted_avg = sum(s * w for s, w in zip(scores, weights)) / sum(weights)
            
            # Determine predicted grade
            predicted_grade = 'F9'
            for (low, high), grade in WAECJAMBCorrelation.JAMB_TO_WAEC_MAP.items():
                if low <= weighted_avg <= high:
                    predicted_grade = grade
                    break
            
            # Calculate confidence based on consistency and sample size
            std_dev = ExamAnalytics.calculate_standard_deviation(scores)
            consistency = max(0, 100 - std_dev * 2)
            sample_confidence = min(len(scores) * 25, 100)
            overall_confidence = round((consistency + sample_confidence) / 2)
            
            # Determine grade range
            grade_index = list(ExamAnalytics.WAEC_GRADE_POINTS.keys()).index(predicted_grade) if predicted_grade in ExamAnalytics.WAEC_GRADE_POINTS else 8
            
            predictions.append({
                'subject': subject,
                'mock_average': round(weighted_avg, 1),
                'mock_highest': max(scores),
                'mock_lowest': min(scores),
                'exams_taken': len(scores),
                'predicted_grade': predicted_grade,
                'grade_range': {
                    'best_case': list(ExamAnalytics.WAEC_GRADE_POINTS.keys())[max(0, grade_index - 1)],
                    'worst_case': list(ExamAnalytics.WAEC_GRADE_POINTS.keys())[min(8, grade_index + 1)],
                },
                'confidence': overall_confidence,
                'confidence_level': 'High' if overall_confidence >= 70 else 'Medium' if overall_confidence >= 40 else 'Low',
            })
        
        predictions.sort(key=lambda x: x['mock_average'], reverse=True)
        
        # Calculate overall prediction summary
        predicted_credits = sum(1 for p in predictions if p['predicted_grade'] in ['A1', 'B2', 'B3', 'C4', 'C5', 'C6'])
        predicted_distinctions = sum(1 for p in predictions if p['predicted_grade'] in ['A1', 'B2', 'B3'])
        
        # Check if likely to meet university requirements
        english_pred = next((p for p in predictions if 'English' in p['subject']), None)
        maths_pred = next((p for p in predictions if 'Mathematics' in p['subject'] or 'Maths' in p['subject']), None)
        
        meets_requirement = (
            predicted_credits >= 5 and
            english_pred and english_pred['predicted_grade'] in ['A1', 'B2', 'B3', 'C4', 'C5', 'C6'] and
            maths_pred and maths_pred['predicted_grade'] in ['A1', 'B2', 'B3', 'C4', 'C5', 'C6']
        )
        
        return {
            'student_id': student_id,
            'student_name': student.full_name if student else 'Unknown',
            'total_subjects': len(predictions),
            'subject_predictions': predictions,
            'summary': {
                'predicted_credits': predicted_credits,
                'predicted_distinctions': predicted_distinctions,
                'predicted_fails': len(predictions) - predicted_credits,
                'likely_meets_university_requirement': meets_requirement,
                'overall_outlook': 'Excellent' if predicted_credits >= 7 and predicted_distinctions >= 3 else
                                   'Good' if predicted_credits >= 5 and predicted_distinctions >= 1 else
                                   'Fair' if predicted_credits >= 5 else
                                   'Needs Improvement',
            },
            'recommendations': WAECJAMBCorrelation._generate_waec_recommendations(predictions),
        }
    
    @staticmethod
    def _generate_waec_recommendations(predictions):
        """Generate study recommendations based on predictions"""
        recommendations = []
        
        # Find weak subjects
        weak_subjects = [p for p in predictions if p['predicted_grade'] in ['D7', 'E8', 'F9']]
        borderline_subjects = [p for p in predictions if p['predicted_grade'] in ['C5', 'C6']]
        
        if weak_subjects:
            subjects = ', '.join(p['subject'] for p in weak_subjects[:3])
            recommendations.append({
                'priority': 'High',
                'area': 'Weak Subjects',
                'subjects': [p['subject'] for p in weak_subjects],
                'message': f"Focus intensive study on: {subjects}. These subjects need significant improvement.",
            })
        
        if borderline_subjects:
            subjects = ', '.join(p['subject'] for p in borderline_subjects[:3])
            recommendations.append({
                'priority': 'Medium',
                'area': 'Borderline Subjects',
                'subjects': [p['subject'] for p in borderline_subjects],
                'message': f"Push for better grades in: {subjects}. A little more effort can move these to solid credits.",
            })
        
        # Check core subjects
        english = next((p for p in predictions if 'English' in p['subject']), None)
        maths = next((p for p in predictions if 'Mathematics' in p['subject'] or 'Maths' in p['subject']), None)
        
        if english and english['predicted_grade'] not in ['A1', 'B2', 'B3', 'C4', 'C5', 'C6']:
            recommendations.append({
                'priority': 'Critical',
                'area': 'Core Subject',
                'subjects': ['English Language'],
                'message': "English Language credit is essential for university admission. Make it a top priority.",
            })
        
        if maths and maths['predicted_grade'] not in ['A1', 'B2', 'B3', 'C4', 'C5', 'C6']:
            recommendations.append({
                'priority': 'Critical',
                'area': 'Core Subject',
                'subjects': ['Mathematics'],
                'message': "Mathematics credit is required for most courses. Prioritize it immediately.",
            })
        
        if not recommendations:
            recommendations.append({
                'priority': 'Maintain',
                'area': 'General',
                'subjects': [],
                'message': "Good performance predicted! Maintain your study habits and aim for even higher grades.",
            })
        
        return recommendations
    
    @staticmethod
    def predict_jamb_from_waec(student_id, year=None):
        """
        Predict JAMB score based on WAEC performance.
        Useful for students who have WAEC results but haven't taken JAMB.
        """
        query = WAECResult.query.filter_by(student_id=student_id)
        if year:
            query = query.filter_by(exam_year=year)
        
        results = query.all()
        if not results:
            return None
        
        student = db.session.get(Student, student_id)
        
        # Group by subject
        subject_grades = {}
        for r in results:
            subject_grades[r.subject] = r.grade
        
        # Predict JAMB scores per subject
        subject_predictions = []
        total_predicted = 0
        subjects_for_jamb = []
        
        for subject, grade in subject_grades.items():
            score_range = WAECJAMBCorrelation.WAEC_TO_JAMB_MAP.get(grade, (20, 40))
            predicted_score = (score_range[0] + score_range[1]) // 2
            
            subject_predictions.append({
                'subject': subject,
                'waec_grade': grade,
                'predicted_jamb_score': predicted_score,
                'score_range': {'low': score_range[0], 'high': score_range[1]},
            })
            
            # Track for total (typical JAMB has 4 subjects)
            subjects_for_jamb.append({
                'subject': subject,
                'score': predicted_score,
                'range': score_range,
            })
        
        # Sort by predicted score descending
        subject_predictions.sort(key=lambda x: x['predicted_jamb_score'], reverse=True)
        subjects_for_jamb.sort(key=lambda x: x['score'], reverse=True)
        
        # Take top 4 for JAMB prediction
        top_4 = subjects_for_jamb[:4]
        predicted_total = sum(s['score'] for s in top_4)
        low_estimate = sum(s['range'][0] for s in top_4)
        high_estimate = sum(s['range'][1] for s in top_4)
        
        return {
            'student_id': student_id,
            'student_name': student.full_name if student else 'Unknown',
            'waec_year': year,
            'subject_predictions': subject_predictions,
            'jamb_prediction': {
                'predicted_score': predicted_total,
                'score_range': {'low': low_estimate, 'high': high_estimate},
                'top_4_subjects': [s['subject'] for s in top_4],
                'performance_level': 'Excellent' if predicted_total >= 300 else
                                    'Very Good' if predicted_total >= 250 else
                                    'Good' if predicted_total >= 200 else
                                    'Average' if predicted_total >= 180 else
                                    'Below Average',
            },
            'note': 'This prediction is based on WAEC grades and may vary based on actual JAMB preparation.',
        }
    
    @staticmethod
    def get_correlation_analysis(year=None):
        """
        Analyze correlation between Mock JAMB and actual WAEC results for students who have both.
        This helps validate and improve predictions.
        """
        # Find students with both Mock JAMB and WAEC results
        mock_students = db.session.query(MockJAMBResult.student_id).distinct().all()
        mock_student_ids = [s[0] for s in mock_students]
        
        waec_query = WAECResult.query.filter(WAECResult.student_id.in_(mock_student_ids))
        if year:
            waec_query = waec_query.filter_by(exam_year=year)
        
        waec_results = waec_query.all()
        if not waec_results:
            return None
        
        # Group WAEC by student
        waec_by_student = defaultdict(list)
        for r in waec_results:
            waec_by_student[r.student_id].append(r)
        
        correlations = []
        
        for student_id, waec_list in waec_by_student.items():
            # Get mock results for this student
            mock_results = MockJAMBResult.query.filter_by(student_id=student_id).all()
            if not mock_results:
                continue
            
            # Aggregate mock scores by subject
            mock_by_subject = defaultdict(list)
            for m in mock_results:
                if m.subject1 and m.subject1_score:
                    mock_by_subject[m.subject1].append(m.subject1_score)
                if m.subject2 and m.subject2_score:
                    mock_by_subject[m.subject2].append(m.subject2_score)
                if m.subject3 and m.subject3_score:
                    mock_by_subject[m.subject3].append(m.subject3_score)
                if m.subject4 and m.subject4_score:
                    mock_by_subject[m.subject4].append(m.subject4_score)
            
            # Compare with WAEC
            for waec in waec_list:
                if waec.subject in mock_by_subject:
                    mock_avg = sum(mock_by_subject[waec.subject]) / len(mock_by_subject[waec.subject])
                    waec_points = ExamAnalytics.WAEC_GRADE_POINTS.get(waec.grade, 9)
                    
                    correlations.append({
                        'student_id': student_id,
                        'subject': waec.subject,
                        'mock_avg': round(mock_avg, 1),
                        'waec_grade': waec.grade,
                        'waec_points': waec_points,
                    })
        
        if not correlations:
            return None
        
        # Analyze correlation
        # Group by mock score ranges
        score_ranges = [(0, 39), (40, 49), (50, 59), (60, 69), (70, 79), (80, 100)]
        range_analysis = []
        
        for low, high in score_ranges:
            range_data = [c for c in correlations if low <= c['mock_avg'] <= high]
            if range_data:
                grades = [c['waec_grade'] for c in range_data]
                points = [c['waec_points'] for c in range_data]
                
                grade_counts = defaultdict(int)
                for g in grades:
                    grade_counts[g] += 1
                
                most_common_grade = max(grade_counts, key=grade_counts.get)
                
                range_analysis.append({
                    'mock_range': f'{low}-{high}',
                    'sample_size': len(range_data),
                    'avg_waec_points': round(sum(points) / len(points), 2),
                    'most_common_grade': most_common_grade,
                    'grade_distribution': dict(grade_counts),
                })
        
        return {
            'total_comparisons': len(correlations),
            'unique_students': len(waec_by_student),
            'range_analysis': range_analysis,
            'correlations': correlations[:100],  # Limit for performance
        }

