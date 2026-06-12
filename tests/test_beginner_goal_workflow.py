"""Tests for beginner goal checklist and tab normalization."""

from __future__ import annotations

import unittest

from components.beginner_coach import GOAL_CARDS, _resolved_goal_card, render_beginner_goal_tab
from components.beginner_navigation import (
    ADVANCED_TAB_LABELS,
    BEGINNER_TAB_LABELS,
    ETF_HOLDINGS_TAB_LABEL,
    RECOMMENDATIONS_HEALTH_SUBTAB,
    RECOMMENDATIONS_SCROLL_ANCHOR,
    _MAIN_TAB_STEP_ORDER,
    _checklist_state,
    _goal_step_complete,
    active_main_tab,
    is_etf_holdings_tab,
    main_tab_label,
    normalize_tab_label_for_mode,
    sync_beginner_goal_keys_from_portfolio,
)
from investment_workflow import apply_pending_investment_tab


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

    def test_etf_explorer_beginner_fallback_no_crash(self) -> None:
        result = normalize_tab_label_for_mode(ETF_HOLDINGS_TAB_LABEL, beginner=True)
        self.assertIn(result, BEGINNER_TAB_LABELS)

    def test_is_etf_holdings_tab_advanced_only(self) -> None:
        self.assertTrue(is_etf_holdings_tab(ETF_HOLDINGS_TAB_LABEL))
        self.assertFalse(is_etf_holdings_tab(main_tab_label("frontier", beginner=False)))
        self.assertIn(ETF_HOLDINGS_TAB_LABEL, ADVANCED_TAB_LABELS)
        self.assertNotIn(ETF_HOLDINGS_TAB_LABEL, BEGINNER_TAB_LABELS)

    def test_etf_explorer_advanced_mode(self) -> None:
        self.assertEqual(
            normalize_tab_label_for_mode(ETF_HOLDINGS_TAB_LABEL, beginner=False),
            ETF_HOLDINGS_TAB_LABEL,
        )

    def test_apply_pending_etf_tab_advanced(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        ss["_pending_investment_tab"] = ETF_HOLDINGS_TAB_LABEL
        applied = apply_pending_investment_tab(st, ADVANCED_TAB_LABELS, beginner_mode=False)
        self.assertTrue(applied)
        self.assertEqual(ss["investment_active_tab"], ETF_HOLDINGS_TAB_LABEL)

    def test_beginner_mode_ten_tabs_no_etf_label(self) -> None:
        self.assertEqual(len(BEGINNER_TAB_LABELS), 10)
        self.assertNotIn(ETF_HOLDINGS_TAB_LABEL, BEGINNER_TAB_LABELS)
        for step in _MAIN_TAB_STEP_ORDER:
            label = main_tab_label(step, beginner=True)
            self.assertIn(label, BEGINNER_TAB_LABELS)
            self.assertNotEqual(label, ETF_HOLDINGS_TAB_LABEL)

    def test_beginner_main_tab_routing_no_index_ten_crash(self) -> None:
        """Regression: beginner has 10 tabs — routing must not assume index 10."""
        labels = BEGINNER_TAB_LABELS
        self.assertEqual(len(labels), 10)
        for step in _MAIN_TAB_STEP_ORDER:
            self.assertTrue(active_main_tab(main_tab_label(step, beginner=True), step, beginner=True))
        normalized = normalize_tab_label_for_mode(ETF_HOLDINGS_TAB_LABEL, beginner=True)
        self.assertIn(normalized, BEGINNER_TAB_LABELS)
        self.assertFalse(is_etf_holdings_tab(normalized))

    def test_render_beginner_goal_tab_exists(self) -> None:
        self.assertTrue(callable(render_beginner_goal_tab))

    def test_goal_cards_always_defined(self) -> None:
        self.assertGreaterEqual(len(GOAL_CARDS), 4)

    def test_resolved_goal_card_from_session(self) -> None:
        st = _FakeSt()
        st.session_state.beginner_goal_card = "income"
        card = _resolved_goal_card(st)
        self.assertIsNotNone(card)
        self.assertEqual(card["id"], "income")
        self.assertEqual(card["title"], "Income")


if __name__ == "__main__":
    unittest.main()
