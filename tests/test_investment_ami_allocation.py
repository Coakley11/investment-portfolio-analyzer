"""Tests for allocation_recommendation AMI family and Phase 2c sliders."""

from __future__ import annotations

import unittest

from investment_ami_allocation import allocation_recommendation_answer
from investment_ami_answer_format import render_analyst_sections_markdown
from investment_ami_context import detect_investment_send_intent
from investment_ami_instant_solver import solve_instant_investment_insight
from investment_ami_sliders import build_scenario_params_from_sliders, slider_specs_for


class TestAllocationRecommendation(unittest.TestCase):
    _CTX = {
        "experience_mode": "Advanced Mode",
        "current_weights": {
            "VTI": "50.0%",
            "QQQ": "20.0%",
            "VXUS": "20.0%",
            "VNQ": "10.0%",
        },
        "holdings": ["VTI", "QQQ", "VXUS", "VNQ"],
        "objective": "Growth",
    }

    def test_intent_change_question(self) -> None:
        self.assertEqual(
            detect_investment_send_intent("What should I change in my portfolio?", ""),
            "allocation_recommendation",
        )

    def test_intent_rebalance_action(self) -> None:
        self.assertEqual(
            detect_investment_send_intent("Should I rebalance?", ""),
            "allocation_recommendation",
        )

    def test_intent_not_portfolio_risk(self) -> None:
        self.assertNotEqual(
            detect_investment_send_intent("What should I change in my portfolio?", ""),
            "portfolio_risk",
        )

    def test_answer_has_action_sections(self) -> None:
        result = allocation_recommendation_answer(
            self._CTX,
            beginner=False,
            question="What should I change in my portfolio?",
        )
        self.assertEqual(result.problem_type, "allocation_recommendation")
        sections = result.analyst_sections
        self.assertIn("current_strengths", sections)
        self.assertIn("potential_increases", sections)
        self.assertIn("potential_reductions", sections)
        self.assertIn("recommended_actions", sections)
        md = render_analyst_sections_markdown(sections, beginner=False)
        self.assertIn("VTI", md)
        self.assertIn("50", md)

    def test_end_to_end_increase_reduce_language(self) -> None:
        solved = solve_instant_investment_insight(
            "What should I change in my portfolio?",
            self._CTX,
        )
        self.assertIsNotNone(solved)
        _, result = solved
        self.assertEqual(result.problem_type, "allocation_recommendation")
        actions = result.analyst_sections.get("recommended_actions", "").upper()
        self.assertTrue(any(v in actions for v in ("HOLD", "MONITOR", "REDUCE", "INCREASE", "REBALANCE")))

    def test_conservative_changes_recommendation(self) -> None:
        conservative = allocation_recommendation_answer(
            {**self._CTX, "scenario_params": {"risk_tolerance": "Conservative"}},
            beginner=False,
            question="What should I change in my portfolio?",
        )
        moderate = allocation_recommendation_answer(
            {**self._CTX, "scenario_params": {"risk_tolerance": "Moderate"}},
            beginner=False,
            question="What should I change in my portfolio?",
        )
        self.assertNotEqual(conservative.short_answer, moderate.short_answer)


class TestAmiSliders(unittest.TestCase):
    def test_scenario_stress_slider_spec(self) -> None:
        specs = slider_specs_for("scenario_stress", {})
        self.assertEqual(specs[0].key, "tech_drawdown_pct")

    def test_allocation_override_only_when_changed(self) -> None:
        specs = slider_specs_for(
            "allocation_recommendation",
            {"key_numbers": {"holdings_weights": {"QQQ": 20.0, "VTI": 50.0}}},
        )
        values = {s.key: s.default for s in specs}
        for s in specs:
            if s.key == "alloc_QQQ":
                values[s.key] = 20
        params = build_scenario_params_from_sliders(
            specs,
            values,
            problem_type="allocation_recommendation",
            weight_baseline={"QQQ": 20.0, "VTI": 50.0},
        )
        self.assertNotIn("allocation_overrides", params)
        values["alloc_QQQ"] = 10
        params2 = build_scenario_params_from_sliders(
            specs,
            values,
            problem_type="allocation_recommendation",
            weight_baseline={"QQQ": 20.0, "VTI": 50.0},
        )
        self.assertEqual(params2.get("allocation_overrides", {}).get("QQQ"), 10.0)


if __name__ == "__main__":
    unittest.main()
