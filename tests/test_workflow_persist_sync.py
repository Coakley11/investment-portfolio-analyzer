"""Cross-device workflow persistence in full_session."""

from __future__ import annotations

import unittest

import investment_persistent_state as ips
from investment_workflow import (
    WORKFLOW_STATE_BLOB_KEY,
    apply_workflow_persist_blob,
    build_workflow_persist_blob,
    reconcile_workflow_after_restore,
    workflow_checklist,
)


class _FakeSessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class _FakeSt:
    def __init__(self) -> None:
        self.session_state = _FakeSessionState()


class TestWorkflowPersistSync(unittest.TestCase):
    def test_build_includes_workflow_state_blob(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        ss["beginner_goal_card"] = "income"
        ss["guide_goal_choice"] = "Generate income"
        ss["health_objective"] = "income"
        ss["preset_applied"] = "Dividend Income"
        ss["portfolio_built"] = True
        ss["portfolio_analyzed"] = True
        ss["portfolio_health_reviewed"] = False
        ss["health_result_fingerprint"] = "SPY:0.6000|BND:0.4000"
        ss["_workflow_health_status"] = "fresh"
        ss["health_summary"] = {"score": 72.0, "score_label": "OK"}
        ss["_workflow_stale_steps"] = {"health", "recommendations"}

        blob = build_workflow_persist_blob(st)
        self.assertEqual(blob["workflow_stale_steps"], ["health", "recommendations"])
        self.assertEqual(blob["health_result_fingerprint"], "SPY:0.6000|BND:0.4000")
        self.assertTrue(blob["checklist"]["goal"])
        self.assertTrue(blob["checklist"]["analyze"])
        self.assertFalse(blob["checklist"]["health"])

        disk = ips.build_investment_disk_state(st)
        self.assertIn(WORKFLOW_STATE_BLOB_KEY, disk)
        self.assertEqual(disk["portfolio_analyzed"], True)

    def test_restore_without_health_object_keeps_analyze_checked(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        wf = {
            "workflow_stale_steps": ["health", "recommendations"],
            "workflow_health_status": "fresh",
            "health_result_fingerprint": "SPY:0.6000|BND:0.4000",
            "checklist": {
                "goal": True,
                "portfolio": True,
                "analyze": True,
                "health": False,
                "recommendations": False,
            },
        }
        ss["portfolio_analyzed"] = True
        ss["health_summary"] = {"score": 70.0}
        apply_workflow_persist_blob(st, wf)
        reconcile_workflow_after_restore(st)
        checklist = workflow_checklist(st)
        self.assertTrue(checklist["analyze"])
        self.assertFalse(checklist["health"])
        self.assertIn("health", ss["_workflow_stale_steps"])

    def test_restore_without_health_summary_keeps_analyze_when_fingerprint_present(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        ss["portfolio_analyzed"] = True
        ss["portfolio_built"] = True
        ss["guide_goal_choice"] = "Balanced growth"
        ss["health_result_fingerprint"] = "BND:50.0:Bonds|VYM:50.0:Dividend ETF"
        ss["_workflow_health_status"] = "fresh"
        reconcile_workflow_after_restore(st)
        checklist = workflow_checklist(st)
        self.assertTrue(checklist["goal"])
        self.assertTrue(checklist["portfolio"])
        self.assertTrue(checklist["analyze"])
        self.assertEqual(ss["_workflow_health_status"], "fresh")


if __name__ == "__main__":
    unittest.main()
