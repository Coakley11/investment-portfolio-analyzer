"""Tests for allocation_recommendation AMI family and Phase 2c sliders."""

from __future__ import annotations

import unittest

from investment_ami_allocation import allocation_recommendation_answer
from investment_ami_answer_format import render_analyst_sections_markdown
from investment_ami_context import detect_investment_send_intent
from investment_ami_instant_solver import solve_instant_investment_insight
from investment_ami_sliders import (
    build_scenario_params_from_sliders,
    refresh_investment_insight_from_params,
    slider_specs_for,
)
from applied_math_return_insight import SESSION_PENDING_KEY
from investment_ami_answer_format import render_investment_page_insight_markdown


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

    def test_allocation_override_with_explicit_reallocation(self) -> None:
        from investment_ami_allocation import _rows_with_allocation_overrides

        ctx = {
            "current_weights": {"VTI": "40.0%", "BND": "30.0%", "VXUS": "20.0%", "VNQ": "10.0%"},
            "scenario_params": {
                "allocation_overrides": {"BND": 10.0},
                "allocation_reallocations": [
                    {"from_ticker": "BND", "amount_pct": 20.0, "to_ticker": "VTI"},
                ],
            },
        }
        rows = _rows_with_allocation_overrides(ctx)
        weights = {t: p for t, p in rows}
        self.assertAlmostEqual(weights.get("BND", 0), 10.0, places=1)
        self.assertAlmostEqual(weights.get("VTI", 0), 60.0, places=1)

    def test_rebalance_question_leads_with_verdict(self) -> None:
        result = allocation_recommendation_answer(
            self._CTX,
            beginner=False,
            question="Should I rebalance?",
        )
        direct = result.analyst_sections.get("direct_answer", "")
        self.assertTrue(
            any(
                phrase in direct
                for phrase in (
                    "rebalance recommended",
                    "rebalance may be appropriate",
                    "No significant rebalance needed",
                )
            )
        )
        self.assertIn("rebalance_candidates", result.analyst_sections)

    def test_ami_deep_dive_includes_calculation_chains(self) -> None:
        from investment_ami_answer_format import render_ami_deep_dive_markdown

        result = allocation_recommendation_answer(
            self._CTX,
            beginner=False,
            question="What should I change in my portfolio?",
        )
        md = render_ami_deep_dive_markdown(result.analyst_sections, beginner=False)
        self.assertIn("Calculation Chains", md)
        self.assertIn("Methodology", md)
        self.assertIn("Current Portfolio", md)


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

    def test_slider_refresh_preserves_insight_and_recomputes(self) -> None:
        class _SS(dict):
            def get(self, key, default=None):
                return dict.get(self, key, default)

        insight = {
            "question": "Should I rebalance?",
            "question_id": "q-rebalance-slider",
            "insight_id": "stable-insight-id-99",
            "experience_mode": "Advanced Mode",
            "problem_type": "allocation_recommendation",
            "source_app": "investment",
            "source_page": "portfolio",
            "conclusion": "**Moderate rebalance may be appropriate**",
            "analyst_sections": {"direct_answer": "initial"},
            "key_numbers": {
                "holdings_weights": {"VTI": 40.0, "BND": 30.0, "VXUS": 20.0, "VNQ": 10.0},
                "problem_type": "allocation_recommendation",
            },
        }
        params = {
            "risk_tolerance": "Moderate",
            "allocation_overrides": {"VTI": 35.0},
            "allocation_reallocations": [
                {"from_ticker": "VTI", "amount_pct": 5.0, "to_ticker": "VXUS"},
            ],
        }
        ss = _SS({"_ami_scenario_params": {}, "_ami_last_submit_source_page": "portfolio"})
        st = type("ST", (), {"session_state": ss})()
        ok = refresh_investment_insight_from_params(st, insight, params)
        pending = ss.get(SESSION_PENDING_KEY) or {}
        self.assertTrue(ok)
        self.assertEqual(pending.get("insight_id"), "stable-insight-id-99")
        self.assertTrue(pending.get("conclusion"))
        sections = pending.get("analyst_sections") or {}
        self.assertTrue(sections.get("direct_answer"))
        self.assertIn("proposed_portfolio", sections)
        self.assertIn("VXUS", sections.get("proposed_portfolio", ""))
        self.assertIn("35.0%", sections.get("proposed_portfolio", ""))
        body = render_investment_page_insight_markdown(sections, beginner=False)
        self.assertTrue(body)
        self.assertNotIn("Add holdings with weights first", body)


if __name__ == "__main__":
    unittest.main()
