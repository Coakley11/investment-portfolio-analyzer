"""Tests for Investment AMI macro families (rates, recession)."""

from __future__ import annotations

import unittest

from investment_ami_context import detect_investment_send_intent
from investment_ami_instant_solver import solve_instant_investment_insight
from investment_ami_macro import (
    inflation_portfolio_impacts,
    macro_inflation_answer,
    macro_rates_answer,
    macro_recession_answer,
    parse_inflation_pct,
    parse_rate_rise_pct,
    parse_rate_shock_pp,
    rate_rise_portfolio_impacts,
    recession_portfolio_impacts,
)

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

    def test_parse_rate_cut_defaults_negative_shock(self) -> None:
        q = "What happens if the Federal Reserve cuts interest rates?"
        self.assertEqual(parse_rate_shock_pp(q), -2.0)
        self.assertEqual(
            parse_rate_shock_pp(
                "How would Fed easing and lower interest rates affect my portfolio?",
            ),
            -2.0,
        )
        self.assertEqual(
            parse_rate_shock_pp(
                q,
                scenario_params={"rate_rise_pct": 2.0, "rate_shock": "Rising"},
            ),
            -2.0,
        )

    def test_explicit_rate_shock_pp_overrides_question_direction(self) -> None:
        q = "What happens if the Federal Reserve cuts interest rates?"
        self.assertEqual(
            parse_rate_shock_pp(q, scenario_params={"rate_shock_pp": 2.0}),
            2.0,
        )
        self.assertEqual(
            parse_rate_shock_pp(q, scenario_params={"rate_shock_pp": -2.5}),
            -2.5,
        )

    def test_parse_rate_hike_positive_shock(self) -> None:
        self.assertEqual(
            parse_rate_shock_pp("What if the Fed hikes rates by 2%?"),
            2.0,
        )
        self.assertEqual(
            parse_rate_shock_pp("What happens if interest rates rise 2%?"),
            2.0,
        )

    def test_intent_rate_cut_question(self) -> None:
        self.assertEqual(
            detect_investment_send_intent(
                "What happens if the Federal Reserve announces rate cuts?",
                "",
            ),
            "macro_rates",
        )

    def test_macro_rates_answer_rate_cuts_negative_shock(self) -> None:
        result = macro_rates_answer(
            self._CTX,
            beginner=False,
            question="What if the Fed cuts interest rates?",
        )
        self.assertEqual(result.computed.get("rate_shock_pp"), -2.0)
        self.assertIn("-2.0", result.analyst_sections.get("key_variables", ""))
        self.assertIn("fall", result.short_answer.lower())

    def test_macro_rates_answer_rate_hikes_positive_shock(self) -> None:
        result = macro_rates_answer(
            self._CTX,
            beginner=False,
            question="What if the Fed hikes interest rates by 2%?",
        )
        self.assertEqual(result.computed.get("rate_shock_pp"), 2.0)
        self.assertIn("+2.0", result.analyst_sections.get("key_variables", ""))

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


class TestMacroRecession(unittest.TestCase):
    _CTX = {
        "experience_mode": "Advanced Mode",
        "current_weights": {
            "VTI": "50.0%",
            "QQQ": "20.0%",
            "VXUS": "20.0%",
            "VNQ": "10.0%",
        },
        "holdings": ["VTI", "QQQ", "VXUS", "VNQ"],
        "health_recession": 35,
    }

    def test_intent_recession_question(self) -> None:
        self.assertEqual(
            detect_investment_send_intent("What happens in a recession?", ""),
            "macro_recession",
        )
        self.assertEqual(
            detect_investment_send_intent("What if we enter a recession?", ""),
            "macro_recession",
        )

    def test_recession_not_scenario_stress(self) -> None:
        self.assertNotEqual(
            detect_investment_send_intent("What happens in a recession?", ""),
            "scenario_stress",
        )

    def test_macro_recession_answer_sections(self) -> None:
        result = macro_recession_answer(
            self._CTX,
            beginner=False,
            question="What happens in a recession?",
        )
        self.assertEqual(result.problem_type, "macro_recession")
        self.assertIn("direct_answer", result.analyst_sections)
        self.assertIn("recommended_actions", result.analyst_sections)
        self.assertIn("earnings", result.analyst_sections["portfolio_analyst_view"].lower())

    def test_end_to_end_not_tech_scenario(self) -> None:
        solved = solve_instant_investment_insight(
            "What happens in a recession?",
            self._CTX,
        )
        self.assertIsNotNone(solved)
        _, result = solved
        self.assertEqual(result.problem_type, "macro_recession")
        self.assertNotIn("tech drawdown", result.short_answer.lower())
        self.assertIn("recession", result.short_answer.lower())

    def test_equity_heavy_worse_than_defensive(self) -> None:
        growth = recession_portfolio_impacts(
            {"equity": 0.9, "bonds": 0.05, "tbills": 0.05, "reit": 0.0, "dividend": 0.0, "qqq_spy": 0.2, "tech": 0.15}
        )
        defensive = recession_portfolio_impacts(
            {"equity": 0.3, "bonds": 0.4, "tbills": 0.2, "reit": 0.05, "dividend": 0.05, "qqq_spy": 0.0, "tech": 0.0}
        )
        self.assertLess(growth["net_return_shift_pp"], defensive["net_return_shift_pp"])


class TestMacroInflation(unittest.TestCase):
    _CTX = {
        "experience_mode": "Advanced Mode",
        "current_weights": {
            "VTI": "50.0%",
            "QQQ": "20.0%",
            "VXUS": "20.0%",
            "VNQ": "10.0%",
        },
        "holdings": ["VTI", "QQQ", "VXUS", "VNQ"],
    }

    def test_intent_inflation_question(self) -> None:
        self.assertEqual(
            detect_investment_send_intent("What happens if inflation rises to 6%?", ""),
            "macro_inflation",
        )
        self.assertEqual(
            detect_investment_send_intent("Is my portfolio protected from inflation?", ""),
            "macro_inflation",
        )

    def test_inflation_not_recession(self) -> None:
        self.assertNotEqual(
            detect_investment_send_intent("What happens if inflation is 6%?", ""),
            "macro_recession",
        )

    def test_parse_inflation_pct_from_params(self) -> None:
        self.assertEqual(parse_inflation_pct({"inflation_pct": 6.0}), 6.0)
        self.assertEqual(parse_inflation_pct({}), 4.0)

    def test_macro_inflation_answer_sections(self) -> None:
        result = macro_inflation_answer(
            {**self._CTX, "scenario_params": {"inflation_pct": 6.0}},
            beginner=False,
            question="What happens if inflation rises to 6%?",
        )
        self.assertEqual(result.problem_type, "macro_inflation")
        self.assertIn("direct_answer", result.analyst_sections)
        self.assertIn("recommended_actions", result.analyst_sections)
        view = result.analyst_sections["portfolio_analyst_view"].lower()
        self.assertTrue(any(w in view for w in ("bond", "real", "purchasing")))

    def test_end_to_end_inflation_solver(self) -> None:
        solved = solve_instant_investment_insight(
            "What happens if inflation rises to 6%?",
            {**self._CTX, "scenario_params": {"inflation_pct": 6.0}},
        )
        self.assertIsNotNone(solved)
        _, result = solved
        self.assertEqual(result.problem_type, "macro_inflation")
        self.assertIn("inflation", result.short_answer.lower())

    def test_high_inflation_worse_real_return(self) -> None:
        profile = {
            "equity": 0.7,
            "bonds": 0.2,
            "tbills": 0.05,
            "reit": 0.05,
            "growth_proxy": 0.25,
            "dividend": 0.1,
        }
        low = inflation_portfolio_impacts(profile, 2.0)
        high = inflation_portfolio_impacts(profile, 8.0)
        self.assertGreater(low["real_return_estimate_pct"], high["real_return_estimate_pct"])


if __name__ == "__main__":
    unittest.main()
