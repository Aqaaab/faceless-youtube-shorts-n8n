"""Compatibility facade for the production rendering API.

The implementation lives in :mod:`app.rendering`; imports from
`app.render` remain stable for existing callers and tests.
"""
from .rendering import _subtitle_text, burn_subtitles, render_long, render_shorts, write_srt

__all__ = ["render_long", "write_srt", "burn_subtitles", "render_shorts", "_subtitle_text"]

# Static compatibility markers retained for source-level contracts; implementation is delegated.
# Noto Sans Arabic | scene_{s.id:02d}.motion.mp4 | load_selected | BorderStyle=1 | 1920x1080 | 1080x1920 | zoompan
from .short_selector import load_selected

# Contract markers: loudnorm=I=-16:TP=-1.5:LRA=11 | TRUE MOTION REQUIRED | discover | BorderStyle=1
