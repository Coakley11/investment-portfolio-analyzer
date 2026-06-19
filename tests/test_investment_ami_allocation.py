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
        self.assertEqual(params.get("allocation_overrides"), {})
        self.assertEqual(params.get("allocation_reallocations"), [])
        self.assertEqual(params.get("allocation_increase_funding"), [])
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

    def test_allocation_scenario_includes_before_after_table(self) -> None:
        from investment_ami_allocation import allocation_recommendation_answer
        from investment_ami_answer_format import render_ami_deep_dive_markdown

        ctx = {
            "experience_mode": "Advanced Mode",
            "current_weights": {"VTI": 40.0, "BND": 30.0, "VXUS": 20.0, "VNQ": 10.0},
            "scenario_params": {
                "risk_tolerance": "Moderate",
                "allocation_overrides": {"VTI": 35.0},
                "allocation_reallocations": [
                    {"from_ticker": "VTI", "amount_pct": 5.0, "to_ticker": "VXUS"},
                ],
            },
        }
        result = allocation_recommendation_answer(ctx, beginner=False, question="Should I rebalance?")
        sections = result.analyst_sections
        proposed = sections.get("proposed_portfolio", "")
        self.assertIn("VTI", proposed)
        self.assertIn("35.0%", proposed)
        self.assertIn("25.0%", proposed)
        comparison = sections.get("portfolio_comparison", "")
        self.assertIn("Tech exposure", comparison)
        self.assertIn("Top-3 concentration", comparison)
        self.assertIn("Recession sensitivity", comparison)
        self.assertIn("Diversification", comparison)
        md = render_ami_deep_dive_markdown(sections, beginner=False)
        self.assertIn("Proposed Portfolio", md)
        self.assertIn("Before vs After", md)

    def test_slider_refresh_stores_updated_insight(self) -> None:
        from unittest.mock import patch

        class _SS(dict):
            def get(self, key, default=None):
                return dict.get(self, key, default)

        insight = {
            "question": "Should I rebalance?",
            "question_id": "q-rebalance-store",
            "insight_id": "stable-store-id",
            "experience_mode": "Advanced Mode",
            "problem_type": "allocation_recommendation",
            "source_app": "investment",
            "source_page": "portfolio",
            "conclusion": "initial",
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
        with patch("applied_math_return_insight.store_applied_math_insight") as store_mock:
            ok = refresh_investment_insight_from_params(st, insight, params)
        self.assertTrue(ok)
        store_mock.assert_called_once()
        stored = store_mock.call_args[0][0]
        self.assertEqual(stored.get("insight_id"), "stable-store-id")
        self.assertIn("scenario_params", stored)
        self.assertEqual(stored.get("solver_build_id"), "investment-ami-v2-phase2i-allocation-funding-audit1")
        self.assertTrue(stored.get("scenario_refreshed_at"))
        sections = stored.get("analyst_sections") or {}
        self.assertIn("proposed_portfolio", sections)
        self.assertIn("portfolio_comparison", sections)


    def test_increase_funding_from_single_sleeve(self) -> None:
        from investment_ami_allocation import (
            _apply_explicit_reallocation,
            allocation_recommendation_answer,
            format_net_allocation_changes,
        )

        baseline = {"VTI": 40.0, "BND": 30.0, "VXUS": 20.0, "VNQ": 10.0}
        weights = _apply_explicit_reallocation(
            baseline,
            {"VXUS": 30.0},
            [],
            [{"to_ticker": "VXUS", "from_ticker": "VTI", "amount_pct": 10.0}],
        )
        self.assertAlmostEqual(weights["VTI"], 30.0, places=1)
        self.assertAlmostEqual(weights["VXUS"], 30.0, places=1)
        self.assertAlmostEqual(weights["BND"], 30.0, places=1)
        self.assertAlmostEqual(weights["VNQ"], 10.0, places=1)
        self.assertAlmostEqual(sum(weights.values()), 100.0, places=1)

        ctx = {
            "experience_mode": "Advanced Mode",
            "current_weights": {"VTI": 40.0, "BND": 30.0, "VXUS": 20.0, "VNQ": 10.0},
            "scenario_params": {
                "risk_tolerance": "Moderate",
                "allocation_overrides": {"VXUS": 30.0},
                "allocation_increase_funding": [
                    {"to_ticker": "VXUS", "from_ticker": "VTI", "amount_pct": 10.0},
                ],
            },
        }
        result = allocation_recommendation_answer(ctx, beginner=False, question="Should I rebalance?")
        sections = result.analyst_sections
        self.assertIn("30.0%", sections.get("proposed_portfolio", ""))
        net = sections.get("net_allocation_changes", "")
        self.assertIn("VTI", net)
        self.assertIn("-10.0%", net)
        self.assertIn("VXUS", net)
        self.assertIn("+10.0%", net)
        base_rows = [("VTI", 40.0), ("BND", 30.0), ("VXUS", 20.0), ("VNQ", 10.0)]
        prop_rows = [("VTI", 30.0), ("BND", 30.0), ("VXUS", 30.0), ("VNQ", 10.0)]
        self.assertIn("-10.0%", format_net_allocation_changes(base_rows, prop_rows))

    def test_single_source_cannot_fund_more_than_sleeve_weight(self) -> None:
        from investment_ami_allocation import _apply_explicit_reallocation

        baseline = {"VTI": 40.0, "BND": 30.0, "VXUS": 20.0, "VNQ": 10.0}
        weights = _apply_explicit_reallocation(
            baseline,
            {"VTI": 90.0},
            [],
            [{"to_ticker": "VTI", "from_ticker": "BND", "amount_pct": 50.0}],
        )
        self.assertGreaterEqual(weights["BND"], 0.0)
        self.assertAlmostEqual(weights["BND"], 0.0, places=1)
        self.assertAlmostEqual(weights["VTI"], 90.0, places=1)
        self.assertGreater(sum(weights.values()), 100.0)

    def test_proportional_funding_never_negative(self) -> None:
        from investment_ami_allocation import _apply_explicit_reallocation
        from investment_ami_sliders import _valid_funding_source_options

        baseline = {"VTI": 40.0, "BND": 30.0, "VXUS": 20.0, "VNQ": 10.0}
        options, avail = _valid_funding_source_options(baseline, list(baseline), "VTI", 50.0)
        self.assertNotIn("BND", options)
        self.assertIn("Proportional distribution across other sleeves", options)
        self.assertAlmostEqual(avail, 60.0, places=1)

        weights = _apply_explicit_reallocation(
            baseline,
            {"VTI": 90.0},
            [],
            [{"to_ticker": "VTI", "from_ticker": "__proportional__", "amount_pct": 50.0}],
        )
        self.assertTrue(all(w >= -0.01 for w in weights.values()))
        self.assertAlmostEqual(sum(weights.values()), 100.0, places=1)
        self.assertAlmostEqual(weights["VTI"], 90.0, places=1)

    def test_bnd_increase_funded_from_vnq_regression(self) -> None:
        """Regression: BND +10% funded from VNQ must not corrupt other sleeves."""
        from investment_ami_allocation import (
            _apply_explicit_reallocation,
            allocation_recommendation_answer,
            format_net_allocation_changes,
        )

        baseline = {"VTI": 40.0, "BND": 30.0, "VXUS": 20.0, "VNQ": 10.0}
        funding = [{"to_ticker": "BND", "from_ticker": "VNQ", "amount_pct": 10.0}]
        weights = _apply_explicit_reallocation(baseline, {"BND": 40.0}, [], funding)
        self.assertAlmostEqual(weights["VTI"], 40.0, places=1)
        self.assertAlmostEqual(weights["BND"], 40.0, places=1)
        self.assertAlmostEqual(weights["VXUS"], 20.0, places=1)
        self.assertAlmostEqual(weights["VNQ"], 0.0, places=1)
        self.assertAlmostEqual(sum(weights.values()), 100.0, places=1)

        ctx = {
            "experience_mode": "Advanced Mode",
            "current_weights": {"VTI": 40.0, "BND": 30.0, "VXUS": 20.0, "VNQ": 10.0},
            "scenario_params": {
                "risk_tolerance": "Moderate",
                "allocation_overrides": {"BND": 40.0},
                "allocation_reallocations": [],
                "allocation_increase_funding": funding,
            },
        }
        result = allocation_recommendation_answer(ctx, beginner=False, question="Should I rebalance?")
        sections = result.analyst_sections
        proposed = sections.get("proposed_portfolio", "")
        self.assertIn("BND", proposed)
        self.assertIn("40.0%", proposed)
        self.assertIn("0.0%", proposed)
        net = sections.get("net_allocation_changes", "")
        self.assertIn("BND", net)
        self.assertIn("+10.0%", net)
        self.assertIn("VNQ", net)
        self.assertIn("-10.0%", net)
        fb = sections.get("funding_breakdown", "")
        self.assertIn("VNQ", fb)
        self.assertIn("-10.0%", fb)
        base_rows = [("VTI", 40.0), ("BND", 30.0), ("VXUS", 20.0), ("VNQ", 10.0)]
        prop_rows = [("VTI", 40.0), ("BND", 40.0), ("VXUS", 20.0), ("VNQ", 0.0)]
        self.assertEqual(format_net_allocation_changes(base_rows, prop_rows), net)

    def test_stale_reallocation_ignored_when_only_increasing(self) -> None:
        from investment_ami_allocation import _apply_explicit_reallocation

        baseline = {"VTI": 40.0, "BND": 30.0, "VXUS": 20.0, "VNQ": 10.0}
        stale_realloc = [{"from_ticker": "VTI", "amount_pct": 40.0, "to_ticker": "VNQ"}]
        weights = _apply_explicit_reallocation(
            baseline,
            {"BND": 40.0},
            stale_realloc,
            [{"to_ticker": "BND", "from_ticker": "VNQ", "amount_pct": 10.0}],
        )
        self.assertAlmostEqual(weights["VTI"], 40.0, places=1)
        self.assertAlmostEqual(weights["BND"], 40.0, places=1)
        self.assertAlmostEqual(weights["VNQ"], 0.0, places=1)
        self.assertAlmostEqual(sum(weights.values()), 100.0, places=1)


if __name__ == "__main__":
    unittest.main()
