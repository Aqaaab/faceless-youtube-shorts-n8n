from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProductionRecoveryWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = (ROOT / ".github" / "workflows" / "production-recovery.yml").read_text(encoding="utf-8")

    def test_recovery_waits_for_successful_main_push_ci(self):
        self.assertIn("workflow_run:", self.workflow)
        self.assertIn("workflows: [Car Encyclopedia CI]", self.workflow)
        self.assertIn("types: [completed]", self.workflow)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", self.workflow)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", self.workflow)
        self.assertIn("github.event.workflow_run.event == 'push'", self.workflow)
        self.assertIn("startsWith(github.event.workflow_run.head_commit.message, '[run-production]')", self.workflow)

    def test_recovery_has_no_direct_push_or_manual_bypass(self):
        trigger = self.workflow.split("permissions:", 1)[0]
        self.assertNotIn("push:", trigger)
        self.assertNotIn("workflow_dispatch:", trigger)


if __name__ == "__main__":
    unittest.main()
