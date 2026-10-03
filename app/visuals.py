"""Canonical semantic visual helpers used by the WanGP pipeline."""
from .story_visuals import _kind

def _keywords(scene):
    return [_kind(scene)]
