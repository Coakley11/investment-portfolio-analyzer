"""Tests for workflow checklist freshness and completion fingerprints."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import investment_persistent_state as ips
from investment_workflow import (
    _health_is_fresh,
    apply_pending_investment_tab,
    invalidate_workflow_from,
    mark_health_reviewed_for_portfolio,
    portfolio_analysis_fingerprint,
    reconcile_workflow_health,
    record_workflow_health_status,
    request_core_step_navigation,
    request_workflow_tab_navigation,
    workflow_checklist,
)
from components.beginner_navigation import BEGINNER_TAB_LABELS


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

    def test_pending_tab_applied_before_radio(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        ss["investment_active_tab"] = BEGINNER_TAB_LABELS[3]
        request_workflow_tab_navigation("portfolio", beginner=True, st_obj=st)
        self.assertEqual(ss["_pending_investment_tab"], BEGINNER_TAB_LABELS[2])
        self.assertEqual(ss["investment_active_tab"], BEGINNER_TAB_LABELS[2])
        applied = apply_pending_investment_tab(st, BEGINNER_TAB_LABELS, beginner_mode=True)
        self.assertTrue(applied)
        self.assertEqual(ss["investment_active_tab"], BEGINNER_TAB_LABELS[2])
        self.assertNotIn("_pending_investment_tab", ss)

    def test_health_is_fresh_requires_cached_blob(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        record_workflow_health_status("fresh", st)
        self.assertFalse(_health_is_fresh(st))
        ss["health_result"] = object()
        ss["health_result_fingerprint"] = "SPY:1.0000"
        self.assertTrue(_health_is_fresh(st))

    def test_reconcile_matching_fp_sets_fresh_status(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        fp = portfolio_analysis_fingerprint(["SPY", "BND"], [0.6, 0.4])
        ss["health_result"] = object()
        ss["health_result_fingerprint"] = fp
        record_workflow_health_status("portfolio_stale", st)
        reconcile_workflow_health(["SPY", "BND"], [0.6, 0.4], st)
        self.assertEqual(ss["_workflow_health_status"], "fresh")
        self.assertTrue(_health_is_fresh(st))

    def test_core_step_navigation_without_st_obj(self) -> None:
        """Regression: CTA handlers that omit st_obj must not crash notify_investment_tab_change."""
        import streamlit as st

        fake_ss = _FakeSessionState()
        fake_ss["investment_active_tab"] = BEGINNER_TAB_LABELS[0]
        fake_ss[ips._LAST_PERSISTED_TAB_KEY] = BEGINNER_TAB_LABELS[0]
        with patch.object(st, "session_state", fake_ss), patch.object(
            ips, "autosave_investment_state", lambda *_a, **_k: None
        ):
            request_core_step_navigation("analyze", beginner=True)
        self.assertEqual(fake_ss["investment_active_tab"], BEGINNER_TAB_LABELS[3])

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
