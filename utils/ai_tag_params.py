"""Request settings for the AI question taggers that depend on the model.

The newer Claude models (the 5 family, Fable and Mythos) think before they
answer, and those thinking tokens count against ``max_tokens``. A limit that is
plenty for the JSON answer alone can be used up by the thinking, which cuts the
answer off and leaves the question untagged. For those models this adds room
for the thinking and sets the effort level, which controls how much thinking
the model does (and is billed as output). Older models (Haiku 4.5, Sonnet 4.6,
...) don't think unless asked, so their requests stay as they were.

The effort is ``AI_TAG_EFFORT`` from the environment / Config, default ``low``:
picking a syllabus code from a fixed list needs little reasoning. ``medium``
or ``high`` costs more output tokens per question.
"""
from __future__ import annotations

import os
import re

_THINKS = re.compile(r'^claude-(fable|mythos|opus-5|sonnet-5|haiku-5)', re.I)
_EFFORTS = ('low', 'medium', 'high', 'xhigh', 'max')
_THINK_ROOM = 6000           # extra max_tokens left for thinking


def thinks(model):
    """True for models that think by default (thinking uses max_tokens)."""
    return bool(_THINKS.match((model or '').strip()))


def effort():
    val = (os.environ.get('AI_TAG_EFFORT') or '').strip().lower()
    if not val:
        try:
            from config import Config
            val = (getattr(Config, 'AI_TAG_EFFORT', '') or '').strip().lower()
        except Exception:
            val = ''
    return val if val in _EFFORTS else 'low'


def tag_params(model, max_tokens):
    """``(max_tokens, extra)``: the limit to send, and any extra request fields
    (``output_config``) to add to the request body for this model."""
    if not thinks(model):
        return max_tokens, {}
    return max_tokens + _THINK_ROOM, {'output_config': {'effort': effort()}}


def create(client, model, max_tokens, **kwargs):
    """``client.messages.create`` with the right settings for ``model``. The
    extra fields go in ``extra_body`` so older SDK versions send them too."""
    mt, extra = tag_params(model, max_tokens)
    if extra:
        kwargs['extra_body'] = {**kwargs.get('extra_body', {}), **extra}
    return client.messages.create(model=model, max_tokens=mt, **kwargs)
