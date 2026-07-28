"""P2 — PortfolioRiskEngine."""

from __future__ import annotations

import unittest

from investment_ami.engines.base import InstantEngineRequest
from investment_ami.engines.portfolio_risk import PortfolioRiskEngine, assess_portfolio_risk
from investment_ami.pipeline.instant import run_instant_engine
from investment_ami_phase2_solvers import structured_portfolio_risk_answer


class TestPortfolioRiskAssessment(unittest.TestCase):
    _CTX = {
        "experience_mode": "Advanced Mode",
        "current_weights": {"VOO": "40%", "QQQ": "35%", "BND": "25%"},
        "risk_level": "Moderate",
        "volatility": "14.2%",
    }

    def test_uses_concentration_weights(self) -> None:
        a = assess_portfolio_risk(self._CTX)
        self.assertTrue(a.has_weights)
        self.assertEqual(a.top_ticker, "VOO")
        self.assertAlmostEqual(a.top_weight_pct, 40.0)
        self.assertAlmostEqual(a.top3_weight_pct, 100.0)

    def test_tech_proxy_from_exposure(self) -> None:
        a = assess_portfolio_risk(self._CTX)
        self.assertGreater(a.tech_proxy_pct, 0.0)

    def test_empty_weights_placeholder_ticker(self) -> None:
        a = assess_portfolio_risk({"risk_level": "Moderate"})
        self.assertFalse(a.has_weights)
        self.assertEqual(a.top_ticker, "—")
        self.assertEqual(a.top_weight_pct, 0.0)


class TestPortfolioRiskEngine(unittest.TestCase):
    _CTX = {
        "experience_mode": "Advanced Mode",
        "current_weights": {"VOO": "40%", "QQQ": "35%", "BND": "25%"},
        "holdings": ["VOO", "QQQ", "BND"],
        "health_score": 72,
        "risk_level": "Moderate",
        "volatility": "14.2%",
    }

    def test_engine_metadata_and_computed(self) -> None:
        result = PortfolioRiskEngine().solve(
            InstantEngineRequest(context=self._CTX, beginner=False, question="What is my biggest portfolio risk?")
        )
        self.assertEqual(result.problem_type, "portfolio_risk")
        self.assertEqual(result.confidence_pct, 81)
        self.assertEqual(result.computed.get("ami_engine_id"), "portfolio_risk")
        self.assertEqual(result.computed.get("top_weight_pct"), 40.0)
        self.assertEqual(result.computed.get("top3_weight_pct"), 100.0)
        self.assertIn("tech_proxy_pct", result.computed)

    def test_pipeline_matches_phase2_wrapper(self) -> None:
        ctx = dict(self._CTX)
        via_engine = run_instant_engine("portfolio_risk", ctx, beginner=False)
        via_wrapper = structured_portfolio_risk_answer(ctx, beginner=False)
        self.assertEqual(via_engine.short_answer, via_wrapper.short_answer)
        self.assertEqual(via_engine.computed.get("top3_weight_pct"), via_wrapper.computed.get("top3_weight_pct"))
        self.assertEqual(via_engine.computed.get("tech_proxy_pct"), via_wrapper.computed.get("tech_proxy_pct"))

    def test_risk_analysis_catalog_alias(self) -> None:
        ctx = dict(self._CTX)
        primary = run_instant_engine("portfolio_risk", ctx, beginner=True)
        alias = run_instant_engine("risk_analysis", dict(self._CTX), beginner=True)
        self.assertEqual(primary.short_answer, alias.short_answer)

    def test_beginner_tradeoffs_unchanged(self) -> None:
        ctx = dict(self._CTX)
        ctx["experience_mode"] = "Beginner Mode"
        result = run_instant_engine("portfolio_risk", ctx, beginner=True)
        self.assertIn("growth", str(result.analyst_sections.get("tradeoffs", "")).lower())


if __name__ == "__main__":
    unittest.main()
