"""Tests for beginner goal checklist and tab normalization."""

from __future__ import annotations

import unittest

from components.beginner_navigation import (
    ADVANCED_TAB_LABELS,
    BEGINNER_TAB_LABELS,
    _checklist_state,
    _goal_step_complete,
    normalize_tab_label_for_mode,
    sync_beginner_goal_keys_from_portfolio,
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


class TestGoalWorkflow(unittest.TestCase):
    def test_preset_and_objective_count_as_goal_complete(self) -> None:
        st = _FakeSt()
        st.session_state.preset_applied = "Balanced"
        st.session_state.health_objective = "balanced growth"
        self.assertTrue(_goal_step_complete(st))

    def test_guide_goal_choice_counts_as_complete(self) -> None:
        st = _FakeSt()
        st.session_state.guide_goal_choice = "Grow my money long term"
        self.assertTrue(_goal_step_complete(st))

    def test_sync_goal_keys_from_preset(self) -> None:
        st = _FakeSt()
        st.session_state.preset_applied = "Balanced"
        st.session_state.health_objective = "balanced growth"
        self.assertTrue(sync_beginner_goal_keys_from_portfolio(st))
        self.assertEqual(st.session_state.beginner_goal_card, "balanced")
        self.assertEqual(st.session_state.guide_goal_choice, "Grow my money long term")

    def test_checklist_goal_done_after_sync(self) -> None:
        st = _FakeSt()
        st.session_state.preset_applied = "Balanced"
        st.session_state.health_objective = "balanced growth"
        sync_beginner_goal_keys_from_portfolio(st)
        state = _checklist_state(st)
        self.assertTrue(state["goal"])

    def test_normalize_advanced_tab_to_beginner(self) -> None:
        advanced = ADVANCED_TAB_LABELS[3]
        beginner = normalize_tab_label_for_mode(advanced, beginner=True)
        self.assertEqual(beginner, BEGINNER_TAB_LABELS[3])

    def test_normalize_beginner_tab_to_advanced(self) -> None:
        beginner = BEGINNER_TAB_LABELS[3]
        advanced = normalize_tab_label_for_mode(beginner, beginner=False)
        self.assertEqual(advanced, ADVANCED_TAB_LABELS[3])


if __name__ == "__main__":
    unittest.main()
