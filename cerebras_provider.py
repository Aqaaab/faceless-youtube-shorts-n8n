"""Compatibility shim for GitHub Actions inline imports.

The implementation lives in scripts/cerebras_provider.py. This root-level
module keeps `from cerebras_provider import ...` working when a workflow runs
an inline Python process from the repository root without PYTHONPATH=scripts.
"""
from scripts.cerebras_provider import *  # noqa: F401,F403
