from __future__ import annotations

"""Compatibility guard.

The production workflow must never call individual model providers directly.
Odysseus is the sole AI gateway. Provider credentials stay behind Odysseus.
"""


def call_fallback(*args, **kwargs):
    raise RuntimeError(
        "Direct provider fallback is disabled: production AI traffic must go through Odysseus Gateway"
    )
