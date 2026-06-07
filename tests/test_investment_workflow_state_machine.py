"""End-to-end workflow state machine sequence tests."""

from __future__ import annotations

import unittest

import pandas as pd

from components.beginner_navigation import BEGINNER_TAB_LABELS, STEP_TAB_LABEL
from investment_workflow import (
    begin_goal_change_workflow,
    confirm_portfolio_step,
    invalidate_workflow_from,
    mark_analysis_complete,
    mark_health_reviewed_for_portfolio,
    mark_recommendations_if_current,
    record_goal_selection,
    workflow_checklist,
    workflow_step_visual_states,
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


def _sample_holdings() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Ticker": "SPY", "Weight (%)": 60.0, "Asset Type": "Equity"},
            {"Ticker": "BND", "Weight (%)": 40.0, "Asset Type": "Bonds"},
        ]
    )


class TestWorkflowStateMachine(unittest.TestCase):
    def test_full_sequence_goal_change_through_analyze(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        holdings = _sample_holdings()
        ss["holdings_df"] = holdings

        # 2. Select Goal A
        ss["guide_goal_choice"] = "Grow my money long term"
        ss["beginner_goal_card"] = "long_term"
        ss["health_objective"] = "balanced growth"
        ss["preset_applied"] = "Balanced"

        # 3. Confirm Portfolio
        confirm_portfolio_step(st, holdings_df=holdings)
        self.assertTrue(ss["portfolio_built"])

        # 4. Analyze Portfolio
        ss["health_result_fingerprint"] = "SPY:0.6000|BND:0.4000"
        ss["_workflow_health_status"] = "fresh"
        mark_analysis_complete(st)

        # 5. Health reviewed
        ss["health_result"] = object()
        mark_health_reviewed_for_portfolio(["SPY", "BND"], [0.6, 0.4], st)

        # 6. Recommendations viewed
        mark_recommendations_if_current(st)

        checklist = workflow_checklist(st)
        self.assertTrue(all(checklist.values()))

        # 7. Change to Goal B
        begin_goal_change_workflow(st, beginner=True)
        record_goal_selection(
            st,
            goal_title="Save for retirement",
            preset="Retirement",
            objective="retirement",
            beginner=True,
        )
        ss["guide_goal_choice"] = "Save for retirement"
        ss["preset_applied"] = "Retirement"

        checklist = workflow_checklist(st)
        self.assertTrue(checklist["goal"])
        self.assertFalse(checklist["portfolio"])
        self.assertFalse(checklist["analyze"])
        self.assertFalse(checklist["health"])
        self.assertFalse(checklist["recommendations"])

        stale = ss.get("_workflow_stale_steps", set())
        self.assertIn("portfolio", stale)
        self.assertIn("analyze", stale)

        # 8. Open Portfolio — blue/current, not green
        visuals = workflow_step_visual_states(
            st,
            beginner=True,
            active_tab=STEP_TAB_LABEL["portfolio"],
        )
        self.assertEqual(visuals["portfolio"], "current")
        self.assertNotEqual(visuals["portfolio"], "complete")

        # 9. Use this portfolio — portfolio green, analyze not green
        confirm_portfolio_step(st, holdings_df=holdings)
        checklist = workflow_checklist(st)
        self.assertTrue(checklist["portfolio"])
        self.assertFalse(checklist["analyze"])
        visuals = workflow_step_visual_states(
            st,
            beginner=True,
            active_tab=STEP_TAB_LABEL["portfolio"],
        )
        self.assertEqual(visuals["portfolio"], "complete")

        # 10. Analyze once — analyze green
        ss["health_result_fingerprint"] = "SPY:0.6000|BND:0.4000"
        ss["health_result"] = object()
        ss["health_summary"] = {"score": 75.0, "fingerprint": ss["health_result_fingerprint"]}
        mark_analysis_complete(st)
        checklist = workflow_checklist(st)
        self.assertTrue(checklist["analyze"])
        visuals = workflow_step_visual_states(
            st,
            beginner=True,
            active_tab=BEGINNER_TAB_LABELS[3],
        )
        self.assertEqual(visuals["analyze"], "complete")

    def test_open_goal_marks_downstream_stale(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        ss["guide_goal_choice"] = "Grow my money long term"
        ss["portfolio_built"] = True
        ss["portfolio_analyzed"] = True
        ss["health_result_fingerprint"] = "x"
        ss["_workflow_health_status"] = "fresh"

        begin_goal_change_workflow(st, beginner=True)
        visuals = workflow_step_visual_states(
            st,
            beginner=True,
            active_tab=STEP_TAB_LABEL["goal"],
        )
        self.assertEqual(visuals["goal"], "current")
        self.assertFalse(workflow_checklist(st)["portfolio"])
        self.assertIn("portfolio", ss.get("_workflow_stale_steps", set()))

    def test_invalidate_goal_clears_portfolio_built_even_with_preset(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        ss["preset_applied"] = "Balanced"
        ss["guide_portfolio_loaded"] = True
        ss["portfolio_built"] = True
        invalidate_workflow_from("goal", st)
        self.assertFalse(ss["portfolio_built"])
        self.assertFalse(workflow_checklist(st)["portfolio"])


if __name__ == "__main__":
    unittest.main()
