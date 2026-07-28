"""P2 — ValuationEngine and macro-backed valuation context."""

from __future__ import annotations

import unittest

from investment_ami.engines.base import InstantEngineRequest
from investment_ami.engines.support.macro_context import resolve_macro_scenario_context
from investment_ami.engines.valuation import ValuationEngine, get_valuation_engine
from investment_ami.pipeline.instant import run_instant_engine
from investment_ami_phase2_solvers import valuation_answer
from investment_ami_valuation import resolve_valuation_context


class TestValuationMacroIntegration(unittest.TestCase):
    _CTX = {
        "experience_mode": "Advanced Mode",
        "current_weights": {"SCHD": "40%", "BND": "60%"},
        "health_valuation": "Expensive",
    }

    def test_resolve_valuation_context_uses_macro_scenario(self) -> None:
        macro = resolve_macro_scenario_context(self._CTX)
        vctx = resolve_valuation_context("Is SCHD expensive?", self._CTX)
        self.assertEqual(macro.valuation_environment, "Expensive")
        self.assertEqual(vctx.get("macro_env"), "Expensive")


class TestValuationEngine(unittest.TestCase):
    _CTX = {
        "experience_mode": "Advanced Mode",
        "current_weights": {"SCHD": "40%", "VOO": "30%", "BND": "30%"},
        "health_valuation": "Fair Value",
    }

    def test_engine_metadata(self) -> None:
        result = get_valuation_engine().solve(
            InstantEngineRequest(
                context=self._CTX,
                beginner=False,
                question="Is SCHD expensive?",
            )
        )
        self.assertEqual(result.problem_type, "valuation")
        self.assertEqual(result.computed.get("ami_engine_id"), "valuation")
        self.assertEqual(result.computed.get("target_ticker"), "SCHD")
        self.assertIn("valuation_label", result.computed)

    def test_pipeline_matches_wrapper(self) -> None:
        ctx = dict(self._CTX)
        via_engine = run_instant_engine("valuation", ctx, beginner=False, question="Is SCHD expensive?")
        via_wrapper = valuation_answer(ctx, beginner=False, question="Is SCHD expensive?")
        self.assertEqual(via_engine.short_answer, via_wrapper.short_answer)
        self.assertEqual(via_engine.confidence_pct, via_wrapper.confidence_pct)
        self.assertEqual(
            via_engine.computed.get("valuation_label"),
            via_wrapper.computed.get("valuation_label"),
        )

    def test_empty_target_prompt(self) -> None:
        result = ValuationEngine().solve(
            InstantEngineRequest(context={}, beginner=True, question="Is it expensive?")
        )
        self.assertEqual(result.confidence_pct, 55)
        self.assertIn("SCHD", result.analyst_sections.get("recommended_actions", ""))


if __name__ == "__main__":
    unittest.main()
