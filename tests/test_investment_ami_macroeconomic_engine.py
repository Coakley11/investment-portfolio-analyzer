"""P2 — MacroeconomicEngine and macro context."""

from __future__ import annotations

import unittest

from investment_ami.engines.base import InstantEngineRequest
from investment_ami.engines.macroeconomic import MacroeconomicEngine, get_macroeconomic_engine
from investment_ami.engines.support.macro_context import resolve_macro_scenario_context
from investment_ami.pipeline.instant import run_instant_engine
from investment_ami_macro import macro_inflation_answer, macro_rates_answer, macro_recession_answer


class TestMacroScenarioContext(unittest.TestCase):
    _CTX = {
        "experience_mode": "Advanced Mode",
        "current_weights": {"VTI": "50%", "BND": "50%"},
        "scenario_params": {"rate_shock": "Rising", "inflation_pct": 5.0},
        "health_rate_env": "Rising Rates",
        "health_regime": "Slowdown",
        "health_recession": 35,
    }

    def test_resolve_macro_context(self) -> None:
        macro = resolve_macro_scenario_context(self._CTX)
        self.assertTrue(macro.has_portfolio_weights)
        self.assertEqual(macro.rate_environment, "Rising Rates")
        self.assertEqual(macro.economic_regime, "Slowdown")
        self.assertIsNotNone(macro.recession_probability)
        self.assertEqual(macro.scenario_params.get("inflation_pct"), 5.0)
        self.assertEqual(macro.valuation_environment, "Fair Value")
        self.assertGreater(float(macro.allocation_profile.get("equity") or 0), 0)

    def test_valuation_environment_from_health(self) -> None:
        macro = resolve_macro_scenario_context({**self._CTX, "health_valuation": "Expensive"})
        self.assertEqual(macro.valuation_environment, "Expensive")


class TestMacroeconomicEngine(unittest.TestCase):
    _CTX = {
        "experience_mode": "Advanced Mode",
        "current_weights": {
            "VTI": "50.0%",
            "QQQ": "20.0%",
            "VXUS": "20.0%",
            "VNQ": "10.0%",
        },
        "health_rate_env": "Stable Rates",
    }

    def test_rates_engine_metadata(self) -> None:
        engine = get_macroeconomic_engine("macro_rates")
        result = engine.solve(
            InstantEngineRequest(
                context=self._CTX,
                beginner=False,
                question="What happens if interest rates rise 2%?",
            )
        )
        self.assertEqual(result.problem_type, "macro_rates")
        self.assertEqual(result.computed.get("ami_engine_id"), "macro_rates")
        self.assertIn("net_return_shift_pp", result.computed)

    def test_wrapper_matches_registry(self) -> None:
        ctx = dict(self._CTX)
        via_wrapper = macro_rates_answer(ctx, beginner=False, question="What happens if interest rates rise 2%?")
        via_registry = run_instant_engine(
            "macro_rates",
            ctx,
            beginner=False,
            question="What happens if interest rates rise 2%?",
        )
        self.assertEqual(via_wrapper.short_answer, via_registry.short_answer)
        self.assertEqual(
            via_wrapper.computed.get("net_return_shift_pp"),
            via_registry.computed.get("net_return_shift_pp"),
        )

    def test_recession_and_inflation_intents(self) -> None:
        rec = MacroeconomicEngine("macro_recession").solve(
            InstantEngineRequest(
                context={**self._CTX, "health_recession": 35},
                beginner=False,
                question="What happens in a recession?",
            )
        )
        self.assertEqual(rec.problem_type, "macro_recession")
        self.assertEqual(rec.computed.get("ami_macro_intent"), "macro_recession")

        infl = macro_inflation_answer(
            {**self._CTX, "scenario_params": {"inflation_pct": 6.0}},
            beginner=False,
            question="What happens if inflation rises to 6%?",
        )
        self.assertEqual(infl.problem_type, "macro_inflation")
        self.assertEqual(infl.computed.get("ami_engine_id"), "macro_inflation")


if __name__ == "__main__":
    unittest.main()
