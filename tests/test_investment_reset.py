"""Tests for Investment Reset to Default."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import investment_persistent_state as ips
from components.beginner_navigation import BEGINNER_TAB_LABELS
from investment_workflow import workflow_checklist


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


class TestInvestmentReset(unittest.TestCase):
    def test_apply_defaults_clears_workflow_and_goal(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        ss["beginner_goal_card"] = "income"
        ss["guide_goal_choice"] = "Generate income"
        ss["health_objective"] = "income"
        ss["preset_applied"] = "Dividend Income"
        ss["portfolio_built"] = True
        ss["portfolio_analyzed"] = True
        ss["portfolio_health_reviewed"] = True
        ss["recommendations_displayed"] = True
        ss["health_result"] = {"score": 70}
        ss["_workflow_intent"] = "change_goal"
        ss["_workflow_stale_steps"] = {"analyze"}
        ss[ips.INVESTMENT_ACTIVE_TAB_KEY] = BEGINNER_TAB_LABELS[4]

        ips.apply_investment_session_defaults(st)

        self.assertIsNone(ss.get("beginner_goal_card"))
        self.assertIsNone(ss.get("guide_goal_choice"))
        self.assertEqual(ss.get("health_objective"), "balanced growth")
        self.assertIsNone(ss.get("preset_applied"))
        self.assertFalse(ss.get("portfolio_built"))
        self.assertNotIn("health_result", ss)
        self.assertNotIn("_workflow_intent", ss)
        self.assertEqual(ss[ips.INVESTMENT_ACTIVE_TAB_KEY], BEGINNER_TAB_LABELS[0])
        state = workflow_checklist(st)
        self.assertFalse(state["goal"])
        self.assertFalse(state["portfolio"])
        self.assertFalse(state["analyze"])
        self.assertFalse(state["health"])
        self.assertFalse(state["recommendations"])

    def test_default_reset_persists_fresh_disk_and_cloud(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        ss["beginner_goal_card"] = "balanced"
        ss["preset_applied"] = "Balanced"
        saved_disk: list[dict] = []
        cleared_cloud: list[str] = []
        saved_cloud: list[dict] = []

        with patch("suite_user_persistence.save_user_state") as mock_disk:
            mock_disk.side_effect = lambda _app, state: saved_disk.append(state) or True
            with patch("suite_cloud_state.clear_cloud_full_session") as mock_clear:
                mock_clear.side_effect = lambda app: cleared_cloud.append(app) or True
                with patch("suite_cloud_state.save_cloud_full_session") as mock_cloud:
                    mock_cloud.side_effect = (
                        lambda app, state, **kw: saved_cloud.append({"app": app, "state": state}) or None
                    )
                    ips.default_reset_investment_session(st)

        self.assertTrue(saved_disk)
        self.assertEqual(cleared_cloud, [ips.APP_ID])
        self.assertTrue(saved_cloud)
        self.assertIsNone(saved_disk[0].get("beginner_goal_card"))
        self.assertIsNone(saved_disk[0].get("preset_applied"))
        self.assertFalse(saved_disk[0].get("portfolio_built"))
        self.assertTrue(ss.get(f"_suite_disk_state_restored::{ips.APP_ID}"))


if __name__ == "__main__":
    unittest.main()
