"""Real Portfolio Advisor insight panel navigation."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

from components.beginner_navigation import BEGINNER_REAL_PORTFOLIO_TAB_LABEL, REAL_PORTFOLIO_TAB_LABEL
from components.investment_planning import request_navigate_to_my_portfolio


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


class TestRealPortfolioInsightNavigation(unittest.TestCase):
    @patch("investment_persistent_state.current_experience_mode", return_value="advanced")
    @patch("investment_persistent_state.notify_investment_tab_change")
    def test_navigate_to_my_portfolio_advanced(
        self,
        notify: unittest.mock.MagicMock,
        _mode: unittest.mock.MagicMock,
    ) -> None:
        st = _FakeSt()
        tab = request_navigate_to_my_portfolio(st)
        ss = st.session_state
        self.assertEqual(tab, REAL_PORTFOLIO_TAB_LABEL)
        self.assertEqual(ss["_pending_investment_tab"], REAL_PORTFOLIO_TAB_LABEL)
        self.assertEqual(ss["investment_active_tab"], REAL_PORTFOLIO_TAB_LABEL)
        self.assertNotIn("_pending_scroll_target", ss)
        self.assertNotIn("_force_plan_inputs_expanded", ss)
        notify.assert_called_once()

    @patch("investment_persistent_state.current_experience_mode", return_value="beginner")
    @patch("investment_persistent_state.notify_investment_tab_change")
    def test_navigate_to_my_portfolio_beginner(
        self,
        notify: unittest.mock.MagicMock,
        _mode: unittest.mock.MagicMock,
    ) -> None:
        st = _FakeSt()
        tab = request_navigate_to_my_portfolio(st)
        self.assertEqual(tab, BEGINNER_REAL_PORTFOLIO_TAB_LABEL)
        notify.assert_called_once()

    def test_insight_button_label_in_source(self) -> None:
        text = open("applied_math_return_insight.py", encoding="utf-8").read()
        self.assertIn("Go to My Portfolio", text)
        self.assertIn("request_navigate_to_my_portfolio", text)


if __name__ == "__main__":
    unittest.main()
