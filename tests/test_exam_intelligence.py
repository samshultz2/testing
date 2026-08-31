"""External-exams executive Smart Insights + cached school stats."""
import uuid

from config import Config
from models import db, Student, WAECResult, JAMBResult, AnalyticsCache
from tests.conftest import login_token
from utils import exam_intelligence as ei


def _titles(insights):
    return ' || '.join(i['title'] for i in insights)


def test_low_jamb_readiness_is_critical_and_first():
    ins = ei.school_insights(
        year=2024,
        cutoff={'eligible_200_pct': 22.0, 'competitive_250_pct': 5.0, 'elite_300_pct': 0.0},
        at_risk=[{'risk_level': 'RED'}, {'risk_level': 'AMBER'}],
        urls={'readiness': '/results/admission-readiness'})
    # critical insights sort ahead of everything else
    assert ins[0]['level'] == 'critical'
    joined = _titles(ins)
    assert '22.0% of JAMB candidates' in joined
    assert '2 SSS3 student(s) flagged at risk' in joined
    # the readiness action deep-links
    ready = next(i for i in ins if 'JAMB candidates cleared' in i['title'])
    assert ready['action']['url'] == '/results/admission-readiness'


def test_strong_cohort_reads_as_good_not_alarming():
    ins = ei.school_insights(
        year=2024,
        cutoff={'eligible_200_pct': 80.0, 'competitive_250_pct': 40.0, 'elite_300_pct': 10.0},
        waec_stats={'overall_pass_rate': 88.0, 'overall_distinction_rate': 30.0,
                    'most_failed_subjects': []})
    assert all(i['level'] in ('good', 'info') for i in ins)
    assert '80.0% of JAMB candidates cleared 200' in _titles(ins)


def test_waec_worst_subject_named_in_detail():
    ins = ei.school_insights(
        year=2024,
        waec_stats={'overall_pass_rate': 48.0, 'overall_distinction_rate': 4.0,
                    'most_failed_subjects': [
                        {'subject': 'Mathematics', 'fail_rate': 55.0},
                        {'subject': 'English', 'fail_rate': 30.0}]})
    waec = next(i for i in ins if 'WAEC pass rate is 48.0%' in i['title'])
    assert waec['level'] == 'critical'
    assert 'Mathematics' in waec['detail'] and '55.0% failing' in waec['detail']


def test_declining_jamb_projection_warns():
    ins = ei.school_insights(
        year=2024,
        projection={'direction': 'down', 'projected_mean': 165.0,
                    'slope_per_year': -8.0, 'latest_mean': 172.0})
    p = next(i for i in ins if 'trending down' in i['title'])
    assert p['level'] == 'warn' and '8.0 points a year' in p['detail']


def test_class_gap_flags_weakest_arm():
    ins = ei.school_insights(
        year=2024,
        class_compare=[
            {'arm': 'SSS3 Gold', 'jamb_count': 20, 'jamb_mean': 240.0},
            {'arm': 'SSS3 Silver', 'jamb_count': 18, 'jamb_mean': 200.0}])
    g = next(i for i in ins if 'SSS3 Silver trails' in i['title'])
    assert '240' in g['detail'] and '40' in g['detail']


def test_gender_gap_uses_larger_signal():
    ins = ei.school_insights(
        year=2024,
        jamb_gender_stats=[{'gender': 'Male', 'mean_score': 230},
                           {'gender': 'Female', 'mean_score': 205}])
    g = next(i for i in ins if 'JAMB by' in i['title'])
    assert 'Boys' in g['title']


def test_no_data_returns_single_info():
    ins = ei.school_insights(year=2024)
    assert len(ins) == 1 and ins[0]['level'] == 'info'
    assert 'Not enough data yet' in ins[0]['title']


# --------------------------------------------------------------------------- #
# Cached school statistics (route helpers)
# --------------------------------------------------------------------------- #
def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_school_stats_cached_then_busted(app):
    from routes.results import jamb_school_stats, bust_school_stats, _stats_cache_key
    yr = 2091
    with app.app_context():
        s = Student(student_id='EI' + uuid.uuid4().hex[:7].upper(), first_name='Ex',
                    surname='Am', gender='Male')
        db.session.add(s); db.session.commit()
        db.session.add(JAMBResult(student_id=s.id, exam_year=yr, total_score=250,
                                  subject1='English', subject1_score=70))
        db.session.commit()

        bust_school_stats()                              # cold start (shared DB)
        first = jamb_school_stats(yr, None)
        assert first and first['total_students'] == 1
        # a second call is served from AnalyticsCache (row now present)
        assert AnalyticsCache.get(_stats_cache_key('jamb', yr, None)) is not None
        assert jamb_school_stats(yr, None)['mean_score'] == 250.0

        bust_school_stats()
        assert AnalyticsCache.get(_stats_cache_key('jamb', yr, None)) is None


def test_analytics_hub_renders_smart_insights(app):
    yr = 2092
    with app.app_context():
        s = Student(student_id='EI' + uuid.uuid4().hex[:7].upper(), first_name='Hub',
                    surname='Render', gender='Female')
        db.session.add(s); db.session.commit()
        db.session.add(JAMBResult(student_id=s.id, exam_year=yr, total_score=150,
                                  subject1='English', subject1_score=40))
        db.session.add(WAECResult(student_id=s.id, exam_year=yr, subject='Mathematics', grade='F9'))
        db.session.commit()
    c = _admin(app)
    html = c.get(f'/results/analytics?year={yr}').get_data(as_text=True)
    assert 'Smart Insights' in html
    # executive KPI band with click-through anchors + remembered-filter script
    assert 'exec-band' in html
    assert 'id="sec-atrisk"' in html and 'href="#sec-jamb"' in html
    assert 'exam_hub_year' in html
    # the university-ready card deep-links to the readiness funnel
    assert '/results/admission-readiness' in html
    # export buttons for the executive reports
    assert '/results/analytics/board-pack' in html
    assert '/results/analytics/export.csv' in html


def _seed_year(app, yr, score=250, grade='F9'):
    with app.app_context():
        s = Student(student_id='EI' + uuid.uuid4().hex[:7].upper(), first_name='Rep',
                    surname='Ort', gender='Male')
        db.session.add(s); db.session.commit()
        db.session.add(JAMBResult(student_id=s.id, exam_year=yr, total_score=score,
                                  subject1='English', subject1_score=70,
                                  subject2='Mathematics', subject2_score=60))
        db.session.add(WAECResult(student_id=s.id, exam_year=yr, subject='Mathematics', grade=grade))
        db.session.commit()
        return s.id


def test_analytics_csv_export(app):
    yr = 2093
    _seed_year(app, yr)
    c = _admin(app)
    resp = c.get(f'/results/analytics/export.csv?year={yr}')
    assert resp.status_code == 200
    assert resp.mimetype == 'text/csv'
    assert f'exam_analytics_{yr}.csv' in resp.headers['Content-Disposition']
    body = resp.get_data(as_text=True)
    assert 'JAMB' in body and 'WAEC' in body
    assert 'Insight' in body                       # smart insights are appended


def test_board_pack_pdf(app):
    yr = 2094
    _seed_year(app, yr)
    c = _admin(app)
    resp = c.get(f'/results/analytics/board-pack?year={yr}')
    assert resp.status_code == 200
    assert resp.mimetype == 'application/pdf'
    assert resp.get_data()[:4] == b'%PDF'


def test_board_pack_without_year_redirects(app):
    c = _admin(app)
    resp = c.get('/results/analytics/board-pack')
    assert resp.status_code == 302
