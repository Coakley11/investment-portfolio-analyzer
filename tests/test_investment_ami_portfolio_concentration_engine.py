"""P2 — PortfolioConcentrationEngine."""

from __future__ import annotations

import unittest

from investment_ami.engines.base import InstantEngineRequest
from investment_ami.engines.portfolio_concentration import (
    PortfolioConcentrationEngine,
    assess_portfolio_concentration,
)
from investment_ami.pipeline.instant import run_instant_engine
from investment_ami_phase2_solvers import structured_concentration_answer


class TestConcentrationAssessment(unittest.TestCase):
    def test_empty_context(self) -> None:
        a = assess_portfolio_concentration({})
        self.assertTrue(a.empty)

    def test_flag_bands(self) -> None:
        low = assess_portfolio_concentration(
            {"current_weights": {"A": "20%", "B": "20%", "C": "20%", "D": "20%", "E": "20%"}}
        )
        self.assertEqual(low.flag, "low")
        mod = assess_portfolio_concentration(
            {"current_weights": {"VOO": "30%", "BND": "30%", "C": "25%", "D": "15%"}}
        )
        self.assertEqual(mod.flag, "moderate")
        high = assess_portfolio_concentration({"current_weights": {"VOO": "40%", "BND": "60%"}})
        self.assertEqual(high.flag, "high")

    def test_top3_sum(self) -> None:
        a = assess_portfolio_concentration(
            {
                "current_weights": {
                    "SCHD": "20%",
                    "VYM": "20%",
                    "VNQ": "20%",
                    "BND": "40%",
                }
            }
        )
        self.assertEqual(a.top_ticker, "BND")
        self.assertAlmostEqual(a.top3_pct, 80.0)


class TestPortfolioConcentrationEngine(unittest.TestCase):
    _CTX = {
        "experience_mode": "Advanced Mode",
        "current_weights": {"SCHD": "20%", "VYM": "20%", "VNQ": "20%", "BND": "40%"},
    }

    def test_engine_metadata(self) -> None:
        result = PortfolioConcentrationEngine().solve(
            InstantEngineRequest(context=self._CTX, beginner=False, question="Is my portfolio too concentrated?")
        )
        self.assertEqual(result.computed.get("ami_engine_id"), "portfolio_concentration")
        self.assertEqual(result.computed.get("top_ticker"), "BND")
        self.assertIn("BND", result.analyst_sections.get("direct_answer", ""))

    def test_pipeline_matches_phase2_wrapper(self) -> None:
        ctx = dict(self._CTX)
        via_engine = run_instant_engine("portfolio_concentration", ctx, beginner=False)
        via_wrapper = structured_concentration_answer(ctx, beginner=False)
        self.assertEqual(via_engine.short_answer, via_wrapper.short_answer)
        self.assertEqual(via_engine.computed.get("top3_weight_pct"), via_wrapper.computed.get("top3_weight_pct"))

    def test_catalog_alias_portfolio_analysis(self) -> None:
        ctx = dict(self._CTX)
        primary = run_instant_engine("portfolio_concentration", ctx, beginner=True)
        alias = run_instant_engine("portfolio_analysis", dict(self._CTX), beginner=True)
        self.assertEqual(primary.short_answer, alias.short_answer)

    def test_beginner_high_concentration_wording(self) -> None:
        ctx = {"current_weights": {"VOO": "50%", "BND": "50%"}}
        result = run_instant_engine("portfolio_concentration", ctx, beginner=True)
        self.assertIn("concentrated", result.short_answer.lower())
        self.assertIn("VOO", result.short_answer)


if __name__ == "__main__":
    unittest.main()
