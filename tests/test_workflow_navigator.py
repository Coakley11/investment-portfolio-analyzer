"""Tests for workflow intents, step visuals, and lazy analytics gate."""

from __future__ import annotations

import unittest

from components.beginner_navigation import BEGINNER_TAB_LABELS
from investment_workflow import (
    WORKFLOW_CORE_STEPS,
    begin_goal_change_workflow,
    begin_portfolio_rebuild_workflow,
    classify_goal_change_verdict,
    goal_display_label,
    invalidate_workflow_from,
    needs_analytics_load,
    record_workflow_health_status,
    snapshot_plan_labels,
    workflow_checklist,
    workflow_step_visual_states,
    workflow_tab_label_for_step,
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


class TestWorkflowTrust(unittest.TestCase):
    def test_begin_goal_change_sets_intent_and_stale(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        ss["guide_goal_choice"] = "Grow my money long term"
        ss["preset_applied"] = "Balanced"
        ss["portfolio_analyzed"] = True
        ss["health_result"] = object()
        record_workflow_health_status("fresh", st)
        begin_goal_change_workflow(st, beginner=True)
        self.assertEqual(ss["_workflow_intent"], "change_goal")
        self.assertIn("analyze", ss["_workflow_stale_steps"])
        self.assertFalse(ss.get("portfolio_analyzed"))
        self.assertNotIn("health_result", ss)
        self.assertEqual(ss["_workflow_health_status"], "missing")

    def test_begin_rebuild_invalidates_downstream(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        ss["portfolio_built"] = True
        ss["portfolio_analyzed"] = True
        ss["portfolio_health_reviewed"] = True
        record_workflow_health_status("fresh", st)
        begin_portfolio_rebuild_workflow(st, beginner=False)
        self.assertEqual(ss["_workflow_intent"], "rebuild_portfolio")
        state = workflow_checklist(st)
        self.assertFalse(state["analyze"])
        self.assertFalse(state["health"])

    def test_goal_invalidate_keeps_portfolio_checked(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        ss["guide_goal_choice"] = "Save for retirement"
        ss["preset_applied"] = "Retirement"
        ss["portfolio_built"] = True
        invalidate_workflow_from("goal", st)
        state = workflow_checklist(st)
        self.assertTrue(state["goal"])
        self.assertTrue(state["portfolio"])
        self.assertFalse(state["analyze"])

    def test_needs_analytics_false_on_goal_tab(self) -> None:
        st = _FakeSt()
        self.assertFalse(
            needs_analytics_load(BEGINNER_TAB_LABELS[0], BEGINNER_TAB_LABELS, st)
        )

    def test_needs_analytics_true_on_health_tab(self) -> None:
        st = _FakeSt()
        self.assertTrue(
            needs_analytics_load(BEGINNER_TAB_LABELS[4], BEGINNER_TAB_LABELS, st)
        )

    def test_needs_analytics_when_run_health(self) -> None:
        st = _FakeSt()
        st.session_state["run_health"] = True
        self.assertTrue(
            needs_analytics_load(BEGINNER_TAB_LABELS[0], BEGINNER_TAB_LABELS, st)
        )

    def test_stale_analysis_visual(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        ss["guide_goal_choice"] = "Grow my money long term"
        ss["preset_applied"] = "Balanced"
        ss["portfolio_built"] = True
        invalidate_workflow_from("goal", st)
        visuals = workflow_step_visual_states(
            st, beginner=True, active_tab=BEGINNER_TAB_LABELS[0]
        )
        self.assertEqual(visuals["goal"], "complete")
        self.assertEqual(visuals["portfolio"], "complete")
        self.assertEqual(visuals["analyze"], "stale")

    def test_change_goal_intent_shows_goal_current_on_goal_tab(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        ss["guide_goal_choice"] = "Grow my money long term"
        ss["preset_applied"] = "Balanced"
        ss["portfolio_built"] = True
        begin_goal_change_workflow(st, beginner=True)
        visuals = workflow_step_visual_states(
            st, beginner=True, active_tab=BEGINNER_TAB_LABELS[0]
        )
        self.assertEqual(visuals["goal"], "current")
        self.assertEqual(visuals["analyze"], "stale")

    def test_snapshot_plan_labels(self) -> None:
        st = _FakeSt()
        st.session_state["guide_goal_choice"] = "Generate income"
        st.session_state["preset_applied"] = "Dividend Income"
        snap = snapshot_plan_labels(st)
        self.assertEqual(snap["goal"], "Generate income")
        self.assertEqual(snap["portfolio"], "Dividend Income")

    def test_verdict_b_same_preset_different_card(self) -> None:
        before = {
            "guide_goal_choice": "Grow my money long term",
            "beginner_goal_card": "balanced",
            "preset_applied": "Balanced",
            "objective": "balanced growth",
            "holdings_fp": "SPY:60.0:Equity|BND:40.0:Bonds",
            "goal_banner": "Grow my money long term",
        }
        after = {
            "guide_goal_choice": "Grow my money long term",
            "beginner_goal_card": "growth",
            "preset_applied": "Balanced",
            "objective": "balanced growth",
            "holdings_fp": "SPY:60.0:Equity|BND:40.0:Bonds",
            "goal_banner": "Grow my money long term",
        }
        self.assertEqual(classify_goal_change_verdict(before, after), "B")

    def test_goal_display_uses_card_title(self) -> None:
        st = _FakeSt()
        st.session_state["beginner_goal_card"] = "growth"
        st.session_state["guide_goal_choice"] = "Grow my money long term"
        self.assertEqual(goal_display_label(st), "Long-Term Growth")

    def test_verdict_ok_retirement(self) -> None:
        before = {
            "guide_goal_choice": "Grow my money long term",
            "beginner_goal_card": "balanced",
            "preset_applied": "Balanced",
            "objective": "balanced growth",
            "holdings_fp": "fp-a",
            "goal_banner": "Grow my money long term",
        }
        after = {
            "guide_goal_choice": "Save for retirement",
            "beginner_goal_card": "retirement",
            "preset_applied": "Retirement",
            "objective": "retirement",
            "holdings_fp": "fp-b",
            "goal_banner": "Save for retirement",
        }
        self.assertEqual(classify_goal_change_verdict(before, after), "OK")


if __name__ == "__main__":
    unittest.main()
