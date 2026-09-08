from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SystemGateTests(unittest.TestCase):
    def test_daily_production_uses_successful_scheduled_ci(self):
        gate = (ROOT / "scripts/system_gate.py").read_text(encoding="utf-8")
        self.assertIn('assert "workflow_run:" in daily', gate)
        self.assertIn('assert "workflows: [Car Encyclopedia CI]" in daily', gate)
        self.assertIn('assert "github.event.workflow_run.conclusion == \'success\'" in daily', gate)
        self.assertIn('assert "github.event.workflow_run.event == \'schedule\'" in daily', gate)
        self.assertNotIn('assert "workflow_dispatch:" in daily', gate)

    def test_system_gate_requires_production_quality_stages(self):
        gate = (ROOT / "scripts/system_gate.py").read_text(encoding="utf-8")
        self.assertIn('run_gate("MANIFEST_HARDENING", harden_manifest, run)', gate)
        self.assertIn('run_gate("PRODUCTION_QA", qa, run)', gate)
        self.assertIn('run_gate("EPISODE_QUALITY_GATE", quality_gate)', gate)


if __name__ == "__main__":
    unittest.main()
