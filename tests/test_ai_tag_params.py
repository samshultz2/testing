"""Model-dependent request settings for the AI question taggers."""
from types import SimpleNamespace

from utils.ai_tag_params import create, tag_params, thinks
from utils.mock_bank_batch_retag import build_requests


def test_thinking_models_get_room_and_effort():
    for m in ('claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5', 'claude-fable-5-2'):
        assert thinks(m)
        mt, extra = tag_params(m, 300)
        assert mt > 300 and extra == {'output_config': {'effort': 'low'}}


def test_older_models_unchanged():
    for m in ('claude-haiku-4-5', 'claude-sonnet-4-6', 'claude-opus-4-8', ''):
        assert not thinks(m)
        assert tag_params(m, 300) == (300, {})


def test_effort_from_env(monkeypatch):
    monkeypatch.setenv('AI_TAG_EFFORT', 'medium')
    assert tag_params('claude-opus-5-5', 10)[1]['output_config']['effort'] == 'medium'
    monkeypatch.setenv('AI_TAG_EFFORT', 'silly')
    assert tag_params('claude-opus-5-5', 10)[1]['output_config']['effort'] == 'low'


def test_create_puts_effort_in_extra_body():
    seen = {}
    client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: seen.update(kw)))
    create(client, 'claude-sonnet-5-5', 2000, messages=[])
    assert seen['max_tokens'] > 2000 and seen['extra_body']['output_config']['effort'] == 'low'
    seen.clear()
    create(client, 'claude-haiku-4-5', 2000, messages=[])
    assert seen['max_tokens'] == 2000 and 'extra_body' not in seen


def test_batch_requests_carry_model_settings():
    row = SimpleNamespace(id=7, option_a='a', option_b='b', option_c=None, option_d=None,
                          question_text='Q?')
    p = build_requests('Biology', 'SYL', [row], 'claude-opus-5-5')[0]['params']
    assert p['max_tokens'] > 300 and p['output_config'] == {'effort': 'low'}
    p = build_requests('Biology', 'SYL', [row], 'claude-haiku-4-5')[0]['params']
    assert p['max_tokens'] == 300 and 'output_config' not in p
