from __future__ import annotations

import os
import subprocess
import unittest
from unittest.mock import patch

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from final_gate_runner import run_gate


class FinalGateRunnerTests(unittest.TestCase):
    def test_named_gate_passes(self):
        with patch.dict(os.environ, {"FINAL_GATE_RETRIES": "2"}, clear=False):
            self.assertEqual(run_gate("TEST_GATE", lambda: "ok"), "ok")

    def test_transient_failure_is_retried(self):
        calls = {"count": 0}

        def flaky():
            calls["count"] += 1
            if calls["count"] == 1:
                raise OSError("temporary ffprobe failure")
            return "ok"

        with patch.dict(os.environ, {"FINAL_GATE_RETRIES": "2"}, clear=False):
            self.assertEqual(run_gate("TEST_GATE", flaky), "ok")
        self.assertEqual(calls["count"], 2)

    def test_contract_failure_is_not_retried_or_hidden(self):
        calls = {"count": 0}

        def invalid_contract():
            calls["count"] += 1
            raise AssertionError("Short titles must be unique")

        with patch.dict(os.environ, {"FINAL_GATE_RETRIES": "3"}, clear=False), self.assertRaisesRegex(AssertionError, "Short titles must be unique"):
            run_gate("TEST_GATE", invalid_contract)
        self.assertEqual(calls["count"], 1)

    def test_subprocess_failure_is_retried(self):
        calls = {"count": 0}

        def flaky_subprocess():
            calls["count"] += 1
            if calls["count"] == 1:
                raise subprocess.CalledProcessError(1, ["ffprobe"])
            return True

        with patch.dict(os.environ, {"FINAL_GATE_RETRIES": "2"}, clear=False):
            self.assertTrue(run_gate("TEST_GATE", flaky_subprocess))
        self.assertEqual(calls["count"], 2)


if __name__ == "__main__":
    unittest.main()
