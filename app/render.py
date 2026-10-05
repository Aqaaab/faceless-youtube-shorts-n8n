"""Compatibility facade for the production rendering API.

The implementation lives in :mod:`app.rendering`; imports from
`app.render` remain stable for existing callers and tests.
"""
from .rendering import burn_subtitles, render_long, render_shorts, write_srt

__all__ = ["render_long", "write_srt", "burn_subtitles", "render_shorts"]
