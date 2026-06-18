"""Tests for direct vs embedded technology exposure attribution."""

from __future__ import annotations

import unittest

from investment_ami_exposure import build_tech_exposure_from_weights, resolve_tech_exposure
from investment_ami_instant_solver import solve_instant_investment_insight


class TestTechExposureAttribution(unittest.TestCase):
    _USER_PORTFOLIO = {
        "SCHD": "20%",
        "VYM": "20%",
        "VTI": "20%",
        "VNQ": "20%",
        "BND": "20%",
    }

    def test_dividend_portfolio_has_embedded_not_direct(self) -> None:
        exp = build_tech_exposure_from_weights(self._USER_PORTFOLIO)
        self.assertEqual(exp["direct_pct"], 0.0)
        self.assertGreater(exp["embedded_pct"], 5.0)
        self.assertGreater(exp["total_pct"], exp["direct_pct"])
        tickers = {h["ticker"] for h in exp["embedded_holdings"]}
        self.assertTrue({"VTI", "SCHD", "VYM"} & tickers)

    def test_scenario_uses_embedded_exposure(self) -> None:
        ctx = {
            "experience_mode": "Advanced Mode",
            "current_weights": self._USER_PORTFOLIO,
            "tech_exposure": build_tech_exposure_from_weights(self._USER_PORTFOLIO),
        }
        solved = solve_instant_investment_insight("What happens if tech falls 20%?", ctx)
        self.assertIsNotNone(solved)
        _, result = solved
        self.assertGreater(float(result.computed.get("embedded_tech_pct") or 0), 0)
        self.assertGreater(float(result.computed.get("illustrative_impact_pct") or 0), 0)
        self.assertIn("embedded", result.short_answer.lower())

    def test_resolve_from_context(self) -> None:
        ctx = {"tech_exposure": {"direct_pct": 0, "embedded_pct": 12.5, "total_pct": 12.5}}
        self.assertEqual(resolve_tech_exposure(ctx)["total_pct"], 12.5)


if __name__ == "__main__":
    unittest.main()
