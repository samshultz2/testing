"""When day-separation is on and a run fails for reasons diagnose_infeasibility()
can't pin on a single provable cause, _probe_day_separation_class_exemptions()
tries exempting one whole class at a time (short re-solve each) to tell the
admin up front which per-class exception would actually fix it -- instead of
leaving them to guess-and-check through the Rules page, as reported: turning
the rule on for a subject failed across every class, but exempting it for
just one class and keeping it for the rest worked.

The budgeting/looping/message logic is unit-tested here with the recursive
generate_with_ortools() call mocked out (so it's fast and deterministic);
test_generator_infeasible_diagnostics.py's real combinatorial-failure
scenario gives the end-to-end smoke test that it's actually wired in."""
from routes import generator_ortools as go


def test_probe_skips_when_not_enough_time_left():
    msg = go._probe_day_separation_class_exemptions(
        class_ids=[1], periods_per_day=8, break_after=4, first_period_no_repeat=True,
        day_separation_default_enabled=True, day_separation_default_day_a=0,
        day_separation_default_day_b=4, candidate_classes={'SSS1', 'SSS2'},
        elapsed_so_far=go.PROBE_SAFETY_MARGIN)
    assert 'Not enough time left' in msg
    assert 'Rules page' in msg


def test_probe_reports_which_class_exemption_fixes_it(monkeypatch):
    calls = []

    def fake_generate(*args, **kwargs):
        exempt = kwargs.get('extra_day_sep_class_exempt')
        calls.append(exempt)
        assert kwargs.get('_day_sep_probe') is True
        return {'success': exempt == {'SSS1'}}

    monkeypatch.setattr(go, 'generate_with_ortools', fake_generate)
    msg = go._probe_day_separation_class_exemptions(
        class_ids=[1, 2], periods_per_day=8, break_after=4, first_period_no_repeat=True,
        day_separation_default_enabled=True, day_separation_default_day_a=0,
        day_separation_default_day_b=4, candidate_classes={'SSS1', 'SSS2'},
        elapsed_so_far=0)
    assert len(calls) == 2
    assert 'exempting SSS1 on its own would make this solvable' in msg
    assert 'SSS2' not in msg
    assert 'Per-Class Exceptions' in msg


def test_probe_reports_no_fix_found_when_no_single_exemption_works(monkeypatch):
    monkeypatch.setattr(go, 'generate_with_ortools', lambda *a, **k: {'success': False})
    msg = go._probe_day_separation_class_exemptions(
        class_ids=[1, 2], periods_per_day=8, break_after=4, first_period_no_repeat=True,
        day_separation_default_enabled=True, day_separation_default_day_a=0,
        day_separation_default_day_b=4, candidate_classes={'SSS1', 'SSS2'},
        elapsed_so_far=0)
    assert 'none alone fixed it' in msg
    assert 'SSS1' in msg and 'SSS2' in msg


def test_probe_never_raises_when_recursive_call_throws(monkeypatch):
    """A probe is a best-effort diagnostic bolted onto an already-failed run
    -- it must never itself turn a clean failure response into a 500."""
    def boom(*args, **kwargs):
        raise RuntimeError('boom')
    monkeypatch.setattr(go, 'generate_with_ortools', boom)
    msg = go._probe_day_separation_class_exemptions(
        class_ids=[1], periods_per_day=8, break_after=4, first_period_no_repeat=True,
        day_separation_default_enabled=True, day_separation_default_day_a=0,
        day_separation_default_day_b=4, candidate_classes={'SSS1'},
        elapsed_so_far=0)
    assert 'none alone fixed it' in msg


def test_probe_runs_end_to_end_without_crashing_on_real_combinatorial_failure(app):
    """Smoke test: the probe is actually wired into generate_with_ortools's
    failure path and doesn't break the request, using the same contended-
    teacher + day-separation scenario test_generator_infeasible_diagnostics.py
    already relies on for a genuinely solver-side (not structurally-provable)
    failure."""
    from tests.test_generator_infeasible_diagnostics import _build_contended_scenario
    from config import Config
    from tests.conftest import login_token
    from models import db, Branch, GenTimetableRule

    class_ids = _build_contended_scenario(app, 'ZzProbeE2E', day_separation_enabled=True,
                                          periods_per_week=4)
    try:
        c = app.test_client()
        c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
        with c.session_transaction() as s:
            s['_csrf_token'] = 'a' * 64
        r = c.post('/generator/generate/ortools', follow_redirects=True, data={
            '_csrf_token': 'a' * 64,
            'class_ids[]': [str(i) for i in class_ids],
            'time_limit': '10',
        })
        assert r.status_code == 200
        body = r.data.decode('utf-8', errors='replace')
        assert 'Generation failed' in body
        # Whichever branch it took (ran out of budget vs. actually probed),
        # the probe must have left SOME trace -- not silently skipped.
        assert ('Tried exempting' in body) or ('Not enough time left' in body)
    finally:
        with app.app_context():
            bid = Branch.get_default().id
            GenTimetableRule.query.filter(
                GenTimetableRule.rule_type.in_(['day_separation_enabled', 'first_period_no_repeat']),
                GenTimetableRule.school_level == 'sss', GenTimetableRule.branch_id == bid,
            ).delete(synchronize_session=False)
            db.session.commit()


def test_auto_probe_toggle_defaults_on_and_persists_from_rules_page(app):
    """The Rules page checkbox ("If generation fails, automatically test
    which class exemption would fix it") defaults to checked when never
    saved, and save_rules() writes an explicit true/false every time --
    same pattern as the other day-separation toggles on that page. Uses its
    own dedicated branch, like test_generator_day_separation_opt_in.py's
    rules-page tests, so it never touches the shared default branch other
    tests in this session rely on."""
    import re
    from config import Config
    from models import db, Branch, GenTimetableRule
    from tests.conftest import login_token

    with app.app_context():
        b = Branch(name='ZzAutoProbeToggle', code=None)
        db.session.add(b); db.session.flush(); bid = b.id
        db.session.commit()

    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
        s['view_branch_id'] = bid

    body = c.get('/generator/rules').get_data(as_text=True)
    assert re.search(r'name="day_separation_auto_probe"\s+checked', body), (
        'checkbox should default to checked when no rule row has been saved yet')

    r = c.post('/generator/rules/save', data={
        '_csrf_token': 'a' * 64, 'periods_per_day': '8', 'break_after_period': '5',
        'day_start': '8:00', 'period_minutes': '40', 'break_minutes': '30', 'max_consecutive': '3',
        # day_separation_auto_probe omitted -> unchecked -> must save as 'false'.
    })
    assert r.status_code in (302, 200)
    with app.app_context():
        rule = GenTimetableRule.query.filter_by(rule_type='day_separation_auto_probe',
                                                school_level='sss', branch_id=bid).first()
        assert rule is not None and rule.value == 'false'

    r2 = c.post('/generator/rules/save', data={
        '_csrf_token': 'a' * 64, 'periods_per_day': '8', 'break_after_period': '5',
        'day_start': '8:00', 'period_minutes': '40', 'break_minutes': '30', 'max_consecutive': '3',
        'day_separation_auto_probe': 'on',
    })
    assert r2.status_code in (302, 200)
    with app.app_context():
        rule = GenTimetableRule.query.filter_by(rule_type='day_separation_auto_probe',
                                                school_level='sss', branch_id=bid).first()
        assert rule is not None and rule.value == 'true'


def test_auto_probe_disabled_skips_probing_entirely(app):
    """With the toggle off, a failed run's message must not carry any trace
    of probing (no "Tried exempting", no "Not enough time left") -- the
    extra re-solving must not run at all, not just be hidden."""
    from tests.test_generator_infeasible_diagnostics import _build_contended_scenario
    from config import Config
    from tests.conftest import login_token
    from models import db, Branch, GenTimetableRule

    class_ids = _build_contended_scenario(app, 'ZzProbeOff', day_separation_enabled=True,
                                          periods_per_week=4)
    try:
        with app.app_context():
            bid = Branch.get_default().id
            db.session.add(GenTimetableRule(branch_id=bid, rule_type='day_separation_auto_probe',
                                            value='false', school_level='sss', is_active=True))
            db.session.commit()

        c = app.test_client()
        c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
        with c.session_transaction() as s:
            s['_csrf_token'] = 'a' * 64
        r = c.post('/generator/generate/ortools', follow_redirects=True, data={
            '_csrf_token': 'a' * 64,
            'class_ids[]': [str(i) for i in class_ids],
            'time_limit': '10',
        })
        assert r.status_code == 200
        body = r.data.decode('utf-8', errors='replace')
        assert 'Generation failed' in body
        assert 'Tried exempting' not in body
        assert 'Not enough time left' not in body
    finally:
        with app.app_context():
            bid = Branch.get_default().id
            GenTimetableRule.query.filter(
                GenTimetableRule.rule_type.in_(
                    ['day_separation_enabled', 'first_period_no_repeat', 'day_separation_auto_probe']),
                GenTimetableRule.school_level == 'sss', GenTimetableRule.branch_id == bid,
            ).delete(synchronize_session=False)
            db.session.commit()
