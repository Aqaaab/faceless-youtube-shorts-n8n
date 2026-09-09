from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SystemGateTests(unittest.TestCase):
    def test_daily_production_is_workflow_run_gated(self):
        daily = (ROOT / ".github/workflows/daily-production.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_run:", daily)
        self.assertIn("workflows: [Car Encyclopedia CI]", daily)
        self.assertIn("types: [completed]", daily)
        self.assertIn("workflow_dispatch:", daily)
        self.assertIn("github.event_name == 'workflow_dispatch'", daily)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", daily)
        self.assertIn("github.event.workflow_run.event == 'push'", daily)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", daily)
        self.assertNotIn("startsWith(github.event.workflow_run.head_commit.message, '[run-production]')", daily)
        self.assertNotIn("schedule:", daily)
        self.assertNotIn("cron:", daily)
        self.assertNotIn("push:", daily)

    def test_system_gate_requires_production_quality_stages(self):
        gate = (ROOT / "scripts/system_gate.py").read_text(encoding="utf-8")
        self.assertIn('assert "workflow_dispatch:" in daily', gate)
        self.assertIn('assert "github.event_name == \'workflow_dispatch\'" in daily', gate)
        self.assertIn('assert "github.event.workflow_run.conclusion == \'success\'" in daily', gate)
        self.assertIn('assert "github.event.workflow_run.head_branch == \'main\'" in daily', gate)
        self.assertIn('assert "github.event.workflow_run.event == \'push\'" in daily', gate)
        self.assertNotIn('assert "startsWith(github.event.workflow_run.head_commit.message, \'[run-production]\')" in daily', gate)
        self.assertIn('run_gate("MANIFEST_HARDENING", harden_manifest, run)', gate)
        self.assertIn('run_gate("PRODUCTION_QA", qa, run)', gate)
        self.assertIn('run_gate("EPISODE_QUALITY_GATE", quality_gate)', gate)


if __name__ == "__main__":
    unittest.main()
