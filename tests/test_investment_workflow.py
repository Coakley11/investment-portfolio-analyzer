"""Tests for workflow invalidation and developer diagnostics gate."""

from __future__ import annotations

import unittest

from investment_workflow import (
    developer_access_available,
    developer_diagnostics_enabled,
    invalidate_workflow_from,
    portfolio_analysis_fingerprint,
    reconcile_workflow_health,
    track_holdings_dataframe,
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
        self.query_params: dict[str, str] = {}


class TestInvalidateWorkflow(unittest.TestCase):
    def test_portfolio_change_clears_downstream_only(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        ss["guide_goal_choice"] = "Grow my money long term"
        ss["preset_applied"] = "Balanced"
        ss["portfolio_built"] = True
        ss["portfolio_analyzed"] = True
        ss["portfolio_health_reviewed"] = True
        ss["recommendations_displayed"] = True
        ss["health_result"] = {"score": 80}
        ss["health_result_fingerprint"] = "SPY:1.0000"

        invalidate_workflow_from("portfolio", st)

        self.assertEqual(ss["guide_goal_choice"], "Grow my money long term")
        self.assertEqual(ss["preset_applied"], "Balanced")
        self.assertTrue(ss["portfolio_built"])
        self.assertFalse(ss["portfolio_analyzed"])
        self.assertFalse(ss["portfolio_health_reviewed"])
        self.assertFalse(ss["recommendations_displayed"])
        self.assertNotIn("health_result", ss)

    def test_goal_change_clears_analysis_keeps_goal_portfolio(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        ss["health_objective"] = "balanced growth"
        ss["preset_applied"] = "Balanced"
        ss["portfolio_analyzed"] = True

        invalidate_workflow_from("goal", st)

        self.assertEqual(ss["health_objective"], "balanced growth")
        self.assertEqual(ss["preset_applied"], "Balanced")
        self.assertFalse(ss["portfolio_analyzed"])

    def test_reconcile_stale_fingerprint(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        ss["portfolio_analyzed"] = True
        ss["health_result"] = object()
        ss["health_result_fingerprint"] = "OLD:1.0000"
        reconcile_workflow_health(["SPY"], [1.0], st)
        self.assertFalse(ss["portfolio_analyzed"])
        self.assertNotIn("health_result", ss)

    def test_reconcile_fresh_fingerprint_keeps_analyzed(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        fp = portfolio_analysis_fingerprint(["SPY", "BND"], [0.6, 0.4])
        ss["health_result"] = object()
        ss["health_result_fingerprint"] = fp
        reconcile_workflow_health(["SPY", "BND"], [0.6, 0.4], st)
        self.assertTrue(ss["portfolio_analyzed"])
        self.assertEqual(ss.get("_workflow_health_status"), "fresh")

    def test_developer_diagnostics_default_off(self) -> None:
        st = _FakeSt()
        self.assertFalse(developer_diagnostics_enabled(st))

    def test_developer_access_default_off(self) -> None:
        st = _FakeSt()
        self.assertFalse(developer_access_available(st))

    def test_developer_access_query_param(self) -> None:
        st = _FakeSt()
        st.query_params = {"dev": "1"}
        self.assertTrue(developer_access_available(st))


if __name__ == "__main__":
    unittest.main()
