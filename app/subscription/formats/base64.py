from __future__ import annotations

import base64 as _base64

from app.subscription.formats.text import render as render_text
from app.subscription.models import ProviderConfig


def render(configs: tuple[ProviderConfig, ...]) -> str:
    text = render_text(configs)
    return _base64.b64encode(text.encode("utf-8")).decode("ascii")
