"""Tests for workflow checklist freshness and completion fingerprints."""

from __future__ import annotations

import unittest

from investment_workflow import (
    invalidate_workflow_from,
    mark_health_reviewed_for_portfolio,
    portfolio_analysis_fingerprint,
    record_workflow_health_status,
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


class TestWorkflowChecklistUI(unittest.TestCase):
    def test_stale_analysis_not_checked(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        ss["guide_goal_choice"] = "Grow my money long term"
        ss["preset_applied"] = "Balanced"
        ss["health_objective"] = "balanced growth"
        ss["portfolio_built"] = True
        ss["portfolio_analyzed"] = True
        ss["health_result"] = object()
        ss["health_result_fingerprint"] = "OLD:1.0000"
        record_workflow_health_status("portfolio_stale", st)
        state = workflow_checklist(st)
        self.assertTrue(state["goal"])
        self.assertTrue(state["portfolio"])
        self.assertFalse(state["analyze"])
        self.assertFalse(state["health"])
        self.assertFalse(state["recommendations"])

    def test_fresh_analysis_checked_after_review(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        ss["guide_goal_choice"] = "Grow my money long term"
        ss["preset_applied"] = "Balanced"
        ss["health_objective"] = "balanced growth"
        ss["portfolio_built"] = True
        fp = portfolio_analysis_fingerprint(["SPY", "BND"], [0.6, 0.4])
        ss["health_result"] = object()
        ss["health_result_fingerprint"] = fp
        ss["portfolio_analyzed"] = True
        record_workflow_health_status("fresh", st)
        mark_health_reviewed_for_portfolio(["SPY", "BND"], [0.6, 0.4], st)
        state = workflow_checklist(st)
        self.assertTrue(state["analyze"])
        self.assertTrue(state["health"])

    def test_portfolio_invalidate_keeps_goal(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        ss["guide_goal_choice"] = "Grow my money long term"
        ss["preset_applied"] = "Balanced"
        ss["health_objective"] = "balanced growth"
        ss["portfolio_analyzed"] = True
        ss["portfolio_health_reviewed"] = True
        record_workflow_health_status("fresh", st)
        invalidate_workflow_from("portfolio", st)
        record_workflow_health_status("missing", st)
        state = workflow_checklist(st)
        self.assertTrue(state["goal"])
        self.assertFalse(state["analyze"])


if __name__ == "__main__":
    unittest.main()
