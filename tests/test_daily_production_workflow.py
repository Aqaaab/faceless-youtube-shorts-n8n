from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DailyProductionWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = (ROOT / ".github" / "workflows" / "daily-production.yml").read_text(encoding="utf-8")
        self.ci = (ROOT / ".github" / "workflows" / "car-encyclopedia-ci.yml").read_text(encoding="utf-8")

    def test_daily_production_is_workflow_run_gated(self):
        self.assertIn("workflow_run:", self.workflow)
        self.assertIn("workflows: [Car Encyclopedia CI]", self.workflow)
        self.assertIn("types: [completed]", self.workflow)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", self.workflow)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", self.workflow)
        self.assertIn("github.event.workflow_run.event == 'schedule'", self.workflow)
        self.assertNotIn("  schedule:", self.workflow)
        self.assertNotIn("  push:", self.workflow)

    def test_daily_ci_has_a_schedule_and_dispatch(self):
        self.assertIn("schedule:", self.ci)
        self.assertIn("workflow_dispatch:", self.ci)

    def test_production_has_no_push_or_manual_trigger(self):
        trigger = self.workflow.split("permissions:", 1)[0]
        self.assertNotIn("push:", trigger)
        self.assertNotIn("workflow_dispatch:", trigger)
        self.assertNotIn("workflows: [Daily Production]", trigger)


if __name__ == "__main__":
    unittest.main()
