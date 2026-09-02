"""Canonical portfolio value must sync from plan apply → sidebar → allocation dollars."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import streamlit as st

from components.investment_planning import _apply_plan_portfolio_value, holding_dollar_from_weight
from components.ui_helpers import (
    PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY,
    apply_pending_sidebar_portfolio_value,
)
from planning_portfolio_value import (
    APPLIED_PLAN_PORTFOLIO_VALUE_KEY,
    APPLIED_PLAN_SOURCE_KEY,
    get_applied_plan_portfolio_value,
    initialize_sidebar_portfolio_value_before_widget,
    mark_sidebar_portfolio_widget_instantiated,
    reset_sidebar_portfolio_widget_gate_for_run,
    sidebar_portfolio_widget_instantiated,
)


class _FakeSessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


def _simulate_script_run_sidebar_sync(ss: _FakeSessionState) -> int:
    """Mirror streamlit_app: reset gate → apply pending → init → (widget would bind)."""
    reset_sidebar_portfolio_widget_gate_for_run(ss)
    original = st.session_state
    st.session_state = ss
    try:
        apply_pending_sidebar_portfolio_value()
        initialize_sidebar_portfolio_value_before_widget(ss)
    finally:
        st.session_state = original
    mark_sidebar_portfolio_widget_instantiated(ss)
    return int(round(float(ss["sidebar_portfolio_value"])))


class TestPlanApplyPropagatesCanonicalPortfolioValue(unittest.TestCase):
    def setUp(self) -> None:
        self.ss = _FakeSessionState(
            {
                "sidebar_portfolio_value": 58_451,
                "_sidebar_portfolio_value_widget_instantiated": True,
                "_suite_inv_portfolio_value_user_set": True,
            }
        )

    def _apply_and_rerun(self, amount: float, *, source: str) -> int:
        original = st.session_state
        st.session_state = self.ss
        try:
            with patch(
                "components.investment_planning.maybe_autosave_investment_plan",
                return_value=None,
            ), patch(
                "investment_persistent_state.notify_global_settings_change",
                return_value=None,
            ):
                _apply_plan_portfolio_value(amount, source=source)
        finally:
            st.session_state = original

        # Same-run: widget already instantiated → sidebar must stay stale until next run.
        self.assertTrue(sidebar_portfolio_widget_instantiated(self.ss))
        self.assertEqual(self.ss["sidebar_portfolio_value"], 58_451)
        self.assertEqual(get_applied_plan_portfolio_value(self.ss), int(round(amount)))
        self.assertEqual(self.ss[PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY], int(round(amount)))

        # Next script run: gate clears and pending/applied become canonical sidebar value.
        return _simulate_script_run_sidebar_sync(self.ss)

    def test_recommended_long_term_4250_propagates_to_sidebar_and_dollars(self) -> None:
        canonical = self._apply_and_rerun(4_250, source="long_term")
        self.assertEqual(canonical, 4_250)
        self.assertEqual(self.ss["sidebar_portfolio_value"], 4_250)
        self.assertEqual(self.ss[APPLIED_PLAN_PORTFOLIO_VALUE_KEY], 4_250)
        self.assertEqual(self.ss[APPLIED_PLAN_SOURCE_KEY], "long_term")
        self.assertNotIn(PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY, self.ss)
        # 60% of $4,250 — not ~$35,070 from stale $58,451
        self.assertEqual(holding_dollar_from_weight(canonical, 60.0), 2_550.0)
        self.assertNotAlmostEqual(holding_dollar_from_weight(58_451, 60.0), 2_550.0)

    def test_max_investable_5000_propagates_to_sidebar_and_dollars(self) -> None:
        canonical = self._apply_and_rerun(5_000, source="max_investable")
        self.assertEqual(canonical, 5_000)
        self.assertEqual(self.ss["sidebar_portfolio_value"], 5_000)
        self.assertEqual(self.ss[APPLIED_PLAN_SOURCE_KEY], "max_investable")
        self.assertEqual(holding_dollar_from_weight(canonical, 60.0), 3_000.0)

    def test_subsequent_rerun_does_not_restore_stale_58451(self) -> None:
        self._apply_and_rerun(4_250, source="long_term")
        # Another full script run with no new pending — applied plan must keep sidebar at 4250.
        again = _simulate_script_run_sidebar_sync(self.ss)
        self.assertEqual(again, 4_250)
        self.assertEqual(self.ss["sidebar_portfolio_value"], 4_250)
        self.assertNotEqual(self.ss["sidebar_portfolio_value"], 58_451)

    def test_stale_gate_without_reset_would_block_pending(self) -> None:
        """Documents the bug: leftover instantiation gate blocks pending apply."""
        self.ss[PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY] = 4_250
        self.ss["_sidebar_portfolio_value_widget_instantiated"] = True
        original = st.session_state
        st.session_state = self.ss
        try:
            apply_pending_sidebar_portfolio_value()
        finally:
            st.session_state = original
        self.assertEqual(self.ss["sidebar_portfolio_value"], 58_451)
        self.assertIn(PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY, self.ss)


if __name__ == "__main__":
    unittest.main()
