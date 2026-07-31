"""Navigation from Monthly Contribution Advisor to How Much plan inputs."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

from components.investment_planning import (
    BEGINNER_PLAN_INPUT_TABS,
    request_navigate_to_how_much_plan_inputs,
)
from components.ui_helpers import HOW_MUCH_PLAN_SCROLL_ANCHOR


class _FakeSessionState(dict):
    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


class _FakeSt:
    def __init__(self) -> None:
        self.session_state = _FakeSessionState()


class TestHowMuchPlanNavigation(unittest.TestCase):
    @patch("investment_persistent_state.current_experience_mode", return_value="beginner")
    @patch("investment_persistent_state.notify_investment_tab_change")
    def test_request_nav_beginner_sets_tab_scroll_and_subtab(
        self,
        notify: unittest.mock.MagicMock,
        _mode: unittest.mock.MagicMock,
    ) -> None:
        st = _FakeSt()
        tab = request_navigate_to_how_much_plan_inputs(st)
        ss = st.session_state
        self.assertIn("Build Portfolio", tab)
        self.assertEqual(ss["_pending_investment_tab"], tab)
        self.assertEqual(ss["investment_active_tab"], tab)
        self.assertEqual(ss["_pending_scroll_target"], HOW_MUCH_PLAN_SCROLL_ANCHOR)
        self.assertTrue(ss["_force_plan_inputs_expanded"])
        self.assertEqual(ss["beginner_plan_input_tab"], BEGINNER_PLAN_INPUT_TABS[0])
        notify.assert_called_once()

    @patch("investment_persistent_state.current_experience_mode", return_value="advanced")
    @patch("investment_persistent_state.notify_investment_tab_change")
    def test_request_nav_advanced_uses_portfolio_tab_label(
        self,
        notify: unittest.mock.MagicMock,
        _mode: unittest.mock.MagicMock,
    ) -> None:
        st = _FakeSt()
        tab = request_navigate_to_how_much_plan_inputs(st)
        ss = st.session_state
        self.assertIn("Portfolio", tab)
        self.assertNotIn("beginner_plan_input_tab", ss)
        self.assertEqual(ss["_pending_scroll_target"], HOW_MUCH_PLAN_SCROLL_ANCHOR)
        notify.assert_called_once()
