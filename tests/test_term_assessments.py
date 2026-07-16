"""Per-term assessment settings — a term can carry its own component maxes (e.g.
no CBT, Theory bumped) without affecting other terms; backward compatible."""
from models import db, AssessmentType, Subject, Term, AcademicSession
from utils import assessments as A


def _setup(app):
    with app.app_context():
        from utils.finance_ledger import ensure_tables; ensure_tables()
        # a clean, known assessment scheme for this test
        AssessmentType.query.delete()
        for n, sn, mx, o in [('CA', 'CA', 10, 1), ('CBT', 'CBT', 30, 2), ('Theory', 'EXAM', 40, 3)]:
            db.session.add(AssessmentType(name=n, short_name=sn, max_score=mx, order=o, is_active=True))
        subj = Subject(name='Maths Test')
        db.session.add(subj)
        sess = AcademicSession.query.first() or AcademicSession(name='2024/2025', is_active=True)
        db.session.add(sess); db.session.flush()
        t1 = Term(name='T-normal', term_number=1, session_id=sess.id)
        t2 = Term(name='T-peculiar', term_number=2, session_id=sess.id)
        db.session.add_all([t1, t2]); db.session.commit()
        return {'subj': subj.id, 't1': t1.id, 't2': t2.id,
                'ca': AssessmentType.query.filter_by(short_name='CA').first().id,
                'cbt': AssessmentType.query.filter_by(short_name='CBT').first().id,
                'theory': AssessmentType.query.filter_by(short_name='EXAM').first().id}


def test_no_term_settings_uses_defaults(app):
    ids = _setup(app)
    with app.app_context():
        subj = db.session.get(Subject, ids['subj'])
        theory = db.session.get(AssessmentType, ids['theory'])
        # no per-term settings -> global default
        assert A.effective_max(subj, theory, term=ids['t1']) == 40
        assert not A.has_term_settings(ids['t1'])


def test_peculiar_term_bumps_theory_and_drops_cbt(app):
    ids = _setup(app)
    with app.app_context():
        A.save_term_settings(ids['t2'], {ids['ca']: 10, ids['cbt']: 0, ids['theory']: 70})
        subj = db.session.get(Subject, ids['subj'])
        theory = db.session.get(AssessmentType, ids['theory'])
        assert A.effective_max(subj, theory, term=ids['t2']) == 70
        cols = {at.short_name: mx for at, mx in A.subject_columns(subj, term=ids['t2'])}
        assert cols.get('EXAM') == 70 and 'CBT' not in cols     # CBT (max 0) dropped
        # the OTHER term is untouched
        assert A.effective_max(subj, theory, term=ids['t1']) == 40


def test_copy_and_clear_term_settings(app):
    ids = _setup(app)
    with app.app_context():
        A.save_term_settings(ids['t2'], {ids['ca']: 10, ids['cbt']: 0, ids['theory']: 70})
        subj = db.session.get(Subject, ids['subj'])
        theory = db.session.get(AssessmentType, ids['theory'])
        # copy peculiar settings onto the normal term
        assert A.copy_term_settings(ids['t2'], ids['t1']) == 3
        assert A.effective_max(subj, theory, term=ids['t1']) == 70
        # clearing reverts to the global defaults
        A.save_term_settings(ids['t1'], {})
        assert A.effective_max(subj, theory, term=ids['t1']) == 40
        assert not A.has_term_settings(ids['t1'])


def test_admin_pages_render_and_save(app):
    from config import Config
    from tests.conftest import login_token, auth_csrf
    ids = _setup(app)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    assert c.get('/settings/assessments/terms').status_code == 200
    r = c.get(f"/settings/assessments/terms/{ids['t2']}")
    assert r.status_code == 200 and 'T-peculiar' in r.get_data(as_text=True)
    # save custom maxes via the form
    c.post(f"/settings/assessments/terms/{ids['t2']}/save", data={
        '_csrf_token': auth_csrf(c),
        'at_id[]': [str(ids['ca']), str(ids['cbt']), str(ids['theory'])],
        'max_score[]': ['10', '0', '70']})
    with app.app_context():
        subj = db.session.get(Subject, ids['subj'])
        theory = db.session.get(AssessmentType, ids['theory'])
        assert A.effective_max(subj, theory, term=ids['t2']) == 70
