"""AMI macro-environment routing, shared macro context, and Forward scenario metrics."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

import pandas as pd

from applied_math_context import (
    _apply_forward_metric_fields,
    build_investment_applied_math_context,
)
from investment_ami.engines.support.macro_context import resolve_macro_scenario_context
from investment_ami.engines.support.macro_intelligence import _inflation_label
from investment_ami.integration.instant_solver_facade import solve_instant_insight
from investment_ami.routing.mode_router import route_investment_response_mode
from investment_ami.routing.router import route_instant_question
from investment_ami_context import detect_investment_send_intent


_FROZEN = {
    "health_rate_env": "Rising Rates",
    "health_inflation": "High Inflation",
    "health_recession": 60,
    "health_valuation": "Expensive",
    "health_regime": "Recession",
}

_ORIG = (
    "How does my current macro environment affect my portfolio, "
    "and should I change my allocation because of it?"
)


def _holdings() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Ticker": "VTI", "Weight (%)": 40.0, "Asset Type": "Equity"},
            {"Ticker": "BND", "Weight (%)": 30.0, "Asset Type": "Bond"},
            {"Ticker": "VXUS", "Weight (%)": 20.0, "Asset Type": "Equity"},
            {"Ticker": "VNQ", "Weight (%)": 10.0, "Asset Type": "REIT"},
        ]
    )


def _session(**extra) -> dict:
    ss = dict(_FROZEN)
    ss["holdings_df"] = _holdings()
    ss["investment_active_tab"] = "Portfolio Health"
    ss["objective"] = "balanced growth"
    ss["portfolio_objective"] = "balanced growth"
    # Canonical Forward Macro outputs for the frozen scenario (approx; live data may drift).
    ss["forward_projection"] = SimpleNamespace(
        adjusted_return=-0.2104,
        adjusted_volatility=0.4712,
        adjusted_sharpe=-0.53,
        adjusted_max_drawdown=-0.55,
        projected_value=10000.0,
        forward_insights=[],
        rate_commentary=[],
        inflation_commentary=[],
        adjusted_mean_returns=None,
        adjusted_cov=None,
    )
    # Historical Health metrics — must remain distinct from forward_*.
    ss["health_result"] = SimpleNamespace(
        score=72.0,
        score_label="OK",
        status_message="ok",
        health_diagnostics={
            "annual_return": 0.08,
            "annual_volatility": 0.15,
            "portfolio_sharpe": 0.40,
            "max_drawdown": -0.22,
        },
        expected_return=0.08,
        volatility=0.15,
        sharpe=0.40,
        max_drawdown=-0.22,
        risk_level="Moderate",
    )
    ss.update(extra)
    return ss


def _ctx(ss: dict | None = None) -> dict:
    return build_investment_applied_math_context("Portfolio Health", ss or _session())


class TestAmiMacroEnvironmentIntegration(unittest.TestCase):
    def test_1_original_question_routes_macro_not_rebalance(self) -> None:
        legacy = detect_investment_send_intent(_ORIG, "Portfolio Health")
        self.assertEqual(legacy, "macro_environment")
        mode = route_investment_response_mode(_ORIG, _ctx())
        self.assertEqual(mode.response_mode, "deterministic")
        self.assertEqual(mode.effective_intent_id, "macro_environment")
        self.assertNotEqual(mode.effective_intent_id, "rebalance_allocation")

    def test_2_should_i_rebalance_unchanged(self) -> None:
        q = "Should I rebalance?"
        self.assertEqual(detect_investment_send_intent(q, ""), "allocation_recommendation")
        mode = route_investment_response_mode(q, _ctx())
        self.assertEqual(mode.response_mode, "deterministic")
        self.assertIn(mode.effective_intent_id, {"allocation_recommendation", "rebalance_allocation"})

    def test_3_explain_my_allocation_unchanged(self) -> None:
        q = "Explain my allocation."
        self.assertEqual(detect_investment_send_intent(q, ""), "rebalance_allocation")
        mode = route_investment_response_mode(q, _ctx())
        self.assertEqual(mode.effective_intent_id, "rebalance_allocation")

    def test_4_target_weights_and_drift_unchanged(self) -> None:
        for q in (
            "What are my target weights?",
            "How far am I from my target allocation?",
            "What is my allocation drift?",
        ):
            with self.subTest(q=q):
                self.assertEqual(detect_investment_send_intent(q, ""), "rebalance_allocation")

    def test_5_current_macro_environment_recognized(self) -> None:
        q = "How does the current macro environment affect my portfolio?"
        self.assertEqual(detect_investment_send_intent(q, ""), "macro_environment")
        routed = route_instant_question(q, _ctx())
        assert routed is not None
        self.assertEqual(routed.intent_id, "macro_environment")
        self.assertEqual(routed.response_mode, "deterministic")

    def test_6_high_inflation_remains_high_in_ami(self) -> None:
        ctx = _ctx()
        self.assertEqual(ctx.get("health_inflation"), "High Inflation")
        self.assertEqual(_inflation_label(ctx, dict(ctx.get("scenario_params") or {})), "High Inflation")
        self.assertIn("High Inflation", str(ctx.get("macro_summary") or ""))
        self.assertNotIn("Moderate Inflation", str(ctx.get("macro_summary") or ""))

    def test_7_recession_regime_remains_recession(self) -> None:
        ctx = _ctx()
        macro = resolve_macro_scenario_context(ctx)
        self.assertEqual(macro.economic_regime, "Recession")
        self.assertEqual(ctx.get("health_regime"), "Recession")

    def test_8_all_five_shared_macro_values_reach_context(self) -> None:
        ctx = _ctx()
        macro = resolve_macro_scenario_context(ctx)
        self.assertEqual(ctx["health_inflation"], "High Inflation")
        self.assertEqual(ctx["health_rate_env"], "Rising Rates")
        self.assertEqual(float(ctx["health_recession"]), 60)
        self.assertEqual(ctx["health_valuation"], "Expensive")
        self.assertEqual(ctx["health_regime"], "Recession")
        self.assertEqual(macro.rate_environment, "Rising Rates")
        self.assertAlmostEqual(float(macro.recession_probability or 0), 0.60, places=2)
        self.assertEqual(macro.valuation_environment, "Expensive")
        self.assertEqual(macro.economic_regime, "Recession")
        self.assertEqual(
            str((macro.scenario_params or {}).get("inflation") or ctx.get("health_inflation")),
            "High Inflation",
        )

    def test_9_forward_metrics_from_canonical_forward_projection(self) -> None:
        ctx = _ctx()
        self.assertAlmostEqual(float(ctx["forward_modeled_return"]), -0.2104, places=3)
        self.assertAlmostEqual(float(ctx["forward_modeled_volatility"]), 0.4712, places=3)
        self.assertAlmostEqual(float(ctx["forward_modeled_sharpe"]), -0.53, places=2)

    def test_10_forward_metrics_labeled_scenario_outputs(self) -> None:
        ctx = _ctx()
        self.assertTrue(ctx.get("forward_metrics_are_scenario_outputs"))
        disc = str(ctx.get("forward_metrics_disclaimer") or "").lower()
        self.assertIn("scenario", disc)
        self.assertIn("not factual forecast", disc.replace("forecasts", "forecast"))

        pair = solve_instant_insight(_ORIG, ctx)
        assert pair is not None
        _, result = pair
        text = (result.short_answer or "").lower()
        self.assertIn("scenario", text)
        self.assertTrue(
            "not forecast" in text or "not factual" in text or "scenario/model" in text
        )

    def test_11_historical_health_metrics_not_overwritten(self) -> None:
        ctx = _ctx()
        self.assertEqual(ctx.get("expected_return"), "8.0%")
        self.assertEqual(ctx.get("volatility"), "15.0%")
        self.assertEqual(ctx.get("sharpe_ratio"), "0.40")
        self.assertAlmostEqual(float(ctx["forward_modeled_return"]), -0.2104, places=3)
        # Applying forward fields again must not clobber historical keys.
        _apply_forward_metric_fields(
            ctx,
            {"return": -0.21, "volatility": 0.47, "sharpe": -0.5},
        )
        self.assertEqual(ctx.get("expected_return"), "8.0%")

    def test_12_mixed_answer_distinguishes_stress_guided_optimizer(self) -> None:
        pair = solve_instant_insight(_ORIG, _ctx())
        assert pair is not None
        _, result = pair
        text = (result.short_answer or "").lower()
        self.assertIn("high inflation", text)
        self.assertIn("stress", text)
        self.assertTrue("guided" in text or "strategic" in text)
        self.assertTrue("optimizer" in text or "corner" in text)

    def test_13_no_optimizer_corner_as_recommendation(self) -> None:
        pair = solve_instant_insight(_ORIG, _ctx())
        assert pair is not None
        _, result = pair
        text = (result.short_answer or "").lower()
        self.assertNotIn("100% vti", text)
        self.assertNotIn("move entirely", text)
        self.assertIn("not", text)

    def test_14_macro_free_allocation_has_no_macro_dump(self) -> None:
        q = "Explain my allocation."
        pair = solve_instant_insight(q, _ctx())
        assert pair is not None
        _, result = pair
        self.assertEqual(result.problem_type, "rebalance_allocation")
        text = (result.short_answer or "").lower()
        self.assertNotIn("high inflation", text)
        self.assertNotIn("forward modeled return", text)
        self.assertIn("allocation", text)

    def test_probes_a_through_e(self) -> None:
        probes = {
            "A": "How does the current macro environment affect my portfolio?",
            "B": "What does a recession mean for my portfolio?",
            "C": "How do high inflation and rising rates affect my portfolio?",
            "D": "Should I change my allocation because of the current macro environment?",
            "E": _ORIG,
        }
        ctx = _ctx()
        for key, q in probes.items():
            with self.subTest(probe=key):
                legacy = detect_investment_send_intent(q, "Portfolio Health")
                mode = route_investment_response_mode(q, ctx)
                pair = solve_instant_insight(q, ctx)
                assert pair is not None
                _, result = pair
                text = (result.short_answer or "").lower()
                self.assertNotEqual(mode.effective_intent_id, "rebalance_allocation", msg=key)
                self.assertNotIn("allocation / rebalance assessment", text)
                if key in {"A", "D", "E"}:
                    self.assertEqual(legacy, "macro_environment")
                    self.assertEqual(mode.effective_intent_id, "macro_environment")
                    self.assertIn("high inflation", text)
                if key == "B":
                    self.assertEqual(legacy, "macro_recession")
                    self.assertIn("elevated inflation", text)
                if key == "C":
                    # Rates keyword still wins for this wording; scenario must stay High Inflation.
                    self.assertIn(legacy, {"macro_rates", "macro_inflation", "macro_environment"})
                    self.assertIn("elevated inflation", text)
                if key in {"D", "E"}:
                    self.assertTrue("strategic" in text or "guided" in text)
                    self.assertAlmostEqual(
                        float((result.computed or {}).get("forward_modeled_return") or 0),
                        -0.2104,
                        places=3,
                    )


if __name__ == "__main__":
    unittest.main()
