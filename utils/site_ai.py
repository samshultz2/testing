"""AI copywriting assistant for the Website Builder.

Generates draft copy for a page section from the school's own public branding
(name, motto/description) plus an optional tone and keywords the admin supplies.
It is strictly opt-in and degrades gracefully: with no API key (or without the
``anthropic`` package) it simply reports itself unavailable and the editor hides
the feature. Only non-personal branding is ever sent — never student, parent or
staff data — and the model returns suggestions the admin reviews before saving.
"""
import json
import os

from config import Config

# Props we never ask the model to write: links and images aren't copy.
_SKIP_SUFFIX = ('_href', '_url')
_SKIP_KEYS = {'image', 'bg_image', 'images'}


def _model():
    return os.environ.get('WEBSITE_AI_MODEL', '') or getattr(Config, 'WEBSITE_AI_MODEL', 'claude-haiku-4-5')


def is_available():
    """True only when the feature is enabled, a key is set, and the SDK is here."""
    if not getattr(Config, 'WEBSITE_AI_ENABLED', True):
        return False
    if not (os.environ.get('ANTHROPIC_API_KEY', '') or ''):
        return False
    try:
        import anthropic  # noqa: F401
    except Exception:
        return False
    return True


def copy_fields(props):
    """The subset of a block's props that are editable text (not links/images)."""
    out = []
    for key, val in (props or {}).items():
        if key in _SKIP_KEYS or key.endswith(_SKIP_SUFFIX):
            continue
        if isinstance(val, str):
            out.append(key)
    return out


def _prompt(section_label, fields, current, branding, tone, keywords):
    school = branding.get('name') or 'the school'
    lines = [
        f'You are writing website copy for "{school}", a school.',
        f'Motto/description: {branding.get("motto") or "(none provided)"}.',
        f'Write copy for the "{section_label}" section of its public website.',
    ]
    if tone:
        lines.append(f'Tone: {tone}.')
    if keywords:
        lines.append(f'Naturally work in these themes/keywords where they fit: {keywords}.')
    lines.append('Keep it concise, warm, credible and free of clichés and hype. '
                 'Do not invent facts, statistics, names or awards.')
    fld = ', '.join(fields)
    lines.append(
        'Return ONLY a JSON object (no markdown, no commentary) whose keys are '
        f'exactly these fields: {fld}. Match each field to its role — a field '
        'named "heading" is a short headline, "subheading" or "body" or "intro" '
        'is a sentence or two, "eyebrow" is 1-3 words, a "*_label" is a short '
        'button label. Here are the current values for reference:'
    )
    lines.append(json.dumps({k: current.get(k, '') for k in fields}))
    return '\n'.join(lines)


def suggest_block_copy(section_label, fields, current, *, branding, tone='', keywords=''):
    """Return {field: suggested_text} for the given fields, or {} on any failure.

    Never raises — the editor treats an empty result as "AI couldn't help right
    now" and leaves the existing content untouched."""
    if not fields or not is_available():
        return {}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
        msg = client.messages.create(
            model=_model(), max_tokens=1000,
            messages=[{'role': 'user',
                       'content': _prompt(section_label, fields, current, branding, tone, keywords)}],
        )
        text = next((b.text for b in msg.content if getattr(b, 'type', '') == 'text'), '').strip()
        return _parse(text, fields)
    except Exception:
        return {}


def _parse(text, fields):
    """Pull the JSON object out of the model's reply and keep only wanted, string fields."""
    if text.startswith('```'):
        text = text.strip('`')
        if text.lower().startswith('json'):
            text = text[4:]
    start, end = text.find('{'), text.rfind('}')
    if start == -1 or end == -1:
        return {}
    try:
        data = json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return {}
    allowed = set(fields)
    out = {}
    for k, v in (data.items() if isinstance(data, dict) else []):
        if k in allowed and isinstance(v, str) and v.strip():
            out[k] = v.strip()[:2000]
    return out
