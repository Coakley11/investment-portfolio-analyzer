"""Tests for Investment AMI macro_rates family."""

from __future__ import annotations

import unittest

from investment_ami_context import detect_investment_send_intent
from investment_ami_instant_solver import solve_instant_investment_insight
from investment_ami_macro import macro_rates_answer, parse_rate_rise_pct, rate_rise_portfolio_impacts


class TestMacroRates(unittest.TestCase):
    _CTX = {
        "experience_mode": "Advanced Mode",
        "current_weights": {
            "VTI": "50.0%",
            "QQQ": "20.0%",
            "VXUS": "20.0%",
            "VNQ": "10.0%",
        },
        "holdings": ["VTI", "QQQ", "VXUS", "VNQ"],
        "health_rate_env": "Stable Rates",
    }

    def test_intent_rate_rise_question(self) -> None:
        self.assertEqual(
            detect_investment_send_intent("What happens if interest rates rise 2%?", ""),
            "macro_rates",
        )

    def test_tech_fall_still_scenario_stress(self) -> None:
        self.assertEqual(
            detect_investment_send_intent("What happens if tech falls 20%?", ""),
            "scenario_stress",
        )

    def test_parse_rate_rise_pct(self) -> None:
        self.assertEqual(parse_rate_rise_pct("What happens if interest rates rise 2%?"), 2.0)
        self.assertEqual(parse_rate_rise_pct("Rates rise 1.5%"), 1.5)

    def test_macro_rates_answer_sections(self) -> None:
        result = macro_rates_answer(
            self._CTX,
            beginner=False,
            question="What happens if interest rates rise 2%?",
        )
        self.assertEqual(result.problem_type, "macro_rates")
        self.assertIn("direct_answer", result.analyst_sections)
        self.assertIn("recommended_actions", result.analyst_sections)
        self.assertIn("bond", result.analyst_sections["portfolio_analyst_view"].lower())
        self.assertIn("REIT", result.analyst_sections["portfolio_analyst_view"])

    def test_end_to_end_not_tech_scenario(self) -> None:
        solved = solve_instant_investment_insight(
            "What happens if interest rates rise 2%?",
            self._CTX,
        )
        self.assertIsNotNone(solved)
        _, result = solved
        self.assertEqual(result.problem_type, "macro_rates")
        self.assertNotIn("tech drawdown", result.short_answer.lower())
        self.assertIn("rate", result.short_answer.lower())

    def test_bond_heavy_more_duration_drag(self) -> None:
        growth_profile = rate_rise_portfolio_impacts(
            {
                "equity": 0.9,
                "bonds": 0.05,
                "tbills": 0.05,
                "reit": 0.0,
                "long_duration_bonds": 0.0,
                "qqq_spy": 0.2,
                "tech": 0.15,
            },
            2.0,
        )
        bond_profile = rate_rise_portfolio_impacts(
            {
                "equity": 0.2,
                "bonds": 0.6,
                "tbills": 0.1,
                "reit": 0.1,
                "long_duration_bonds": 0.3,
                "qqq_spy": 0.0,
                "tech": 0.0,
            },
            2.0,
        )
        self.assertLess(
            bond_profile["net_return_shift_pp"],
            growth_profile["net_return_shift_pp"],
        )


if __name__ == "__main__":
    unittest.main()
