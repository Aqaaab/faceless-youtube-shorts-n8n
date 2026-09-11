"""Compatibility surface for legacy imports.

The production visual engine lives in story_visuals.py.  Keep this tiny module
only so older callers of _keywords continue to work without maintaining a
second visual implementation.
"""
from __future__ import annotations

from .story_visuals import _kind


def _keywords(scene):
    """Return the canonical semantic visual mode as a one-item list."""
    return [_kind(scene)]
