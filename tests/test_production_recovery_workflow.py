from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProductionRecoveryWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = (ROOT / ".github" / "workflows" / "production-recovery.yml").read_text(encoding="utf-8")

    def test_recovery_waits_for_failed_daily_production(self):
        self.assertIn("workflow_run:", self.workflow)
        self.assertIn("workflows: [Daily Production]", self.workflow)
        self.assertIn("types: [completed]", self.workflow)
        self.assertIn("github.event.workflow_run.conclusion == 'failure'", self.workflow)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", self.workflow)

    def test_recovery_has_no_direct_push_or_manual_bypass(self):
        trigger = self.workflow.split("permissions:", 1)[0]
        self.assertNotIn("push:", trigger)
        self.assertNotIn("workflow_dispatch:", trigger)
        self.assertNotIn("workflows: [Car Encyclopedia CI]", trigger)

    def test_recovery_keeps_canonical_production_command(self):
        self.assertIn("python scripts/production.py", self.workflow)


if __name__ == "__main__":
    unittest.main()
