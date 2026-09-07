"""Regression: shared macro controls must survive Streamlit widget teardown / navigation."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

import portfolio_core as core
from components.macro_engine import (
    SHARED_MACRO_DEFAULTS,
    SHARED_MACRO_PERSIST_KEYS,
    commit_macro_widget_to_persist,
    ensure_shared_macro_session_defaults,
    macro_assumptions_from_session,
    macro_widget_key,
    seed_macro_widget_from_persist,
    simulate_macro_widget_teardown,
)
from investment_ami.engines.support.macro_context import resolve_macro_scenario_context


def _session(**overrides) -> dict:
    ss = dict(SHARED_MACRO_DEFAULTS)
    ss.update(overrides)
    return ss


def _user_sets_all_macros(ss: dict) -> None:
    """Simulate Health widgets committing non-default values, then navigation teardown."""
    ss["health_rate_env"] = "Rising Rates"
    ss["health_inflation"] = "High Inflation"
    ss["health_recession"] = 55
    ss["health_valuation"] = "Expensive"
    ss["health_regime"] = "Slow Growth"
    for key in SHARED_MACRO_PERSIST_KEYS:
        ss[macro_widget_key(key)] = ss[key]
        commit_macro_widget_to_persist(key, ss)
    simulate_macro_widget_teardown(ss)


class TestSharedMacroPersistence(unittest.TestCase):
    def test_A_valuation_survives_rerun(self) -> None:
        ss = _session(health_valuation="Expensive")
        ss[macro_widget_key("health_valuation")] = "Expensive"
        # Rerun without Health widgets: Streamlit drops widget keys.
        simulate_macro_widget_teardown(ss)
        ensure_shared_macro_session_defaults(ss)
        a = macro_assumptions_from_session(ss)
        self.assertEqual(a.valuation, "Expensive")
        self.assertEqual(ss["health_valuation"], "Expensive")

    def test_B_valuation_survives_health_to_forward_nav(self) -> None:
        ss = _session()
        # On Health: widget + persist
        ss[macro_widget_key("health_valuation")] = "Expensive"
        commit_macro_widget_to_persist("health_valuation", ss)
        # Navigate away: widgets unmounted
        simulate_macro_widget_teardown(ss)
        self.assertNotIn(macro_widget_key("health_valuation"), ss)
        # Forward Macro / return to Health seed
        seed_macro_widget_from_persist("health_valuation", ss)
        self.assertEqual(ss[macro_widget_key("health_valuation")], "Expensive")
        self.assertEqual(macro_assumptions_from_session(ss).valuation, "Expensive")

    def test_C_forward_macro_sees_changed_valuation(self) -> None:
        ss = _session()
        _user_sets_all_macros(ss)
        a = macro_assumptions_from_session(ss)
        text = (
            f"{a.inflation} · {a.rate_environment} · "
            f"Recession {a.recession_probability * 100:.0f}% · {a.valuation} · {a.economic_regime}"
        )
        self.assertEqual(a.valuation, "Expensive")
        self.assertIn("Expensive", text)
        self.assertNotIn("Fair Value", text)

    def test_D_monte_carlo_forward_basis_sees_changed_value(self) -> None:
        # MC forward basis calls get_forward_projection → macro_assumptions_from_session.
        ss = _session()
        _user_sets_all_macros(ss)
        a = macro_assumptions_from_session(ss)
        self.assertEqual(a.valuation, "Expensive")
        self.assertEqual(a.rate_environment, "Rising Rates")
        self.assertAlmostEqual(a.recession_probability, 0.55)

    def test_E_optimizer_forward_basis_sees_changed_value(self) -> None:
        # Optimizer forward basis uses the same macro_assumptions_from_session owner.
        ss = _session()
        _user_sets_all_macros(ss)
        a = macro_assumptions_from_session(ss)
        self.assertEqual(a.valuation, "Expensive")
        self.assertEqual(a.economic_regime, "Slow Growth")

    def test_F_ami_context_sees_changed_value(self) -> None:
        ss = _session()
        _user_sets_all_macros(ss)
        ctx = {
            "health_rate_env": ss["health_rate_env"],
            "health_inflation": ss["health_inflation"],
            "health_recession": ss["health_recession"],
            "health_valuation": ss["health_valuation"],
            "health_regime": ss["health_regime"],
            "scenario_params": {},
            "allocation_profile": {"equity": 0.6, "bonds": 0.3, "reit": 0.1, "tbills": 0.0},
            "weight_rows": (("VTI", 0.4), ("VXUS", 0.2), ("BND", 0.3), ("VNQ", 0.1)),
        }
        macro = resolve_macro_scenario_context(ctx)
        self.assertEqual(macro.valuation_environment, "Expensive")
        self.assertEqual(macro.rate_environment, "Rising Rates")
        self.assertEqual(macro.economic_regime, "Slow Growth")

    def test_G_rates_persist(self) -> None:
        ss = _session(health_rate_env="Falling Rates")
        ss[macro_widget_key("health_rate_env")] = "Falling Rates"
        simulate_macro_widget_teardown(ss)
        self.assertEqual(macro_assumptions_from_session(ss).rate_environment, "Falling Rates")

    def test_H_inflation_persist(self) -> None:
        ss = _session(health_inflation="Deflation")
        ss[macro_widget_key("health_inflation")] = "Deflation"
        simulate_macro_widget_teardown(ss)
        self.assertEqual(macro_assumptions_from_session(ss).inflation, "Deflation")

    def test_I_recession_probability_persists(self) -> None:
        ss = _session(health_recession=70)
        ss[macro_widget_key("health_recession")] = 70
        simulate_macro_widget_teardown(ss)
        self.assertAlmostEqual(macro_assumptions_from_session(ss).recession_probability, 0.70)

    def test_J_economic_regime_persists(self) -> None:
        ss = _session(health_regime="Stagflation")
        ss[macro_widget_key("health_regime")] = "Stagflation"
        simulate_macro_widget_teardown(ss)
        self.assertEqual(macro_assumptions_from_session(ss).economic_regime, "Stagflation")

    def test_K_no_macro_control_silently_resets_another(self) -> None:
        ss = _session()
        _user_sets_all_macros(ss)
        # Re-seed / re-commit only valuation (as if only that widget re-rendered).
        seed_macro_widget_from_persist("health_valuation", ss)
        commit_macro_widget_to_persist("health_valuation", ss)
        ensure_shared_macro_session_defaults(ss)
        a = macro_assumptions_from_session(ss)
        self.assertEqual(a.valuation, "Expensive")
        self.assertEqual(a.rate_environment, "Rising Rates")
        self.assertEqual(a.inflation, "High Inflation")
        self.assertAlmostEqual(a.recession_probability, 0.55)
        self.assertEqual(a.economic_regime, "Slow Growth")

    def test_L_core_health_independent_of_macro_under_option_c(self) -> None:
        tickers = ["VTI", "VXUS", "BND", "VNQ"]
        weights = np.array([0.40, 0.20, 0.30, 0.10], dtype=float)
        types = ["Equity", "Equity", "Bonds", "REIT"]
        idx = pd.date_range("2019-01-01", periods=200, freq="B")
        rng = np.random.default_rng(42)
        rets = pd.DataFrame(
            {
                "VTI": rng.normal(0.00055, 0.010, size=len(idx)),
                "VXUS": rng.normal(0.00035, 0.012, size=len(idx)),
                "BND": rng.normal(0.00008, 0.003, size=len(idx)),
                "VNQ": rng.normal(0.00040, 0.014, size=len(idx)),
            },
            index=idx,
        )
        proxy = pd.DataFrame(
            {
                "SPY": rng.normal(0.0005, 0.01, size=len(idx)),
                "AGG": rng.normal(0.0001, 0.003, size=len(idx)),
                "BIL": rng.normal(0.00005, 0.0004, size=len(idx)),
            },
            index=idx,
        )
        policy, meta = core.build_policy_benchmark_returns(proxy, "balanced growth")
        metrics = core.compute_extended_metrics(rets, weights, 0.04, 10_000.0, tickers=tickers)
        aligned, _, _ = core.align_returns_and_weights(rets, weights, tickers=tickers)
        corr = aligned.corr()
        rc = core.risk_contribution(rets, weights, tickers=tickers)

        def _run(valuation: str):
            return core.evaluate_portfolio_health(
                tickers=tickers,
                weights=weights,
                asset_types=types,
                metrics=metrics,
                asset_returns=rets,
                corr=corr,
                risk_contrib_df=rc,
                assumptions=core.ForwardMacroAssumptions(
                    rate_environment="Stable Rates",
                    inflation="Moderate Inflation",
                    recession_probability=0.25,
                    valuation=valuation,
                    economic_regime="Expansion",
                ),
                objective="balanced growth",
                risk_free_rate=0.04,
                initial_value=10_000.0,
                policy_benchmark_returns=policy,
                policy_benchmark_meta=meta,
                recommended_type_mix=core.OBJECTIVE_ALLOCATIONS["balanced growth"],
            )

        fair = _run("Fair Value")
        rich = _run("Expensive")
        self.assertAlmostEqual(fair.score, rich.score, places=9)
        self.assertEqual(fair.score_breakdown, rich.score_breakdown)

    def test_defaults_do_not_overwrite_user_values(self) -> None:
        ss = _session(health_valuation="Bubble-like", health_recession=90)
        ensure_shared_macro_session_defaults(ss)
        self.assertEqual(ss["health_valuation"], "Bubble-like")
        self.assertEqual(ss["health_recession"], 90)

    def test_widget_keys_are_not_canonical_owner(self) -> None:
        for key in SHARED_MACRO_PERSIST_KEYS:
            self.assertFalse(macro_widget_key(key).startswith("health_"))
            self.assertTrue(macro_widget_key(key).startswith("_w_"))


if __name__ == "__main__":
    unittest.main()
