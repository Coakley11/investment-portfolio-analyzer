"""Tests for Investment AMI Phase 2b valuation family."""

from __future__ import annotations

import unittest

from investment_ami_context import detect_investment_send_intent
from investment_ami_instant_solver import solve_instant_investment_insight
from investment_ami_phase2_solvers import valuation_answer
from investment_ami_valuation import (
    assess_valuation_richness,
    lookup_ticker_valuation,
    resolve_valuation_context,
)


class TestInvestmentValuation(unittest.TestCase):
    _CTX = {
        "experience_mode": "Advanced Mode",
        "current_weights": {"SCHD": "20%", "VYM": "20%", "VTI": "20%", "VNQ": "20%", "BND": "20%"},
        "health_valuation": "Fair Value",
    }

    def test_intent_schd_expensive(self) -> None:
        self.assertEqual(detect_investment_send_intent("Is SCHD expensive?", ""), "valuation")

    def test_intent_implied_growth(self) -> None:
        self.assertEqual(
            detect_investment_send_intent("What growth rate is implied for VOO?", ""),
            "valuation",
        )

    def test_rate_rise_not_valuation(self) -> None:
        """Rate-rise 'what if' routes to macro_rates (see test_investment_ami_macro), not valuation."""
        intent = detect_investment_send_intent("What happens if rates rise?", "")
        self.assertNotEqual(intent, "valuation")
        self.assertEqual(intent, "macro_rates")

    def test_schd_not_expensive_vs_growth(self) -> None:
        data = lookup_ticker_valuation("SCHD")
        assessment = assess_valuation_richness(data, macro_env="Fair Value")
        self.assertIn(assessment["label"], {"fairly valued", "cheap", "moderately rich"})

    def test_voo_richer_than_schd(self) -> None:
        voo = lookup_ticker_valuation("VOO")
        schd = lookup_ticker_valuation("SCHD")
        self.assertIsNotNone(voo.get("pe"))
        self.assertIsNotNone(schd.get("pe"))
        self.assertGreater(float(voo["pe"]), float(schd["pe"]))

    def test_valuation_answer_sections(self) -> None:
        result = valuation_answer(self._CTX, beginner=False, question="Is SCHD expensive?")
        self.assertEqual(result.problem_type, "valuation")
        self.assertIn("direct_answer", result.analyst_sections)
        self.assertIn("portfolio_analyst_view", result.analyst_sections)
        self.assertIn("what_if_scenarios", result.analyst_sections)
        self.assertIn("SCHD", result.short_answer)

    def test_valuation_uses_macro_context(self) -> None:
        ctx = {**self._CTX, "health_valuation": "Expensive"}
        vctx = resolve_valuation_context("Is VOO expensive?", ctx)
        self.assertEqual(vctx["macro_env"], "Expensive")
        result = valuation_answer(ctx, beginner=False, question="Is VOO expensive?")
        self.assertIn("Expensive", result.analyst_sections.get("key_variables", ""))

    def test_end_to_end_voo_expensive(self) -> None:
        solved = solve_instant_investment_insight("Is VOO expensive?", self._CTX)
        self.assertIsNotNone(solved)
        _, result = solved
        self.assertEqual(result.problem_type, "valuation")
        self.assertIn("VOO", result.short_answer)
        self.assertIn("recommended_actions", result.analyst_sections)

    def test_assumptions_matter_question(self) -> None:
        solved = solve_instant_investment_insight(
            "What assumptions matter most for VOO?",
            self._CTX,
        )
        self.assertIsNotNone(solved)
        _, result = solved
        self.assertEqual(result.problem_type, "valuation")
        self.assertIn("tradeoffs", result.analyst_sections)


if __name__ == "__main__":
    unittest.main()
