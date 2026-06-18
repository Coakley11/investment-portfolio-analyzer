"""Investment AMI Phase 2 — structured answers and new question families."""

from __future__ import annotations

import unittest

from investment_ami_answer_format import render_analyst_sections_markdown
from investment_ami_context import detect_investment_send_intent
from investment_ami_instant_solver import INVESTMENT_AMI_BUILD_ID, solve_instant_investment_insight


class TestInvestmentAmiPhase2(unittest.TestCase):
    _CTX = {
        "experience_mode": "Advanced Mode",
        "current_weights": {"SCHD": "20%", "VYM": "20%", "VNQ": "20%", "BND": "40%"},
        "holdings": ["SCHD", "VYM", "VNQ", "BND"],
        "health_score": 72,
        "risk_level": "Moderate",
        "volatility": "14.2%",
    }

    def test_build_id_phase2(self) -> None:
        self.assertIn("phase2", INVESTMENT_AMI_BUILD_ID)

    def test_concentration_has_analyst_sections(self) -> None:
        solved = solve_instant_investment_insight("Is my portfolio too concentrated?", self._CTX)
        self.assertIsNotNone(solved)
        _, result = solved
        self.assertIn("direct_answer", result.analyst_sections)
        self.assertIn("portfolio_analyst_view", result.analyst_sections)
        self.assertIn("SCHD", result.analyst_sections["direct_answer"])

    def test_portfolio_risk_structured_depth(self) -> None:
        solved = solve_instant_investment_insight("What is my biggest portfolio risk?", self._CTX)
        self.assertIsNotNone(solved)
        _, result = solved
        self.assertIn("recommended_actions", result.analyst_sections)
        self.assertIn("Tradeoffs", render_analyst_sections_markdown(result.analyst_sections))

    def test_etf_overlap_intent_and_answer(self) -> None:
        self.assertEqual(
            detect_investment_send_intent("Should I own both VOO and QQQ?", ""),
            "etf_overlap",
        )
        ctx = {
            **self._CTX,
            "etf_overlap_pairs": [{"pair": "VOO/QQQ", "overlap_pct": 72.5}],
        }
        solved = solve_instant_investment_insight("Should I own both VOO and QQQ?", ctx)
        self.assertIsNotNone(solved)
        _, result = solved
        self.assertEqual(result.problem_type, "etf_overlap")
        self.assertIn("VOO", result.short_answer)

    def test_diversification_intent(self) -> None:
        self.assertEqual(detect_investment_send_intent("Am I diversified enough?", ""), "diversification")
        ctx = {
            **self._CTX,
            "asset_class_breakdown": {"Equity": 60.0, "Bonds": 40.0},
        }
        solved = solve_instant_investment_insight("Am I diversified enough?", ctx)
        self.assertIsNotNone(solved)
        _, result = solved
        self.assertIn("Equity", result.analyst_sections.get("key_variables", ""))

    def test_scenario_stress_intent(self) -> None:
        self.assertEqual(
            detect_investment_send_intent("What happens if tech falls 20%?", ""),
            "scenario_stress",
        )
        ctx = {**self._CTX, "current_weights": {**self._CTX["current_weights"], "QQQ": "30%"}, "scenario_params": {"tech_drawdown_pct": 20}}
        solved = solve_instant_investment_insight("What happens if tech falls 20%?", ctx)
        self.assertIsNotNone(solved)
        _, result = solved
        self.assertIn("what_if_scenarios", result.analyst_sections)


if __name__ == "__main__":
    unittest.main()
