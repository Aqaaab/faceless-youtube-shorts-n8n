#!/usr/bin/env python3
"""Deprecated compatibility entrypoint; use patent_story_engine.py."""
from patent_story_engine import generate

if __name__ == "__main__":
    raise SystemExit(generate())
