"""Production rendering facade.

Implementations are split by responsibility:
- render_ffmpeg: media primitives
- render_video: long-form assembly
- render_subtitles: Arabic timing/burning
- render_shorts: candidate-driven vertical delivery

This module intentionally keeps the historical import surface stable.
"""
from .render_ffmpeg import render_segment as _render_segment, mux_motion as _mux_motion, concat as _concat, run as _run
from .render_subtitles import subtitle_text as _subtitle_text, write_srt, burn_subtitles, candidate_srt as _candidate_srt
from .render_video import render_long
from .render_shorts import render_shorts

__all__ = ["render_long", "write_srt", "burn_subtitles", "render_shorts", "_subtitle_text", "_render_segment", "_mux_motion", "_concat", "_run", "_candidate_srt"]
