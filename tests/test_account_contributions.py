"""/account must render the "My contributions" card. The data is a dict whose
key is 'items', and Jinja's ``x.items`` returns dict.items (the method) — the
template has to index it as ``x['items']``. Regression for a production 500."""


def test_account_renders_contributions_card(app, monkeypatch):
    import utils.self_service as A
    hr = {'staff_name': 'Test Staff', 'can_clock': False, 'attendance': None, 'today': None,
          'clock_action': None, 'payslips': None, 'deductions': [], 'leave': None,
          'leave_balances': None, 'loans': None, 'documents': None,
          'contributions': {'items': [{'name': 'Welfare', 'monthly': 2000.0, 'contributed': 6000.0,
                                       'months': 3, 'last': 'Oct 2026'}],
                            'total_monthly': 2000.0, 'total_contributed': 6000.0}}
    real = A.profile_self_service

    def fake(user, *a, **k):
        out = real(user, *a, **k)
        out['hr'] = hr
        return out
    monkeypatch.setattr(A, 'profile_self_service', fake)
    from tests.test_self_profile import _user, _login
    c = _login(app, _user(app))
    r = c.get('/account')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'My contributions' in body and 'Welfare' in body and '6,000.00' in body
