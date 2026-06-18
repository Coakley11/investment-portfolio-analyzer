"""Investment AMI instant solver — Phase 1 routing and answers."""

from __future__ import annotations

import unittest

from investment_ami_context import detect_investment_send_intent
from investment_ami_instant_solver import solve_instant_investment_insight


class TestInvestmentIntentRouting(unittest.TestCase):
    def test_concentration_question(self) -> None:
        q = "Is my portfolio too concentrated?"
        self.assertEqual(detect_investment_send_intent(q, "Portfolio Health"), "portfolio_concentration")

    def test_rebalance_question(self) -> None:
        self.assertEqual(detect_investment_send_intent("Should I rebalance?", "Portfolio Health"), "allocation_recommendation")

    def test_risk_question(self) -> None:
        self.assertEqual(detect_investment_send_intent("What is my biggest portfolio risk?", ""), "portfolio_risk")

    def test_tech_exposure_question(self) -> None:
        self.assertEqual(detect_investment_send_intent("Am I too exposed to tech?", ""), "sector_exposure")

    def test_risk_reduction_question(self) -> None:
        self.assertEqual(detect_investment_send_intent("What should I change if I want less risk?", ""), "risk_reduction")


class TestInvestmentInstantSolver(unittest.TestCase):
    _CTX = {
        "experience_mode": "Advanced Mode",
        "current_weights": {"VOO": "40%", "QQQ": "35%", "BND": "25%"},
        "holdings": ["VOO", "QQQ", "BND"],
        "health_score": 72,
        "risk_level": "Moderate",
        "volatility": "14.2%",
    }

    def test_concentration_answer_uses_weights(self) -> None:
        solved = solve_instant_investment_insight("Is my portfolio too concentrated?", self._CTX)
        self.assertIsNotNone(solved)
        route, result = solved
        self.assertEqual(route.problem_type, "portfolio_concentration")
        self.assertIn("VOO", result.short_answer)
        self.assertIn("40", result.short_answer)

    def test_tech_exposure_answer(self) -> None:
        solved = solve_instant_investment_insight("Am I too exposed to tech?", self._CTX)
        self.assertIsNotNone(solved)
        route, result = solved
        self.assertEqual(route.problem_type, "sector_exposure")
        self.assertIn("QQQ", result.short_answer)

    def test_beginner_mode_simpler_language(self) -> None:
        ctx = dict(self._CTX)
        ctx["experience_mode"] = "Beginner Mode"
        solved = solve_instant_investment_insight("What is my biggest portfolio risk?", ctx)
        self.assertIsNotNone(solved)
        _, result = solved
        self.assertTrue(result.analyst_sections.get("tradeoffs"))
        self.assertIn("growth", str(result.analyst_sections.get("tradeoffs", "")).lower())

    def test_rebalance_allocation_question(self) -> None:
        solved = solve_instant_investment_insight(
            "Explain my allocation.",
            {**self._CTX, "rebalance_drift": {"VOO": "+5.0pp", "BND": "-3.0pp"}},
        )
        self.assertIsNotNone(solved)
        route, result = solved
        self.assertEqual(route.problem_type, "rebalance_allocation")
        self.assertIn("drift", result.short_answer.lower())


if __name__ == "__main__":
    unittest.main()
