"""Durable persistence for How Much Should I Invest (workspace blob + scalars)."""

from __future__ import annotations

import copy
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

import portfolio_core as core

from components.investment_planning import (
    INVESTMENT_PLAN_PERSIST_SCHEMA,
    PLAN_COMPARE_AMOUNTS_KEY,
    PLAN_MONTHLY_PROVIDED_KEY,
    apply_investment_plan_persist_blob,
    capture_investment_plan_persist_blob,
    investment_plan_persist_fingerprint,
    parse_current_monthly_investment_input,
    sanitize_plan_session_integers,
)
from investment_persistent_state import (
    INVESTMENT_PLAN_PERSIST_KEY,
    apply_investment_disk_state,
    build_investment_disk_state,
    notify_investment_plan_change,
    PERSIST_FIELD_DEFAULTS,
)


class _FakeSessionState(dict):
    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


class _FakeSt:
    def __init__(self, ss: _FakeSessionState | None = None) -> None:
        self.session_state = ss if ss is not None else _FakeSessionState()


class TestInvestmentPlanPersistence(unittest.TestCase):
    def test_blank_vs_zero_monthly_semantics(self) -> None:
        blank_amt, blank_provided, blank_err = parse_current_monthly_investment_input("")
        zero_amt, zero_provided, zero_err = parse_current_monthly_investment_input("0")
        self.assertIsNone(blank_amt)
        self.assertFalse(blank_provided)
        self.assertIsNone(blank_err)
        self.assertEqual(zero_amt, 0.0)
        self.assertTrue(zero_provided)
        self.assertIsNone(zero_err)

    def test_plan_blob_round_trip(self) -> None:
        plan = core.compute_investment_plan(
            total_available=100_000,
            emergency_fund_needed=20_000,
            money_needed_1_2_years=0,
            existing_debt_obligations=0,
            planned_large_expenses=0,
            horizon_years=20,
            risk_tolerance="High",
            current_monthly_investment=None,
        )
        ss = _FakeSessionState(
            plan_total_cash=100_000,
            plan_emergency=20_000,
            plan_horizon=20,
            plan_risk="High",
            investment_plan_generated=True,
            investment_plan=plan,
        )
        ss[PLAN_COMPARE_AMOUNTS_KEY] = [10_000, 25_000]
        ss[PLAN_MONTHLY_PROVIDED_KEY] = False
        blob = capture_investment_plan_persist_blob(ss)
        self.assertEqual(blob.get("schema"), INVESTMENT_PLAN_PERSIST_SCHEMA)
        self.assertEqual(blob.get("plan_compare_amounts_list"), [10_000, 25_000])

        st = _FakeSt(_FakeSessionState())
        apply_investment_plan_persist_blob(st, blob)
        self.assertTrue(st.session_state.get("investment_plan_generated"))
        self.assertEqual(st.session_state.get(PLAN_COMPARE_AMOUNTS_KEY), [10_000, 25_000])
        restored = st.session_state.get("investment_plan")
        self.assertIsNotNone(restored)
        self.assertAlmostEqual(float(getattr(restored, "long_term_suggested", 0)), float(plan.long_term_suggested))

    def test_disk_state_includes_plan_blob(self) -> None:
        ss = _FakeSessionState(plan_total_cash=50_000, plan_horizon=10, plan_risk="Low")
        ss[PLAN_MONTHLY_PROVIDED_KEY] = True
        ss["plan_monthly"] = 0
        st = _FakeSt(ss)
        state = build_investment_disk_state(st)
        self.assertEqual(state.get("plan_horizon"), 10)
        self.assertEqual(state.get("plan_risk"), "Low")
        self.assertTrue(state.get("plan_monthly_provided"))
        self.assertIn(INVESTMENT_PLAN_PERSIST_KEY, state)

    def test_hydrate_does_not_clobber_with_defaults_when_blob_present(self) -> None:
        saved = {
            "plan_total_cash": 88_000,
            "plan_emergency": 12_000,
            "plan_horizon": 25,
            "plan_risk": "Low",
            "plan_monthly_provided": False,
            INVESTMENT_PLAN_PERSIST_KEY: {
                "schema": INVESTMENT_PLAN_PERSIST_SCHEMA,
                "plan_compare_amounts_list": [15_000],
                "investment_plan": core.compute_investment_plan(
                    total_available=88_000,
                    emergency_fund_needed=12_000,
                    money_needed_1_2_years=0,
                    existing_debt_obligations=0,
                    planned_large_expenses=0,
                    horizon_years=25,
                    risk_tolerance="Low",
                    current_monthly_investment=None,
                ).to_dict(),
            },
        }
        st = _FakeSt(_FakeSessionState(plan_total_cash=999_999))
        apply_investment_disk_state(st, copy.deepcopy(saved))
        sanitize_plan_session_integers(st.session_state, PERSIST_FIELD_DEFAULTS)
        self.assertEqual(st.session_state.get("plan_total_cash"), 88_000)
        self.assertEqual(st.session_state.get("plan_horizon"), 25)
        self.assertEqual(st.session_state.get("plan_risk"), "Low")
        self.assertEqual(st.session_state.get(PLAN_COMPARE_AMOUNTS_KEY), [15_000])

    def test_account_isolation_via_workspace_state(self) -> None:
        a = _FakeSessionState(plan_total_cash=10_000, plan_risk="Low")
        b = _FakeSessionState(plan_total_cash=20_000, plan_risk="High")
        self.assertNotEqual(investment_plan_persist_fingerprint(a), investment_plan_persist_fingerprint(b))

    def test_notify_plan_change_sets_saved_status_on_write(self) -> None:
        ss = _FakeSessionState(
            plan_total_cash=40_000,
            _suite_inv_persistence_bootstrapped=True,
        )
        ss[PLAN_MONTHLY_PROVIDED_KEY] = False
        st = _FakeSt(ss)

        def _fake_autosave(_st: Any, *, end_of_run: bool = False, trigger: str = "unknown") -> None:
            ss["_suite_inv_debug_last_autosave_event"] = {"outcome": "written", "trigger": trigger}

        with patch("investment_persistent_state.autosave_investment_state", side_effect=_fake_autosave), patch(
            "investment_persistent_state._autosave_would_clobber_saved_portfolio",
            return_value=(False, ""),
        ):
            notify_investment_plan_change(st, source="test_plan", fingerprint="abc123")
        self.assertEqual(ss.get("_investment_plan_save_status"), "saved")

    def test_failed_write_keeps_prior_fingerprint_and_shows_error(self) -> None:
        ss = _FakeSessionState(
            plan_total_cash=40_000,
            _suite_inv_persistence_bootstrapped=True,
            _investment_plan_last_persist_fp="keep-me",
        )
        st = _FakeSt(ss)
        with patch(
            "investment_persistent_state._autosave_would_clobber_saved_portfolio",
            return_value=(True, "empty_holdings_would_overwrite_cloud"),
        ):
            notify_investment_plan_change(st, source="test_blocked", fingerprint="new-fp")
        self.assertEqual(ss.get("_investment_plan_last_persist_fp"), "keep-me")
        self.assertEqual(ss.get("_investment_plan_save_status"), "error")


if __name__ == "__main__":
    unittest.main()
