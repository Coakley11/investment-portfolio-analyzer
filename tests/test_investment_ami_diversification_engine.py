"""P2 — DiversificationEngine reference implementation."""

from __future__ import annotations

import unittest

from investment_ami.engines.diversification import (
    DiversificationEngine,
    assess_diversification,
)
from investment_ami.pipeline.instant import run_instant_engine
from investment_ami_phase2_solvers import diversification_answer


class TestDiversificationAssessment(unittest.TestCase):
    def test_empty_context(self) -> None:
        a = assess_diversification({})
        self.assertTrue(a.empty)

    def test_concentrated_single_class(self) -> None:
        a = assess_diversification({"asset_class_breakdown": {"Equity": 80.0, "Bonds": 20.0}})
        self.assertEqual(a.judgment, "Not fully diversified")

    def test_three_class_balanced(self) -> None:
        a = assess_diversification(
            {
                "asset_class_breakdown": {
                    "Dividend ETF": 30.0,
                    "REIT": 30.0,
                    "Bonds": 40.0,
                }
            }
        )
        self.assertEqual(a.judgment, "Yes — moderately diversified")

    def test_two_class_moderate_top(self) -> None:
        a = assess_diversification({"asset_class_breakdown": {"Equity": 55.0, "Bonds": 45.0}})
        self.assertEqual(a.judgment, "Partially diversified — room to improve")

    def test_weights_fallback_when_no_breakdown(self) -> None:
        a = assess_diversification({"current_weights": {"VOO": "60%", "BND": "40%"}})
        self.assertFalse(a.empty)
        self.assertIn("proxy", a.judgment.lower())


class TestDiversificationEngine(unittest.TestCase):
    _CTX = {
        "experience_mode": "Advanced Mode",
        "asset_class_breakdown": {"Equity": 60.0, "Bonds": 40.0},
    }

    def test_engine_id_on_result(self) -> None:
        from investment_ami.engines.base import InstantEngineRequest

        result = DiversificationEngine().solve(
            InstantEngineRequest(context=self._CTX, beginner=False, question="Am I diversified enough?")
        )
        self.assertEqual(result.computed.get("ami_engine_id"), "diversification")
        self.assertEqual(result.computed.get("equity_pct"), 60.0)
        self.assertIn("Equity", result.analyst_sections.get("key_variables", ""))

    def test_pipeline_matches_phase2_wrapper(self) -> None:
        ctx = dict(self._CTX)
        via_engine = run_instant_engine("diversification", ctx, beginner=False)
        via_wrapper = diversification_answer(ctx, beginner=False)
        self.assertEqual(via_engine.short_answer, via_wrapper.short_answer)
        self.assertEqual(via_engine.computed.get("equity_pct"), via_wrapper.computed.get("equity_pct"))

    def test_beginner_equity_heavy_actions(self) -> None:
        ctx = {"asset_class_breakdown": {"Equity": 85.0, "Bonds": 5.0, "Cash": 10.0}}
        result = run_instant_engine("diversification", ctx, beginner=True)
        self.assertIn("equity-heavy", result.analyst_sections.get("recommended_actions", "").lower())


if __name__ == "__main__":
    unittest.main()
